"""Tüm koşuları analiz eder: özet tablolar ve grafikler.

Kullanım:
    python analiz/analiz.py                         # sonuclar/ klasörünü analiz et
    python analiz/analiz.py --sonuclar sonuclar_sentetik

Çıktılar (--cikti, varsayılan <sonuclar>/analiz):
    kosular.csv   her koşu için bir satır (tüm metrikler)
    gruplar.csv   tekrarlar birleştirilmiş, her (deney, mod, nokta) için bir satır
    *.png         rapor ve sunum grafikleri
Ekrana da kısa bir özet tablo yazar.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from analiz import metrikler  # noqa: E402


def _yuzde(x) -> str:
    return "-" if x is None else f"%{100 * x:.0f}"


def _sn(x) -> str:
    return "-" if x is None else f"{x:.2f}"


def ozet_tablo(gruplar) -> str:
    satirlar = [f"{'deney':<8} {'mod':<4} {'nokta':<7} {'n':>2} {'teslim':>7} "
                f"{'min-max':>9} {'medyan s':>9} {'p95 s':>8} {'ek yük':>7}"]
    for g in gruplar:
        aralik = (f"{_yuzde(g['teslim_orani_min'])}-{_yuzde(g['teslim_orani_max'])}"
                  if g["teslim_orani_min"] is not None else "-")
        ek = "-" if g["ek_yuk_orani_ort"] is None else f"{g['ek_yuk_orani_ort']:.2f}"
        satirlar.append(
            f"{g['deney']:<8} {g['mod']:<4} {g['nokta']:<7} {g['n']:>2} "
            f"{_yuzde(g['teslim_orani_ort']):>7} {aralik:>9} {_sn(g['gecikme_medyan_s']):>9} "
            f"{_sn(g['gecikme_p95_s']):>8} {ek:>7}")
    return "\n".join(satirlar)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Koşu sonuçlarını analiz eder.")
    p.add_argument("--sonuclar", type=Path, default=KOK / "sonuclar")
    p.add_argument("--cikti", type=Path, default=None)
    p.add_argument("--grafiksiz", action="store_true", help="yalnızca tabloları üret")
    a = p.parse_args(argv)

    cikti = a.cikti or (a.sonuclar / "analiz")
    kosular = metrikler.tum_kosular(a.sonuclar)
    if not kosular:
        print(f"{a.sonuclar} altında tamamlanmış koşu bulunamadı.")
        return 1
    gruplar = metrikler.grupla(kosular)
    metrikler.csv_yaz(cikti / "kosular.csv", kosular, metrikler.KOSU_SUTUNLARI)
    metrikler.csv_yaz(cikti / "gruplar.csv", gruplar, metrikler.GRUP_SUTUNLARI)

    if any(k["sentetik"] for k in kosular):
        print("UYARI: Bu veri SENTETİK, gerçek ölçüm değil. Rapora girmez.\n")
    elif any(k.get("ortam") == "yerel" for k in kosular):
        print("UYARI: Bu veri yerel denemeden, gerçek ölçüm değil.\n")
    print(ozet_tablo(gruplar))
    print(f"\n{len(kosular)} koşu, {len(gruplar)} grup -> {cikti}")

    if not a.grafiksiz:
        try:
            from analiz import grafikler
        except ImportError as hata:
            print(f"Grafikler atlandı ({hata}). Kurmak için: pip install pandas matplotlib")
            return 0
        for yol in grafikler.hepsini_ciz(gruplar, cikti):
            print(f"grafik: {yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
