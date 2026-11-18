"""Testler için uD3TN AAP 2.0 arayüzünün küçük bir taklidi (test double).

UYARI: Bu bir DTN uygulaması DEĞİLDİR ve deneylerde kullanılmaz. Yalnızca
dtn_gonderici.py ve dtn_alici.py betiklerinin AAP 2.0 protokolünü doğru
konuştuğunu, uD3TN kurulmadan önce kendi bilgisayarında sınamak içindir.

Taklit edilen davranış (gerçek uD3TN'in AAP 2.0 akışına göre):
    * Bağlantıda 0x2F sihirli baytı ve WELCOME mesajı gönderilir.
    * İstemcinin CONFIGURE mesajına SUCCESS yanıtı verilir.
    * Aktif istemciden gelen her bundle ADU'su SUCCESS ile kabul edilir ve
      --gecikme saniye sonra hedef EID'ye abone olan istemciye iletilir.
      Abone yoksa, abone bağlanana kadar bekletilir (sakla-ve-ilet gibi).

Çalıştırma:
    python testler/sahte_ud3tn.py --port 4242 --gecikme 0.5
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from google.protobuf.internal.decoder import _DecodeVarint32
from google.protobuf.internal.encoder import _VarintBytes
from ud3tn_utils.aap2 import (
    AAPMessage, AAPResponse, BundleADU, BundleADUFlags, ResponseStatus, Welcome,
)

DUGUM_EID = "dtn://sahte.dtn/"


def _tam_oku(s: socket.socket, n: int) -> bytes:
    tampon = bytearray()
    while len(tampon) < n:
        parca = s.recv(n - len(tampon))
        if not parca:
            raise ConnectionError("istemci bağlantıyı kapattı")
        tampon.extend(parca)
    return bytes(tampon)


def _sinirli_oku(s: socket.socket) -> bytes:
    ham = bytearray()
    while True:
        b = _tam_oku(s, 1)
        ham += b
        if not b[0] & 0x80:
            break
        if len(ham) > 10:
            raise ValueError("geçersiz varint")
    uzunluk = _DecodeVarint32(bytes(ham), 0)[0]
    return _tam_oku(s, uzunluk)


def _sinirli_gonder(s: socket.socket, mesaj) -> None:
    ham = mesaj.SerializeToString()
    s.sendall(_VarintBytes(len(ham)) + ham)


class SahteUd3tn:
    def __init__(self, host: str = "127.0.0.1", port: int = 0,
                 gecikme: float = 0.0) -> None:
        self.gecikme = gecikme
        self._kilit = threading.Lock()
        self._aboneler: Dict[str, Tuple[socket.socket, threading.Lock]] = {}
        self._bekleyen: Dict[str, List[Tuple[str, bytes]]] = defaultdict(list)
        self._sunucu = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sunucu.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sunucu.bind((host, port))
        self._sunucu.listen(16)
        self.adres = self._sunucu.getsockname()
        self._calisiyor = True
        self.iletilen = 0

    def baslat(self) -> "SahteUd3tn":
        threading.Thread(target=self._kabul_dongusu, daemon=True).start()
        return self

    def durdur(self) -> None:
        self._calisiyor = False
        try:
            self._sunucu.close()
        except OSError:
            pass

    # -- iç işleyiş ---------------------------------------------------------

    def _kabul_dongusu(self) -> None:
        while self._calisiyor:
            try:
                s, _ = self._sunucu.accept()
            except OSError:
                return
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self._istemci, args=(s,), daemon=True).start()

    def _istemci(self, s: socket.socket) -> None:
        eid: Optional[str] = None
        try:
            s.sendall(b"\x2f")
            _sinirli_gonder(s, AAPMessage(welcome=Welcome(node_id=DUGUM_EID)))
            mesaj = AAPMessage()
            mesaj.ParseFromString(_sinirli_oku(s))
            if mesaj.WhichOneof("msg") != "config":
                return
            eid = mesaj.config.endpoint_id
            _sinirli_gonder(s, AAPResponse(
                response_status=ResponseStatus.RESPONSE_STATUS_SUCCESS))

            if mesaj.config.is_subscriber:
                yazma_kilidi = threading.Lock()
                with self._kilit:
                    self._aboneler[eid] = (s, yazma_kilidi)
                    bekleyen = self._bekleyen.pop(eid, [])
                for kaynak, yuk in bekleyen:
                    self._ilet(eid, kaynak, yuk)
                # Abonenin her ADU için gönderdiği yanıtları tüket.
                while True:
                    _sinirli_oku(s)
            else:
                while True:
                    m = AAPMessage()
                    m.ParseFromString(_sinirli_oku(s))
                    if m.WhichOneof("msg") == "keepalive":
                        _sinirli_gonder(s, AAPResponse(
                            response_status=ResponseStatus.RESPONSE_STATUS_ACK))
                        continue
                    if m.WhichOneof("msg") != "adu":
                        continue
                    yuk = _tam_oku(s, m.adu.payload_length)
                    _sinirli_gonder(s, AAPResponse(
                        response_status=ResponseStatus.RESPONSE_STATUS_SUCCESS))
                    hedef = m.adu.dst_eid
                    t = threading.Timer(self.gecikme, self._ilet_ya_da_beklet,
                                        args=(hedef, eid or "", yuk))
                    t.daemon = True
                    t.start()
        except (ConnectionError, OSError, ValueError):
            pass
        finally:
            with self._kilit:
                if eid and eid in self._aboneler and self._aboneler[eid][0] is s:
                    del self._aboneler[eid]
            try:
                s.close()
            except OSError:
                pass

    def _ilet_ya_da_beklet(self, hedef: str, kaynak: str, yuk: bytes) -> None:
        with self._kilit:
            abone_var = hedef in self._aboneler
            if not abone_var:
                self._bekleyen[hedef].append((kaynak, yuk))
        if abone_var:
            self._ilet(hedef, kaynak, yuk)

    def _ilet(self, hedef: str, kaynak: str, yuk: bytes) -> None:
        with self._kilit:
            kayit = self._aboneler.get(hedef)
        if kayit is None:
            with self._kilit:
                self._bekleyen[hedef].append((kaynak, yuk))
            return
        s, yazma_kilidi = kayit
        adu = BundleADU(src_eid=kaynak, dst_eid=hedef, payload_length=len(yuk),
                        creation_timestamp_ms=int(time.time() * 1000),
                        adu_flags=[BundleADUFlags.BUNDLE_ADU_NORMAL])
        try:
            with yazma_kilidi:
                _sinirli_gonder(s, AAPMessage(adu=adu))
                s.sendall(yuk)
            with self._kilit:
                self.iletilen += 1
        except OSError:
            with self._kilit:
                self._bekleyen[hedef].append((kaynak, yuk))


def main() -> int:
    p = argparse.ArgumentParser(description="uD3TN AAP 2.0 taklidi (yalnızca test için)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4242)
    p.add_argument("--gecikme", type=float, default=0.0,
                   help="her bundle'ın iletilmeden önce bekletileceği süre, saniye")
    args = p.parse_args()
    sunucu = SahteUd3tn(args.host, args.port, args.gecikme).baslat()
    print(f"HAZIR sahte_ud3tn {sunucu.adres[0]}:{sunucu.adres[1]}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        sunucu.durdur()
    return 0


if __name__ == "__main__":
    sys.exit(main())
