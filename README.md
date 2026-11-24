# DTN ve TCP: Dünya–Mars Senaryosunda Karşılaştırma

Communication Systems and Networks dersi grup projesi. Bağlantının sık koptuğu ve
gecikmenin çok yüksek olduğu bir Dünya–Mars hattında TCP ile DTN'i (µD3TN) teslim
oranı, uçtan uca gecikme ve protokol ek yükü açısından karşılaştırıyoruz.

Üç düğüm: **Dünya istasyonu** (`dunya`), Mars yörüngesindeki **aktarıcı uydu**
(`aktarici`) ve Mars yüzeyindeki **araç** (`arac`). Düğümler Docker konteynerleridir,
gecikme ve kopmalar `tc netem` ile uygulanır. Tüm süreler ölçeklidir (gerçek 3–22
dakika yerine saniyeler).

| Deney | Soru | Düzen |
| --- | --- | --- |
| Deney 1 | TCP hangi gecikmede çalışamaz hale geliyor? | Linkler hep açık, Dünya–uydu gecikmesi 0,1 → 160 s |
| Deney 2 | Uçtan uca yol hiç açık değilken ne oluyor? | Gecikme 1 s, iki linkin pencereleri hiç örtüşmüyor |

## Klasör yapısı

| Klasör | İçerik | Sorumlu |
| --- | --- | --- |
| `trafik/` | TCP ve DTN gönderici/alıcı betikleri, ortak mesaj ve günlük biçimi | Nesibe |
| `deney/` | Deney koşturucu (`run_experiment.py`), ortam dosyaları, deney matrisleri, takvim üretici | Nesibe |
| `analiz/` | Metrikler, pcap bayt sayımı, grafikler, Colab defteri, sentetik test verisi | Nesibe |
| `testler/` | Birim ve uçtan uca testler, testler için µD3TN AAP 2.0 taklidi | Nesibe |
| `docker-compose.yml`, ağ ve pencere betikleri | Topoloji, netem, `contact_controller.py` | Elif |
| µD3TN Dockerfile ve yapılandırma | Düğümler, kontaklar, takvim yükleyici | Azra |
| `docs/` | Ortam ayarları, GitHub kurulumu | Ortak |

## Hızlı başlangıç (Windows, Mac veya Linux, Docker gerekmez)

Python 3.9 veya üzeri gerekir.

```bash
pip install -r requirements.txt

# 1. Tüm testler (yaklaşık 15 saniye)
python -m unittest discover -s testler -v

# 2. Tüm akışı yerelde dene: koşturucu + analiz (yaklaşık 30 saniye)
python deney/run_experiment.py --ortam deney/ortam_yerel.json --matris deney/matrisler/deneme.json
python analiz/analiz.py        # deneme için yalnızca tablolar; grafikler deney1/deney2'den çizilir

# 3. Grafiklerin neye benzeyeceğini gör (SENTETİK veri, rapora girmez)
python analiz/sentetik_veri.py
python analiz/analiz.py --sonuclar sonuclar_sentetik
```

Yerel ortamda gecikme ve pencere yoktur ve DTN modunda µD3TN yerine
`testler/sahte_ud3tn.py` taklidi kullanılır. Çıkan sayılar ölçüm değildir; yalnızca
betiklerin ve analizin doğru çalıştığını gösterir. Grafikler bu durumda üzerlerine
"YEREL DENEME" veya "SENTETİK VERİ" uyarısı yazar.

## Asıl deney (Docker)

Koşturucu, `netem` testini geçen bilgisayarda (host'ta) çalışır ve konteynerlere
`docker exec` ile komut verir. Önce `docs/ortam_ayarlari.md`'deki gereksinimler
karşılanmalı; Compose ve DTN ortam ayarları güncel `main` yapılandırmasıyla
eşleştirilmelidir. Koşulardan önce `docker compose config` ve aşağıdaki `--kuru`
çıktısı kontrol edilmelidir.

```bash
# Önce ne çalıştırılacağını gör (hiçbir şey çalıştırmaz)
python3 deney/run_experiment.py --ortam deney/ortam_docker.json --matris deney/matrisler/deney1.json --kuru

# Tek bir koşuyla dene
python3 deney/run_experiment.py --ortam deney/ortam_docker.json --matris deney/matrisler/deney1.json --kosu d1_tcp_g1_t1

# Tam Deney 1 (80 koşu)
python3 deney/run_experiment.py --ortam deney/ortam_docker.json --matris deney/matrisler/deney1.json

# Tam Deney 2 (30 koşu): 10 s penceredeki DTN teslim oranı incelendikten sonra çalıştır
python3 deney/run_experiment.py --ortam deney/ortam_docker.json --matris deney/matrisler/deney2.json

# Analiz ve grafikler
python3 analiz/analiz.py
```

Koşturucu yarıda kalırsa (Ctrl+C, elektrik, uyku modu) aynı komut yeniden
çalıştırıldığında tamamlanmış koşular atlanır. `--yeniden` hepsini baştan yapar.
Diğer seçenekler: `--mod tcp`, `--tekrar 3`, `--en-fazla 4`, `--dur-hatada`.

## Ölçüm tasarımı

### Mesajlar

Her koşuda gönderici, belirlenen aralıkla `adet` mesaj gönderir (varsayılan 50 mesaj
× 1024 bayt, 0,1 s aralık). Her mesajın ilk 32 baytı bir başlıktır:

| Alan | Bayt | Açıklama |
| --- | --- | --- |
| Sihir, sürüm, mod | 4 + 1 + 1 | `DTNM`, 1, tcp veya dtn |
| Başlık uzunluğu | 2 | 32 |
| Koşu belirteci | 8 | Koşu kimliğinin SHA-256 özetinden; önceki koşulardan geç gelen mesajları ayırır |
| Mesaj no, toplam | 4 + 4 | 0'dan başlayan sıra |
| Gönderme zamanı | 8 | Unix zamanı, nanosaniye |

Kalan baytlar mesaj numarasından türetilen dolgudur; alıcı bozulmayı bununla fark eder.
TCP'de her mesajın önüne 4 baytlık uzunluk eklenir (TCP bir bayt akışıdır). DTN'de
her mesaj bir bundle'ın yüküdür.

### Günlükler (her koşu klasöründe)

| Dosya | Sütunlar / içerik |
| --- | --- |
| `alici.csv` | `deney_id, mod, mesaj_no, gonderme_zamani, alma_zamani, boyut_byte` (kopyalar dahil) |
| `gonderici.csv` | `deney_id, mod, mesaj_no, gonderme_zamani, boyut_byte, durum` (`gonderildi` / `gonderilemedi`) |
| `*_ozet.json` | Bağlantı denemeleri, kopya ve yabancı mesaj sayısı, çıkış nedeni |
| `kosu.json` | Parametreler, durum, uyarılar, git sürümü, hesaplanan metrikler |
| `hat.pcap` | Aktarıcıda yakalanan trafik (Docker ortamında) |
| `takvim.csv` | Deney 2'nin iletişim takvimi |

Zaman damgaları gönderici ve alıcının saatinden alınır. Aynı makinedeki konteynerler
aynı çekirdek saatini paylaştığı için fark doğrudan tek yön gecikmeyi verir.

### Metrikler

| Metrik | Tanım |
| --- | --- |
| Teslim oranı | Benzersiz teslim edilen mesaj / planlanan mesaj. Payda planlanan adettir; hiç gönderilemeyen mesajlar da sayılır. |
| Uçtan uca gecikme | Alma zamanı − gönderme zamanı, her mesajın ilk kopyası. Koşu başına medyan ve %95'lik değer. |
| Protokol ek yükü | Hatta yakalanan toplam bayt / gönderilen asıl veri baytı (hocanın tanımı). Hat baytı, aktarıcının iki link arayüzündeki tüm çerçevelerin kablodaki uzunluğudur. |
| Bağlantı kurma süresi | Yalnızca TCP: `connect()` çağrısının sürdüğü süre. |

Tekrarlar `gruplar.csv`'de birleştirilir: teslim oranı için ortalama, standart sapma,
en küçük ve en büyük; gecikme için koşu medyanlarının medyanı.

### Ölçüm kararları

- **TCP'de kısa uygulama zaman aşımı yok.** Bağlantı kurma süresini işletim sistemi
  belirler (Linux'ta `net.ipv4.tcp_syn_retries`, varsayılan 6, yaklaşık 2 dakika).
  Tek üst sınır koşu süresidir. Kullanılan `sysctl` değerleri raporda yazılmalıdır.
- **Düz TCP:** varsayılan tek bağlantı denemesi. Kopan bağlantıda kalan mesajlar
  yeniden gönderilmez, `gonderilemedi` olarak kaydedilir.
- **Nagle kapalı (`TCP_NODELAY`).** Açıkken küçük mesajlar bir önceki mesajın ACK'ini
  bekler; yüksek gecikmede bu, protokolü değil Nagle'ı ölçmek olur. `--nagle` ile açılır.
- **DTN'de "gönderildi"** = yerel µD3TN düğümü bundle'ı kabul etti. Bundle ömrü
  µD3TN yapılandırmasından gelir ve koşu süresinden uzun olmalıdır.
- **Erken bitiş:** alıcı tüm mesajları alınca çıkar; hiç mesaj gönderilemeyen koşularda
  koşturucu alıcıyı beklemeden durdurur. Koşu süreleri bu yüzden çoğunlukla üst sınırın
  altındadır.

## Sınırlılıklar ve doğrulanmamış noktalar

- Otomatik yazılım testleri yerelde ve µD3TN AAP2 taklidiyle çalışır. Gerçek üç düğümlü
  µD3TN ve `netem` ortamında ilk smoke koşuları tamamlandı; tam deney matrisleri henüz
  tamamlanmadı. Tek koşuluk sonuçlar nihai ölçüm olarak değerlendirilmemelidir.
- Deney 2'nin 10 s pencere koşulunda bildirilen %38 DTN teslim oranının nedeni
  incelenmektedir. Tam Deney 2 matrisi bu inceleme tamamlanana kadar bekletilmelidir.
- µD3TN'in düğümler arası taşıma katmanları TCP tabanlıdır; çok yüksek gecikmede DTN
  bağlantısı da TCP zaman aşımlarına takılabilir (yol haritası bölüm 2).
- `testler/sahte_ud3tn.py` bir DTN uygulaması değildir, deneylerde kullanılmaz.
- `netem`'in kapalı linkte düşürdüğü paketler `tcpdump` yakalamasında görünmeyebilir;
  ek yük ölçümünün bu yönü Docker ortamında doğrulanmalı.
