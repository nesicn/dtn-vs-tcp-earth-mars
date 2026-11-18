"""Uçtan uca testler: betikler gerçek alt süreçler olarak, yerel ağda çalıştırılır.

    * TCP gönderici ve alıcı localhost üzerinde.
    * DTN gönderici ve alıcı, uD3TN'in AAP 2.0 arayüzünü taklit eden
      testler/sahte_ud3tn.py üzerinden (gerçek ud3tn-utils istemcisiyle).
    * TCP alıcı yokken gönderici "bağlantı kurulamadı" ile düzgün kapanır.
    * Koşturucu, yerel ortamda küçük bir matrisi koşturup analiz tablosunu üretir.

Çalıştırma (proje kökünde):
    python -m unittest discover -s testler -v
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from analiz import metrikler  # noqa: E402

import importlib.util  # noqa: E402

UD3TN_VAR = importlib.util.find_spec("ud3tn_utils") is not None


def bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def calistir(*argumanlar, bekle=True, **kw):
    komut = [sys.executable] + [str(a) for a in argumanlar]
    if bekle:
        return subprocess.run(komut, cwd=KOK, capture_output=True, text=True,
                              timeout=kw.get("zaman_asimi", 60))
    return subprocess.Popen(komut, cwd=KOK, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)


def hazir_bekle(surec: subprocess.Popen, zaman_asimi: float = 10.0) -> None:
    bitis = time.time() + zaman_asimi
    while time.time() < bitis:
        satir = surec.stdout.readline()
        if satir.startswith("HAZIR"):
            return
        if not satir and surec.poll() is not None:
            break
    raise AssertionError("süreç hazır olmadı")


class TcpUctanUcaTesti(unittest.TestCase):
    def test_elli_mesaj(self):
        with tempfile.TemporaryDirectory() as d:
            port = bos_port()
            alici = calistir("trafik/tcp_alici.py", "--deney-id", "t1", "--host", "127.0.0.1",
                             "--port", port, "--adet", 50, "--sure", 20, "--cikti", d,
                             bekle=False)
            hazir_bekle(alici)
            g = calistir("trafik/tcp_gonderici.py", "--deney-id", "t1", "--hedef", "127.0.0.1",
                         "--port", port, "--adet", 50, "--aralik", 0.005, "--sure", 20,
                         "--cikti", d)
            self.assertEqual(g.returncode, 0, g.stdout + g.stderr)
            alici.wait(timeout=10)
            alici.stdout.close()
            ao = json.loads((Path(d) / "alici_ozet.json").read_text("utf-8"))
            go = json.loads((Path(d) / "gonderici_ozet.json").read_text("utf-8"))
            self.assertEqual((ao["cikis_nedeni"], ao["alinan_benzersiz"], ao["kopya"]),
                             ("tamamlandi", 50, 0))
            self.assertEqual((go["cikis_nedeni"], go["gonderilen"]), ("alici_kapatti", 50))

    def test_baska_kosunun_mesajlari_sayilmaz(self):
        with tempfile.TemporaryDirectory() as d:
            port = bos_port()
            alici = calistir("trafik/tcp_alici.py", "--deney-id", "dogru", "--host",
                             "127.0.0.1", "--port", port, "--adet", 5, "--sure", 4,
                             "--cikti", d, bekle=False)
            hazir_bekle(alici)
            calistir("trafik/tcp_gonderici.py", "--deney-id", "yanlis", "--hedef", "127.0.0.1",
                     "--port", port, "--adet", 5, "--aralik", 0, "--sure", 6,
                     "--cikti", Path(d) / "g")
            alici.wait(timeout=10)
            alici.stdout.close()
            ao = json.loads((Path(d) / "alici_ozet.json").read_text("utf-8"))
            self.assertEqual((ao["alinan_benzersiz"], ao["yabanci"]), (0, 5))

    def test_alici_yoksa_baglanti_kurulamadi(self):
        with tempfile.TemporaryDirectory() as d:
            g = calistir("trafik/tcp_gonderici.py", "--deney-id", "t2", "--hedef", "127.0.0.1",
                         "--port", bos_port(), "--adet", 10, "--sure", 3, "--cikti", d)
            self.assertEqual(g.returncode, 0, g.stdout + g.stderr)
            go = json.loads((Path(d) / "gonderici_ozet.json").read_text("utf-8"))
            self.assertEqual((go["cikis_nedeni"], go["gonderilen"], go["gonderilemeyen"]),
                             ("baglanti_kurulamadi", 0, 10))
            satirlar = (Path(d) / "gonderici.csv").read_text("utf-8").strip().splitlines()
            self.assertEqual(len(satirlar), 11)    # başlık + 10 "gonderilemedi"


@unittest.skipUnless(UD3TN_VAR, "ud3tn-utils kurulu değil (pip install ud3tn-utils)")
class DtnUctanUcaTesti(unittest.TestCase):
    def test_sahte_ud3tn_uzerinden(self):
        from testler.sahte_ud3tn import SahteUd3tn
        sunucu = SahteUd3tn(gecikme=0.2).baslat()
        adres = f"127.0.0.1:{sunucu.adres[1]}"
        try:
            with tempfile.TemporaryDirectory() as d:
                alici = calistir("trafik/dtn_alici.py", "--deney-id", "x1", "--aap2-tcp",
                                 adres, "--ajan-id", "sink", "--adet", 30, "--sure", 20,
                                 "--cikti", d, bekle=False)
                hazir_bekle(alici)
                g = calistir("trafik/dtn_gonderici.py", "--deney-id", "x1", "--aap2-tcp",
                             adres, "--hedef-eid", "dtn://sahte.dtn/sink", "--adet", 30,
                             "--boyut", 4096, "--aralik", 0.01, "--sure", 20, "--cikti", d)
                self.assertEqual(g.returncode, 0, g.stdout + g.stderr)
                alici.wait(timeout=15)
                alici.stdout.close()
                ao = json.loads((Path(d) / "alici_ozet.json").read_text("utf-8"))
                go = json.loads((Path(d) / "gonderici_ozet.json").read_text("utf-8"))
                self.assertEqual(go["gonderilen"], 30)
                self.assertEqual((ao["cikis_nedeni"], ao["alinan_benzersiz"]),
                                 ("tamamlandi", 30))
        finally:
            sunucu.durdur()

    def test_ud3tn_yoksa_baglanti_hatasi(self):
        with tempfile.TemporaryDirectory() as d:
            calistir("trafik/dtn_gonderici.py", "--deney-id", "x2", "--aap2-tcp",
                         f"127.0.0.1:{bos_port()}", "--hedef-eid", "dtn://a.dtn/sink",
                         "--adet", 3, "--sure", 5, "--cikti", d)
            go = json.loads((Path(d) / "gonderici_ozet.json").read_text("utf-8"))
            self.assertEqual((go["cikis_nedeni"], go["gonderilemeyen"]),
                             ("baglanti_hatasi", 3))


class KosturucuTesti(unittest.TestCase):
    def test_yerel_matris_ve_kaldigi_yerden_devam(self):
        matris = {
            "deney": "test", "kisa_ad": "ts", "modlar": ["tcp", "dtn"] if UD3TN_VAR else ["tcp"],
            "tekrar": 1, "mesaj": {"adet": 10, "boyut": 512, "aralik": 0.01},
            "nokta_etiketi": "g{g1}", "varsayilan": {"g2": 0.05},
            "noktalar": [{"g1": 0.1}], "sure": {"sabit": 10},
        }
        with tempfile.TemporaryDirectory() as d:
            ortam = json.loads((KOK / "deney" / "ortam_yerel.json").read_text("utf-8"))
            ortam["tcp"]["port"] = bos_port()
            p = bos_port()
            ortam["dtn"]["dunya_aap2"] = ortam["dtn"]["arac_aap2"] = f"127.0.0.1:{p}"
            ortam["kancalar"]["arka_plan"][0]["komut"][3] = str(p)
            (Path(d) / "ortam.json").write_text(json.dumps(ortam), "utf-8")
            (Path(d) / "matris.json").write_text(json.dumps(matris), "utf-8")
            argumanlar = ["deney/run_experiment.py", "--ortam", Path(d) / "ortam.json",
                          "--matris", Path(d) / "matris.json", "--sonuclar", Path(d) / "s"]
            r = calistir(*argumanlar, zaman_asimi=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            kosular = metrikler.tum_kosular(Path(d) / "s" / "test")
            self.assertEqual(len(kosular), len(matris["modlar"]))
            for k in kosular:
                self.assertEqual(k["teslim_orani"], 1.0, k)
            self.assertTrue((Path(d) / "s" / "test" / "gruplar.csv").exists())
            r2 = calistir(*argumanlar, zaman_asimi=60)
            self.assertIn("atlandı", r2.stdout)


if __name__ == "__main__":
    unittest.main()
