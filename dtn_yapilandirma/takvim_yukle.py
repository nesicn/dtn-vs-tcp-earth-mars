
#!/usr/bin/env python3
"""Load link contact windows into the relevant µD3TN node via docker exec.

CSV columns: link,baslangic_s,bitis_s,gecikme_s
`t0` is a Unix timestamp (seconds). Schedule offsets are relative to now.
`gecikme_s` is applied by the network/netem controller, not by this script.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import time
from pathlib import Path

LINK_TO_CONTAINER = {
    "link1": "dunya",
    "link2": "aktarici",
}

# Contact peer: (EID, CLA address, reachable EIDs)
LINK_TO_PEER = {
    "link1": (
        "dtn://aktarici.dtn/",
        "mtcp:10.0.1.3:4225",
        ["dtn://arac.dtn/"],
    ),
    "link2": (
        "dtn://arac.dtn/",
        "mtcp:10.0.2.3:4226",
        [],
    ),
}

AAP2_HOST = "127.0.0.1"
AAP2_PORT = "4242"
DEFAULT_BITRATE = "1000000000"


def load_rows(csv_path: Path):
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"link", "baslangic_s", "bitis_s", "gecikme_s"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                "CSV başlıkları şu şekilde olmalı: "
                "link,baslangic_s,bitis_s,gecikme_s"
            )
        return list(reader)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--takvim", required=True, help="Takvim CSV dosyası")
    parser.add_argument(
        "--t0", required=True, type=float,
        help="Deney başlangıç Unix zamanı"
    )
    parser.add_argument(
        "--bitrate", default=DEFAULT_BITRATE,
        help="aap2-config bitrate değeri"
    )
    args = parser.parse_args()

    rows = load_rows(Path(args.takvim))

    for row in rows:
        link = row["link"].strip()
        if link not in LINK_TO_CONTAINER:
            raise ValueError(
                f"Bilinmeyen link: {link!r}; beklenen: link1 veya link2"
            )

        start_s = float(row["baslangic_s"])
        end_s = float(row["bitis_s"])

        if end_s <= start_s:
            raise ValueError(
                f"{link}: bitis_s, baslangic_s değerinden büyük olmalı"
            )

        start_offset = round(args.t0 + start_s - time.time())
        duration = int(round(end_s - start_s))

        if start_offset < 0:
            print(
                f"UYARI: {link} penceresinin başlangıcı geçmişte; "
                "komut yine de gönderiliyor.",
                file=sys.stderr,
            )

        container = LINK_TO_CONTAINER[link]
        peer_eid, peer_cla, reaches = LINK_TO_PEER[link]

        cmd = [
            "docker", "exec", container,
            "aap2-config",
            "--tcp", AAP2_HOST, AAP2_PORT,
            peer_eid, peer_cla,
            "--schedule", str(start_offset), str(duration),
            str(args.bitrate),
        ]

        for eid in reaches:
            cmd += ["-r", eid]

        print("Çalıştırılıyor:", " ".join(cmd), flush=True)
        subprocess.run(cmd, check=True)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        raise SystemExit(1)
