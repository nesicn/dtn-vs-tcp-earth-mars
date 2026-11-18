"""TCP gönderici: Dünya istasyonunda çalışır, alıcıya test mesajları yollar.

Örnek (Docker, dunya konteynerinde):
    python3 trafik/tcp_gonderici.py --deney-id d1_tcp_g10_t1 --hedef 10.0.2.3 \\
        --port 5000 --adet 50 --boyut 1024 --aralik 0.1 --sure 300 \\
        --cikti sonuclar/deney1/d1_tcp_g10_t1

Örnek (kendi bilgisayarında deneme):
    python trafik/tcp_gonderici.py --deney-id deneme --hedef 127.0.0.1 --port 5000 \\
        --adet 50 --sure 60 --cikti sonuclar/deneme

Çıktılar (--cikti klasöründe):
    gonderici.csv        her mesaj için bir satır: gönderildi mi, ne zaman
    gonderici_ozet.json  bağlantı denemeleri, bağlantı kurma süresi, hata, çıkış nedeni

Ölçüm ilkesi:
    Bu betik TCP'nin kendi davranışını ölçmek içindir. Bu yüzden uygulamaya kısa bir
    zaman aşımı koyulmaz: bağlantı kurma süresini işletim sistemi belirler (Linux'ta
    net.ipv4.tcp_syn_retries). Tek üst sınır --sure, yani koşunun toplam süresidir.

    Varsayılan olarak tek bağlantı denemesi yapılır (düz TCP). --baglanti-denemesi ile
    bağlantı kurulamazsa yeniden denenir. Kurulmuş bir bağlantı koparsa kalan mesajlar
    "gonderilemedi" olarak kaydedilir: alıcının neyi aldığını uygulama katmanında
    bilmeyen düz TCP ile bunu yeniden göndermek ölçümü çarpıtır.

    Nagle algoritması varsayılan olarak kapalıdır (TCP_NODELAY). Açıkken küçük
    mesajlar bir önceki mesajın onayı (ACK) gelene kadar bekletilir; yüksek gecikmede
    bu, protokol farkını değil Nagle'ın etkisini ölçmek olur. --nagle ile açılabilir.
"""

from __future__ import annotations

import argparse
import errno
import socket
import sys
import time
from pathlib import Path
from typing import Dict, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trafik import ortak  # noqa: E402

BETIK = "tcp_gonderici"


def arguman_cozucu() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TCP üzerinden test mesajları gönderir.")
    p.add_argument("--deney-id", required=True, help="koşunun kimliği (alıcı ile aynı)")
    p.add_argument("--hedef", required=True, help="alıcının IP adresi veya adı")
    p.add_argument("--port", type=int, default=5000, help="alıcının TCP portu")
    p.add_argument("--adet", type=int, default=50, help="gönderilecek mesaj sayısı")
    p.add_argument("--boyut", type=int, default=1024, help="mesaj boyutu, bayt")
    p.add_argument("--aralik", type=float, default=0.1,
                   help="mesajlar arasındaki süre, saniye (varsayılan 0.1)")
    p.add_argument("--sure", type=float, required=True,
                   help="koşunun toplam süresi, saniye; bundan sonra vazgeçilir")
    p.add_argument("--baglanti-denemesi", type=int, default=1,
                   help="bağlantı kurulamazsa en fazla kaç kez denensin (varsayılan 1)")
    p.add_argument("--nagle", action="store_true",
                   help="Nagle algoritmasını açık bırak (varsayılan: kapalı)")
    p.add_argument("--cikti", type=Path, required=True, help="günlüklerin yazılacağı klasör")
    return p


def _hata_metni(hata: BaseException) -> str:
    kod = getattr(hata, "errno", None)
    ad = errno.errorcode.get(kod, "") if isinstance(kod, int) else ""
    return f"{type(hata).__name__}{'/' + ad if ad else ''}: {hata}"


def _baglan(args, bitis: float, ozet: Dict[str, object]) -> Optional[socket.socket]:
    """Bağlantıyı kurar; kurulamazsa None döner."""
    for deneme in range(1, args.baglanti_denemesi + 1):
        kalan = bitis - ortak.simdi()
        if kalan <= 0:
            break
        ozet["baglanti_denemeleri"] = deneme
        t0 = ortak.simdi()
        ortak.bilgi(BETIK, f"bağlanılıyor {args.hedef}:{args.port} (deneme {deneme})")
        try:
            # Zaman aşımı yalnızca koşunun kalan süresidir; daha kısa bir sınır
            # yok, bağlantı kurma süresini işletim sistemi belirler.
            s = socket.create_connection((args.hedef, args.port), timeout=kalan)
        except (OSError, socket.timeout) as hata:
            ozet["son_baglanti_hatasi"] = _hata_metni(hata)
            ortak.bilgi(BETIK, f"bağlantı kurulamadı ({ortak.simdi() - t0:.1f} s): "
                               f"{ozet['son_baglanti_hatasi']}")
            # Reddedilen bağlantı anında döner; aynı anda yeniden denemeyi önle.
            time.sleep(min(1.0, max(0.0, bitis - ortak.simdi())))
            continue
        ozet["baglanti_kurma_suresi_s"] = ortak.simdi() - t0
        if not args.nagle:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        ortak.bilgi(BETIK, f"bağlandı ({ozet['baglanti_kurma_suresi_s']:.2f} s)")
        return s
    return None


def calistir(args: argparse.Namespace) -> Dict[str, object]:
    belirtec = ortak.kosu_belirteci(args.deney_id)
    baslangic = ortak.simdi()
    bitis = baslangic + args.sure
    ozet: Dict[str, object] = {
        "betik": BETIK, "deney_id": args.deney_id, "mod": "tcp",
        "hedef": f"{args.hedef}:{args.port}", "planlanan_adet": args.adet,
        "boyut_byte": args.boyut, "aralik_s": args.aralik, "nagle": args.nagle,
        "baslangic": baslangic, "baglanti_denemeleri": 0, "baglanti_kuruldu": False,
        "baglanti_kurma_suresi_s": None, "son_baglanti_hatasi": None,
        "gonderilen": 0, "gonderilemeyen": 0, "hata": None, "cikis_nedeni": None,
    }
    gunluk = ortak.CsvGunluk(args.cikti / "gonderici.csv", ortak.GONDERICI_SUTUNLARI)
    siradaki = 0  # henüz kaydı yazılmamış ilk mesaj

    def kaydet(no: int, zaman: Optional[float], durum: str) -> None:
        gunluk.yaz({"deney_id": args.deney_id, "mod": "tcp", "mesaj_no": no,
                    "gonderme_zamani": ortak.zaman_bicimle(zaman),
                    "boyut_byte": args.boyut, "durum": durum})

    soket = None
    try:
        soket = _baglan(args, bitis, ozet)
        if soket is None:
            ozet["cikis_nedeni"] = "baglanti_kurulamadi"
            return ozet
        ozet["baglanti_kuruldu"] = True

        akis_baslangici = ortak.simdi()
        for no in range(args.adet):
            hedef_zaman = akis_baslangici + no * args.aralik
            bekle = hedef_zaman - ortak.simdi()
            if bekle > 0:
                time.sleep(bekle)
            kalan = bitis - ortak.simdi()
            if kalan <= 0:
                ozet["cikis_nedeni"] = "sure_doldu"
                return ozet
            zaman_ns = time.time_ns()
            veri = ortak.cerceve_ekle(ortak.mesaj_olustur(
                "tcp", belirtec, no, args.adet, args.boyut, zaman_ns))
            soket.settimeout(kalan)
            try:
                soket.sendall(veri)
            except (OSError, socket.timeout) as hata:
                ozet["hata"] = _hata_metni(hata)
                ortak.bilgi(BETIK, f"mesaj {no} gönderilemedi: {ozet['hata']}")
                ozet["cikis_nedeni"] = ("sure_doldu" if isinstance(hata, socket.timeout)
                                        else "baglanti_koptu")
                return ozet
            kaydet(no, zaman_ns / 1e9, ortak.DURUM_GONDERILDI)
            siradaki = no + 1
            ozet["gonderilen"] = siradaki

        # Gönderim bitti: yazma yönünü kapat, alıcının kapatmasını bekle.
        # Alıcı tüm mesajları alınca bağlantıyı kapatır (recv boş döner).
        ortak.bilgi(BETIK, f"{args.adet} mesaj çekirdeğe yazıldı, alıcı bekleniyor")
        try:
            soket.shutdown(socket.SHUT_WR)
            while True:
                kalan = bitis - ortak.simdi()
                if kalan <= 0:
                    ozet["cikis_nedeni"] = "sure_doldu"
                    break
                soket.settimeout(min(5.0, kalan))
                try:
                    if not soket.recv(4096):
                        ozet["cikis_nedeni"] = "alici_kapatti"
                        break
                except socket.timeout:
                    continue
        except OSError as hata:
            ozet["hata"] = _hata_metni(hata)
            ozet["cikis_nedeni"] = "baglanti_koptu"
        return ozet
    except ortak.DurdurmaIstegi:
        ozet["cikis_nedeni"] = "durduruldu"
        return ozet
    except Exception as hata:
        ozet["cikis_nedeni"] = "hata"
        ozet["hata"] = _hata_metni(hata)
        raise
    finally:
        # Ağa hiç çıkamamış mesajlar da kaydedilir; teslim oranının paydası planlanan adettir.
        for no in range(siradaki, args.adet):
            kaydet(no, None, ortak.DURUM_GONDERILEMEDI)
        ozet["gonderilemeyen"] = args.adet - siradaki
        if soket is not None:
            soket.close()
        gunluk.kapat()
        ozet["bitis"] = ortak.simdi()
        ortak.json_yaz(args.cikti / "gonderici_ozet.json", ozet)
        ortak.bilgi(BETIK, f"bitti ({ozet['cikis_nedeni']}): "
                           f"{siradaki}/{args.adet} mesaj gönderildi")


def main(argv=None) -> int:
    ortak.python_surumunu_dogrula()
    args = arguman_cozucu().parse_args(argv)
    if args.adet <= 0 or args.sure <= 0 or args.aralik < 0 or args.baglanti_denemesi < 1:
        sys.exit("--adet, --sure ve --baglanti-denemesi pozitif, --aralik negatif olmamalı")
    ortak.durdurma_sinyallerini_yakala()
    calistir(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
