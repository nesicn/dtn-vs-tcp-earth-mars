"""Deney 2 için iletişim takvimi (contact plan) üretir.

Takvim, ekipte kararlaştırılan tek doğruluk kaynağıdır: Elif'in link betiği ve
Azra'nın uD3TN yapılandırması aynı CSV dosyasını okur.

Biçim (zamanlar t0'a göre saniye):
    link,baslangic_s,bitis_s,gecikme_s
    link1,0,20,1
    link2,30,50,0.05
    ...

Kurallar (yol haritası bölüm 4):
    * link1 (Dünya-uydu) ve link2 (uydu-araç) pencereleri hiç örtüşmez.
    * Pencereler arasındaki boşluk, Dünya-uydu gecikmesinden uzun olmalıdır;
      aksi halde link1 penceresinin sonunda gönderilen bir paket link2 penceresine
      yetişir ve uçtan uca yol fiilen açılmış olur.
    * Periyot = 2 x (pencere + boşluk).

Komut satırı:
    python deney/takvim.py --pencere 20 --bosluk 10 --g1 1 --g2 0.05 \\
        --periyot-sayisi 3 --cikti contact_plan.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List

TAKVIM_SUTUNLARI = ["link", "baslangic_s", "bitis_s", "gecikme_s"]


def _sayi_yaz(x: float) -> str:
    """CSV'de gereksiz ondalık gösterme: 20.0 -> 20, 0.05 -> 0.05."""
    return f"{x:g}"


def takvim_uret(pencere: float, bosluk: float, g1: float, g2: float,
                periyot_sayisi: int) -> List[Dict[str, float]]:
    """Örtüşmeyen pencereli takvim satırlarını üretir."""
    if pencere <= 0 or bosluk <= 0 or periyot_sayisi < 1:
        raise ValueError("pencere ve boşluk pozitif, periyot sayısı en az 1 olmalı")
    if bosluk <= g1:
        raise ValueError(
            f"Boşluk ({bosluk} s), Dünya-uydu gecikmesinden ({g1} s) uzun olmalı; "
            "aksi halde uçtan uca yol fiilen açılır.")
    periyot = 2 * (pencere + bosluk)
    satirlar = []
    for k in range(periyot_sayisi):
        t = k * periyot
        satirlar.append({"link": "link1", "baslangic_s": t,
                         "bitis_s": t + pencere, "gecikme_s": g1})
        satirlar.append({"link": "link2", "baslangic_s": t + pencere + bosluk,
                         "bitis_s": t + 2 * pencere + bosluk, "gecikme_s": g2})
    return satirlar


def takvim_dogrula(satirlar: List[Dict[str, float]]) -> None:
    """link1 ve link2 pencerelerinin hiçbir anda örtüşmediğini denetler."""
    l1 = [(s["baslangic_s"], s["bitis_s"]) for s in satirlar if s["link"] == "link1"]
    l2 = [(s["baslangic_s"], s["bitis_s"]) for s in satirlar if s["link"] == "link2"]
    for a0, a1 in l1:
        for b0, b1 in l2:
            if a0 < b1 and b0 < a1:
                raise ValueError(f"Pencereler örtüşüyor: link1 [{a0},{a1}] ve link2 [{b0},{b1}]")


def takvim_yaz(yol: Path, satirlar: List[Dict[str, float]]) -> None:
    Path(yol).parent.mkdir(parents=True, exist_ok=True)
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TAKVIM_SUTUNLARI)
        w.writeheader()
        for s in satirlar:
            w.writerow({k: (s[k] if k == "link" else _sayi_yaz(float(s[k])))
                        for k in TAKVIM_SUTUNLARI})


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Örtüşmeyen pencereli iletişim takvimi üretir.")
    p.add_argument("--pencere", type=float, required=True, help="pencere süresi, s")
    p.add_argument("--bosluk", type=float, default=10.0, help="pencereler arası boşluk, s")
    p.add_argument("--g1", type=float, default=1.0, help="Dünya-uydu tek yön gecikme, s")
    p.add_argument("--g2", type=float, default=0.05, help="uydu-araç tek yön gecikme, s")
    p.add_argument("--periyot-sayisi", type=int, default=3)
    p.add_argument("--cikti", type=Path, default=Path("contact_plan.csv"))
    a = p.parse_args(argv)
    satirlar = takvim_uret(a.pencere, a.bosluk, a.g1, a.g2, a.periyot_sayisi)
    takvim_dogrula(satirlar)
    takvim_yaz(a.cikti, satirlar)
    print(f"{a.cikti} yazıldı: {len(satirlar)} pencere, periyot "
          f"{2 * (a.pencere + a.bosluk):g} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
