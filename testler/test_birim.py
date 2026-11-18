"""Birim testleri: mesaj biçimi, çerçeveleme, takvim, pcap okuma, metrikler.

Çalıştırma (proje kökünde):
    python -m unittest discover -s testler -v
"""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from analiz import metrikler, pcap_okuyucu  # noqa: E402
from deney import takvim  # noqa: E402
from deney.run_experiment import kosulari_uret, sure_hesapla  # noqa: E402
from trafik import ortak  # noqa: E402


class MesajBicimiTesti(unittest.TestCase):
    def test_gidis_donus(self):
        b = ortak.kosu_belirteci("d1_tcp_g10_t1")
        veri = ortak.mesaj_olustur("tcp", b, 7, 50, 1024, gonderme_zamani_ns=123456789)
        self.assertEqual(len(veri), 1024)
        m = ortak.mesaj_coz(veri)
        self.assertEqual((m.mod, m.kosu_belirteci, m.mesaj_no, m.toplam, m.boyut),
                         ("tcp", b, 7, 50, 1024))
        self.assertAlmostEqual(m.gonderme_zamani, 0.123456789)

    def test_bozuk_mesajlar_reddedilir(self):
        veri = bytearray(ortak.mesaj_olustur("dtn", 1, 0, 1, 256))
        with self.assertRaises(ortak.MesajHatasi):
            ortak.mesaj_coz(b"XXXX" + bytes(veri[4:]))
        veri[-1] ^= 0xFF
        with self.assertRaises(ortak.MesajHatasi):
            ortak.mesaj_coz(bytes(veri))
        with self.assertRaises(ortak.MesajHatasi):
            ortak.mesaj_coz(b"kisa")

    def test_gecersiz_parametre(self):
        with self.assertRaises(ValueError):
            ortak.mesaj_olustur("udp", 1, 0, 1, 1024)
        with self.assertRaises(ValueError):
            ortak.mesaj_olustur("tcp", 1, 5, 5, 1024)
        with self.assertRaises(ValueError):
            ortak.mesaj_olustur("tcp", 1, 0, 1, 10)

    def test_farkli_kosularin_belirteci_farkli(self):
        self.assertNotEqual(ortak.kosu_belirteci("a"), ortak.kosu_belirteci("b"))
        self.assertEqual(ortak.kosu_belirteci("a"), ortak.kosu_belirteci("a"))


class CerceveTesti(unittest.TestCase):
    def test_parcali_ve_birlesik_akis(self):
        mesajlar = [ortak.mesaj_olustur("tcp", 9, i, 3, 100 + i) for i in range(3)]
        akis = b"".join(ortak.cerceve_ekle(m) for m in mesajlar)
        c = ortak.CerceveCozucu()
        cikan = []
        for i in range(0, len(akis), 7):     # 7 baytlık parçalarla besle
            cikan.extend(c.ekle(akis[i:i + 7]))
        self.assertEqual(cikan, mesajlar)
        self.assertEqual(c.bekleyen_bayt, 0)

    def test_bozuk_uzunluk(self):
        c = ortak.CerceveCozucu()
        with self.assertRaises(ortak.MesajHatasi):
            list(c.ekle(struct.pack("!I", 3) + b"abc"))


class TakvimTesti(unittest.TestCase):
    def test_ornek_takvim(self):
        s = takvim.takvim_uret(20, 10, 1, 0.05, 2)
        self.assertEqual([(r["link"], r["baslangic_s"], r["bitis_s"]) for r in s], [
            ("link1", 0, 20), ("link2", 30, 50), ("link1", 60, 80), ("link2", 90, 110)])
        takvim.takvim_dogrula(s)

    def test_bosluk_gecikmeden_kisa_olamaz(self):
        with self.assertRaises(ValueError):
            takvim.takvim_uret(20, 5, 5, 0.05, 1)

    def test_ortusme_yakalanir(self):
        with self.assertRaises(ValueError):
            takvim.takvim_dogrula([
                {"link": "link1", "baslangic_s": 0, "bitis_s": 20, "gecikme_s": 1},
                {"link": "link2", "baslangic_s": 15, "bitis_s": 30, "gecikme_s": 1}])


class MatrisTesti(unittest.TestCase):
    def test_matris_dosyalari(self):
        for ad, beklenen in (("deney1", 8 * 2 * 5), ("deney2", 3 * 2 * 5)):
            m = json.loads((KOK / "deney" / "matrisler" / f"{ad}.json").read_text("utf-8"))
            kosular = kosulari_uret(m)
            self.assertEqual(len(kosular), beklenen)
            self.assertEqual(len({k["kosu_id"] for k in kosular}), beklenen)
            for k in kosular:
                self.assertRegex(k["kosu_id"], r"^[a-z0-9_]+$")

    def test_sure_kurallari(self):
        self.assertEqual(sure_hesapla({"g1": 160, "g2": 0.05},
                                      {"en_az": 90, "gecikme_carpani": 4, "ek": 60}), 700.2)
        self.assertEqual(sure_hesapla({"g1": 0.1, "g2": 0.05},
                                      {"en_az": 90, "gecikme_carpani": 4, "ek": 60}), 90)
        self.assertEqual(sure_hesapla({"g1": 1, "g2": 0.05, "pencere": 10, "bosluk": 10},
                                      {"periyot_carpani": 2, "ek": 15}), 95)


def _ethernet_tcp(yuk: int) -> bytes:
    eth = b"\x00" * 12 + b"\x08\x00"
    ip = bytes([0x45, 0]) + struct.pack("!H", 20 + 20 + yuk) + b"\x00" * 5 + bytes([6]) \
        + b"\x00" * 10
    return eth + ip + b"\x00" * 20 + b"\x00" * yuk


class PcapTesti(unittest.TestCase):
    def _pcap_yaz(self, yol: Path, cerceveler, baglanti=1, sihir=0xA1B2C3D4) -> None:
        with open(yol, "wb") as f:
            f.write(struct.pack("<IHHiIII", sihir, 2, 4, 0, 0, 65535, baglanti))
            for i, c in enumerate(cerceveler):
                kayit = c[:64]                       # kesilmiş yakalama (snaplen)
                f.write(struct.pack("<IIII", 100 + i, 0, len(kayit), len(c)))
                f.write(kayit)

    def test_pcap_kablodaki_uzunluk_toplanir(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "a.pcap"
            cerceveler = [_ethernet_tcp(1028), _ethernet_tcp(0), b"\x00" * 60]
            self._pcap_yaz(yol, cerceveler)
            s = pcap_okuyucu.bayt_say(yol)
            self.assertEqual(s["cerceve"], 3)
            self.assertEqual(s["bayt"], sum(len(c) for c in cerceveler))
            self.assertEqual(s["protokole_gore_bayt"]["tcp"],
                             len(cerceveler[0]) + len(cerceveler[1]))
            self.assertEqual(pcap_okuyucu.bayt_say(yol, bas=101)["cerceve"], 2)

    def test_linux_cooked_any(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "sll.pcap"
            ip_tcp = _ethernet_tcp(10)[14:]
            sll = b"\x00" * 14 + b"\x08\x00" + ip_tcp
            self._pcap_yaz(yol, [sll], baglanti=113)
            self.assertEqual(pcap_okuyucu.bayt_say(yol)["protokole_gore_bayt"],
                             {"tcp": len(sll)})

    def test_pcapng(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "a.pcapng"
            cerceve = _ethernet_tcp(100)
            shb = struct.pack("<IIIHHq", 0x0A0D0D0A, 28, 0x1A2B3C4D, 1, 0, -1) \
                + struct.pack("<I", 28)
            idb = struct.pack("<IIHHI", 1, 20, 1, 0, 65535) + struct.pack("<I", 20)
            dolgu = (-len(cerceve)) % 4
            epb_govde = struct.pack("<IIIII", 0, 0, 1000000, len(cerceve), len(cerceve)) \
                + cerceve + b"\x00" * dolgu
            epb_uzunluk = 8 + len(epb_govde) + 4
            epb = struct.pack("<II", 6, epb_uzunluk) + epb_govde \
                + struct.pack("<I", epb_uzunluk)
            yol.write_bytes(shb + idb + epb)
            s = pcap_okuyucu.bayt_say(yol)
            self.assertEqual((s["cerceve"], s["bayt"]), (1, len(cerceve)))
            self.assertAlmostEqual(s["ilk"], 1.0)

    def test_gecersiz_dosya(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "x.pcap"
            yol.write_bytes(b"bu bir pcap degil")
            with self.assertRaises(pcap_okuyucu.PcapHatasi):
                pcap_okuyucu.bayt_say(yol)


class MetrikTesti(unittest.TestCase):
    def test_yuzdelik_numpy_ile_ayni(self):
        v = [1.0, 2.0, 3.0, 4.0, 10.0]
        self.assertAlmostEqual(metrikler.yuzdelik(v, 0.95), 8.8)
        self.assertAlmostEqual(metrikler.yuzdelik(v, 0.5), 3.0)
        self.assertIsNone(metrikler.yuzdelik([], 0.5))

    def test_kosu_metrikleri(self):
        with tempfile.TemporaryDirectory() as d:
            dizin = Path(d) / "d1_tcp_g1_t1"
            ortak.json_yaz(dizin / "kosu.json", {
                "deney": "deney1", "kosu_id": dizin.name, "mod": "tcp", "nokta": "g1",
                "tekrar": 1, "durum": "tamamlandi", "ortam": "test",
                "parametreler": {"adet": 4, "boyut": 1000, "g1": 1, "g2": 0.05}})
            with ortak.CsvGunluk(dizin / "gonderici.csv", ortak.GONDERICI_SUTUNLARI) as g:
                for i in range(4):
                    g.yaz({"deney_id": dizin.name, "mod": "tcp", "mesaj_no": i,
                           "gonderme_zamani": "" if i == 3 else f"{100 + i}",
                           "boyut_byte": 1000,
                           "durum": "gonderilemedi" if i == 3 else "gonderildi"})
            with ortak.CsvGunluk(dizin / "alici.csv", ortak.ALICI_SUTUNLARI) as a:
                for i, gecikme in ((0, 1.0), (1, 2.0), (1, 9.0), (2, 3.0)):  # 1 kopya
                    a.yaz({"deney_id": dizin.name, "mod": "tcp", "mesaj_no": i,
                           "gonderme_zamani": f"{100 + i}",
                           "alma_zamani": f"{100 + i + gecikme}", "boyut_byte": 1000})
            k = metrikler.kosu_hesapla(dizin)
            self.assertEqual((k["planlanan"], k["gonderilen"], k["teslim"], k["kopya"]),
                             (4, 3, 3, 1))
            self.assertAlmostEqual(k["teslim_orani"], 0.75)
            self.assertAlmostEqual(k["gecikme_medyan_s"], 2.0)   # kopyanın 9 s'si sayılmaz
            self.assertIsNone(k["ek_yuk_orani"])                 # pcap yok

            g = metrikler.grupla([k, dict(k, teslim_orani=0.25, kosu_id="x")])
            self.assertEqual(len(g), 1)
            self.assertAlmostEqual(g[0]["teslim_orani_ort"], 0.5)
            self.assertEqual((g[0]["teslim_orani_min"], g[0]["teslim_orani_max"]), (0.25, 0.75))


if __name__ == "__main__":
    unittest.main()
