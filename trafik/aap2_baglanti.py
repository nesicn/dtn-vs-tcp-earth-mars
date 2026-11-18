"""uD3TN'e AAP 2.0 arayüzü üzerinden bağlanmak için ortak yardımcılar.

DTN gönderici ve alıcı, uD3TN'in resmi Python paketi ud3tn-utils'in AAP2
istemcisini kullanır (pip install ud3tn-utils). Bu modül adres ayrıştırma,
bağlantı kurma ve bir bundle yükünü eksiksiz okuma işlerini tek yerde toplar.
"""

from __future__ import annotations

import socket
from typing import Optional

try:
    from ud3tn_utils.aap2 import AAP2TCPClient, AAP2UnixClient
except ImportError as _hata:  # pragma: no cover - kurulum eksikse açık mesaj ver
    raise SystemExit(
        "ud3tn-utils paketi bulunamadı. Kurmak için: pip install ud3tn-utils"
    ) from _hata


def adres_coz(tcp: Optional[str], soket_yolu: Optional[str]):
    """--aap2-tcp HOST:PORT veya --aap2-soket YOL argümanından istemci üretir."""
    if tcp:
        if ":" not in tcp:
            raise SystemExit("--aap2-tcp HOST:PORT biçiminde olmalı, örn. localhost:4242")
        host, port = tcp.rsplit(":", 1)
        return AAP2TCPClient(address=(host, port))
    if soket_yolu:
        return AAP2UnixClient(address=soket_yolu)
    raise SystemExit("--aap2-tcp veya --aap2-soket verilmeli")


def tam_oku(soket: socket.socket, uzunluk: int) -> bytes:
    """Soketten tam olarak `uzunluk` bayt okur.

    ud3tn-utils içindeki receive_adu() yükü tek bir recv() ile okur; büyük
    yüklerde eksik okuyabilir. Bu fonksiyon yükü parçalar halinde tamamlar.
    """
    tampon = bytearray()
    while len(tampon) < uzunluk:
        parca = soket.recv(uzunluk - len(tampon))
        if not parca:
            raise ConnectionError("uD3TN bağlantıyı yük okunurken kapattı")
        tampon.extend(parca)
    return bytes(tampon)


def eid_dogrula(eid: str) -> str:
    """Hedef EID için basit biçim denetimi (dtn:// veya ipn:)."""
    if not (eid.startswith("dtn://") or eid.startswith("ipn:")):
        raise SystemExit(f"Geçersiz EID: {eid!r} (dtn://... veya ipn:... olmalı)")
    return eid

