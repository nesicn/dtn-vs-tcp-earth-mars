"""DTN gönderici: Dünya istasyonundaki uD3TN düğümü üzerinden bundle gönderir.

Her test mesajı bir bundle'ın yükü olur. Betik yerel uD3TN düğümüne AAP 2.0 ile
bağlanır; bundle'ı düğüme teslim eder ve düğümün kabul yanıtını bekler. Bundle'ın
hedefe ne zaman ulaşacağına uD3TN karar verir (sakla-ve-ilet).

Örnek (Docker, dunya konteynerinde; uD3TN'in AAP2 portu 4242 varsayımıyla):
    python3 trafik/dtn_gonderici.py --deney-id d1_dtn_g10_t1 \\
        --aap2-tcp localhost:4242 --hedef-eid dtn://arac.dtn/sink \\
        --adet 50 --boyut 1024 --aralik 0.1 --sure 300 \\
        --cikti sonuclar/deney1/d1_dtn_g10_t1

Çıktılar (--cikti klasöründe):
    gonderici.csv        her mesaj için bir satır; "gonderildi" = yerel düğüm kabul etti
    gonderici_ozet.json  kabul edilen/reddedilen sayıları, hata, çıkış nedeni

Not: Bundle ömrü (lifetime) bu betikten değil, uD3TN düğümünün ayarından gelir.
Ömür koşu süresinden uzun olmalıdır, yoksa bundle'lar yolda silinir. (Azra'nın
yapılandırmasında kontrol edilir.)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trafik import ortak  # noqa: E402
from trafik import aap2_baglanti  # noqa: E402
from ud3tn_utils.aap2 import (  # noqa: E402
    AAP2Error, BundleADU, BundleADUFlags, ResponseStatus,
)

BETIK = "dtn_gonderici"
YANIT_ZAMAN_ASIMI_S = 30.0   # yerel düğümün kabul yanıtı için


def arguman_cozucu() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="uD3TN üzerinden test bundle'ları gönderir.")
    p.add_argument("--deney-id", required=True, help="koşunun kimliği (alıcı ile aynı)")
    adres = p.add_mutually_exclusive_group(required=True)
    adres.add_argument("--aap2-tcp", help="yerel uD3TN AAP2 adresi, HOST:PORT")
    adres.add_argument("--aap2-soket", help="yerel uD3TN AAP2 UNIX soketi yolu")
    p.add_argument("--hedef-eid", required=True, type=aap2_baglanti.eid_dogrula,
                   help="alıcının EID'si, örn. dtn://arac.dtn/sink")
    p.add_argument("--ajan-id", default=None,
                   help="göndericinin ajan kimliği (varsayılan: rastgele)")
    p.add_argument("--adet", type=int, default=50, help="gönderilecek mesaj sayısı")
    p.add_argument("--boyut", type=int, default=1024, help="mesaj boyutu, bayt")
    p.add_argument("--aralik", type=float, default=0.1,
                   help="mesajlar arasındaki süre, saniye (varsayılan 0.1)")
    p.add_argument("--sure", type=float, required=True,
                   help="koşunun toplam süresi, saniye")
    p.add_argument("--cikti", type=Path, required=True, help="günlüklerin yazılacağı klasör")
    return p


def calistir(args: argparse.Namespace) -> Dict[str, object]:
    belirtec = ortak.kosu_belirteci(args.deney_id)
    baslangic = ortak.simdi()
    bitis = baslangic + args.sure
    ozet: Dict[str, object] = {
        "betik": BETIK, "deney_id": args.deney_id, "mod": "dtn",
        "hedef_eid": args.hedef_eid, "planlanan_adet": args.adet,
        "boyut_byte": args.boyut, "aralik_s": args.aralik, "baslangic": baslangic,
        "dugum_eid": None, "gonderilen": 0, "reddedilen": 0, "gonderilemeyen": 0,
        "hata": None, "cikis_nedeni": None,
    }
    gunluk = ortak.CsvGunluk(args.cikti / "gonderici.csv", ortak.GONDERICI_SUTUNLARI)
    siradaki = 0

    def kaydet(no: int, zaman: Optional[float], durum: str) -> None:
        gunluk.yaz({"deney_id": args.deney_id, "mod": "dtn", "mesaj_no": no,
                    "gonderme_zamani": ortak.zaman_bicimle(zaman),
                    "boyut_byte": args.boyut, "durum": durum})

    istemci = aap2_baglanti.adres_coz(args.aap2_tcp, args.aap2_soket)
    try:
        with istemci:
            istemci.socket.settimeout(YANIT_ZAMAN_ASIMI_S)
            istemci.configure(args.ajan_id, subscribe=False)
            ozet["dugum_eid"] = istemci.node_eid
            ortak.bilgi(BETIK, f"uD3TN düğümüne bağlandı: {istemci.node_eid}")

            akis_baslangici = ortak.simdi()
            for no in range(args.adet):
                bekle = akis_baslangici + no * args.aralik - ortak.simdi()
                if bekle > 0:
                    time.sleep(bekle)
                if ortak.simdi() >= bitis:
                    ozet["cikis_nedeni"] = "sure_doldu"
                    return ozet
                zaman_ns = time.time_ns()
                yuk = ortak.mesaj_olustur("dtn", belirtec, no, args.adet,
                                          args.boyut, zaman_ns)
                istemci.send_adu(
                    BundleADU(dst_eid=args.hedef_eid, payload_length=len(yuk),
                              adu_flags=[BundleADUFlags.BUNDLE_ADU_NORMAL]),
                    yuk,
                )
                yanit = istemci.receive_response()
                if yanit.response_status == ResponseStatus.RESPONSE_STATUS_SUCCESS:
                    kaydet(no, zaman_ns / 1e9, ortak.DURUM_GONDERILDI)
                    ozet["gonderilen"] = int(ozet["gonderilen"]) + 1
                else:
                    durum_adi = istemci.response_status_name(yanit.response_status)
                    ozet["reddedilen"] = int(ozet["reddedilen"]) + 1
                    ozet["hata"] = f"uD3TN reddetti: {durum_adi}"
                    ortak.bilgi(BETIK, f"mesaj {no} reddedildi: {durum_adi}")
                    kaydet(no, zaman_ns / 1e9, ortak.DURUM_GONDERILEMEDI)
                siradaki = no + 1
            ozet["cikis_nedeni"] = "tamamlandi"
            return ozet
    except ortak.DurdurmaIstegi:
        ozet["cikis_nedeni"] = "durduruldu"
        return ozet
    except (AAP2Error, OSError, RuntimeError) as hata:
        ozet["cikis_nedeni"] = "baglanti_hatasi"
        ozet["hata"] = f"{type(hata).__name__}: {hata}"
        ortak.bilgi(BETIK, f"uD3TN bağlantı hatası: {ozet['hata']}")
        return ozet
    finally:
        for no in range(siradaki, args.adet):
            kaydet(no, None, ortak.DURUM_GONDERILEMEDI)
        ozet["gonderilemeyen"] = (args.adet - siradaki) + int(ozet["reddedilen"])
        gunluk.kapat()
        ozet["bitis"] = ortak.simdi()
        ortak.json_yaz(args.cikti / "gonderici_ozet.json", ozet)
        ortak.bilgi(BETIK, f"bitti ({ozet['cikis_nedeni']}): "
                           f"{ozet['gonderilen']}/{args.adet} bundle düğüme teslim edildi")


def main(argv=None) -> int:
    ortak.python_surumunu_dogrula()
    args = arguman_cozucu().parse_args(argv)
    if args.adet <= 0 or args.sure <= 0 or args.aralik < 0:
        sys.exit("--adet ve --sure pozitif, --aralik negatif olmamalı")
    ortak.durdurma_sinyallerini_yakala()
    calistir(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
