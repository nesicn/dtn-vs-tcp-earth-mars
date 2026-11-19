# Nesibe'nin çalışma ve rapor bölümü

## Amaç ve deney tasarımı

Bu projede, Dünya istasyonu, aktarıcı uydu ve Mars yüzey aracı arasındaki iletişimde TCP ile µD3TN tabanlı Gecikmeye Toleranslı Ağ (DTN) yaklaşımı karşılaştırılmaktadır. Karşılaştırma, kontrollü gecikme ve kesintili bağlantı koşullarında mesaj teslim oranı, uçtan uca gecikme ve ağdaki protokol ek yükü üzerinden yapılacaktır. Deney değerleri gerçek Dünya–Mars sürelerini temsil etmez; koşuların yönetilebilir sürede tamamlanması için saniye ölçeğine indirgenmiştir.

Deney 1'de bağlantılar sürekli açık tutulur ve Dünya–aktarıcı bağlantısının tek yön gecikmesi 0,1 saniyeden 160 saniyeye kadar değiştirilir. Deney 2'de iki bağlantı için birbiriyle örtüşmeyen iletişim pencereleri tanımlanır; böylece Dünya'dan araca kesintisiz uçtan uca yol bulunmadığı durumda iki yaklaşımın davranışı incelenir. Her koşuda 50 adet, 1024 baytlık mesaj 0,1 saniye aralıklarla gönderilecek ve her parametre noktası beş kez tekrarlanacaktır. Bu tasarımla Deney 1 için 80, Deney 2 için 30 koşu planlanmıştır.

## Gerçekleştirdiğim yazılım çalışmaları

TCP ve DTN için gönderici-alıcı betiklerini, ortak mesaj biçimini ve deney günlüklerini hazırladım. Mesaj başlığı koşu belirteci, sıra numarası ve gönderim zamanını taşır. Bu alanlar, önceki koşulardan gecikerek ulaşan mesajların yeni koşuya aitmiş gibi sayılmasını önler; alıcı tarafında yinelenen, yabancı veya bozulmuş mesajlar belirlenebilir. TCP'de mesaj sınırlarını korumak için uzunluk öneki kullanılır; DTN kipinde her uygulama mesajı bir bundle yükü olarak gönderilir.

Deney koşturucusu, JSON ortam ve matris dosyalarından koşu komutlarını üretir, her koşunun parametre ve günlüklerini saklar ve tamamlanan koşuları yeniden başlatmada atlar. `--kuru` seçeneği komutları çalıştırmadan gözden geçirmeye yarar. Docker ortamı için düğüm başına TCP AAP2 veya UNIX soketi adresi seçilebilir; iki taşıma türünün aynı düğümde birlikte tanımlanması hata olarak bildirilir. Bu değişiklikle `deney/ortam_docker.json` Dünya, aktarıcı ve araç konteynerlerini, AAP2 adreslerini, hedef EID'yi ve DTN koşuları öncesindeki yeniden başlatma kancasını içerir. Takvim yükleme kancası, kontak yapılandırmasının doğrulanması tamamlanana kadar devre dışı bırakılmıştır.

Analiz kodu her koşu ve tekrar grubu için teslim oranını, ilk kopyanın uçtan uca gecikme medyanı ve yüzde 95 değerini, pcap kayıtlarından protokol ek yükünü ve TCP bağlantı kurma süresini hesaplayıp CSV tabloları ve grafikler üretir. Teslim oranının paydası, gönderilemeyen mesajlar da dahil olmak üzere planlanan mesaj sayısıdır.

## Doğrulama ve mevcut durum

Yerel doğrulamada 26 testin tamamı geçmiş ve atlanan test olmamıştır. Testler TCP gönderme-alma akışını, sahte AAP 2.0 sunucusu üzerinden DTN istemci akışını, analiz çıktısını, koşu devamlılığını ve AAP2 taşıma seçimini kapsar. Ayrıca `--kuru` çalıştırmasıyla Docker koşuları için üretilecek komutlar gözden geçirilmiştir. Bu kontroller yazılım akışının işlediğini gösterir; gerçek µD3TN düğümleri veya netem üzerinden alınmış deney ölçümü değildir.

Rapor tarihi itibarıyla tam deney matrisleri ve gerçek üç düğümlü DTN bundle koşusu henüz tamamlanmamıştır. Azra'nın açık entegrasyon PR'ındaki takvim yükleyicisi `aap2-config` komutuna gerekli hedef düğüm kimliği ve CLA adresi konumsal argümanlarını vermemektedir; ayrıca Dünya'dan aktarıcı üzerinden araca giden rotanın kontakta ilan edilmesi gerekir. Bu entegrasyon düzeltilip gerçek bundle aktarımı doğrulanmadan N3–N7 koşularının sonuçları veya TCP ile DTN'nin performans üstünlüğü hakkında sayısal bir sonuca varılmayacaktır. Takvim komutunun biçimi µD3TN'in [kontak ve bağlantı yapılandırması belgeleri](https://d3tn.gitlab.io/ud3tn/tools/link_and_contact_configuration/) ile karşılaştırılmalıdır.

## Katkı beyanı

Bu bölümde anlatılan trafik üretimi ve alma betikleri, deney koşturucusu, deney matrisleri, analiz araçları, testler ve Docker ortamına ait Nesibe yapılandırması tarafımdan hazırlanmıştır. Elif'in Docker topolojisi ve Azra'nın µD3TN imajı ile takvim yükleyicisi ayrı ekip katkılarıdır; gerçek DTN sonuçları bu bileşenlerin entegrasyonu ve doğrulanmasından sonra eklenecektir.
