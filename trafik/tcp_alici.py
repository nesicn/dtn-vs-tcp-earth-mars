"""TCP alıcı: Mars aracında çalışır, gelen test mesajlarını günlüğe yazar.

Örnek (Docker, arac konteynerinde):
    python3 trafik/tcp_alici.py --deney-id d1_tcp_g10_t1 --port 5000 \\
        --adet 50 --sure 300 --cikti sonuclar/deney1/d1_tcp_g10_t1

Örnek (kendi bilgisayarında deneme):
    python trafik/tcp_alici.py --deney-id deneme --port 5000 --adet 50 --sure 60 \\
        --cikti sonuclar/deneme

Çıktılar (--cikti klasöründe):
    alici.csv        her alınan mesaj için bir satır (kopyalar dahil)
    alici_ozet.json  alınan, kopya, yabancı ve hatalı mesaj sayıları, çıkış nedeni

Davranış:
    * Birden fazla bağlantıyı kabul eder (gönderici yeniden bağlanırsa da çalışır).
    * Tüm mesajlar (--adet) benzersiz olarak alındığında bağlantıları kapatır ve çıkar.
      Gönderici bu kapanışı "alıcı her şeyi aldı" işareti olarak görür.
    * --sure dolduğunda veya SIGTERM/SIGINT geldiğinde günlükleri kapatıp çıkar.
    * Başka bir koşuya ait mesajları (farklı koşu belirteci) saymaz, ayrı sayar.
"""

from __future__ import annotations

import argparse
import selectors
import socket
import sys
from pathlib import Path
from typing import Dict

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trafik import ortak  # noqa: E402

BETIK = "tcp_alici"


def arguman_cozucu() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TCP test mesajlarını alır ve günlüğe yazar.")
    p.add_argument("--deney-id", required=True, help="koşunun kimliği (gönderici ile aynı)")
    p.add_argument("--host", default="0.0.0.0", help="dinlenecek adres (varsayılan: tümü)")
    p.add_argument("--port", type=int, default=5000, help="dinlenecek TCP portu")
    p.add_argument("--adet", type=int, required=True, help="beklenen mesaj sayısı")
    p.add_argument("--sure", type=float, required=True,
                   help="en fazla bekleme süresi, saniye (koşunun toplam süresi)")
    p.add_argument("--cikti", type=Path, required=True, help="günlüklerin yazılacağı klasör")
    return p


class _Baglanti:
    __slots__ = ("soket", "adres", "cozucu")

    def __init__(self, soket: socket.socket, adres) -> None:
        self.soket = soket
        self.adres = adres
        self.cozucu = ortak.CerceveCozucu()


def calistir(args: argparse.Namespace) -> Dict[str, object]:
    beklenen_belirtec = ortak.kosu_belirteci(args.deney_id)
    baslangic = ortak.simdi()
    bitis = baslangic + args.sure

    ozet: Dict[str, object] = {
        "betik": BETIK, "deney_id": args.deney_id, "mod": "tcp",
        "beklenen_adet": args.adet, "dinlenen_port": args.port,
        "baslangic": baslangic, "alinan_benzersiz": 0, "alinan_toplam": 0,
        "kopya": 0, "yabanci": 0, "hatali": 0, "baglanti_sayisi": 0,
        "ilk_alma": None, "son_alma": None, "cikis_nedeni": None, "hata": None,
    }
    gorulen = set()

    secici = selectors.DefaultSelector()
    dinleyici = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    dinleyici.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    dinleyici.bind((args.host, args.port))
    dinleyici.listen(8)
    dinleyici.setblocking(False)
    secici.register(dinleyici, selectors.EVENT_READ, data=None)

    baglantilar: Dict[int, _Baglanti] = {}

    def baglantiyi_kapat(b: _Baglanti) -> None:
        try:
            secici.unregister(b.soket)
        except (KeyError, ValueError):
            pass
        try:
            b.soket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        b.soket.close()
        baglantilar.pop(id(b), None)

    gunluk = ortak.CsvGunluk(args.cikti / "alici.csv", ortak.ALICI_SUTUNLARI)
    ortak.hazir_bildir(BETIK)
    ortak.bilgi(BETIK, f"{args.host}:{args.port} dinleniyor, {args.adet} mesaj bekleniyor")

    try:
        while True:
            if len(gorulen) >= args.adet:
                ozet["cikis_nedeni"] = "tamamlandi"
                break
            kalan = bitis - ortak.simdi()
            if kalan <= 0:
                ozet["cikis_nedeni"] = "sure_doldu"
                break
            for anahtar, _olay in secici.select(timeout=min(1.0, kalan)):
                if anahtar.data is None:                      # yeni bağlantı
                    try:
                        soket, adres = dinleyici.accept()
                    except BlockingIOError:
                        continue
                    soket.setblocking(False)
                    b = _Baglanti(soket, adres)
                    baglantilar[id(b)] = b
                    secici.register(soket, selectors.EVENT_READ, data=b)
                    ozet["baglanti_sayisi"] = int(ozet["baglanti_sayisi"]) + 1
                    ortak.bilgi(BETIK, f"bağlantı kabul edildi: {adres[0]}:{adres[1]}")
                    continue

                b = anahtar.data
                try:
                    veri = b.soket.recv(65536)
                except (BlockingIOError, InterruptedError):
                    continue
                except OSError as hata:
                    ortak.bilgi(BETIK, f"bağlantı hatası: {hata}")
                    baglantiyi_kapat(b)
                    continue
                if not veri:
                    ortak.bilgi(BETIK, f"gönderici bağlantıyı kapattı: {b.adres[0]}")
                    baglantiyi_kapat(b)
                    continue

                alma = ortak.simdi()
                try:
                    for ham in b.cozucu.ekle(veri):
                        try:
                            m = ortak.mesaj_coz(ham)
                        except ortak.MesajHatasi as hata:
                            ozet["hatali"] = int(ozet["hatali"]) + 1
                            ortak.bilgi(BETIK, f"hatalı mesaj atlandı: {hata}")
                            continue
                        if m.kosu_belirteci != beklenen_belirtec or m.mod != "tcp":
                            ozet["yabanci"] = int(ozet["yabanci"]) + 1
                            continue
                        ozet["alinan_toplam"] = int(ozet["alinan_toplam"]) + 1
                        if m.mesaj_no in gorulen:
                            ozet["kopya"] = int(ozet["kopya"]) + 1
                        else:
                            gorulen.add(m.mesaj_no)
                        if ozet["ilk_alma"] is None:
                            ozet["ilk_alma"] = alma
                        ozet["son_alma"] = alma
                        gunluk.yaz({
                            "deney_id": args.deney_id, "mod": "tcp",
                            "mesaj_no": m.mesaj_no,
                            "gonderme_zamani": ortak.zaman_bicimle(m.gonderme_zamani),
                            "alma_zamani": ortak.zaman_bicimle(alma),
                            "boyut_byte": m.boyut,
                        })
                except ortak.MesajHatasi as hata:
                    # Çerçeve uzunluğu bozuksa akışın geri kalanı okunamaz.
                    ozet["hatali"] = int(ozet["hatali"]) + 1
                    ortak.bilgi(BETIK, f"akış bozuk, bağlantı kapatılıyor: {hata}")
                    baglantiyi_kapat(b)
    except ortak.DurdurmaIstegi:
        ozet["cikis_nedeni"] = "durduruldu"
    except Exception as hata:  # beklenmeyen durum: özete yaz, sonra yeniden fırlat
        ozet["cikis_nedeni"] = "hata"
        ozet["hata"] = f"{type(hata).__name__}: {hata}"
        raise
    finally:
        for b in list(baglantilar.values()):
            baglantiyi_kapat(b)
        secici.close()
        dinleyici.close()
        gunluk.kapat()
        ozet["alinan_benzersiz"] = len(gorulen)
        ozet["bitis"] = ortak.simdi()
        ortak.json_yaz(args.cikti / "alici_ozet.json", ozet)
        ortak.bilgi(BETIK, f"bitti ({ozet['cikis_nedeni']}): "
                           f"{len(gorulen)}/{args.adet} benzersiz mesaj alındı")
    return ozet


def main(argv=None) -> int:
    ortak.python_surumunu_dogrula()
    args = arguman_cozucu().parse_args(argv)
    if args.adet <= 0 or args.sure <= 0:
        sys.exit("--adet ve --sure pozitif olmalı")
    ortak.durdurma_sinyallerini_yakala()
    ozet = calistir(args)
    return 0 if ozet["cikis_nedeni"] in ("tamamlandi", "sure_doldu", "durduruldu") else 1


if __name__ == "__main__":
    sys.exit(main())
