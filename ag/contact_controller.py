"""Deney 2: linkleri iletişim takvimine göre açıp kapatır (sorumlu: Elif).

Host'ta çalışır, konteynerlere `docker exec <konteyner> tc ...` ile komut verir.

Takvim (CSV, zamanlar t0'a göre saniye):
    link,baslangic_s,bitis_s,gecikme_s
    link1,0,20,1
    link2,30,50,0.05

Link -> arayüz eşlemesi deney/ortam_docker.json içindeki "arayuzler" alanından okunur:
    link1: dunya/<dunya_link1>, aktarici/<aktarici_link1>
    link2: aktarici/<aktarici_link2>, arac/<arac_link2>

Davranış:
    * Başlangıçta tüm linkler KAPALI yapılır (netem loss 100%).
    * Her pencerenin başlangıcında link açılır (netem delay <gecikme_s>),
      bitişinde yeniden kapatılır.
    * Takvim bitince linkler KAPALI kalır ve betik SIGTERM'i bekler (koşu hâlâ
      sürüyorsa uçtan uca yol yanlışlıkla açılmasın diye).
    * SIGTERM / SIGINT: tüm linkler AÇIK bırakılarak çıkılır
      (koşturucunun kosu_sonrasi kancaları ardından qdisc'leri siler).

Kullanım:
    python3 ag/contact_controller.py --takvim takvim.csv --t0 1764000000
    python3 ag/contact_controller.py --takvim ornek.csv --t0 now --kuru   # yalnızca yazdırır
"""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

PROJE_KOK = Path(__file__).resolve().parent.parent
VARSAYILAN_ORTAM = PROJE_KOK / "deney" / "ortam_docker.json"

# Link -> [(konteyner, arayuzler anahtarı)]
LINK_UCLARI: Dict[str, List[Tuple[str, str]]] = {
    "link1": [("dunya", "dunya_link1"), ("aktarici", "aktarici_link1")],
    "link2": [("aktarici", "aktarici_link2"), ("arac", "arac_link2")],
}
NETEM_LIMIT = 100000


def gunluk(mesaj: str) -> None:
    print(f"[contact_controller {time.time():.3f}] {mesaj}", flush=True)


def takvim_oku(yol: Path) -> List[Dict]:
    satirlar = []
    with open(yol, newline="", encoding="utf-8") as f:
        for s in csv.DictReader(f):
            if s["link"] not in LINK_UCLARI:
                raise ValueError(f"Bilinmeyen link: {s['link']}")
            satirlar.append({"link": s["link"],
                             "baslangic_s": float(s["baslangic_s"]),
                             "bitis_s": float(s["bitis_s"]),
                             "gecikme_s": float(s["gecikme_s"])})
    return satirlar


def olaylari_uret(satirlar: List[Dict]) -> List[Tuple[float, str, str, float]]:
    """(göreli zaman, link, 'ac'|'kapat', gecikme_s) olaylarını zamana göre sıralar.
    Aynı anda kapatma açmadan önce gelir."""
    olaylar = []
    for s in satirlar:
        olaylar.append((s["baslangic_s"], s["link"], "ac", s["gecikme_s"]))
        olaylar.append((s["bitis_s"], s["link"], "kapat", s["gecikme_s"]))
    olaylar.sort(key=lambda o: (o[0], 0 if o[2] == "kapat" else 1))
    return olaylar


class Kontrolcu:
    def __init__(self, arayuzler: Dict[str, str], kuru: bool):
        self.arayuzler = arayuzler
        self.kuru = kuru
        self.son_gecikme: Dict[str, float] = {}

    def _tc(self, konteyner: str, arayuz: str, netem: str) -> None:
        komut = ["docker", "exec", konteyner, "tc", "qdisc", "replace", "dev", arayuz,
                 "root", "netem"] + netem.split() + ["limit", str(NETEM_LIMIT)]
        if self.kuru:
            gunluk("KURU: " + shlex.join(komut))
            return
        r = subprocess.run(komut, capture_output=True, text=True)
        if r.returncode != 0:
            gunluk(f"UYARI: {shlex.join(komut)} -> {r.returncode}: {r.stderr.strip()}")

    def ayarla(self, link: str, acik: bool, gecikme_s: float) -> None:
        self.son_gecikme[link] = gecikme_s
        netem = f"delay {gecikme_s * 1000:g}ms"
        if not acik:
            netem += " loss 100%"
        for konteyner, anahtar in LINK_UCLARI[link]:
            self._tc(konteyner, self.arayuzler[anahtar], netem)
        gunluk(f"{link} {'AÇIK' if acik else 'KAPALI'} (gecikme {gecikme_s:g} s)")

    def hepsini_ac(self) -> None:
        for link in LINK_UCLARI:
            self.ayarla(link, True, self.son_gecikme.get(link, 0.0))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Takvime göre linkleri açıp kapatır.")
    p.add_argument("--takvim", type=Path, required=True, help="takvim.csv yolu")
    p.add_argument("--t0", required=True, help="başlangıç anı (Unix saniye) veya 'now'")
    p.add_argument("--ortam", type=Path, default=VARSAYILAN_ORTAM,
                   help="arayüz adlarının okunacağı ortam dosyası")
    p.add_argument("--kuru", action="store_true", help="tc komutlarını yalnızca yazdır")
    a = p.parse_args(argv)

    t0 = time.time() if a.t0 == "now" else float(a.t0)
    arayuzler = json.loads(Path(a.ortam).read_text(encoding="utf-8"))["arayuzler"]
    satirlar = takvim_oku(a.takvim)
    olaylar = olaylari_uret(satirlar)
    k = Kontrolcu(arayuzler, a.kuru)

    def cikis(signum, _frame):
        gunluk(f"sinyal {signum}: linkler açık bırakılıyor")
        k.hepsini_ac()
        sys.exit(0)

    signal.signal(signal.SIGTERM, cikis)
    signal.signal(signal.SIGINT, cikis)

    ilk_gecikme = {s["link"]: s["gecikme_s"] for s in reversed(satirlar)}
    for link in LINK_UCLARI:
        k.ayarla(link, False, ilk_gecikme.get(link, 0.0))

    for zaman, link, eylem, gecikme in olaylar:
        bekle = t0 + zaman - time.time()
        if bekle > 0:
            time.sleep(bekle)
        elif bekle < -0.5:
            gunluk(f"UYARI: {link} {eylem} olayı {-bekle:.2f} s geç")
        k.ayarla(link, eylem == "ac", gecikme)

    # Takvim bitti ama koşu sürüyor olabilir (koşturucu alıcıyı beklerken). Linkleri burada
    # açarsak uçtan uca yol açılır ve Deney 2'nin "yol hiç açık değil" koşulu bozulur.
    # Bu yüzden son durumda (kapalı) bekleriz; linkler yalnızca SIGTERM/SIGINT ile açılır.
    gunluk("takvim bitti: linkler kapalı, SIGTERM bekleniyor")
    while True:
        signal.pause()


if __name__ == "__main__":
    sys.exit(main())
