# Yüz veritabanını (yuzler.pkl) kisiler/ klasöründeki fotoğraflardan baştan oluşturur.
# Normalde gerekmez: site üzerinden öğrenci eklenince/silinince yuzler.pkl kendiliğinden güncellenir.
# Ne zaman lazım? kisiler/ klasörüne elle fotoğraf koyduysan ya da yuzler.pkl bozulduysa.
#
# Dosya adları: <öğrenci numarası>_<sıra>.jpg  (ör. 2024123456_1.jpg, 2024123456_2.jpg)
# Öğrencinin önce sitede kayıtlı olması gerekir (numara + ad soyad + onay);
# kayıtlı olmayan numaraların fotoğrafları atlanır.

import os

import face_recognition

from veri import KISILER, ogrenci_adlari, ogrenci_dosyalari, yuzleri_yaz

adlar = ogrenci_adlari()
numaralar, kodlar = [], []

for numara, dosyalar in ogrenci_dosyalari().items():
    if numara not in adlar:
        print(f"{numara}: sitede kayıtlı öğrenci değil, {len(dosyalar)} fotoğraf atlandı")
        continue
    for dosya in dosyalar:
        resim = face_recognition.load_image_file(os.path.join(KISILER, dosya))
        yuzler = face_recognition.face_encodings(resim)
        if len(yuzler) != 1:
            print(f"{dosya}: {len(yuzler)} yüz bulundu, atlandı (fotoğrafta tam 1 yüz olmalı)")
            continue
        numaralar.append(numara)
        kodlar.append(yuzler[0])
        print(f"{dosya}: tamam ({adlar[numara]})")

yuzleri_yaz(numaralar, kodlar)
kisiler = ", ".join(f"{adlar[n]} ({n})" for n in sorted(set(numaralar))) or "-"
print(f"\n{len(kodlar)} yüz kaydedildi: {kisiler}")
