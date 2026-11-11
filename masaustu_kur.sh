#!/usr/bin/env bash
# Sınav Giriş Sistemi simgesini bu bilgisayara kurar (uygulamalar menüsü + masaüstü).
# Proje hangi klasördeyse simge o klasörü kullanır; klasörü taşırsan bu betiği yeniden çalıştır.
#   ./masaustu_kur.sh

KLASOR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
chmod +x "$KLASOR/sinav_giris.sh"

simge() {
  cat <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Sınav Giriş Sistemi
GenericName=Yüz tanımalı sınav girişi
Comment=Kamerayı, yüz tanımayı ve web sitesini başlatır, tarayıcıyı açar
Exec="$KLASOR/sinav_giris.sh"
Icon=$KLASOR/static/marka/amblem.png
Terminal=false
Categories=Education;
Keywords=sınav;yüz;tanıma;kiosk;
StartupNotify=false
Actions=kiosk;durdur;

[Desktop Action kiosk]
Name=Giriş kioskunu aç
Exec="$KLASOR/sinav_giris.sh" kiosk

[Desktop Action durdur]
Name=Sistemi durdur
Exec="$KLASOR/sinav_giris.sh" durdur
EOF
}

MENU="$HOME/.local/share/applications"
mkdir -p "$MENU"
simge > "$MENU/sinav-giris.desktop"
echo "Menüye eklendi: $MENU/sinav-giris.desktop"

MASAUSTU="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [ -d "$MASAUSTU" ]; then
  simge > "$MASAUSTU/sinav-giris.desktop"
  chmod +x "$MASAUSTU/sinav-giris.desktop"
  gio set "$MASAUSTU/sinav-giris.desktop" metadata::trusted true 2>/dev/null
  echo "Masaüstüne eklendi: $MASAUSTU/sinav-giris.desktop"
fi
update-desktop-database "$MENU" 2>/dev/null
exit 0
