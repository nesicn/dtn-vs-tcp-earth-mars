# Deney sonuçlarının özeti

`analiz/analiz.py` çıktıları. Ham koşular (`sonuclar/`) `.gitignore`'da; burada yalnızca özetler var.

- **Deney 1:** 80 koşu, 25.11.2026 17:42 – 23:37 (Elif'in Mac'i, Colima)
- **Deney 2:** 30 koşu, 25.11.2026 23:37 – 26.11.2026 01:12 (aynı makine)
- **Kod sürümü:** her koşu `git: f59902a`
- Uykuyla çakışan koşular geçersiz sayılıp yeniden koşuldu (Mac uyurken saat ilerliyor, paketler ilerlemiyor).
  Ayrıntılar: `docs/bulgular.md`.

| Dosya | İçerik |
| --- | --- |
| `gruplar.csv` | Nokta başına (5 tekrar) teslim oranı ort/std/min/max, medyan ve %95'lik gecikme, ek yük |
| `kosular.csv` | Koşu başına aynı metrikler |
| `deney1_teslim_orani.png`, `deney1_gecikme.png` | Deney 1 |
| `deney2_teslim_ve_gecikme.png` | Deney 2 |
| `ek_yuk.png` | Deney 1 protokol ek yükü |

**Okurken dikkat:**
- Deney 2'de 10 s pencerede DTN teslimi ortalama %75 görünür, ama dağılım iki tepelidir:
  3 koşu %100, 2 koşu %38 (`docs/bulgular.md`, Bulgu 1).
- Ek yük oranının g1 ≥ 40 s'de 1'in altına düşmesi ek yükün azaldığı anlamına gelmez; o koşularda
  veri linki büyük ölçüde hiç geçemedi.
