#!/bin/sh
# Konteyner açılışında rota ve kalıcı ARP kayıtlarını kurar, sonra uyur (sorumlu: Elif).
# Kullanım (docker-compose.yml içinden):
#   sh /proje/ag/komsu_ayarla.sh <dunya|aktarici|arac> [asıl komut ve argümanları]
#
# Neden kalıcı ARP? Deney 2'de kapalı link = netem "loss 100%"; bu ARP paketlerini de
# düşürür. Kalıcı kayıt olmazsa pencere açılınca ilk paket ARP çözümlemesini bekler.
set -e

# Verilen alt ağdaki (ör. 10.0.1.) adrese sahip arayüzün adını bulur.
# Docker arayüz sırasını garanti etmediği için eth0/eth1 sabit yazılmaz.
arayuz() { ip -o -4 addr show | awk -v ag="$1" 'index($4, ag) == 1 {print $2}'; }

case "$1" in
  dunya)
    L1=$(arayuz 10.0.1.)
    ip neigh replace 10.0.1.3 lladdr 02:00:00:00:01:03 dev "$L1" nud permanent
    ip route replace 10.0.2.0/24 via 10.0.1.3 dev "$L1"
    ;;
  aktarici)
    L1=$(arayuz 10.0.1.)
    L2=$(arayuz 10.0.2.)
    ip neigh replace 10.0.1.2 lladdr 02:00:00:00:01:02 dev "$L1" nud permanent
    ip neigh replace 10.0.2.3 lladdr 02:00:00:00:02:03 dev "$L2" nud permanent
    ;;
  arac)
    L2=$(arayuz 10.0.2.)
    ip neigh replace 10.0.2.2 lladdr 02:00:00:00:02:02 dev "$L2" nud permanent
    ip route replace 10.0.1.0/24 via 10.0.2.2 dev "$L2"
    ;;
  *)
    echo "kullanım: $0 dunya|aktarici|arac" >&2; exit 1 ;;
esac

echo "$1 hazır"
shift
# Ağ hazır olduktan sonra asıl süreci başlat. Compose'daki "command" imajın kendi
# CMD'sini ezdiği için µD3TN gibi bir süreç buraya ek argüman olarak verilir:
#   command: ["sh", "/proje/ag/komsu_ayarla.sh", "dunya", "ud3tn", "-e", "dtn://dunya.dtn/", ...]
# Ek argüman yoksa konteyner yalnızca uyur.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
exec sleep infinity
