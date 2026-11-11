# Türkçe metni sese çevirir (Piper, internet gerektirmez).
# Model dosyası: sesler/tr_TR-dfki-medium.onnx (+ .onnx.json). Yoksa ses üretilmez;
# kiosk sayfası o zaman tarayıcının kendi konuşma özelliğini dener.
# Aynı cümle bir kez üretilir, sonra sesler/onbellek/ klasöründen okunur.

import hashlib
import io
import os
import threading
import wave

MODEL = "sesler/tr_TR-dfki-medium.onnx"
ONBELLEK = "sesler/onbellek"

_ses = None
_kilit = threading.Lock()


def hazir():
    if not os.path.exists(MODEL):
        return False
    try:
        import piper  # noqa: F401
        return True
    except ImportError:
        return False


def _yukle():
    global _ses
    with _kilit:
        if _ses is None:
            from piper import PiperVoice
            _ses = PiperVoice.load(MODEL)


def isit(cumleler=()):
    """Modeli önceden belleğe yükle ve sık kullanılan cümleleri önceden üret;
    ilk öğrenci 2-3 saniye beklemesin."""
    def calis():
        _yukle()
        for metin in cumleler:
            konus(metin)
    if hazir():
        threading.Thread(target=calis, daemon=True).start()


def konus(metin):
    """Metnin WAV ses verisini döndürür; ses motoru yoksa None."""
    if not hazir():
        return None
    yol = os.path.join(ONBELLEK, hashlib.sha1(metin.encode()).hexdigest() + ".wav")
    if os.path.exists(yol):
        with open(yol, "rb") as f:
            return f.read()

    _yukle()
    with _kilit:
        tampon = io.BytesIO()
        with wave.open(tampon, "wb") as wav:
            if hasattr(_ses, "synthesize_wav"):   # piper-tts 1.3 ve sonrası
                _ses.synthesize_wav(metin, wav)
            else:                                 # eski sürümler
                _ses.synthesize(metin, wav)
    veri = tampon.getvalue()
    os.makedirs(ONBELLEK, exist_ok=True)
    with open(yol, "wb") as f:
        f.write(veri)
    return veri
