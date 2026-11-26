"""Rapor ve sunum grafikleri (pandas + matplotlib).

Üretilen grafikler (varsa ilgili deneyin verisinden):
    deney1_teslim_orani.png   gecikmeye karşı teslim oranı, TCP ve DTN; TCP eşiği işaretli
    deney1_gecikme.png        gecikmeye karşı uçtan uca gecikme (medyan, %95'lik değer)
    deney2_teslim_ve_gecikme.png  pencere süresine karşı teslim oranı ve DTN gecikmesi
    ek_yuk.png                protokol ek yükü (hatta yakalanan bayt / asıl veri)

Görsel kurallar: TCP ve DTN hem renkle hem çizgi/işaret biçimiyle ayrılır (siyah-beyaz
baskıda ve renk körlüğünde de okunur). Tek eksen, ince işaretler, sönük ızgara.
Sentetik veya yerel deneme verisi kullanıldığında grafiğe açık bir uyarı yazılır.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

YUZEY = "#fcfcfb"
METIN = "#0b0b0b"
IKINCIL = "#52514e"
IZGARA = "#e6e5e0"
BANT = "#efeeea"
STIL = {
    "tcp": {"renk": "#2a78d6", "cizgi": "--", "isaret": "o", "ad": "TCP"},
    "dtn": {"renk": "#eb6834", "cizgi": "-", "isaret": "s", "ad": "DTN (µD3TN)"},
}
MODLAR = ["tcp", "dtn"]


def _tema() -> None:
    plt.rcParams.update({
        "figure.facecolor": YUZEY, "axes.facecolor": YUZEY, "savefig.facecolor": YUZEY,
        "axes.edgecolor": IZGARA, "axes.labelcolor": METIN, "axes.titlecolor": METIN,
        "xtick.color": IKINCIL, "ytick.color": IKINCIL, "text.color": METIN,
        "axes.grid": True, "grid.color": IZGARA, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False,
        "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "legend.frameon": False,
        "figure.dpi": 100, "savefig.dpi": 200,
    })


def _uyari_metni(df: pd.DataFrame) -> Optional[str]:
    if "sentetik" in df and df["sentetik"].astype(str).str.lower().isin(["true", "1"]).any():
        return "SENTETİK VERİ – GERÇEK ÖLÇÜM DEĞİL"
    if "ortam" in df and df["ortam"].astype(str).str.contains("yerel").any():
        return "YEREL DENEME – GERÇEK ÖLÇÜM DEĞİL"
    return None


def _uyari_ekle(fig, metin: Optional[str]) -> None:
    if metin:
        fig.text(0.5, 0.5, metin, ha="center", va="center", rotation=20,
                 fontsize=26, color="#c9c7c0", alpha=0.55, weight="bold", zorder=0)


def _kaydet(fig, yol: Path) -> Path:
    yol.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(yol, bbox_inches="tight")
    plt.close(fig)
    return yol


def _saniye_bicimi(x, _pos) -> str:
    return f"{x:g}"


def _seri(g: pd.DataFrame, mod: str, x: str) -> pd.DataFrame:
    return g[g["mod"] == mod].sort_values(x)


def esik_bul(g1_gruplari: pd.DataFrame, mod: str, oran: float = 0.5):
    """`mod`un ortalama teslim oranının ilk kez `oran`ın altına düştüğü aralık."""
    t = _seri(g1_gruplari, mod, "g1_s").dropna(subset=["teslim_orani_ort"])
    onceki = None
    for _, satir in t.iterrows():
        if satir["teslim_orani_ort"] < oran:
            return (onceki, float(satir["g1_s"]))
        onceki = float(satir["g1_s"])
    return None


def tcp_esigi(g1_gruplari: pd.DataFrame, oran: float = 0.5):
    """TCP'nin ortalama teslim oranının ilk kez `oran`ın altına düştüğü aralık."""
    return esik_bul(g1_gruplari, "tcp", oran)


def _dogrudan_etiket(ax, xs, ys, mod: str, dy: float = 0.0) -> None:
    if len(xs) == 0:
        return
    ax.annotate(STIL[mod]["ad"], (xs[-1], ys[-1]), xytext=(8, dy), textcoords="offset points",
                va="center", fontsize=9, color=METIN)


def deney1_teslim(g: pd.DataFrame, yol: Path, uyari: Optional[str]) -> Optional[Path]:
    if g.empty:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    _uyari_ekle(fig, uyari)
    esik = esik_bul(g, "tcp")
    dtn_esik = esik_bul(g, "dtn")
    ayni_esik = esik is not None and dtn_esik == esik
    if esik and esik[0] is not None:
        ax.axvspan(esik[0], esik[1], color=BANT, zorder=0)
        ax.text(esik[0] * 0.9, 55, ("Her iki protokolün\neşiği bu aralıkta"
                                    if ayni_esik else "TCP eşiği\nbu aralıkta"),
                ha="right", va="center", fontsize=8.5, color=IKINCIL)
    for mod in MODLAR:
        s = _seri(g, mod, "g1_s").dropna(subset=["teslim_orani_ort"])
        if s.empty:
            continue
        x = s["g1_s"].astype(float).to_numpy()
        y = 100 * s["teslim_orani_ort"].astype(float).to_numpy()
        alt = y - 100 * s["teslim_orani_min"].astype(float).to_numpy()
        ust = 100 * s["teslim_orani_max"].astype(float).to_numpy() - y
        st = STIL[mod]
        ax.errorbar(x, y, yerr=[alt, ust], color=st["renk"], linestyle=st["cizgi"],
                    marker=st["isaret"], markersize=6, linewidth=1.8, capsize=3,
                    elinewidth=1, label=st["ad"], zorder=4 if mod == "tcp" else 3)
        _dogrudan_etiket(ax, x, y, mod, dy=8 if mod == "dtn" else -8)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(_saniye_bicimi))
    ax.set_ylim(-4, 108)
    ax.set_xlabel("Dünya–uydu tek yön gecikmesi (s, ölçekli, log eksen)")
    ax.set_ylabel("Teslim oranı (%)")
    kim = "TCP ve DTN'nin teslim oranı" if ayni_esik else "TCP'nin teslim oranı"
    if esik and esik[0] is not None:
        baslik = f"{kim} {esik[0]:g}–{esik[1]:g} s arasında %50'nin altına düşüyor"
    elif esik:
        baslik = f"{kim} en düşük gecikmede bile %50'nin altında"
    else:
        baslik = "TCP denenen tüm gecikmelerde %50'nin üzerinde teslim ediyor"
    ax.set_title(baslik)
    n = int(g["n"].max())
    # İki protokol aynı değerleri verdiğinde eğriler tam üst üste biner ve alttaki
    # görünmez; bunu altyazıda söylemezsek "DTN nerede?" diye okunur.
    ortusme = (" Aynı gecikmede iki protokol de aynı sonucu verdiği yerlerde eğriler "
               "üst üste biner; DTN eğrisi TCP'nin altındadır." if ayni_esik else "")
    fig.text(0.0, -0.16 if ortusme else -0.04,
             f"Deney 1: linkler sürekli açık. Noktalar {n} tekrarın ortalaması, "
             f"dikey çubuklar en küçük–en büyük değer.{ortusme}",
             fontsize=8.5, color=IKINCIL, wrap=True)
    ax.legend(loc="lower left")
    return _kaydet(fig, yol)


def deney1_gecikme(g: pd.DataFrame, yol: Path, uyari: Optional[str]) -> Optional[Path]:
    g = g.dropna(subset=["gecikme_medyan_s"])
    if g.empty:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    _uyari_ekle(fig, uyari)
    for mod in MODLAR:
        s = _seri(g, mod, "g1_s")
        if s.empty:
            continue
        x = s["g1_s"].astype(float).to_numpy()
        y = s["gecikme_medyan_s"].astype(float).to_numpy()
        p95 = s["gecikme_p95_s"].astype(float).to_numpy()
        st = STIL[mod]
        ax.errorbar(x, y, yerr=[[0] * len(y), p95 - y], color=st["renk"],
                    linestyle=st["cizgi"], marker=st["isaret"], markersize=6, linewidth=1.8,
                    capsize=3, elinewidth=1, label=st["ad"], zorder=4 if mod == "tcp" else 3)
        _dogrudan_etiket(ax, x, y, mod, dy=-8 if mod == "tcp" else 8)
    sinir = g["g1_s"].astype(float)
    ax.plot([sinir.min(), sinir.max()],
            [sinir.min() + float(g["g2_s"].iloc[0]), sinir.max() + float(g["g2_s"].iloc[0])],
            color=IKINCIL, linewidth=1, linestyle=":", zorder=1)
    orta = math.sqrt(sinir.min() * sinir.max())
    ax.annotate("yalnızca yayılım gecikmesi (g1 + g2)", (orta, orta + float(g["g2_s"].iloc[0])),
                xytext=(10, -14), textcoords="offset points", fontsize=8, color=IKINCIL)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(_saniye_bicimi))
    ax.yaxis.set_major_formatter(FuncFormatter(_saniye_bicimi))
    ax.set_xlabel("Dünya–uydu tek yön gecikmesi (s, ölçekli, log eksen)")
    ax.set_ylabel("Uçtan uca gecikme (s, log eksen)")
    ax.set_title("Teslim edilen mesajların uçtan uca gecikmesi")
    fig.text(0.0, -0.04, "Deney 1. Noktalar tekrarların medyan gecikmesi, çubuklar %95'lik "
             "değere kadar. Yalnızca teslim edilen mesajlar.", fontsize=8.5, color=IKINCIL)
    ax.legend(loc="upper left")
    return _kaydet(fig, yol)


def deney2(g: pd.DataFrame, yol: Path, uyari: Optional[str]) -> Optional[Path]:
    if g.empty:
        return None
    pencereler = sorted(g["pencere_s"].dropna().astype(float).unique())
    fig, (sol, sag) = plt.subplots(1, 2, figsize=(9.6, 4.0))
    _uyari_ekle(fig, uyari)
    genislik = 0.36
    for i, mod in enumerate(MODLAR):
        s = _seri(g, mod, "pencere_s")
        if s.empty:
            continue
        st = STIL[mod]
        konum = [pencereler.index(float(p)) + (i - 0.5) * (genislik + 0.02)
                 for p in s["pencere_s"]]
        degerler = 100 * s["teslim_orani_ort"].astype(float)
        enaz = 100 * s["teslim_orani_min"].astype(float).to_numpy()
        encok = 100 * s["teslim_orani_max"].astype(float).to_numpy()
        cubuklar = sol.bar(konum, degerler, width=genislik, color=st["renk"],
                           label=st["ad"], hatch=None if mod == "dtn" else "///",
                           edgecolor=YUZEY, linewidth=0.8, zorder=3)
        # Tekrarlar dağıldığında (ör. 10 s pencerede 3x %100, 2x %38) yalnızca ortalama
        # gösterilirse sonuç tek tepeliymiş gibi okunur. En küçük-en büyük çubuğu ve
        # etiketteki aralık bunu görünür kılar.
        y = degerler.to_numpy()
        sol.errorbar(konum, y, yerr=[y - enaz, encok - y], fmt="none", ecolor=METIN,
                     capsize=3, elinewidth=1, zorder=4)
        for c, v, a, b in zip(cubuklar, y, enaz, encok):
            etiket = f"%{v:.0f}" if a == b else f"%{v:.0f}\n(%{a:.0f}–%{b:.0f})"
            sol.text(c.get_x() + c.get_width() / 2, max(v, b) + 3, etiket, ha="center",
                     va="bottom", fontsize=8.5, color=METIN, linespacing=1.3)
    sol.set_xticks(range(len(pencereler)))
    sol.set_xticklabels([f"{p:g} s" for p in pencereler])
    sol.set_ylim(0, 158)  # iki satırlık aralık etiketi ile açıklama kutusu çakışmasın
    sol.set_yticks(range(0, 101, 20))
    sol.set_xlabel("Pencere süresi")
    sol.set_ylabel("Teslim oranı (%)")
    sol.set_title("Teslim oranı")
    sol.grid(axis="x", visible=False)
    sol.legend(loc="upper left", ncols=2)

    d = _seri(g, "dtn", "pencere_s").dropna(subset=["gecikme_medyan_s"])
    if not d.empty:
        x = d["pencere_s"].astype(float).to_numpy()
        y = d["gecikme_medyan_s"].astype(float).to_numpy()
        p95 = d["gecikme_p95_s"].astype(float).to_numpy()
        sag.errorbar(x, y, yerr=[[0] * len(y), p95 - y], color=STIL["dtn"]["renk"],
                     marker="s", markersize=6, linewidth=1.8, capsize=3, elinewidth=1,
                     zorder=3)
        for xi, yi in zip(x, y):
            sag.annotate(f"{yi:.1f} s", (xi, yi), xytext=(8, -2), textcoords="offset points",
                         fontsize=8.5, color=METIN)
        sag.set_xticks(x)
        sag.set_xticklabels([f"{v:g} s" for v in x])
        sag.set_ylim(0, max(p95.max(), y.max()) * 1.2)
    sag.set_xlabel("Pencere süresi")
    sag.set_ylabel("Uçtan uca gecikme (s)")
    sag.set_title("DTN gecikmesi (medyan, %95'lik değere kadar)")

    tcp = _seri(g, "tcp", "pencere_s")
    dtn = _seri(g, "dtn", "pencere_s")
    if not tcp.empty and not dtn.empty:
        # Başlık koşu başına en küçük-en büyük değerden kurulur: ortalamayla kurulursa
        # dağılan tekrarlar (10 s pencere) gizlenir.
        t_encok = 100 * float(tcp["teslim_orani_max"].max())
        d_enaz = 100 * float(dtn["teslim_orani_min"].min())
        d_encok = 100 * float(dtn["teslim_orani_max"].max())
        tcp_kismi = ("TCP hiçbir mesajı teslim edemiyor" if t_encok == 0
                     else f"TCP en fazla %{t_encok:.0f} teslim ediyor")
        dtn_kismi = (f"DTN %{d_enaz:.0f}" if d_enaz == d_encok
                     else f"DTN koşu başına %{d_enaz:.0f}–%{d_encok:.0f}")
        fig.suptitle(f"Uçtan uca yol hiç açılmadığında {tcp_kismi}, {dtn_kismi} teslim ediyor",
                     x=0.01, ha="left", fontsize=12, weight="bold", y=1.03)
    fig.text(0.01, -0.05, "Deney 2: Dünya–uydu ve uydu–araç pencereleri hiç örtüşmüyor. "
             "Çubuklar tekrarların ortalaması, dikey çizgiler en küçük–en büyük koşu; "
             "gecikme tekrarların medyanı.", fontsize=8.5, color=IKINCIL)
    fig.tight_layout()
    return _kaydet(fig, yol)


def ek_yuk(g: pd.DataFrame, yol: Path, uyari: Optional[str]) -> Optional[Path]:
    g = g.dropna(subset=["ek_yuk_orani_ort"])
    g = g[g["deney"] == "deney1"]
    # Hiçbir mesajın teslim edilemediği noktalarda ek yük oranı anlamsızdır: payda
    # gönderilen asıl veridir (DTN'de yerel düğümün kabul ettiği bundle'lar), ama hatta
    # neredeyse hiç bayt geçmemiştir. Oran 1'in çok altına düşer ve çizilirse "yüksek
    # gecikmede ek yük azalıyor" diye okunur. Bu noktalar çizilmez, altyazıda belirtilir.
    teslimsiz = g[g["teslim_orani_ort"].fillna(0) <= 0] if "teslim_orani_ort" in g else g.iloc[:0]
    g = g.drop(index=teslimsiz.index)
    if g.empty:
        return None
    atlanan = sorted({float(v) for v in teslimsiz["g1_s"].dropna()})
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    _uyari_ekle(fig, uyari)
    for mod in MODLAR:
        s = _seri(g, mod, "g1_s")
        if s.empty:
            continue
        x = s["g1_s"].astype(float).to_numpy()
        y = s["ek_yuk_orani_ort"].astype(float).to_numpy()
        e = s["ek_yuk_orani_std"].fillna(0).astype(float).to_numpy()
        st = STIL[mod]
        ax.errorbar(x, y, yerr=e, color=st["renk"], linestyle=st["cizgi"],
                    marker=st["isaret"], markersize=6, linewidth=1.8, capsize=3,
                    elinewidth=1, label=st["ad"], zorder=3)
        _dogrudan_etiket(ax, x, y, mod, dy=8 if mod == "tcp" else -8)
    ax.axhline(1.0, color=IKINCIL, linewidth=1, linestyle=":")
    # x eksen koordinatında (0 = sol kenar), y veri koordinatında. get_xlim() log ölçekten
    # önce okunursa negatif olabiliyor; o zaman etiket çok uzağa düşüp resmi devleştiriyordu.
    ax.text(0.01, 1.0, " yalnızca asıl veri = 1", fontsize=8, color=IKINCIL,
            va="bottom", transform=ax.get_yaxis_transform())
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(_saniye_bicimi))
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Dünya–uydu tek yön gecikmesi (s, ölçekli, log eksen)")
    ax.set_ylabel("Ek yük oranı (hat baytı / asıl veri baytı)")
    ax.set_title("Protokol ek yükü")
    if atlanan:
        liste = ", ".join(f"{v:g}" for v in atlanan)
        not_metni = (f" Teslim oranı %0 olan noktalar (g1 = {liste} s) gösterilmez: orada "
                     "oran düşüktür çünkü hatta neredeyse hiç bayt geçmemiştir, ek yük "
                     "azaldığı için değil.")
    else:
        not_metni = " Hiç veri gönderilemeyen koşularda oran tanımsızdır ve gösterilmez."
    fig.text(0.0, -0.16 if atlanan else -0.04,
             "Deney 1. Hat baytı aktarıcıda tcpdump ile, iki linkteki tüm "
             f"çerçeveler.{not_metni}", fontsize=8.5, color=IKINCIL, wrap=True)
    ax.legend(loc="upper left")
    return _kaydet(fig, yol)


def hepsini_ciz(gruplar: List[Dict], cikti: Path) -> List[Path]:
    """Grup özetlerinden tüm grafikleri çizer, üretilen dosyaların listesini döndürür."""
    _tema()
    df = pd.DataFrame(gruplar)
    if df.empty:
        return []
    for sutun in ("g1_s", "g2_s", "pencere_s", "teslim_orani_ort", "teslim_orani_min",
                  "teslim_orani_max", "gecikme_medyan_s", "gecikme_p95_s",
                  "ek_yuk_orani_ort", "ek_yuk_orani_std", "n"):
        if sutun in df:
            df[sutun] = pd.to_numeric(df[sutun], errors="coerce")
    uyari = _uyari_metni(df)
    cikti = Path(cikti)
    uretilen = [
        deney1_teslim(df[df["deney"] == "deney1"], cikti / "deney1_teslim_orani.png", uyari),
        deney1_gecikme(df[df["deney"] == "deney1"], cikti / "deney1_gecikme.png", uyari),
        deney2(df[df["deney"] == "deney2"], cikti / "deney2_teslim_ve_gecikme.png", uyari),
        ek_yuk(df, cikti / "ek_yuk.png", uyari),
    ]
    return [y for y in uretilen if y is not None]
