#!/usr/bin/env bash
# Sınav Giriş Sistemi — tek tıkla başlatma (masaüstü simgesi bunu çalıştırır).
#   ./sinav_giris.sh            sistemi arka planda başlatır, hazır olunca tarayıcıyı açar
#   ./sinav_giris.sh durdur     sistemi kapatır
#   ./sinav_giris.sh kiosk      giriş kioskunu tarayıcıda açar (sistem kapalıysa önce başlatır)
# Sistem zaten çalışıyorsa yeniden başlatmaz, sadece tarayıcıyı açar.
# Çıktılar: loglar/sistem.log

cd "$(dirname "$(readlink -f "$0")")" || exit 1
SITE="http://localhost:5000"
AMBLEM="$PWD/static/marka/amblem.png"

PIDDOSYA="loglar/sistem.pid"

# Çalışan sistemin PID'i: önce PID dosyasından (bu betikle başlatıldıysa), yoksa sadece
# "python ... baslat.py" biçimindeki süreçlerden. Başka programlara (ör. dosyayı açmış bir editöre) dokunmaz.
sistem_pid() {
  if [ -f "$PIDDOSYA" ]; then
    local pid; pid="$(cat "$PIDDOSYA")"
    if [ -n "$pid" ] && [ -r "/proc/$pid/cmdline" ] && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q "baslat\.py"; then
      echo "$pid"; return 0
    fi
  fi
  pgrep -f "^[^ ]*python[0-9.]* ([^ ]*/)?baslat\.py( |$)" | head -1
}
calisiyor() { [ -n "$(sistem_pid)" ]; }
bildir() { notify-send -a "Sınav Giriş" -i "$AMBLEM" "$1" "${2:-}" 2>/dev/null || true; }

case "${1:-}" in
  durdur)
    if calisiyor; then
      kill -TERM "$(sistem_pid)"   # baslat.py SIGTERM'de kamera, tanıma ve siteyi düzgünce kapatır
      for _ in $(seq 1 20); do calisiyor || break; sleep 0.5; done
      rm -f "$PIDDOSYA"
      bildir "Sınav Giriş sistemi kapatıldı"
    else
      bildir "Sınav Giriş sistemi zaten kapalı"
    fi
    exit 0 ;;
  kiosk) SAYFA="$SITE/kiosk" ;;
  *)     SAYFA="$SITE" ;;
esac

if calisiyor && curl -s -o /dev/null --max-time 2 "$SITE/giris"; then
  xdg-open "$SAYFA" >/dev/null 2>&1 &   # zaten çalışıyor: sadece aç
  exit 0
fi

mkdir -p loglar
[ -f loglar/sistem.log ] && mv -f loglar/sistem.log loglar/sistem.onceki.log
bildir "Sınav Giriş sistemi başlatılıyor" "Kamera, tanıma ve site açılıyor; birkaç saniye sürer."
nohup python3 baslat.py > loglar/sistem.log 2>&1 &
echo $! > "$PIDDOSYA"   # baslat.py venv'e geçerken aynı PID'i korur

# Site hazır olunca istenen sayfayı aç (en çok 40 sn bekle)
for _ in $(seq 1 80); do
  if curl -s -o /dev/null --max-time 1 "$SITE/giris"; then
    xdg-open "$SAYFA" >/dev/null 2>&1 &
    exit 0
  fi
  sleep 0.5
done
bildir "Sınav Giriş sistemi açılamadı" "Ayrıntı: $PWD/loglar/sistem.log"
exit 1
