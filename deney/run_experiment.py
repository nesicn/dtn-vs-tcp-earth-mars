"""Deney koşturucu: bir deney matrisini baştan sona otomatik koşturur.

Her koşu için sırasıyla:
    1. Koşu klasörünü açar, parametreleri kosu.json'a yazar.
    2. Deney 2'de iletişim takvimini (takvim.csv) üretir ve ortak başlangıç anını
       (t0) belirler.
    3. Ortam kancalarını çalıştırır: gecikme ayarı, takvim betikleri vb.
       (Elif'in ve Azra'nın betikleri ortam dosyasından çağrılır.)
    4. Varsa trafik yakalamayı (tcpdump) başlatır.
    5. Alıcıyı başlatır, hazır olmasını bekler; t0 anında göndericiyi başlatır.
    6. Süre dolunca veya iş bitince her şeyi durdurur, ortamı temizler.
    7. Metrikleri hesaplar ve kosu.json'a ekler.
Tüm koşular bitince sonuclar/<deney>/kosular.csv ve gruplar.csv yazılır.

Yarıda kalan bir matris yeniden başlatıldığında tamamlanmış koşular atlanır.

Kullanım:
    # Kendi bilgisayarında, Docker olmadan, tüm akışı kısa bir matrisle dene:
    python deney/run_experiment.py --ortam deney/ortam_yerel.json \\
        --matris deney/matrisler/deneme.json

    # Docker ortamında Deney 1:
    python3 deney/run_experiment.py --ortam deney/ortam_docker.json \\
        --matris deney/matrisler/deney1.json

    # Ne çalıştırılacağını görmek için (hiçbir şey çalıştırmaz):
    python deney/run_experiment.py --ortam ... --matris ... --kuru
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from analiz import metrikler  # noqa: E402
from deney import takvim as takvim_modulu  # noqa: E402
from trafik import ortak  # noqa: E402

BETIK = "kosturucu"
HAZIR_ZAMAN_ASIMI_S = 30.0
ALICI_EK_SURE_S = 10.0       # alıcı göndericiden biraz geç başlar, biraz geç bitsin
DURDURMA_PAYI_S = 20.0       # süre dolduktan sonra düzgün kapanma için tanınan pay


# ---------------------------------------------------------------------------
# Yapılandırma
# ---------------------------------------------------------------------------

def json_yukle(yol: Path) -> Dict:
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def _etiket(sablon: str, nokta: Dict) -> str:
    ham = sablon.format(**nokta)
    return re.sub(r"[^a-z0-9_]", "", ham.replace(".", "p").lower())


def sure_hesapla(nokta: Dict, kural: Dict) -> float:
    """Koşu süresini matristeki kurala göre hesaplar."""
    if "sabit" in kural:
        return float(kural["sabit"])
    sure = float(kural.get("ek", 0))
    sure += float(kural.get("gecikme_carpani", 0)) * (nokta["g1"] + nokta["g2"])
    if "periyot_carpani" in kural:
        periyot = 2 * (nokta["pencere"] + nokta["bosluk"])
        sure += float(kural["periyot_carpani"]) * periyot
    return max(float(kural.get("en_az", 0)), sure)


def kosulari_uret(matris: Dict, tekrar: Optional[int] = None) -> List[Dict]:
    """Matristen sıralı koşu listesi üretir.

    Sıra: tekrar -> nokta -> mod. Böylece aynı noktanın tekrarları zamana yayılır,
    TCP ve DTN koşuları birbirine yakın zamanda (benzer koşullarda) yapılır.
    """
    deney = matris["deney"]
    kisa = matris.get("kisa_ad", deney)
    varsayilan = matris.get("varsayilan", {})
    tekrar_sayisi = tekrar or int(matris.get("tekrar", 1))
    kosular = []
    for t in range(1, tekrar_sayisi + 1):
        for ham_nokta in matris["noktalar"]:
            nokta = dict(varsayilan)
            nokta.update(ham_nokta)
            etiket = _etiket(matris.get("nokta_etiketi", "n"), nokta)
            for mod in matris["modlar"]:
                if mod not in ("tcp", "dtn"):
                    raise ValueError(f"Bilinmeyen mod: {mod}")
                parametre = dict(nokta)
                parametre.update(matris.get("mesaj", {}))
                parametre["sure"] = sure_hesapla(nokta, matris["sure"])
                kosular.append({
                    "deney": deney, "mod": mod, "nokta": etiket, "tekrar": t,
                    "kosu_id": f"{kisa}_{mod}_{etiket}_t{t}",
                    "takvimli": "pencere" in nokta,
                    "parametreler": parametre,
                })
    return kosular


# ---------------------------------------------------------------------------
# Süreç yönetimi
# ---------------------------------------------------------------------------

class Surec:
    """Bir alt süreci başlatır, çıktısını günlüğe yazar, HAZIR işaretini yakalar."""

    def __init__(self, ad: str, komut: List[str], gunluk: Optional[Path]) -> None:
        self.ad = ad
        self.komut = komut
        self.hazir = threading.Event()
        ortam = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        self._gunluk = open(gunluk, "a", encoding="utf-8") if gunluk else None
        self.p = subprocess.Popen(komut, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL, env=ortam)
        self._okuyucu = threading.Thread(target=self._oku, daemon=True)
        self._okuyucu.start()

    def _oku(self) -> None:
        assert self.p.stdout is not None
        for ham in self.p.stdout:
            satir = ham.decode("utf-8", errors="replace").rstrip()
            if satir.startswith("HAZIR"):
                self.hazir.set()
            if self._gunluk:
                self._gunluk.write(satir + "\n")
                self._gunluk.flush()

    def bekle(self, zaman_asimi: Optional[float]) -> Optional[int]:
        try:
            return self.p.wait(timeout=zaman_asimi)
        except subprocess.TimeoutExpired:
            return None

    def calisiyor(self) -> bool:
        return self.p.poll() is None

    def durdur(self, kibar_bekleme: float = 5.0) -> None:
        if self.calisiyor():
            self.p.terminate()
            if self.bekle(kibar_bekleme) is None:
                self.p.kill()
                self.bekle(5.0)
        self._okuyucu.join(timeout=2.0)
        if self._gunluk:
            self._gunluk.close()
            self._gunluk = None


def _komut_bol(metin: str) -> List[str]:
    return shlex.split(metin, posix=(os.name != "nt"))


class Kosturucu:
    def __init__(self, ortam: Dict, sonuc_kok: Path, kuru: bool = False) -> None:
        self.ortam = ortam
        self.sonuc_kok = sonuc_kok
        self.kuru = kuru
        self.python = ortam.get("python") or sys.executable
        self.proje_kok = ortam.get("proje_kok") or str(KOK)

    # -- yardımcılar ---------------------------------------------------------

    def _dugum_yolu(self, host_yolu: Path) -> str:
        """Host'taki bir yolu düğümün (konteynerin) gördüğü yola çevirir."""
        if not self.ortam.get("proje_kok"):
            return str(Path(host_yolu).resolve())
        try:
            goreli = Path(host_yolu).resolve().relative_to(KOK)
        except ValueError:
            raise RuntimeError(
                f"{host_yolu} proje klasörünün dışında; konteynerler yalnızca proje "
                "klasörünü görür. --sonuclar için proje içinde bir klasör verin.") from None
        return self.proje_kok.rstrip("/") + "/" + goreli.as_posix()

    def _dugum_komutu(self, dugum: str, betik: str, argumanlar: List[str]) -> List[str]:
        onek = list(self.ortam["dugumler"][dugum].get("komut_oneki", []))
        betik_yolu = (self.proje_kok.rstrip("/") + "/" + betik if self.ortam.get("proje_kok")
                      else str(KOK / betik))
        return onek + [self.python, betik_yolu] + [str(a) for a in argumanlar]

    @staticmethod
    def _aap2_erisimi(dtn: Dict, dugum: str) -> List[str]:
        """Seçilen düğümün AAP2 taşıma türünü komut satırı argümanına çevirir.

        Yerel UNIX soketi tercih edilir; TCP de eski ortam dosyalarıyla geriye
        dönük uyumluluk için desteklenir. Bir düğüm için ikisini birden
        tanımlamak belirsiz olduğundan hata verir.
        """
        soket = dtn.get(f"{dugum}_aap2_soket")
        tcp = dtn.get(f"{dugum}_aap2")
        if soket and tcp:
            raise ValueError(
                f"dtn.{dugum} için AAP2 soketi veya TCP adresinden yalnızca biri tanımlanmalı")
        if soket:
            return ["--aap2-soket", str(soket)]
        if tcp:
            return ["--aap2-tcp", str(tcp)]
        raise ValueError(f"dtn.{dugum}_aap2_soket veya dtn.{dugum}_aap2 tanımlanmalı")

    def _degiskenler(self, kosu: Dict, dizin: Path, t0: float,
                     takvim_yolu: Optional[Path]) -> Dict[str, object]:
        p = kosu["parametreler"]
        d: Dict[str, object] = {
            "python": self.python, "kok": str(KOK), "proje_kok": self.proje_kok,
            "kosu_dizini": str(dizin), "kosu_dizini_dugum": self._dugum_yolu(dizin),
            "deney_id": kosu["kosu_id"], "mod": kosu["mod"], "t0": f"{t0:.3f}",
            "g1": p.get("g1", 0), "g2": p.get("g2", 0),
            "g1_ms": int(round(float(p.get("g1", 0)) * 1000)),
            "g2_ms": int(round(float(p.get("g2", 0)) * 1000)),
            "pencere": p.get("pencere", ""), "bosluk": p.get("bosluk", ""),
            "sure": p["sure"], "arayuz": self.ortam.get("arayuzler", {}),
            "takvim": str(takvim_yolu) if takvim_yolu else "",
            "takvim_dugum": self._dugum_yolu(takvim_yolu) if takvim_yolu else "",
        }
        d.update(self.ortam.get("degiskenler", {}))
        return d

    def _kancalar(self, ad: str, kosu: Dict) -> List[Dict]:
        """Ortam dosyasındaki bir kanca listesini, koşunun moduna göre süzer."""
        sonuc = []
        for k in self.ortam.get("kancalar", {}).get(ad, []):
            if isinstance(k, (str, list)):
                k = {"komut": k}
            if k.get("devre_disi"):
                continue
            if "modlar" in k and kosu["mod"] not in k["modlar"]:
                continue
            if "takvimli" in k and bool(k["takvimli"]) != kosu["takvimli"]:
                continue
            sonuc.append(k)
        return sonuc

    def _bicimle(self, sablon, degiskenler: Dict) -> List[str]:
        """Kanca komutundaki {değişken}leri doldurur.

        Komut bir liste olarak verilirse her öğe ayrı doldurulur ve bölünmez; boşluk
        içeren Windows yolları için bu biçim güvenlidir. Metin olarak verilirse
        doldurulduktan sonra kabuk kurallarıyla parçalara ayrılır.
        """
        try:
            if isinstance(sablon, list):
                return [str(parca).format(**degiskenler) for parca in sablon]
            return _komut_bol(str(sablon).format(**degiskenler))
        except KeyError as hata:
            raise ValueError(f"Kancadaki bilinmeyen değişken {hata}: {sablon}") from None

    def _calistir_on_planda(self, komut: List[str], gunluk: Path, zaman_asimi: float) -> None:
        if self.kuru:
            print("    [kanca]", " ".join(komut))
            return
        with open(gunluk, "a", encoding="utf-8") as f:
            f.write("$ " + " ".join(komut) + "\n")
            f.flush()
            sonuc = subprocess.run(komut, stdout=f, stderr=subprocess.STDOUT,
                                   timeout=zaman_asimi, stdin=subprocess.DEVNULL)
        if sonuc.returncode != 0:
            raise RuntimeError(f"Kanca başarısız (çıkış {sonuc.returncode}): {' '.join(komut)}")

    def _dugum_surecini_durdur(self, dugum: str, kosu_id: str, surec: Optional[Surec]) -> None:
        onek = self.ortam["dugumler"][dugum].get("komut_oneki", [])
        if onek and surec is not None and surec.calisiyor():
            # docker exec istemcisini öldürmek konteynerdeki süreci durdurmaz;
            # süreci konteynerin içinde SIGTERM ile kapat.
            # Desen "-" ile başlamasın (pkill onu seçenek sanar); "( |$)" ile t1, t10'u yakalamaz.
            subprocess.run(list(onek) + ["pkill", "-TERM", "-f", f"deney-id {kosu_id}( |$)"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL, timeout=15)
            surec.bekle(5.0)
        if surec is not None:
            surec.durdur()

    # -- tek koşu -------------------------------------------------------------

    def kosu_calistir(self, kosu: Dict) -> Dict:
        p = kosu["parametreler"]
        dizin = self.sonuc_kok / kosu["deney"] / kosu["kosu_id"]
        kosu_kaydi = dict(kosu)
        kosu_kaydi.update({"ortam": self.ortam.get("ad", ""), "durum": "basladi",
                           "baslangic": ortak.simdi(), "git": _git_surumu(),
                           "uyarilar": []})
        tcp = self.ortam.get("tcp", {})
        dtn = self.ortam.get("dtn", {})
        baslama_payi = float(self.ortam.get("baslama_payi_s", 5.0))

        if self.kuru:
            print(f"\n== {kosu['kosu_id']} (süre {p['sure']:g} s)")
        else:
            if dizin.exists():
                for eski in dizin.iterdir():
                    if eski.is_file():
                        eski.unlink()
            dizin.mkdir(parents=True, exist_ok=True)
            ortak.json_yaz(dizin / "kosu.json", kosu_kaydi)
        gunluk = dizin / "kosturucu.log"

        takvim_yolu: Optional[Path] = None
        if kosu["takvimli"]:
            satirlar = takvim_modulu.takvim_uret(
                float(p["pencere"]), float(p["bosluk"]), float(p["g1"]), float(p["g2"]),
                int(p.get("periyot_sayisi", 3)))
            takvim_modulu.takvim_dogrula(satirlar)
            takvim_yolu = dizin / "takvim.csv"
            if not self.kuru:
                takvim_modulu.takvim_yaz(takvim_yolu, satirlar)

        t0 = ortak.simdi() + baslama_payi
        degisken = self._degiskenler(kosu, dizin, t0, takvim_yolu)
        kosu_kaydi["t0"] = t0

        arka_plan: List[Surec] = []
        alici: Optional[Surec] = None
        gonderici: Optional[Surec] = None
        yakalama = self.ortam.get("yakalama")
        yakalama_basladi = False
        dizin_dugum = self._dugum_yolu(dizin)

        try:
            for k in self._kancalar("kosu_oncesi", kosu):
                self._calistir_on_planda(self._bicimle(k["komut"], degisken), gunluk,
                                         float(k.get("zaman_asimi_s", 120)))

            for k in self._kancalar("arka_plan", kosu):
                komut = self._bicimle(k["komut"], degisken)
                if self.kuru:
                    print("    [arka plan]", " ".join(komut))
                    continue
                arka_plan.append(Surec(k.get("ad", "arka_plan"), komut, gunluk))
                time.sleep(float(k.get("bekle_s", 1.0)))
                if not arka_plan[-1].calisiyor():
                    raise RuntimeError(f"Arka plan süreci hemen kapandı: {' '.join(komut)}")

            if yakalama and kosu["mod"] in yakalama.get("modlar", ["tcp", "dtn"]):
                self._calistir_on_planda(self._bicimle(yakalama["baslat"], degisken),
                                         gunluk, 30)
                yakalama_basladi = True
                if not self.kuru:
                    time.sleep(float(yakalama.get("bekle_s", 1.0)))

            ortak_arg = ["--deney-id", kosu["kosu_id"], "--adet", p["adet"]]
            if kosu["mod"] == "tcp":
                alici_komut = self._dugum_komutu("arac", "trafik/tcp_alici.py", ortak_arg + [
                    "--port", tcp.get("port", 5000),
                    "--sure", p["sure"] + ALICI_EK_SURE_S, "--cikti", dizin_dugum])
                gonderici_komut = self._dugum_komutu(
                    "dunya", "trafik/tcp_gonderici.py", ortak_arg + [
                        "--hedef", tcp["alici_host"], "--port", tcp.get("port", 5000),
                        "--boyut", p["boyut"], "--aralik", p["aralik"],
                        "--sure", p["sure"], "--cikti", dizin_dugum]
                    + [str(a) for a in tcp.get("gonderici_ek_argumanlar", [])])
            else:
                alici_komut = self._dugum_komutu("arac", "trafik/dtn_alici.py", ortak_arg + [
                    *self._aap2_erisimi(dtn, "arac"),
                    "--ajan-id", dtn.get("ajan_id", "sink"),
                    "--sure", p["sure"] + ALICI_EK_SURE_S, "--cikti", dizin_dugum])
                gonderici_komut = self._dugum_komutu(
                    "dunya", "trafik/dtn_gonderici.py", ortak_arg + [
                        *self._aap2_erisimi(dtn, "dunya"),
                        "--hedef-eid", dtn["hedef_eid"],
                        "--boyut", p["boyut"], "--aralik", p["aralik"],
                        "--sure", p["sure"], "--cikti", dizin_dugum])

            if self.kuru:
                print("    [alıcı]    ", " ".join(alici_komut))
                print("    [gönderici]", " ".join(gonderici_komut))
                return kosu_kaydi

            alici = Surec("alici", alici_komut, dizin / "alici.log")
            if not alici.hazir.wait(HAZIR_ZAMAN_ASIMI_S):
                raise RuntimeError("Alıcı hazır olmadı (alici.log dosyasına bakın)")

            bekle = t0 - ortak.simdi()
            if bekle > 0:
                time.sleep(bekle)
            elif kosu["takvimli"]:
                kosu_kaydi["uyarilar"].append(
                    f"Gönderici t0'dan {-bekle:.1f} s geç başladı; baslama_payi_s'i artırın")

            gonderici = Surec("gonderici", gonderici_komut, dizin / "gonderici.log")
            gonderici.bekle(p["sure"] + DURDURMA_PAYI_S)
            self._dugum_surecini_durdur("dunya", kosu["kosu_id"], gonderici)

            # Hiçbir mesaj ağa çıkamadıysa (örn. TCP bağlantısı kurulamadı) alıcı
            # boşuna beklemesin: gelebilecek bir şey yok.
            g_ozet = metrikler._json_oku(dizin / "gonderici_ozet.json")
            if g_ozet and int(g_ozet.get("gonderilen", 0)) == 0:
                kosu_kaydi["uyarilar"].append("Hiç mesaj gönderilemedi, alıcı erken durduruldu")
            else:
                kalan = (t0 + p["sure"] + ALICI_EK_SURE_S + DURDURMA_PAYI_S) - ortak.simdi()
                alici.bekle(max(1.0, kalan))
            self._dugum_surecini_durdur("arac", kosu["kosu_id"], alici)
            kosu_kaydi["durum"] = "tamamlandi"
        except Exception as hata:
            kosu_kaydi["durum"] = "hata"
            kosu_kaydi["hata"] = f"{type(hata).__name__}: {hata}"
            ortak.bilgi(BETIK, f"{kosu['kosu_id']} HATA: {kosu_kaydi['hata']}")
        finally:
            if not self.kuru:
                for s, dugum in ((gonderici, "dunya"), (alici, "arac")):
                    if s is not None and s.calisiyor():
                        self._dugum_surecini_durdur(dugum, kosu["kosu_id"], s)
                for s in arka_plan:
                    s.durdur()
                if yakalama_basladi:
                    try:
                        self._calistir_on_planda(self._bicimle(yakalama["durdur"], degisken),
                                                 gunluk, 30)
                        time.sleep(float(yakalama.get("bekle_s", 1.0)))  # dosya kapansın
                    except Exception as hata:  # temizlik hatası koşuyu bozmasın
                        kosu_kaydi["uyarilar"].append(f"Yakalama durdurulamadı: {hata}")
                for k in self._kancalar("kosu_sonrasi", kosu):
                    try:
                        self._calistir_on_planda(self._bicimle(k["komut"], degisken), gunluk,
                                                 float(k.get("zaman_asimi_s", 60)))
                    except Exception as hata:
                        kosu_kaydi["uyarilar"].append(f"Temizlik kancası başarısız: {hata}")
                kosu_kaydi["bitis"] = ortak.simdi()
                ortak.json_yaz(dizin / "kosu.json", kosu_kaydi)
                if kosu_kaydi["durum"] == "tamamlandi":
                    kosu_kaydi["ozet"] = metrikler.kosu_hesapla(dizin)
                    ortak.json_yaz(dizin / "kosu.json", kosu_kaydi)
        return kosu_kaydi

    # -- matris ---------------------------------------------------------------

    def matris_calistir(self, kosular: List[Dict], yeniden: bool, dur_hatada: bool) -> None:
        toplam_sure = sum(k["parametreler"]["sure"] for k in kosular)
        ortak.bilgi(BETIK, f"{len(kosular)} koşu, en fazla ~{toplam_sure / 3600:.1f} saat "
                           f"(gerçekte çoğu koşu süresinden önce biter)")
        for i, kosu in enumerate(kosular, 1):
            kayit = self.sonuc_kok / kosu["deney"] / kosu["kosu_id"] / "kosu.json"
            if not yeniden and not self.kuru and kayit.exists():
                if metrikler._json_oku(kayit).get("durum") == "tamamlandi":
                    ortak.bilgi(BETIK, f"[{i}/{len(kosular)}] {kosu['kosu_id']} zaten var, atlandı")
                    continue
            if not self.kuru:
                ortak.bilgi(BETIK, f"[{i}/{len(kosular)}] {kosu['kosu_id']} başlıyor "
                                   f"(en fazla {kosu['parametreler']['sure']:g} s)")
            sonuc = self.kosu_calistir(kosu)
            if self.kuru:
                continue
            ozet = sonuc.get("ozet") or {}
            oran = ozet.get("teslim_orani")
            medyan = ozet.get("gecikme_medyan_s")
            ortak.bilgi(BETIK, f"[{i}/{len(kosular)}] {kosu['kosu_id']}: {sonuc['durum']}, "
                               f"teslim {'-' if oran is None else f'%{100 * oran:.0f}'}, "
                               f"medyan gecikme {'-' if medyan is None else f'{medyan:.2f} s'}")
            if sonuc["durum"] != "tamamlandi" and dur_hatada:
                ortak.bilgi(BETIK, "--dur-hatada verildiği için duruluyor")
                break
        if not self.kuru:
            deneyler = sorted({k["deney"] for k in kosular})
            for deney in deneyler:
                tum = metrikler.tum_kosular(self.sonuc_kok / deney)
                metrikler.csv_yaz(self.sonuc_kok / deney / "kosular.csv", tum,
                                  metrikler.KOSU_SUTUNLARI)
                metrikler.csv_yaz(self.sonuc_kok / deney / "gruplar.csv",
                                  metrikler.grupla(tum), metrikler.GRUP_SUTUNLARI)
                ortak.bilgi(BETIK, f"{deney}: {len(tum)} tamamlanmış koşu, özetler "
                                   f"{self.sonuc_kok / deney} altında")


def _git_surumu() -> Optional[str]:
    try:
        sonuc = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=KOK,
                               capture_output=True, text=True, timeout=5)
        return sonuc.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Deney matrisini koşturur.")
    p.add_argument("--ortam", type=Path, required=True,
                   help="ortam dosyası (deney/ortam_yerel.json veya ortam_docker.json)")
    p.add_argument("--matris", type=Path, required=True, help="deney matrisi (JSON)")
    p.add_argument("--sonuclar", type=Path, default=KOK / "sonuclar",
                   help="sonuç kök klasörü (varsayılan: sonuclar/)")
    p.add_argument("--mod", choices=["tcp", "dtn"], help="yalnızca bu modu koştur")
    p.add_argument("--tekrar", type=int, help="matristeki tekrar sayısını geçersiz kıl")
    p.add_argument("--kosu", help="yalnızca bu koşu kimliğini koştur")
    p.add_argument("--en-fazla", type=int, help="en fazla bu kadar koşu yap")
    p.add_argument("--yeniden", action="store_true", help="tamamlanmış koşuları da yeniden yap")
    p.add_argument("--dur-hatada", action="store_true", help="ilk hatalı koşuda dur")
    p.add_argument("--kuru", action="store_true",
                   help="hiçbir şey çalıştırmadan komutları yazdır")
    a = p.parse_args(argv)

    ortam = json_yukle(a.ortam)
    matris = json_yukle(a.matris)
    kosular = kosulari_uret(matris, a.tekrar)
    if a.mod:
        kosular = [k for k in kosular if k["mod"] == a.mod]
    if a.kosu:
        kosular = [k for k in kosular if k["kosu_id"] == a.kosu]
        if not kosular:
            sys.exit(f"Matriste {a.kosu} kimlikli koşu yok")
    if a.en_fazla:
        kosular = kosular[:a.en_fazla]

    kosturucu = Kosturucu(ortam, a.sonuclar.resolve(), kuru=a.kuru)
    try:
        kosturucu.matris_calistir(kosular, a.yeniden, a.dur_hatada)
    except KeyboardInterrupt:
        ortak.bilgi(BETIK, "Ctrl+C: durduruldu. Yeniden başlatınca tamamlanan koşular atlanır.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
