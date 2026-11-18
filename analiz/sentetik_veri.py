"""Analiz ve grafik kodunu gerçek ölçümler gelmeden sınamak için SENTETİK veri üretir.

UYARI: Buradaki sayılar ölçüm değil, kaba bir varsayımla üretilmiş örnek
değerlerdir. Rapora veya sunuma girmez. Üretilen her koşu "sentetik": true olarak
işaretlenir ve grafikler bu durumda üzerlerine açık bir uyarı yazar.

Kullanılan varsayım (yalnızca grafiklerin şeklini görmek için):
    * TCP, gidiş-dönüş süresi Linux'un bağlantı kurma sınırına (~127 s) yaklaşınca
      bağlanamaz; bağlanabildiğinde gecikmeyle artan gereksiz yeniden iletimler yapar.
    * DTN her mesajı teslim eder; Deney 2'de bir sonraki link2 penceresini bekler.

Kullanım:
    python analiz/sentetik_veri.py --cikti sonuclar_sentetik
    python analiz/analiz.py --sonuclar sonuclar_sentetik
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from deney.run_experiment import json_yukle, kosulari_uret  # noqa: E402
from trafik import ortak  # noqa: E402

TCP_BAGLANTI_SINIRI_S = 127.0   # Linux varsayılanı tcp_syn_retries=6 ile yaklaşık
BASLIK_BAYT = 66                # Ethernet + IP + TCP başlıkları, kaba
ACK_BAYT = 66


def _kosu_yaz(dizin: Path, kosu: dict, rng: random.Random) -> None:
    p = kosu["parametreler"]
    adet, boyut, aralik = int(p["adet"]), int(p["boyut"]), float(p["aralik"])
    g1, g2 = float(p["g1"]), float(p["g2"])
    yol = g1 + g2
    t0 = 1_800_000_000.0 + rng.random() * 1000
    dizin.mkdir(parents=True, exist_ok=True)

    gonderilen, alinan, hat_bayt, baglanti = [], [], 0, None
    gonder_zaman = [t0 + i * aralik for i in range(adet)]

    if kosu["mod"] == "tcp":
        rtt = 2 * yol
        acik_yol = not kosu["takvimli"] and rtt < TCP_BAGLANTI_SINIRI_S
        if acik_yol:
            baglanti = rtt * rng.uniform(1.0, 1.05)
            yeniden = 1 + min(3.0, yol / 20.0)          # gecikmeyle artan tekrarlar
            for i, t in enumerate(gonder_zaman):
                gonderilen.append((i, t))
                alinan.append((i, t, t + yol + rng.uniform(0, 0.02 + 0.01 * yol)))
            hat_bayt = int(2 * adet * ((boyut + 4 + BASLIK_BAYT) * yeniden + ACK_BAYT))
        else:
            hat_bayt = int(2 * 7 * 74)                   # yalnızca SYN denemeleri
    else:
        for i, t in enumerate(gonder_zaman):
            gonderilen.append((i, t))
            if kosu["takvimli"]:
                pencere, bosluk = float(p["pencere"]), float(p["bosluk"])
                varis = t0 + pencere + bosluk + g2 + rng.uniform(0, 0.3) + i * 0.002
            else:
                varis = t + yol + rng.uniform(0, 0.05)
            alinan.append((i, t, varis))
        hat_bayt = int(2 * adet * (boyut + 40 + BASLIK_BAYT + ACK_BAYT))

    with ortak.CsvGunluk(dizin / "gonderici.csv", ortak.GONDERICI_SUTUNLARI) as g:
        gonderildi = {i for i, _ in gonderilen}
        for i, t in enumerate(gonder_zaman):
            g.yaz({"deney_id": kosu["kosu_id"], "mod": kosu["mod"], "mesaj_no": i,
                   "gonderme_zamani": ortak.zaman_bicimle(t if i in gonderildi else None),
                   "boyut_byte": boyut,
                   "durum": ortak.DURUM_GONDERILDI if i in gonderildi
                   else ortak.DURUM_GONDERILEMEDI})
    with ortak.CsvGunluk(dizin / "alici.csv", ortak.ALICI_SUTUNLARI) as a:
        for i, t, v in alinan:
            a.yaz({"deney_id": kosu["kosu_id"], "mod": kosu["mod"], "mesaj_no": i,
                   "gonderme_zamani": ortak.zaman_bicimle(t),
                   "alma_zamani": ortak.zaman_bicimle(v), "boyut_byte": boyut})
    ortak.json_yaz(dizin / "gonderici_ozet.json", {
        "mod": kosu["mod"], "planlanan_adet": adet, "boyut_byte": boyut,
        "gonderilen": len(gonderilen), "baglanti_kurma_suresi_s": baglanti,
        "cikis_nedeni": "alici_kapatti" if alinan else "baglanti_kurulamadi"})
    ortak.json_yaz(dizin / "alici_ozet.json", {
        "mod": kosu["mod"], "alinan_benzersiz": len(alinan), "yabanci": 0,
        "cikis_nedeni": "tamamlandi" if len(alinan) == adet else "sure_doldu"})
    kayit = dict(kosu)
    kayit.update({"durum": "tamamlandi", "ortam": "sentetik", "sentetik": True,
                  "hat_bayt": hat_bayt})
    ortak.json_yaz(dizin / "kosu.json", kayit)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="SENTETİK (sahte) koşu verisi üretir.")
    p.add_argument("--cikti", type=Path, default=KOK / "sonuclar_sentetik")
    p.add_argument("--tohum", type=int, default=7)
    a = p.parse_args(argv)
    if a.cikti.resolve() == (KOK / "sonuclar").resolve():
        sys.exit("Sentetik veri gerçek sonuçların klasörüne yazılamaz.")
    if a.cikti.exists():
        shutil.rmtree(a.cikti)
    rng = random.Random(a.tohum)
    toplam = 0
    for ad in ("deney1", "deney2"):
        matris = json_yukle(KOK / "deney" / "matrisler" / f"{ad}.json")
        for kosu in kosulari_uret(matris):
            _kosu_yaz(a.cikti / kosu["deney"] / kosu["kosu_id"], kosu, rng)
            toplam += 1
    print(f"{toplam} SENTETİK koşu {a.cikti} altına yazıldı (gerçek ölçüm değil).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
