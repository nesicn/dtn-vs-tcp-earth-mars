# Koşturucunun Docker ortamından beklentileri

Bu belge, `deney/run_experiment.py`'nin Elif'in ağ düzeni ve Azra'nın µD3TN kurulumuyla
birlikte çalışması için gerekenleri listeler. Koşturucu ortama yalnızca
`deney/ortam_docker.json` üzerinden bağlıdır: bir isim veya komut farklıysa koşturucunun
kodu değil, bu dosya değiştirilir.

## Elif: Docker Compose

1. **Konteyner adları** tam olarak `dunya`, `aktarici`, `arac` olmalı (`container_name`).
   Koşturucu `docker exec dunya ...` biçiminde komut verir.
2. **Proje klasörü** her üç konteynerde `/proje` altına bağlanmalı:
   ```yaml
   volumes:
     - ./:/proje
   ```
   Betikler buradan çalışır, sonuçlar `sonuclar/` altına doğrudan host'a yazılır.
3. **Yetki:** üç konteynere de `cap_add: [NET_ADMIN]`.
4. **Paketler:**
   - `dunya`, `aktarici`, `arac`: µD3TN daemon, `iproute2`, `procps`.
   - Üç düğümde de `python3` ve `ud3tn-utils` (`aap2-config`) bulunmalı; `aktarici`
     ayrıca `tcpdump` içermeli.
   - `dunya` ve `arac` trafik betikleri için Python 3.9+ gerektirir.
   (`procps`, koşturucunun süreçleri `pkill` ile durdurabilmesi için gerekli.)
5. **Yönlendirme:** `aktarici` IP paketlerini iki ağ arasında iletmeli
   (`sysctls: net.ipv4.ip_forward: 1`), `dunya` ve `arac`'ta karşı ağa giden rota
   `aktarici` üzerinden tanımlı olmalı. Doğrulama: `docker exec dunya ping -c 3 <arac IP>`.
6. **`ortam_docker.json` içinde doğrulanacaklar:**
   - `tcp.alici_host`: `arac`'ın link2 IP adresi.
   - `arayuzler`: her konteynerde `ip -br addr` çıktısına göre hangi arayüzün hangi
     linke bağlı olduğu. Docker arayüz sırasını garanti etmez; `aktarici`'de `eth0`
     ve `eth1`'in hangi ağa denk geldiğini mutlaka kontrol et.
7. **Pencere betiği (`contact_controller.py`)** koşturucudan şu biçimde çağrılır
   (argüman adları farklıysa `kancalar.arka_plan` içindeki komutu düzelt ve
   `devre_disi` satırını sil):
   ```bash
   python3 <yol>/contact_controller.py --takvim <takvim.csv> --t0 <unix_saniye>
   ```
   - `takvim.csv` biçimi: `link,baslangic_s,bitis_s,gecikme_s` (zamanlar t0'a göre).
     Örnek üretmek için: `python deney/takvim.py --pencere 20 --cikti ornek.csv`
   - Betik host'ta çalışır ve konteynerlere `docker exec ... tc` ile komut verir.
   - Koşu boyunca çalışır; koşu bitince koşturucu ona SIGTERM gönderir. Betik SIGTERM'de
     linkleri açık bırakarak çıkmalı.
   - Deney 1'de çağrılmaz; orada gecikmeyi koşturucu `kosu_oncesi` kancalarıyla
     doğrudan uygular, `kosu_sonrasi` kancalarıyla kaldırır.

## Azra: µD3TN

1. **AAP 2.0 erişimi:** Her düğümün µD3TN AAP2 arayüzü konteyner içinde
   `127.0.0.1:4242` adresinde dinler. Koşturucu trafik istemcilerini `docker exec` ile
   konteyner içinde başlattığından `dtn.dunya_aap2`, `dtn.aktarici_aap2` ve
   `dtn.arac_aap2` bu adresi kullanır. Takvim yükleyici host'ta çalışır; AAP2'ye
   `docker exec <dugum> aap2-config --tcp 127.0.0.1 4242 ...` üzerinden bağlanır.
   `ud3tn-utils` üç düğümde de kurulu olmalı.
2. **µD3TN başlatma argümanları:** Her Compose hizmeti `ag/komsu_ayarla.sh` ile
   rotaları kurduktan sonra daemon'u başlatmalı. Azra'nın açık entegrasyon PR'ındaki
   ortak AAP2 argümanları `--aap2-host 127.0.0.1 --aap2-port 4242`; üç düğüm EID'si
   şöyledir:

   | Hizmet | EID | AAP2 |
   | --- | --- | --- |
   | `dunya` | `dtn://dunya.dtn/` | `127.0.0.1:4242` |
   | `aktarici` | `dtn://aktarici.dtn/` | `127.0.0.1:4242` |
   | `arac` | `dtn://arac.dtn/` | `127.0.0.1:4242` |

   Her düğümde bundle ömrü `--lifetime 900` olmalı; bu, Deney 1'in yaklaşık 700
   saniyelik en uzun koşusunu aşar. PR'da bildirilen MTCP dinleme portları `dunya:4224`,
   `aktarici:4225` ve `arac:4226`'dır. Compose komutu
   `sh /proje/ag/komsu_ayarla.sh <hizmet> ud3tn ...` biçiminde olmalı.
   Gerçek takvim yükleme testi öncesinde PR'daki `aap2-config` çağrısı düzeltilmelidir:
   resmî kullanımda `--schedule` seçeneklerinden sonra hedef `NODE_ID` ve `CLA_ADDR`
   konumsal argümanları da verilir. Dünya'dan aktarıcıya kurulan kontak, aracın bu
   sonraki düğüm üzerinden erişilebilir olduğunu `-r dtn://arac.dtn/` ile bildirmelidir.
3. **EID'ler:** aracın düğüm EID'si `dtn.hedef_eid`'in ön ekidir. Alıcı `sink` ajan
   kimliğiyle kayıt olur; varsayılan hedef `dtn://arac.dtn/sink`.
4. **Her DTN koşusu temiz başlamalı.** Önceki koşudan kalan bundle'lar alıcıya geç
   ulaşabilir. Alıcı bunları koşu belirtecinden tanıyıp saymaz, ama ağda yük
   oluştururlar ve ek yük ölçümünü bozarlar. `kancalar.kosu_oncesi` DTN kancası
   konteynerleri yeniden başlatır.
5. **Takvim yükleyici:** Deney 2'de aynı `takvim.csv` ve `t0` ile µD3TN kontaklarını
   kuran betik, `kancalar.kosu_oncesi` içinde şu biçimde çağrılır:
   ```bash
   python3 <yol>/takvim_yukle.py --takvim <takvim.csv> --t0 <unix_saniye>
   ```
   µD3TN `aap2-config --schedule` başlangıç ofsetini komut çağrısından itibaren saniye
   olarak alır. Her pencere için `START_OFFSET = t0 + baslangic_s - time.time()` ve
   `DURATION = bitis_s - baslangic_s` hesaplanmalıdır. Yükleyici host'ta çalıştığından
   AAP2'ye `docker exec <dugum> aap2-config --tcp 127.0.0.1 4242 ...` ile bağlanır.
   Koşturucu `t0`'ı, kancalar bitecek kadar ileride seçer (`baslama_payi_s`, varsayılan
   10 s). Gerçek bundle testi, yukarıda belirtilen hedef EID/CLA argümanları ve rota
   ilanı eklenip takvim yükleyicisi çalıştırılmadan tamamlanmış sayılmaz.

## Koşturucunun çalıştığı bilgisayar

- `netem` testini geçen bilgisayar (yol haritası bölüm 3).
- Python 3.9+; koşturucu yalnızca standart kütüphaneyi kullanır.
- Grafikler için ayrıca `pip install pandas matplotlib`.
- Uzun koşular sırasında bilgisayarın uyku moduna geçmemesi gerekir.
  Mac'te: `caffeinate -i python3 deney/run_experiment.py ...`

## İlk entegrasyon testi için önerilen sıra

1. `--kuru` ile komutları gözden geçir.
2. Gecikmesiz tek bir TCP koşusu: `--kosu d1_tcp_g0p1_t1`. Teslim %100 olmalı.
3. Aynısını DTN ile: `--kosu d1_dtn_g0p1_t1`.
4. Yüksek gecikmede tek koşu: `--kosu d1_tcp_g80_t1` ve `--kosu d1_dtn_g80_t1`.
5. Deney 2'den tek koşu: `--kosu d2_dtn_p20_t1`. `takvim.csv`, `kosturucu.log` ve
   µD3TN günlüklerinden bundle'ın aktarıcıda beklediği görülmeli.
6. Her koşudan sonra `kosu.json` içindeki `uyarilar` alanına bak.
