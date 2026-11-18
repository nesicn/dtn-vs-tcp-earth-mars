"""Koşu klasörlerinden metrikleri hesaplar (yalnızca standart kütüphane).

Tanımlar (raporda da aynen kullanılır):
    teslim_orani   = benzersiz olarak teslim edilen mesaj / planlanan mesaj
                     Payda planlanan adettir: hiç gönderilemeyen mesajlar da sayılır.
    uctan_uca_gecikme = alıcıdaki alma zamanı - göndericideki gönderme zamanı
                     Her mesajın yalnızca ilk kopyası kullanılır. Koşu başına medyan,
                     %95'lik değer, ortalama, en küçük ve en büyük raporlanır.
    ek_yuk_orani   = hatta yakalanan toplam bayt / uygulamanın gönderdiği asıl veri baytı
                     (hocanın tanımı). Asıl veri = gönderilen mesaj sayısı x mesaj boyutu.
    teslim_basina_hat_bayti = hatta yakalanan toplam bayt / teslim edilen asıl veri baytı
                     Hiç teslim yoksa tanımsızdır.

Bir koşu klasörü şunları içerir:
    kosu.json            koşturucunun yazdığı parametreler ve durum
    gonderici.csv/.json  gönderici günlüğü ve özeti
    alici.csv/.json      alıcı günlüğü ve özeti
    hat.pcap             (varsa) aktarıcıda yakalanan trafik
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

try:  # paket olarak veya betik olarak çalışabilsin
    from analiz import pcap_okuyucu
except ImportError:  # pragma: no cover
    import pcap_okuyucu  # type: ignore

KOSU_SUTUNLARI = [
    "deney", "kosu_id", "mod", "nokta", "tekrar", "g1_s", "g2_s", "pencere_s",
    "bosluk_s", "sure_s", "planlanan", "gonderilen", "teslim", "teslim_orani",
    "kopya", "yabanci", "gecikme_medyan_s", "gecikme_p95_s", "gecikme_ort_s",
    "gecikme_min_s", "gecikme_max_s", "baglanti_kurma_s", "hat_bayt",
    "asil_veri_bayt", "ek_yuk_orani", "teslim_basina_hat_bayti",
    "gonderici_cikis", "alici_cikis", "durum", "ortam", "sentetik",
]

GRUP_SUTUNLARI = [
    "deney", "mod", "nokta", "g1_s", "g2_s", "pencere_s", "n",
    "teslim_orani_ort", "teslim_orani_std", "teslim_orani_min", "teslim_orani_max",
    "gecikme_medyan_s", "gecikme_p95_s", "ek_yuk_orani_ort", "ek_yuk_orani_std",
    "baglanti_kurma_s_ort", "ortam", "sentetik",
]


def yuzdelik(degerler: Sequence[float], oran: float) -> Optional[float]:
    """Doğrusal ara değerli yüzdelik (numpy.percentile varsayılanıyla aynı)."""
    if not degerler:
        return None
    s = sorted(degerler)
    if len(s) == 1:
        return s[0]
    konum = (len(s) - 1) * oran
    alt = math.floor(konum)
    ust = min(alt + 1, len(s) - 1)
    return s[alt] + (s[ust] - s[alt]) * (konum - alt)


def _json_oku(yol: Path) -> Dict[str, object]:
    if not yol.exists():
        return {}
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def _csv_oku(yol: Path) -> List[Dict[str, str]]:
    if not yol.exists():
        return []
    with open(yol, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _sayi(deger) -> Optional[float]:
    if deger in (None, ""):
        return None
    try:
        return float(deger)
    except (TypeError, ValueError):
        return None


def kosu_hesapla(dizin: Path) -> Dict[str, object]:
    """Tek bir koşunun metriklerini hesaplar."""
    dizin = Path(dizin)
    kosu = _json_oku(dizin / "kosu.json")
    parametre = kosu.get("parametreler", {}) if isinstance(kosu.get("parametreler"), dict) else {}
    g_ozet = _json_oku(dizin / "gonderici_ozet.json")
    a_ozet = _json_oku(dizin / "alici_ozet.json")
    g_satir = _csv_oku(dizin / "gonderici.csv")
    a_satir = _csv_oku(dizin / "alici.csv")

    planlanan = int(parametre.get("adet") or g_ozet.get("planlanan_adet")
                    or len(g_satir) or 0)
    boyut = int(parametre.get("boyut") or g_ozet.get("boyut_byte") or 0)
    gonderilen = sum(1 for r in g_satir if r.get("durum") == "gonderildi")

    ilk_gecikme: Dict[int, float] = {}
    toplam_alinan = 0
    for r in a_satir:
        try:
            no = int(r["mesaj_no"])
        except (KeyError, ValueError):
            continue
        if planlanan and not 0 <= no < planlanan:
            continue
        g, a = _sayi(r.get("gonderme_zamani")), _sayi(r.get("alma_zamani"))
        if g is None or a is None:
            continue
        toplam_alinan += 1
        if no not in ilk_gecikme:
            ilk_gecikme[no] = a - g
    teslim = len(ilk_gecikme)
    gecikmeler = list(ilk_gecikme.values())

    hat_bayt: Optional[int] = None
    pcap = dizin / "hat.pcap"
    if pcap.exists() and pcap.stat().st_size > 24:
        try:
            hat_bayt = int(pcap_okuyucu.bayt_say(pcap)["bayt"])
        except pcap_okuyucu.PcapHatasi:
            hat_bayt = None
    elif "hat_bayt" in kosu:            # sentetik veri gibi önceden hesaplanmış değer
        hat_bayt = kosu.get("hat_bayt")  # type: ignore[assignment]

    asil = gonderilen * boyut
    teslim_asil = teslim * boyut

    def oran(pay, payda):
        return (pay / payda) if (pay is not None and payda) else None

    return {
        "deney": kosu.get("deney", ""),
        "kosu_id": kosu.get("kosu_id", dizin.name),
        "mod": kosu.get("mod", g_ozet.get("mod", "")),
        "nokta": kosu.get("nokta", ""),
        "tekrar": kosu.get("tekrar", ""),
        "g1_s": parametre.get("g1"), "g2_s": parametre.get("g2"),
        "pencere_s": parametre.get("pencere"), "bosluk_s": parametre.get("bosluk"),
        "sure_s": parametre.get("sure"),
        "planlanan": planlanan, "gonderilen": gonderilen, "teslim": teslim,
        "teslim_orani": oran(teslim, planlanan),
        "kopya": toplam_alinan - teslim,
        "yabanci": a_ozet.get("yabanci", 0),
        "gecikme_medyan_s": statistics.median(gecikmeler) if gecikmeler else None,
        "gecikme_p95_s": yuzdelik(gecikmeler, 0.95),
        "gecikme_ort_s": statistics.fmean(gecikmeler) if gecikmeler else None,
        "gecikme_min_s": min(gecikmeler) if gecikmeler else None,
        "gecikme_max_s": max(gecikmeler) if gecikmeler else None,
        "baglanti_kurma_s": g_ozet.get("baglanti_kurma_suresi_s"),
        "hat_bayt": hat_bayt, "asil_veri_bayt": asil,
        "ek_yuk_orani": oran(hat_bayt, asil),
        "teslim_basina_hat_bayti": oran(hat_bayt, teslim_asil),
        "gonderici_cikis": g_ozet.get("cikis_nedeni"),
        "alici_cikis": a_ozet.get("cikis_nedeni"),
        "durum": kosu.get("durum", ""),
        "ortam": kosu.get("ortam", ""),
        "sentetik": bool(kosu.get("sentetik", False)),
    }


def kosu_dizinleri(kok: Path) -> List[Path]:
    """kok altındaki tüm koşu klasörleri (içinde kosu.json olanlar)."""
    return sorted(p.parent for p in Path(kok).rglob("kosu.json"))


def tum_kosular(kok: Path, sadece_tamamlanan: bool = True) -> List[Dict[str, object]]:
    sonuc = []
    for d in kosu_dizinleri(kok):
        k = kosu_hesapla(d)
        if sadece_tamamlanan and k["durum"] != "tamamlandi":
            continue
        sonuc.append(k)
    return sonuc


def _ort_std(degerler: Iterable[Optional[float]]):
    v = [x for x in degerler if x is not None]
    if not v:
        return None, None
    return statistics.fmean(v), (statistics.stdev(v) if len(v) > 1 else 0.0)


def grupla(kosular: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    """Tekrarları birleştirir: her (deney, mod, nokta) için bir satır."""
    gruplar: Dict[tuple, List[Dict[str, object]]] = {}
    for k in kosular:
        gruplar.setdefault((k["deney"], k["mod"], k["nokta"]), []).append(k)
    satirlar = []
    for (deney, mod, nokta), ks in sorted(gruplar.items(), key=lambda x: (
            str(x[0][0]), str(x[0][1]), _sayi(x[1][0]["g1_s"]) or 0,
            _sayi(x[1][0]["pencere_s"]) or 0)):
        to_ort, to_std = _ort_std(k["teslim_orani"] for k in ks)
        ey_ort, ey_std = _ort_std(k["ek_yuk_orani"] for k in ks)
        bk_ort, _ = _ort_std(k["baglanti_kurma_s"] for k in ks)
        # Gecikme: tüm tekrarlardaki mesajlar tek dağılım değil, koşu medyanlarının medyanı.
        medyanlar = [k["gecikme_medyan_s"] for k in ks if k["gecikme_medyan_s"] is not None]
        p95ler = [k["gecikme_p95_s"] for k in ks if k["gecikme_p95_s"] is not None]
        oranlar = [k["teslim_orani"] for k in ks if k["teslim_orani"] is not None]
        satirlar.append({
            "deney": deney, "mod": mod, "nokta": nokta,
            "g1_s": ks[0]["g1_s"], "g2_s": ks[0]["g2_s"], "pencere_s": ks[0]["pencere_s"],
            "n": len(ks),
            "teslim_orani_ort": to_ort, "teslim_orani_std": to_std,
            "teslim_orani_min": min(oranlar) if oranlar else None,
            "teslim_orani_max": max(oranlar) if oranlar else None,
            "gecikme_medyan_s": statistics.median(medyanlar) if medyanlar else None,
            "gecikme_p95_s": statistics.median(p95ler) if p95ler else None,
            "ek_yuk_orani_ort": ey_ort, "ek_yuk_orani_std": ey_std,
            "baglanti_kurma_s_ort": bk_ort,
            "ortam": ",".join(sorted({str(k["ortam"]) for k in ks if k["ortam"]})),
            "sentetik": any(k["sentetik"] for k in ks),
        })
    return satirlar


def csv_yaz(yol: Path, satirlar: Sequence[Dict[str, object]], sutunlar: Sequence[str]) -> None:
    Path(yol).parent.mkdir(parents=True, exist_ok=True)
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sutunlar), extrasaction="ignore")
        w.writeheader()
        for s in satirlar:
            w.writerow({k: ("" if s.get(k) is None else s.get(k)) for k in sutunlar})
