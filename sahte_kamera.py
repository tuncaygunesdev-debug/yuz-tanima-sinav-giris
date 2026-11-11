# ESP32-CAM gelene kadar onun yerine geçen sahte kamera.
# Webcam'den ya da bir video dosyasından, ESP32-CAM ile aynı formatta görüntü yayınlar.
# Adres: http://localhost:8081/stream

import sys

import cv2
from flask import Flask, Response

KAYNAK = 0   # 0 = bilgisayarın webcam'i. Video için: KAYNAK = "video.mp4"

app = Flask(__name__)
kaynak = None   # açılan kamera / video (ana bölümde açılır)


def kareler():
    while True:
        ok, kare = kaynak.read()
        if not ok:  # video dosyası bittiyse başa sar
            kaynak.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        kare = cv2.resize(kare, (640, 480))  # ESP32-CAM'in VGA çözünürlüğü
        _, jpg = cv2.imencode(".jpg", kare)
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"


@app.route("/stream")
def stream():
    return Response(kareler(), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    kaynak = cv2.VideoCapture(KAYNAK)
    if not kaynak.isOpened():
        sys.exit(f"Kaynak açılamadı: {KAYNAK}. Webcam yoksa KAYNAK'a bir video dosyası yaz.")
    app.run(host="0.0.0.0", port=8081)
