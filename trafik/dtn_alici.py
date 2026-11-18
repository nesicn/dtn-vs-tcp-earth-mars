"""DTN alıcı: Mars aracındaki uD3TN düğümüne gelen bundle'ları günlüğe yazar.

Betik yerel uD3TN düğümüne AAP 2.0 ile abone (subscriber) olarak bağlanır ve
belirtilen ajan kimliğine (örn. "sink") gelen bundle'ları alır. Alıcının EID'si
düğüm EID'si + ajan kimliğidir: dtn://arac.dtn/ + sink = dtn://arac.dtn/sink.

Örnek (Docker, arac konteynerinde):
    python3 trafik/dtn_alici.py --deney-id d1_dtn_g10_t1 --aap2-tcp localhost:4242 \\
        --ajan-id sink --adet 50 --sure 300 --cikti sonuclar/deney1/d1_dtn_g10_t1

Çıktılar (--cikti klasöründe):
    alici.csv        her alınan bundle için bir satır (kopyalar dahil)
    alici_ozet.json  alınan, kopya, yabancı, hatalı sayıları ve çıkış nedeni

Davranış:
    * Tüm mesajlar (--adet) benzersiz olarak alındığında, --sure dolduğunda veya
      SIGTERM/SIGINT geldiğinde çıkar.
    * Önceki koşulardan geç gelen bundle'ları (farklı koşu belirteci) saymaz.
"""

from __future__ import annotations

import argparse
import select
import sys
from pathlib import Path
from typing import Dict

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trafik import ortak  # noqa: E402
from trafik import aap2_baglanti  # noqa: E402
from ud3tn_utils.aap2 import (  # noqa: E402
    AAP2Error, BundleADUFlags, ResponseStatus,
)

BETIK = "dtn_alici"
MESAJ_OKUMA_ZAMAN_ASIMI_S = 30.0   # okunmaya başlanmış bir mesajın tamamı için


def arguman_cozucu() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="uD3TN'den test bundle'larını alır.")
    p.add_argument("--deney-id", required=True, help="koşunun kimliği (gönderici ile aynı)")
    adres = p.add_mutually_exclusive_group(required=True)
    adres.add_argument("--aap2-tcp", help="yerel uD3TN AAP2 adresi, HOST:PORT")
    adres.add_argument("--aap2-soket", help="yerel uD3TN AAP2 UNIX soketi yolu")
    p.add_argument("--ajan-id", default="sink",
                   help="dinlenecek ajan kimliği (varsayılan: sink)")
    p.add_argument("--adet", type=int, required=True, help="beklenen mesaj sayısı")
    p.add_argument("--sure", type=float, required=True,
                   help="en fazla bekleme süresi, saniye (koşunun toplam süresi)")
    p.add_argument("--keepalive", type=int, default=0,
                   help="uD3TN'in canlılık mesajı aralığı, saniye (0 = kapalı)")
    p.add_argument("--cikti", type=Path, required=True, help="günlüklerin yazılacağı klasör")
    return p


def calistir(args: argparse.Namespace) -> Dict[str, object]:
    beklenen_belirtec = ortak.kosu_belirteci(args.deney_id)
    baslangic = ortak.simdi()
    bitis = baslangic + args.sure
    ozet: Dict[str, object] = {
        "betik": BETIK, "deney_id": args.deney_id, "mod": "dtn",
        "beklenen_adet": args.adet, "ajan_id": args.ajan_id, "alici_eid": None,
        "baslangic": baslangic, "alinan_benzersiz": 0, "alinan_toplam": 0,
        "kopya": 0, "yabanci": 0, "hatali": 0, "durum_raporu": 0,
        "ilk_alma": None, "son_alma": None, "cikis_nedeni": None, "hata": None,
    }
    gorulen = set()
    gunluk = ortak.CsvGunluk(args.cikti / "alici.csv", ortak.ALICI_SUTUNLARI)
    istemci = aap2_baglanti.adres_coz(args.aap2_tcp, args.aap2_soket)

    try:
        with istemci:
            istemci.socket.settimeout(MESAJ_OKUMA_ZAMAN_ASIMI_S)
            istemci.configure(args.ajan_id, subscribe=True,
                              keepalive_seconds=args.keepalive)
            ozet["alici_eid"] = istemci.eid
            ortak.hazir_bildir(BETIK)
            ortak.bilgi(BETIK, f"{istemci.eid} dinleniyor, {args.adet} mesaj bekleniyor")

            while True:
                if len(gorulen) >= args.adet:
                    ozet["cikis_nedeni"] = "tamamlandi"
                    break
                kalan = bitis - ortak.simdi()
                if kalan <= 0:
                    ozet["cikis_nedeni"] = "sure_doldu"
                    break
                # Okumaya yalnızca veri gelmişken başla: böylece süre kontrolü için
                # beklerken bir mesajın ortasında zaman aşımına uğranmaz.
                okunabilir, _, _ = select.select([istemci.socket], [], [], min(1.0, kalan))
                if not okunabilir:
                    continue

                mesaj = istemci.receive_msg()
                tur = mesaj.WhichOneof("msg")
                if tur == "keepalive":
                    istemci.send_response_status(ResponseStatus.RESPONSE_STATUS_ACK)
                    continue
                if tur != "adu":
                    continue
                yuk = aap2_baglanti.tam_oku(istemci.socket, mesaj.adu.payload_length)
                istemci.send_response_status(ResponseStatus.RESPONSE_STATUS_SUCCESS)
                alma = ortak.simdi()

                if BundleADUFlags.BUNDLE_ADU_STATUS_REPORT in mesaj.adu.adu_flags:
                    ozet["durum_raporu"] = int(ozet["durum_raporu"]) + 1
                    continue
                try:
                    m = ortak.mesaj_coz(yuk)
                except ortak.MesajHatasi as hata:
                    ozet["hatali"] = int(ozet["hatali"]) + 1
                    ortak.bilgi(BETIK, f"hatalı yük atlandı ({mesaj.adu.src_eid}): {hata}")
                    continue
                if m.kosu_belirteci != beklenen_belirtec or m.mod != "dtn":
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
                    "deney_id": args.deney_id, "mod": "dtn", "mesaj_no": m.mesaj_no,
                    "gonderme_zamani": ortak.zaman_bicimle(m.gonderme_zamani),
                    "alma_zamani": ortak.zaman_bicimle(alma), "boyut_byte": m.boyut,
                })
    except ortak.DurdurmaIstegi:
        ozet["cikis_nedeni"] = "durduruldu"
    except (AAP2Error, OSError, RuntimeError, ConnectionError) as hata:
        ozet["cikis_nedeni"] = "baglanti_hatasi"
        ozet["hata"] = f"{type(hata).__name__}: {hata}"
        ortak.bilgi(BETIK, f"uD3TN bağlantı hatası: {ozet['hata']}")
    finally:
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
    if args.adet <= 0 or args.sure <= 0 or args.keepalive < 0:
        sys.exit("--adet ve --sure pozitif, --keepalive negatif olmamalı")
    ortak.durdurma_sinyallerini_yakala()
    ozet = calistir(args)
    return 1 if ozet["cikis_nedeni"] == "baglanti_hatasi" else 0


if __name__ == "__main__":
    sys.exit(main())
