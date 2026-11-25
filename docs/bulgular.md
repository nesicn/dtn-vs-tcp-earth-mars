# Bulgular ve deney düzeneğinde bulunan sorunlar

Final rapor ve sunum için ortak kaynak. Her bulgu ölçümle desteklenir; tek koşudan
çıkan sayılar "ön sonuç" olarak işaretlidir ve tam matris koşulduktan sonra
güncellenmelidir.

Ortam: üç düğümlü Docker topolojisi (`docker-compose.yml`), µD3TN v0.15.0, MTCP
bağlantı katmanı, macOS + Colima. Son güncelleme: 26.11.2026 (Elif), tam matris sonuçlarıyla.

---

## Bulgu 1 — Kısa pencerelerde µD3TN bundle kaybediyor (Deney 2, 10 s pencere)

**Özet:** Deney 2'de 10 s'lik pencerelerle DTN koşuları ya %100 ya da %38 teslim
ediyor; ara değer yok. 20 s pencerede her koşu %100. Kayıp bir kurulum hatası değil,
µD3TN'in MTCP katmanıyla birlikte davranışıdır.

### Ölçüm (g1 = 1 s, g2 = 0,05 s, pencere 10 s, boşluk 10 s)

| Koşu | Teslim | Not |
| --- | --- | --- |
| p10 t1 | 19/50 (%38) | |
| p10 t2 | 19/50 (%38) | |
| p10 t3 | 50/50 (%100) | konteynerler sıfırdan oluşturulmuştu |
| p10 t4 | 19/50 (%38) | |
| p10 t5 | 19/50 (%38) | |
| p10 t4 (tekrar) | 50/50 (%100) | konteynerler sıfırdan oluşturulmuştu |
| p10 t5 (tekrar) | 19/50 (%38) | konteynerler sıfırdan oluşturulmuştu |
| p20 t1 (3 makine/koşu) | 50/50 (%100) | medyan 27,77 / 27,99 / 28,20 s; Azra'nın Mac'inde 27,90 s |

Hiçbir koşuda kopya, hatalı veya yabancı mesaj yok. Kaybolan mesajlar her seferinde
aynı: 19 – 49 numaralı mesajlar (gönderim sırasında sonda kalanlar).

### Mekanizma (kanıt: µD3TN günlüğü `--log-level 4` ve aktarıcıdaki `hat.pcap`)

1. link1 penceresi açılınca dünya düğümü 50 bundle'ın hepsini MTCP'ye, yani TCP
   soketine yazıyor ve hemen kendi deposundan siliyor:
   ```
   TX: Sending bundle 0x... via CLA mtcp
   BundleProcessor: Discarding bundle 0x...
   ```
   µD3TN açısından bundle bu noktada iletilmiş sayılır.
2. MTCP'de bundle düzeyinde onay (ACK) yoktur. µD3TN bundle'ın karşıya ulaşıp
   ulaşmadığını bilmez.
3. g1 = 1 s'de (gidiş-dönüş 2 s) TCP bağlantısı kurulumu ve yavaş başlangıç pencerenin
   büyük kısmını harcar. Pencere kapanınca µD3TN bağlantıyı kapatır
   (`MTCP: Terminating contact link manager`); TCP tamponunda kalan bundle'lar kaybolur
   ve sonraki pencerelerde tekrar gönderilmez.
4. Sonucu belirleyen, verinin SYN'den kaç tur sonra akmaya başladığıdır:

   | Koşu | SYN (t0'a göre) | İlk veri | Pencerede geçen veri |
   | --- | --- | --- | --- |
   | %100 (t3) | 1,4 s | 3,4 s (1 tur sonra) | 56,6 KB ≈ 50 bundle |
   | %38 (t4) | 1,8 s | 5,8 s (2 tur sonra) | 20,3 KB ≈ 19 bundle |

   20 s pencerede bu 2 s'lik fark tolere edildiği için kayıp yok.

**Denenen ve elenen açıklama:** "Konteynerin `docker restart` ile yeniden başlatılması
bir durumu sıfırlamıyor" — elendi; sıfırdan oluşturulan konteynerlerde de %38 çıktı.

### Raporda nasıl yorumlanır

- DTN'nin depola-ilet garantisi, kullanılan bağlantı katmanının güvenilirliğine
  bağlıdır. µD3TN bundle'ı TCP'ye verdiği anda sorumluluğu bırakıyor (custody yok,
  MTCP'de onay yok); kısa ve yüksek gecikmeli pencerelerde bu varsayım bozuluyor.
- Yol haritasındaki karar: "µD3TN yüksek gecikmede TCP sınırlamasına takılırsa bu bir
  bulgudur, saklanmaz."
- Olası iyileştirme (denenmedi): bundle düzeyinde onayı olan TCPCLv3 katmanı
  (µD3TN destekliyor), daha uzun pencereler veya custody transfer.

### Deney 2 tam koşusu için karar (24.11.2026)

Matris değiştirilmeden koşulur. 10 s pencerenin 5 tekrarındaki %100 / %38 dağılımı
raporlanır; ortalamanın yanında dağılım da verilmelidir (iki tepeli sonuç ortalamayla
özetlenirse yanıltıcı olur).

### Tam matris sonucu (26.11.2026, `docs/sonuclar/`)

| Pencere | TCP (5 tekrar) | DTN (5 tekrar) |
| --- | --- | --- |
| 10 s | hepsi %0 | 3× %100 (medyan ~18 s), 2× %38 (~20 s); ortalama %75 |
| 20 s | hepsi %0 | hepsi %100, medyan 28,0–28,7 s |
| 30 s | hepsi %0 | hepsi %100, medyan 38,2–38,7 s |

Gecikmeler tasarımla uyumlu: mesajlar ilk 5 s'de gönderilir (ortalama ~2,5 s), link2
10 / 20 / 30 s pencerede sırasıyla 20 / 30 / 40 s'de açılır.

---

## Bulgu 2 — Linkler hep açıkken DTN'nin avantajı yok, TCP'den yavaş (Deney 1)

Tam matris, her nokta 5 tekrar, medyan gecikme (aralık):

| g1 | TCP | DTN |
| --- | --- | --- |
| 0,1 s | %100 · 0,15–0,16 s | %100 · 0,20 s |
| 1 s | %100 · 1,06–1,15 s | %100 · 2,22–2,32 s |
| 5 s | %100 · 13,1–13,4 s | %100 · 19,2–20,2 s |
| 10 s | %100 · 28,0–28,3 s | %100 · 44,3–44,9 s |
| 20 s | %100 · 57,8–58,3 s | %100 · 93,7–94,7 s |
| 40 / 80 / 160 s | %0 | %0 |

DTN her noktada TCP'den yavaş. µD3TN'in MTCP katmanı da TCP tabanlı; iki atlamanın her
birinde ayrı bağlantı kurulumu ve yavaş başlangıç ödeniyor, aktarıcıda depolama da ekleniyor.
Uçtan uca yol açıkken DTN bir şey kazandırmıyor; avantajı yalnızca yol hiç açılmadığında
(Deney 2) görülüyor.

---

## Bulgu 3 — TCP'nin sınırı bağlantı kurulumu (Deney 1, g1 ≥ 40 s)

TCP iki farklı şekilde kopuyor (gönderici günlüklerinden):

| g1 | Gidiş-dönüş | Ne oluyor |
| --- | --- | --- |
| 40 s | 80 s | Bağlantı kuruluyor, 46/50 mesaj gönderiliyor, ama mesajlar koşu süresi (220 s) içinde varmıyor; alıcı kapanınca `ECONNRESET`. Sınır: koşu süresi. |
| 80 s | 160 s | Bağlantı hiç kurulamıyor: ~133 s sonra `ETIMEDOUT`. |
| 160 s | 320 s | Aynı: ~132 s sonra `ETIMEDOUT`. |

Açıklama: SYN'in ilk zaman aşımı 1 s (RFC 6298); Linux SYN'i varsayılan 6 kez tekrarlayıp
yaklaşık 127 s sonra vazgeçer (`net.ipv4.tcp_syn_retries`). Gidiş-dönüş bundan uzunsa
(g1 ≳ 64 s) TCP bağlantıyı **hiçbir zaman** kuramaz; daha kısa gecikmelerde kurar ama
her gidiş-dönüş gecikmeye eklenir (g1 = 20 s'de medyan 58 s ≈ 1,5 gidiş-dönüş + iletim).

DTN de g1 ≥ 40 s'de %0, çünkü MTCP bağlantısı da TCP: µD3TN aktarıcıya bağlanamadığı için
bundle'lar Dünya düğümünde bekliyor. Bu, µD3TN'in TCP tabanlı katmanının bir sınırıdır,
DTN mimarisinin değil (RFC 4838 TCP olmayan, bağlantısız katmanlara da izin verir).

Not: Ön testlerde bir kez g1 = 20 s'de TCP ve DTN %0 çıkmıştı; tam matriste 10/10 koşu
%100. O test uyku sorunlarının çözülmediği döneme denk geliyordu ve sonuçlarda kullanılmadı.

---

## Deney düzeneğinde bulunup düzeltilen sorunlar

Bunlar ölçümleri sessizce bozabilecek hatalardı; hepsi gerçek koşuyla bulundu ve
düzeltmeden sonra yeniden test edildi.

| Sorun | Belirti | Düzeltme |
| --- | --- | --- |
| netem `loss 100%` ARP'yi de düşürüyor | Pencere açılınca ilk paket 812 ms (beklenen 405 ms) | Sabit MAC + kalıcı ARP (`ag/komsu_ayarla.sh`) |
| Docker yeniden kurulumda aktarıcının `eth0`/`eth1`'ini yer değiştirdi | Gecikme yanlış linke uygulanacaktı | `interface_name` + her koşudan önce `ag/arayuz_dogrula.py` (PR #1) |
| Takvim bitince linkleri açmak | 10 s pencerede uçtan uca yol koşu bitmeden açılabilirdi | Takvim sonunda linkler kapalı, yalnızca SIGTERM'de açılır |
| Deney 1'de µD3TN'e kontak tanımlanmıyordu | DTN teslim %0 | Takvimsiz DTN koşularına kalıcı kontaklar (PR #3) |
| Yeniden başlatma kancası netem'den sonra çalışıyordu | g1 = 5 s'de DTN 0,05 s ölçüldü (netem silinmişti) | Sıra: yeniden başlatma → kontaklar → netem (PR #3) |
| `takvim_yukle.py` hedef EID/CLA vermiyordu, süre ondalıklıydı | Her çağrıda `aap2-config` hatası | Azra düzeltti (PR #2) |
| Mac pildeyken / kapak kapanınca uyudu | Aynı noktanın tekrarları tutmadı (ör. TCP g1 = 1 s'de 0/50) | Uykuyla çakışan koşular arşivlendi ve yeniden koşuldu; uzun koşular şarjda, kapak açık |
| Ek yük grafiği 317.757 piksel genişlikteydi | Grafik kullanılamazdı | Etiket eksen koordinatına alındı (PR #7) |
