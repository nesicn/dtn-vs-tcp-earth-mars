# Koşturucunun Docker ortamından beklentileri

Bu belge, `deney/run_experiment.py`'nin Elif'in ağ düzeni ve Azra'nın µD3TN kurulumuyla
birlikte çalışması için gerekenleri listeler. Koşturucu ortama yalnızca
`deney/ortam_docker.json` üzerinden bağlıdır: bir isim veya komut farklıysa koşturucunun
kodu değil, bu dosya değiştirilir.

## Ağ topolojisi ve Docker Compose

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
6. **Doğrulanmış ağ değerleri:** `tcp.alici_host` `10.0.2.3`'tür. `arayuzler` eşlemesi
   `dunya eth0 = link1`, `aktarici eth0 = link1`, `aktarici eth1 = link2` ve
   `arac eth0 = link2` şeklindedir. Koşturucu her deneyden önce bu eşlemeyi denetler.
7. **Pencere betiği (`contact_controller.py`)** koşturucunun `kancalar.arka_plan`
   bölümünden şu biçimde çağrılır:
   ```bash
   python3 <yol>/contact_controller.py --takvim <takvim.csv> --t0 <unix_saniye>
   ```
   - `takvim.csv` biçimi: `link,baslangic_s,bitis_s,gecikme_s` (zamanlar t0'a göre).
     Örnek üretmek için: `python deney/takvim.py --pencere 20 --cikti ornek.csv`
   - Betik host'ta çalışır ve konteynerlere `docker exec ... tc` ile komut verir.
   - Koşu boyunca çalışır; koşu bitince koşturucu ona SIGTERM gönderir. Betik SIGTERM'de
     linkleri açık bırakarak çıkmalı.
   - Deney 1'de çağrılmaz; gecikmeyi koşturucu `kosu_oncesi` kancalarıyla uygular,
     `kosu_sonrasi` kancalarıyla kaldırır.

## µD3TN ve AAP2 yapılandırması

1. **AAP 2.0 erişimi:** Her düğümün µD3TN AAP2 arayüzü konteyner içinde
   `127.0.0.1:4242` adresinde dinler. Koşturucu trafik istemcilerini `docker exec` ile
   konteyner içinde başlattığından `dtn.dunya_aap2`, `dtn.aktarici_aap2` ve
   `dtn.arac_aap2` bu adresi kullanır. Takvim yükleyici host'ta çalışır; AAP2'ye
   `docker exec <dugum> aap2-config --tcp 127.0.0.1 4242 ...` üzerinden bağlanır.
   `ud3tn-utils` üç düğümde de kurulu olmalı.
2. **µD3TN başlatma argümanları:** Her Compose hizmeti `ag/komsu_ayarla.sh` ile
   rotaları kurduktan sonra daemon'u başlatır. Ortak AAP2 argümanları
   `--aap2-host 127.0.0.1 --aap2-port 4242`; düğüm EID'leri ve MTCP dinleme portları
   şöyledir:

   | Hizmet | EID | AAP2 | MTCP |
   | --- | --- | --- | --- |
   | `dunya` | `dtn://dunya.dtn/` | `127.0.0.1:4242` | `4224` |
   | `aktarici` | `dtn://aktarici.dtn/` | `127.0.0.1:4242` | `4225` |
   | `arac` | `dtn://arac.dtn/` | `127.0.0.1:4242` | `4226` |

   Her düğümde bundle ömrü `--lifetime 900` olmalı; bu, Deney 1'in yaklaşık 700
   saniyelik en uzun koşusunu aşar. Compose komutu
   `sh /proje/ag/komsu_ayarla.sh <hizmet> ud3tn ...` biçimindedir.
3. **EID'ler:** aracın düğüm EID'si `dtn.hedef_eid`'in ön ekidir. Alıcı `sink` ajan
   kimliğiyle kayıt olur; varsayılan hedef `dtn://arac.dtn/sink`.
4. **Her DTN koşusu temiz başlamalı.** Önceki koşudan kalan bundle'lar alıcıya geç
   ulaşabilir. Alıcı bunları koşu belirtecinden tanıyıp saymaz, ama ağda yük
   oluştururlar ve ek yük ölçümünü bozarlar. `kancalar.kosu_oncesi` DTN kancası
   konteynerleri yeniden başlatır.
5. **Takvim yükleyici:** Deney 2'de host'ta çalışan `dtn_yapilandirma/takvim_yukle.py`
   aynı `takvim.csv` ve `t0` ile µD3TN kontaklarını kurar. `link1` kontağı `dunya`
   düğümünde `dtn://aktarici.dtn/` ve `mtcp:10.0.1.3:4225` için; `link2` kontağı
   `aktarici` düğümünde `dtn://arac.dtn/` ve `mtcp:10.0.2.3:4226` için tanımlanır.
   Dünya'nın aktarıcıya kontağı ayrıca `-r dtn://arac.dtn/` ile aracı erişilebilir
   olarak bildirir. Betik, düğüm EID'si ve CLA adresini `aap2-config` çağrısına verir:
   ```bash
   python3 <yol>/takvim_yukle.py --takvim <takvim.csv> --t0 <unix_saniye>
   ```
   Her pencerenin başlangıç ofseti `round(t0 + baslangic_s - time.time())`, süresi
   `int(round(bitis_s - baslangic_s))` olarak hesaplanır. Host'tan AAP2'ye
   `docker exec <dugum> aap2-config --tcp 127.0.0.1 4242 <NODE_ID> <CLA_ADDR> --schedule ...`
   ile bağlanılır. Koşturucu `t0`'ı kancalar bitecek kadar ileride seçer
   (`baslama_payi_s`, varsayılan 10 s).

## Güncel doğrulama durumu

- Deney 1 DTN için yeniden başlatma ve kalıcı kontak kancaları `netem` ayarından önce
  çalışır; bu sıra µD3TN'in temiz başlaması ve gecikmenin doğru uygulanması için gereklidir.
- `d2_dtn_p20_t1` smoke koşusunda Azra'nın Mac'inde 50/50 mesaj teslim edildi ve medyan
  gecikme 27,90 s ölçüldü. Elif'in Mac'inde 27,77 s ve 27,99 s sonuçları alındı.
- 10 s pencere koşusunda DTN teslim oranı %38 olarak bildirildi; µD3TN'in TCP tabanlı
  bağlantı kurma süresinin kısa pencereye etkisi inceleniyor. Bu nedenle Deney 2'nin tam
  matrisi, ekip bu bulguyu açıklığa kavuşturana kadar bekletilmelidir.

## Koşturucunun çalıştığı bilgisayar

- `netem` testini geçen bilgisayar (yol haritası bölüm 3).
- Python 3.9+; koşturucu yalnızca standart kütüphaneyi kullanır.
- Grafikler için ayrıca `pip install pandas matplotlib`.
- Uzun koşular sırasında bilgisayarın uyku moduna geçmemesi gerekir.
  Mac'te: `caffeinate -i python3 deney/run_experiment.py ...`

## Koşu öncesi kontrol

1. `--kuru` ile komutları gözden geçir ve `kosu.json` içindeki `uyarilar` alanını kontrol et.
2. Deney 1 DTN koşularında temiz başlatma ve kalıcı kontakların netem'den önce
   çalıştığını doğrula.
3. Deney 2'nin 10 s pencere teslim oranı için yürütülen inceleme tamamlanmadan tam
   matrisi başlatma. İnceleme sonrası önce ilgili smoke koşularını tekrarla.
