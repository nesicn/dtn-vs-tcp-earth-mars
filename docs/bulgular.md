# Bulgular ve deney düzeneğinde bulunan sorunlar

Final rapor ve sunum için ortak kaynak. Her bulgu ölçümle desteklenir; tek koşudan
çıkan sayılar "ön sonuç" olarak işaretlidir ve tam matris koşulduktan sonra
güncellenmelidir.

Ortam: üç düğümlü Docker topolojisi (`docker-compose.yml`), µD3TN v0.15.0, MTCP
bağlantı katmanı, macOS + Colima. Son güncelleme: 24.11.2026 (Elif).

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

---

## Bulgu 2 (ön sonuç) — Linkler hep açıkken yüksek gecikmede DTN, TCP'den yavaş

| Koşu (Deney 1, g1 = 5 s) | Teslim | Medyan gecikme |
| --- | --- | --- |
| DTN | %100 | 19,95 / 20,05 / 20,19 s |
| TCP | %100 | 13,18 / 13,19 s |

Tek koşular; tam matristen sonra doğrulanmalı. Olası açıklama: MTCP de TCP tabanlı ve
iki atlamanın her birinde ayrı bağlantı kurulumu ve yavaş başlangıç ödeniyor. Uçtan uca
yol açıkken DTN'nin avantajı yok; avantajı Deney 2'de (yol hiç açılmadığında) görülüyor:
aynı takvimde TCP %0, DTN %100 (20 s pencere).

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
