# Sistemin bütün ayarları burada. Değiştirdikten sonra baslat.py'yi yeniden başlat.

# Görüntü kaynağı
KAMERA = "http://10.139.94.107:8080/video"  # telefon kamerası (IP Webcam uygulaması, 640x480)
# KAMERA = "http://localhost:8081/stream"   # bilgisayarın webcam'i (sahte kamera)
# KAMERA = "http://192.168.1.50:81/stream"  # gerçek ESP32-CAM gelince bunu kullan
# (KAMERA localhost:8081 olduğu sürece baslat.py sahte kamerayı da kendisi açar.)
# Telefonun adresi ağa her bağlanışta değişebilir: IP Webcam ekranının altındaki adresle aynı olmalı.
KAMERA_DONDUR = 0     # gelen görüntüyü saat yönünde kaç derece çevir (0, 90, 180, 270).
                      # Telefon yatay ve sabit duruyor; IP Webcam görüntüyü düz gönderiyor -> 0.
                      # Görüntü baş aşağı gelirse 180, telefon dik tutulursa 90 dene. Webcam / ESP32 için 0.
GORUNTU_AYNA = True   # ekranlarda görüntüyü ayna gibi göster (sağ elini kaldıran ekranda sağda görür).
                      # Sadece gösterimi etkiler; tanıma ve kayıt fotoğrafları kameranın verdiği gibi kalır.

# Tanıma. Yüz "mesafesi": 0 = aynı fotoğraf, büyüdükçe daha farklı.
# Ölçüm (9 Kasım, 4 kişi, 19 foto): aynı kişi 0.26-0.59 (ort. 0.41), farklı kişiler 0.51-0.85 (ort. 0.66).
# Kendi sınıfınla ölçmek için: venv/bin/python hassasiyet.py
TOLERANS = 0.47  # en yakın kişi bundan yakınsa "tanındı" (düşük = daha katı)
MARJ = 0.05      # en yakın kişi, ikinci en yakın kişiden en az bu kadar daha yakın olmalı;
                 # değilse sistem "emin değilim" der (ekranda ?) ve karar vermez
ONAY_KARE = 3    # bir yüz art arda bu kadar analizde aynı kişi çıkarsa kayıt düşülür
AYRILMA = 3      # kişi kameradan bu kadar saniye kaybolursa, geri geldiğinde yeni bir olay sayılır
                 # (kameranın önünde durduğu sürece aynı mesaj tekrar tekrar çıkmaz)

# Rehberli kayıt (baş yönü). Oran: burnun iki göz ortasından sapması / göz arası mesafe.
# Düz bakışta ~0, yana dönünce ±0.2 ve üstü.
KAYIT_DUZ_ESIK = 0.08   # |oran| bundan küçükse "düz bakıyor"
KAYIT_YAN_ESIK = 0.20   # |oran| bundan büyükse "yana dönmüş" (çok dönülürse yüz bulunamaz)

# Canlılık kontrolü (fotoğrafla / telefon ekranıyla kandırmaya karşı)
# Tanınan öğrenci girişten önce gözlerini kırpmalı. Fotoğraf göz kırpamaz.
CANLILIK = True        # False yapılırsa göz kırpma istenmez
CANLILIK_SURE = 7      # bu kadar saniyede göz kırpılmazsa "Canlılık doğrulanamadı"
KIRPMA_ORANI = 0.72    # göz açıklığı, kişinin normal açıklığının bu oranının altına inerse "kapandı"

# Sınav salonu
KOLTUK_SAYISI = 30   # giriş yapan öğrenciye 1..KOLTUK_SAYISI arasından boş bir sıra rastgele verilir

# Web sitesi
SITE_PORT = 5000
