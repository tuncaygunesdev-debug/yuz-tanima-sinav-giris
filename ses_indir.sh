#!/usr/bin/env bash
# Sesli karşılama için Türkçe ses modelini (Piper, tr_TR-dfki-medium, ~66 MB) indirir.
# Model depoda yoktur; kaynağı: https://huggingface.co/rhasspy/piper-voices
#   ./ses_indir.sh
# Model olmadan da sistem çalışır: kiosk tarayıcının kendi Türkçe sesini kullanır.

cd "$(dirname "$(readlink -f "$0")")" || exit 1
ADRES="https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium"
MODEL="tr_TR-dfki-medium.onnx"
mkdir -p sesler

for dosya in "$MODEL" "$MODEL.json"; do
  if [ -s "sesler/$dosya" ]; then
    echo "Zaten var: sesler/$dosya"
    continue
  fi
  echo "İndiriliyor: $dosya"
  if ! curl -fL --progress-bar -o "sesler/$dosya.part" "$ADRES/$dosya"; then
    rm -f "sesler/$dosya.part"
    echo "İndirilemedi: $dosya (internet bağlantısını kontrol et)" >&2
    exit 1
  fi
  mv "sesler/$dosya.part" "sesler/$dosya"
done

if [ -x venv/bin/python ] && ! venv/bin/python -c "import piper" 2>/dev/null; then
  echo "piper-tts kuruluyor..."
  venv/bin/pip install -q piper-tts
fi
echo "Tamam. Sistemi yeniden başlatınca sesli karşılama açılır."
