"""tcpdump/Wireshark yakalama dosyalarından bayt sayımı (yalnızca standart kütüphane).

Protokol ek yükü = ağa gönderilen toplam bayt / asıl veri baytı. Payı bu modül
hesaplar: yakalamadaki her çerçevenin kablodaki uzunluğu (orig_len) toplanır.

Desteklenen biçimler:
    * pcap (tcpdump -w varsayılanı), mikro ve nano saniye çözünürlüklü
    * pcapng (Wireshark'ın varsayılan kayıt biçimi)
Desteklenen bağlantı türleri (L4 protokolüne göre ayırmak için):
    Ethernet, Linux "cooked" (SLL ve SLL2, tcpdump -i any), ham IP, BSD loopback.

Komut satırı:
    python analiz/pcap_okuyucu.py sonuclar/deney1/d1_tcp_g10_t1/hat.pcap
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple

# Bağlantı türü -> IP başlığının çerçevedeki konumunu bulan fonksiyon
_ETHERNET, _RAW, _SLL, _SLL2, _NULL, _RAW_IPV4, _RAW_IPV6 = 1, 101, 113, 276, 0, 228, 229


class PcapHatasi(ValueError):
    pass


def _ip_konumu(baglanti: int, veri: bytes) -> Optional[int]:
    if baglanti == _ETHERNET:
        if len(veri) < 14:
            return None
        konum, tur = 14, struct.unpack_from("!H", veri, 12)[0]
        while tur in (0x8100, 0x88A8) and len(veri) >= konum + 4:  # VLAN etiketleri
            tur = struct.unpack_from("!H", veri, konum + 2)[0]
            konum += 4
        return konum if tur in (0x0800, 0x86DD) else None
    if baglanti == _SLL:
        if len(veri) < 16:
            return None
        return 16 if struct.unpack_from("!H", veri, 14)[0] in (0x0800, 0x86DD) else None
    if baglanti == _SLL2:
        if len(veri) < 20:
            return None
        return 20 if struct.unpack_from("!H", veri, 0)[0] in (0x0800, 0x86DD) else None
    if baglanti in (_RAW, 12, 14, _RAW_IPV4, _RAW_IPV6):
        return 0
    if baglanti == _NULL:
        return 4
    return None


def l4_protokolu(baglanti: int, veri: bytes) -> str:
    """Çerçevenin taşıma katmanı protokolü: 'tcp', 'udp', 'icmp' veya 'diger'."""
    konum = _ip_konumu(baglanti, veri)
    if konum is None or len(veri) <= konum:
        return "diger"
    surum = veri[konum] >> 4
    if surum == 4 and len(veri) >= konum + 20:
        proto = veri[konum + 9]
    elif surum == 6 and len(veri) >= konum + 40:
        proto = veri[konum + 6]
    else:
        return "diger"
    return {6: "tcp", 17: "udp", 1: "icmp", 58: "icmp"}.get(proto, "diger")


def _pcap_cerceveleri(f, sihir: bytes) -> Iterator[Tuple[float, int, int, bytes]]:
    if sihir in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        bo = ">"
    else:
        bo = "<"
    nano = sihir in (b"\xa1\xb2\x3c\x4d", b"\x4d\x3c\xb2\xa1")
    kalan_baslik = f.read(20)
    if len(kalan_baslik) < 20:
        raise PcapHatasi("pcap genel başlığı eksik")
    baglanti = struct.unpack(bo + "HHiIII", kalan_baslik)[5] & 0x0FFFFFFF
    bolen = 1e9 if nano else 1e6
    while True:
        b = f.read(16)
        if len(b) < 16:
            return
        sn, kesir, kayitli, gercek = struct.unpack(bo + "IIII", b)
        veri = f.read(kayitli)
        if len(veri) < kayitli:
            return  # yakalama yarıda kesilmiş; son eksik çerçeve sayılmaz
        yield sn + kesir / bolen, gercek, baglanti, veri


def _pcapng_cerceveleri(f) -> Iterator[Tuple[float, int, int, bytes]]:
    f.seek(0)
    bo = "<"
    arayuzler = []   # (bağlantı türü, zaman çözünürlüğü bölen)
    while True:
        b = f.read(8)
        if len(b) < 8:
            return
        tur = struct.unpack(bo + "I", b[:4])[0]
        if tur == 0x0A0D0D0A:  # Section Header Block: bayt sırası burada belirlenir
            sihir = f.read(4)
            bo = "<" if sihir == b"\x4d\x3c\x2b\x1a" else ">"
            uzunluk = struct.unpack(bo + "I", b[4:8])[0]
            f.seek(uzunluk - 12, 1)
            arayuzler = []
            continue
        uzunluk = struct.unpack(bo + "I", b[4:8])[0]
        if uzunluk < 12:
            raise PcapHatasi("pcapng blok uzunluğu geçersiz")
        govde = f.read(uzunluk - 8)
        if len(govde) < uzunluk - 8:
            return
        if tur == 1:  # Interface Description Block
            baglanti = struct.unpack_from(bo + "H", govde, 0)[0]
            bolen = 1e6
            konum = 8
            while konum + 4 <= len(govde) - 4:
                kod, olen = struct.unpack_from(bo + "HH", govde, konum)
                if kod == 0:
                    break
                if kod == 9 and olen >= 1:  # if_tsresol
                    r = govde[konum + 4]
                    bolen = float(2 ** (r & 0x7F)) if r & 0x80 else float(10 ** r)
                konum += 4 + ((olen + 3) // 4) * 4
            arayuzler.append((baglanti, bolen))
        elif tur == 6:  # Enhanced Packet Block
            ar, ust, alt, kayitli, gercek = struct.unpack_from(bo + "IIIII", govde, 0)
            baglanti, bolen = arayuzler[ar] if ar < len(arayuzler) else (_ETHERNET, 1e6)
            yield ((ust << 32) | alt) / bolen, gercek, baglanti, govde[20:20 + kayitli]
        elif tur == 3:  # Simple Packet Block
            gercek = struct.unpack_from(bo + "I", govde, 0)[0]
            baglanti = arayuzler[0][0] if arayuzler else _ETHERNET
            yield 0.0, gercek, baglanti, govde[4:4 + min(gercek, len(govde) - 8)]


def cerceveler(yol: Path) -> Iterator[Tuple[float, int, int, bytes]]:
    """(zaman, kablodaki_uzunluk, bağlantı_türü, yakalanan_veri) dörtlülerini verir."""
    with open(yol, "rb") as f:
        sihir = f.read(4)
        if sihir in (b"\xa1\xb2\xc3\xd4", b"\xd4\xc3\xb2\xa1",
                     b"\xa1\xb2\x3c\x4d", b"\x4d\x3c\xb2\xa1"):
            yield from _pcap_cerceveleri(f, sihir)
        elif sihir == b"\x0a\x0d\x0d\x0a":
            yield from _pcapng_cerceveleri(f)
        else:
            raise PcapHatasi(f"{yol} pcap veya pcapng dosyası değil")


def bayt_say(yol: Path, bas: Optional[float] = None,
             bit: Optional[float] = None) -> Dict[str, object]:
    """Yakalamadaki çerçeve sayısını ve toplam baytı döndürür.

    bas/bit verilirse yalnızca o zaman aralığındaki çerçeveler sayılır.
    """
    sonuc: Dict[str, object] = {"cerceve": 0, "bayt": 0, "ilk": None, "son": None,
                                "protokole_gore_bayt": {}}
    protokol: Dict[str, int] = {}
    for zaman, gercek, baglanti, veri in cerceveler(Path(yol)):
        if bas is not None and zaman < bas:
            continue
        if bit is not None and zaman > bit:
            continue
        sonuc["cerceve"] = int(sonuc["cerceve"]) + 1
        sonuc["bayt"] = int(sonuc["bayt"]) + gercek
        p = l4_protokolu(baglanti, veri)
        protokol[p] = protokol.get(p, 0) + gercek
        if sonuc["ilk"] is None:
            sonuc["ilk"] = zaman
        sonuc["son"] = zaman
    sonuc["protokole_gore_bayt"] = protokol
    return sonuc


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("Kullanım: python analiz/pcap_okuyucu.py DOSYA.pcap [DOSYA2.pcap ...]")
        return 2
    for yol in argv:
        s = bayt_say(Path(yol))
        print(f"{yol}: {s['cerceve']} çerçeve, {s['bayt']} bayt, "
              f"protokole göre {s['protokole_gore_bayt']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
