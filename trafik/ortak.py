"""TCP ve DTN trafik betiklerinin ortak parçaları.

Bu modül yalnızca Python standart kütüphanesini kullanır, böylece betikler
Docker konteynerlerinde ek kurulum olmadan çalışır (Python 3.9+).

İçerik:
  * Mesaj biçimi: her test mesajı sabit uzunlukta bir başlık ve dolgu baytlarından
    oluşur. Başlıkta sıra numarası, toplam mesaj sayısı, gönderme zamanı ve koşuya
    özgü bir kimlik (koşu belirteci) bulunur.
  * CSV günlük yazıcıları: gönderici ve alıcı günlükleri, ekip içinde kararlaştırılan
    sütun adlarıyla, her satırdan sonra diske yazılır (koşu yarıda kesilse bile
    veri kaybolmaz).
  * Yardımcılar: zaman, koşu belirteci, sinyal yakalama, JSON özet yazma.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import signal
import struct
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, Optional

# ---------------------------------------------------------------------------
# Mesaj biçimi
# ---------------------------------------------------------------------------

SIHIR = b"DTNM"          # her mesajın ilk 4 baytı
SURUM = 1

MOD_KODLARI = {"tcp": 1, "dtn": 2}
KOD_MODLARI = {v: k for k, v in MOD_KODLARI.items()}

# Ağ bayt sırası (büyük uçlu):
#   4s sihir | B sürüm | B mod | H başlık_uzunluğu | Q koşu_belirteci |
#   I mesaj_no | I toplam | Q gönderme_zamanı_ns
BASLIK_BICIMI = "!4sBBHQIIQ"
BASLIK_BOYUTU = struct.calcsize(BASLIK_BICIMI)   # 32 bayt

EN_KUCUK_MESAJ = BASLIK_BOYUTU
EN_BUYUK_MESAJ = 1024 * 1024                     # 1 MiB, bozuk veriye karşı sınır

# TCP'de mesaj sınırlarını belirlemek için her mesajın önüne 4 baytlık uzunluk eklenir.
CERCEVE_BICIMI = "!I"
CERCEVE_BOYUTU = struct.calcsize(CERCEVE_BICIMI)


class MesajHatasi(ValueError):
    """Çözümlenemeyen veya biçimi bozuk bir mesaj."""


class Mesaj:
    """Çözümlenmiş bir test mesajı."""

    __slots__ = ("mod", "kosu_belirteci", "mesaj_no", "toplam",
                 "gonderme_zamani_ns", "boyut")

    def __init__(self, mod: str, kosu_belirteci: int, mesaj_no: int,
                 toplam: int, gonderme_zamani_ns: int, boyut: int) -> None:
        self.mod = mod
        self.kosu_belirteci = kosu_belirteci
        self.mesaj_no = mesaj_no
        self.toplam = toplam
        self.gonderme_zamani_ns = gonderme_zamani_ns
        self.boyut = boyut

    @property
    def gonderme_zamani(self) -> float:
        """Gönderme zamanı, Unix zamanı olarak saniye."""
        return self.gonderme_zamani_ns / 1e9

    def __repr__(self) -> str:  # pragma: no cover - hata ayıklama için
        return (f"Mesaj(mod={self.mod!r}, no={self.mesaj_no}/{self.toplam}, "
                f"boyut={self.boyut})")


def _dolgu(mesaj_no: int, uzunluk: int) -> bytes:
    """Mesaj numarasına bağlı, belirlenimci dolgu baytları üretir."""
    if uzunluk <= 0:
        return b""
    tohum = hashlib.sha256(mesaj_no.to_bytes(4, "big")).digest()
    tekrar = uzunluk // len(tohum) + 1
    return (tohum * tekrar)[:uzunluk]


def mesaj_olustur(mod: str, kosu_belirteci: int, mesaj_no: int, toplam: int,
                  boyut: int, gonderme_zamani_ns: Optional[int] = None) -> bytes:
    """Belirtilen toplam boyutta (bayt) bir test mesajı üretir.

    Gönderme zamanı verilmezse şu anki zaman kullanılır. Zamanı mesajı
    göndermeden hemen önce üretmek, gönderme zamanının doğru olmasını sağlar.
    """
    if mod not in MOD_KODLARI:
        raise ValueError(f"Bilinmeyen mod: {mod!r} (tcp veya dtn olmalı)")
    if not EN_KUCUK_MESAJ <= boyut <= EN_BUYUK_MESAJ:
        raise ValueError(
            f"Mesaj boyutu {EN_KUCUK_MESAJ} ile {EN_BUYUK_MESAJ} bayt arasında olmalı")
    if not 0 <= mesaj_no < toplam:
        raise ValueError("mesaj_no, 0 ile toplam-1 arasında olmalı")
    if gonderme_zamani_ns is None:
        gonderme_zamani_ns = time.time_ns()
    baslik = struct.pack(BASLIK_BICIMI, SIHIR, SURUM, MOD_KODLARI[mod],
                         BASLIK_BOYUTU, kosu_belirteci, mesaj_no, toplam,
                         gonderme_zamani_ns)
    return baslik + _dolgu(mesaj_no, boyut - BASLIK_BOYUTU)


def mesaj_coz(veri: bytes) -> Mesaj:
    """Bir test mesajını çözümler, biçim hatasında MesajHatasi fırlatır."""
    if len(veri) < BASLIK_BOYUTU:
        raise MesajHatasi(f"Mesaj çok kısa: {len(veri)} bayt")
    (sihir, surum, mod_kodu, baslik_uzunlugu, belirtec, mesaj_no, toplam,
     zaman_ns) = struct.unpack_from(BASLIK_BICIMI, veri)
    if sihir != SIHIR:
        raise MesajHatasi("Sihirli bayt eşleşmiyor (bu bir test mesajı değil)")
    if surum != SURUM:
        raise MesajHatasi(f"Desteklenmeyen mesaj sürümü: {surum}")
    if baslik_uzunlugu != BASLIK_BOYUTU:
        raise MesajHatasi(f"Beklenmeyen başlık uzunluğu: {baslik_uzunlugu}")
    if mod_kodu not in KOD_MODLARI:
        raise MesajHatasi(f"Bilinmeyen mod kodu: {mod_kodu}")
    if toplam == 0 or mesaj_no >= toplam:
        raise MesajHatasi(f"Geçersiz sıra numarası: {mesaj_no}/{toplam}")
    beklenen_dolgu = _dolgu(mesaj_no, len(veri) - BASLIK_BOYUTU)
    if veri[BASLIK_BOYUTU:] != beklenen_dolgu:
        raise MesajHatasi("Dolgu baytları bozuk")
    return Mesaj(KOD_MODLARI[mod_kodu], belirtec, mesaj_no, toplam, zaman_ns,
                 len(veri))


def cerceve_ekle(mesaj: bytes) -> bytes:
    """TCP akışında kullanılmak üzere mesajın önüne uzunluk ekler."""
    return struct.pack(CERCEVE_BICIMI, len(mesaj)) + mesaj


class CerceveCozucu:
    """TCP akışından gelen baytları tam mesajlara ayırır.

    TCP bir bayt akışıdır: bir recv() çağrısı yarım mesaj veya birden fazla mesaj
    döndürebilir. Bu sınıf baytları biriktirir ve tamamlanan mesajları verir.
    """

    def __init__(self) -> None:
        self._tampon = bytearray()

    def ekle(self, veri: bytes) -> Iterable[bytes]:
        self._tampon.extend(veri)
        while True:
            if len(self._tampon) < CERCEVE_BOYUTU:
                return
            (uzunluk,) = struct.unpack_from(CERCEVE_BICIMI, self._tampon)
            if not EN_KUCUK_MESAJ <= uzunluk <= EN_BUYUK_MESAJ:
                raise MesajHatasi(f"Geçersiz çerçeve uzunluğu: {uzunluk}")
            if len(self._tampon) < CERCEVE_BOYUTU + uzunluk:
                return
            mesaj = bytes(self._tampon[CERCEVE_BOYUTU:CERCEVE_BOYUTU + uzunluk])
            del self._tampon[:CERCEVE_BOYUTU + uzunluk]
            yield mesaj

    @property
    def bekleyen_bayt(self) -> int:
        return len(self._tampon)


# ---------------------------------------------------------------------------
# Koşu kimliği ve zaman
# ---------------------------------------------------------------------------

def kosu_belirteci(deney_id: str) -> int:
    """Koşu kimliğinden 64 bitlik bir belirteç türetir.

    Belirteç her mesaja yazılır. Böylece alıcı, önceki bir koşudan geç gelen
    mesajları (özellikle DTN'de saklanıp sonradan iletilen bundle'ları) ayırt eder.
    """
    ozet = hashlib.sha256(deney_id.encode("utf-8")).digest()
    return int.from_bytes(ozet[:8], "big")


def simdi() -> float:
    """Unix zamanı, saniye. Aynı makinedeki konteynerler aynı saati paylaşır."""
    return time.time()


def zaman_bicimle(t: Optional[float]) -> str:
    """CSV için zaman damgası: mikro saniye hassasiyetinde saniye."""
    return "" if t is None else f"{t:.6f}"


# ---------------------------------------------------------------------------
# CSV günlükleri
# ---------------------------------------------------------------------------

ALICI_SUTUNLARI = ["deney_id", "mod", "mesaj_no", "gonderme_zamani",
                   "alma_zamani", "boyut_byte"]
GONDERICI_SUTUNLARI = ["deney_id", "mod", "mesaj_no", "gonderme_zamani",
                       "boyut_byte", "durum"]

# Gönderici günlüğündeki durum değerleri
DURUM_GONDERILDI = "gonderildi"       # TCP: çekirdeğe yazıldı / DTN: düğüm kabul etti
DURUM_GONDERILEMEDI = "gonderilemedi"  # hiç ağa çıkamadı (bağlantı yok, ret, süre doldu)


class CsvGunluk:
    """Her satırı hemen diske yazan basit CSV yazıcısı."""

    def __init__(self, yol: Path, sutunlar: Iterable[str]) -> None:
        self.yol = Path(yol)
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        self._dosya = open(self.yol, "w", newline="", encoding="utf-8")
        self._yazici = csv.DictWriter(self._dosya, fieldnames=list(sutunlar))
        self._yazici.writeheader()
        self._dosya.flush()

    def yaz(self, satir: Dict[str, object]) -> None:
        self._yazici.writerow(satir)
        self._dosya.flush()

    def kapat(self) -> None:
        if not self._dosya.closed:
            self._dosya.flush()
            try:
                os.fsync(self._dosya.fileno())
            except OSError:
                pass
            self._dosya.close()

    def __enter__(self) -> "CsvGunluk":
        return self

    def __exit__(self, *_exc) -> None:
        self.kapat()


def json_yaz(yol: Path, veri: Dict[str, object]) -> None:
    """JSON dosyasını önce geçici dosyaya yazıp sonra yerine taşır (yarım dosya kalmaz)."""
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".tmp")
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(gecici, yol)


# ---------------------------------------------------------------------------
# Sinyaller ve çıktı
# ---------------------------------------------------------------------------

class DurdurmaIstegi(Exception):
    """SIGTERM veya SIGINT geldiğinde fırlatılır, betik düzgünce kapanır."""


def durdurma_sinyallerini_yakala() -> None:
    """SIGTERM/SIGINT'i DurdurmaIstegi istisnasına çevirir.

    Böylece koşturucu bir betiği durdurduğunda betik günlüklerini ve özetini
    yazarak çıkar. Windows'ta Popen.terminate() sinyal göndermez; orada da veri
    kaybolmaz çünkü CSV satırları anında diske yazılır.
    """
    def _isleyici(signum, _frame):
        raise DurdurmaIstegi(f"sinyal {signum}")

    for ad in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, ad, None)
        if sig is not None:
            try:
                signal.signal(sig, _isleyici)
            except (ValueError, OSError):  # ana iş parçacığı değilse
                pass


def bilgi(betik: str, metin: str) -> None:
    """Zaman damgalı tek satırlık durum mesajı yazar (eski konsollarda ASCII'ye düşer)."""
    zaman = time.strftime("%H:%M:%S")
    try:
        print(f"[{zaman}] {betik}: {metin}", flush=True)
    except UnicodeEncodeError:  # eski Windows konsolları
        print(f"[{zaman}] {betik}: {metin}".encode("ascii", "replace").decode(),
              flush=True)


def hazir_bildir(betik: str) -> None:
    """Koşturucunun beklediği hazır işareti."""
    print(f"HAZIR {betik}", flush=True)


def python_surumunu_dogrula() -> None:
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9 veya üzeri gerekli.")
