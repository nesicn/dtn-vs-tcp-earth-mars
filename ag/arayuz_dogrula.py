"""Her koşudan önce arayüzlerin doğru linke bağlı olduğunu denetler (sorumlu: Elif).

Neden: netem gecikmesi arayüz adına (eth0/eth1) uygulanır. Docker arayüz sırasını garanti
etmez; adlar karışırsa Dünya-uydu gecikmesi uydu-araç linkine uygulanır ve sonuçlar
SESSİZCE yanlış çıkar. Bu betik hata verirse koşturucu koşuyu hatalı sayar.

deney/ortam_docker.json içindeki "arayuzler" okunur. Anahtar biçimi <konteyner>_<link>:
    dunya_link1: eth0  ->  dunya'da eth0'ın adresi 10.0.1.x olmalı
    link1 = 10.0.1.0/24, link2 = 10.0.2.0/24 (docker-compose.yml)

Kullanım:
    python3 ag/arayuz_dogrula.py [--ortam deney/ortam_docker.json]
Çıkış kodu: 0 = hepsi doğru, 1 = en az bir uyumsuzluk.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJE_KOK = Path(__file__).resolve().parent.parent
LINK_AGLARI = {"link1": "10.0.1.", "link2": "10.0.2."}


def arayuz_adresi(konteyner: str, arayuz: str) -> str:
    r = subprocess.run(["docker", "exec", konteyner, "ip", "-o", "-4", "addr", "show", "dev", arayuz],
                       capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        return ""
    # Örnek satır: "2: eth0    inet 10.0.1.3/24 brd ... scope global eth0"
    parcalar = r.stdout.split()
    return parcalar[parcalar.index("inet") + 1].split("/")[0] if "inet" in parcalar else ""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Arayüz-link eşlemesini denetler.")
    p.add_argument("--ortam", type=Path, default=PROJE_KOK / "deney" / "ortam_docker.json")
    a = p.parse_args(argv)

    arayuzler = json.loads(a.ortam.read_text(encoding="utf-8"))["arayuzler"]
    hatalar = []
    for anahtar, arayuz in arayuzler.items():
        if anahtar.startswith("_"):
            continue
        konteyner, link = anahtar.rsplit("_", 1)
        beklenen = LINK_AGLARI[link]
        adres = arayuz_adresi(konteyner, arayuz)
        durum = "doğru" if adres.startswith(beklenen) else "YANLIŞ"
        print(f"{konteyner:9s} {arayuz:5s} -> {adres or '(adres yok)':12s} beklenen {link} ({beklenen}x): {durum}")
        if durum != "doğru":
            hatalar.append(anahtar)

    if hatalar:
        print(f"HATA: arayüz eşlemesi yanlış: {', '.join(hatalar)}. "
              "docker-compose.yml'deki interface_name ile ortam_docker.json'u karşılaştırın.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
