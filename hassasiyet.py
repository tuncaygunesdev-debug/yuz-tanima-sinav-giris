# Tanıma hassasiyeti ölçümü: kayıtlı öğrencilerin fotoğraflarıyla, ayarlar.py'deki
# TOLERANS ve MARJ değerlerinin bu sınıf için güvenli olup olmadığını gösterir.
# Sonuçlar "benzerlik yüzdesi" olarak yazılır: %50'nin üstü tanınır (eşik), büyük = daha benzer.
# Parantez içindeki sayı teknik yüz mesafesidir (ayarlar.py'deki TOLERANS bu birimdedir).
#
#   venv/bin/python hassasiyet.py
#
# Ne yapar?
#   1. Her öğrencinin fotoğrafları birbirine ne kadar benziyor (aynı kişi mesafeleri)
#   2. Hangi iki FARKLI öğrenci birbirine en çok benziyor (karıştırılma riski)
#   3. Her fotoğrafı, kendisi hariç tüm kayıtlarla tanımaya çalışır (gerçek tanımanın provası):
#      doğru / yanlış kişi / emin değil / tanınmadı sayıları
# Sistemi durdurmaya gerek yok; sadece okur, hiçbir şeyi değiştirmez.

import itertools
import os
import sys

import face_recognition
import numpy as np

from ayarlar import MARJ, TOLERANS
from veri import KISILER, benzerlik, ogrenci_adlari, ogrenci_dosyalari

adlar = ogrenci_adlari()
print("Fotoğraflar okunuyor...")
kayitlar = []   # (numara, dosya, yüz kodu)
for numara, dosyalar in ogrenci_dosyalari().items():
    if numara not in adlar:
        continue
    for dosya in dosyalar:
        kodlar = face_recognition.face_encodings(face_recognition.load_image_file(os.path.join(KISILER, dosya)))
        if len(kodlar) == 1:
            kayitlar.append((numara, dosya, kodlar[0]))

ogrenciler = sorted({n for n, _, _ in kayitlar})
if len(ogrenciler) < 2:
    sys.exit("Ölçüm için en az 2 kayıtlı öğrenci gerekiyor.")
ad = lambda n: f"{adlar.get(n, '?')} ({n})"
mesafe = lambda a, b: float(np.linalg.norm(a - b))
yuzde = lambda m: f"%{benzerlik(m)} ({m:.2f})"

print(f"\n{len(ogrenciler)} öğrenci, {len(kayitlar)} fotoğraf. Ayarlar: TOLERANS={TOLERANS}, MARJ={MARJ}\n")

# 1) Aynı öğrencinin fotoğrafları arası
print("1) AYNI ÖĞRENCİ — kendi fotoğrafları birbirine ne kadar benziyor (yüksek = iyi)")
ayni = []
for n in ogrenciler:
    foto = [(d, k) for m, d, k in kayitlar if m == n]
    if len(foto) < 2:
        print(f"   {ad(n):40} tek fotoğraf — daha fazla açıdan fotoğraf eklenmeli")
        continue
    ciftler = [(mesafe(a[1], b[1]), a[0], b[0]) for a, b in itertools.combinations(foto, 2)]
    ayni += [c[0] for c in ciftler]
    en_uzak = max(ciftler)
    uyari = "  <-- bu fotoğraflardan biri kötü olabilir" if en_uzak[0] > TOLERANS + 0.1 else ""
    print(f"   {ad(n):40} {len(foto)} foto, en az benzeyen iki fotoğrafı {yuzde(en_uzak[0])} "
          f"[{en_uzak[1]} - {en_uzak[2]}]{uyari}")

# 2) Farklı öğrenciler arası
print("\n2) FARKLI ÖĞRENCİLER — birbirine en çok benzeyen çiftler (düşük = iyi, %50 üstü tehlikeli)")
cift_en_yakin = {}
for (n1, d1, k1), (n2, d2, k2) in itertools.combinations(kayitlar, 2):
    if n1 != n2:
        anahtar = tuple(sorted((n1, n2)))
        cift_en_yakin[anahtar] = min(mesafe(k1, k2), cift_en_yakin.get(anahtar, 9.0))
farkli = sorted((m, a, b) for (a, b), m in cift_en_yakin.items())
for m, a, b in farkli[:8]:
    if m < TOLERANS:
        durum = "RİSKLİ: eşiğin altında, karıştırılabilir"
    elif m < TOLERANS + MARJ:
        durum = "dikkat: eşiğe çok yakın"
    else:
        durum = "güvenli"
    print(f"   {yuzde(m):12} {ad(a)}  ~  {ad(b)}   [{durum}]")

# 3) Tanıma provası (her fotoğraf, kendisi dışındaki kayıtlarla)
print("\n3) TANIMA PROVASI — her fotoğraf, kendisi hariç kayıtlarla tanınmaya çalışılır")
sonuc = {"dogru": 0, "yanlis": 0, "belirsiz": 0, "tanimadi": 0}
yanlislar = []
for numara, dosya, kod in kayitlar:
    en_yakin = {}
    for n2, d2, k2 in kayitlar:
        if d2 != dosya:
            en_yakin[n2] = min(mesafe(kod, k2), en_yakin.get(n2, 9.0))
    siralama = sorted((m, n) for n, m in en_yakin.items())
    d1, n1 = siralama[0]
    if numara not in en_yakin:       # öğrencinin başka fotoğrafı yok, tanınamaz (beklenen)
        sonuc["tanimadi"] += 1
    elif d1 >= TOLERANS:
        sonuc["tanimadi"] += 1
    elif len(siralama) > 1 and siralama[1][0] - d1 < MARJ:
        sonuc["belirsiz"] += 1
    elif n1 == numara:
        sonuc["dogru"] += 1
    else:
        sonuc["yanlis"] += 1
        yanlislar.append(f"{dosya} -> {ad(n1)} sanıldı ({yuzde(d1)})")
toplam = len(kayitlar)
print(f"   doğru: {sonuc['dogru']}/{toplam}   YANLIŞ KİŞİ: {sonuc['yanlis']}   "
      f"emin değil (?): {sonuc['belirsiz']}   tanınmadı: {sonuc['tanimadi']}")
for y in yanlislar:
    print("   !", y)

# Öneri
print("\nÖNERİ")
en_yakin_farkli = farkli[0][0]
en_uzak_ayni = max(ayni) if ayni else None
if sonuc["yanlis"]:
    print(f"   Yanlış kişi tanındı. TOLERANS'ı düşürün (ör. {max(0.35, en_yakin_farkli - 0.05):.2f}) "
          "ya da karışan öğrencilere farklı açılardan yeni fotoğraf ekleyin.")
elif en_yakin_farkli < TOLERANS + MARJ:
    print(f"   En benzer iki farklı öğrenci {yuzde(en_yakin_farkli)}: eşiğe yakın. Sistem bu durumda '?' diyerek "
          "bekler (yanlış giriş vermez); gerekirse TOLERANS'ı biraz düşürün.")
else:
    print(f"   Güvenli: en benzer iki farklı öğrenci bile {yuzde(en_yakin_farkli)} (tanıma eşiği %50).")
if sonuc["tanimadi"] > toplam * 0.2:
    print("   Çok fotoğraf tanınmadı: öğrencilere daha fazla fotoğraf ekleyin ya da TOLERANS'ı biraz artırın"
          + (f" (aynı kişinin en az benzeyen iki fotoğrafı {yuzde(en_uzak_ayni)})." if en_uzak_ayni else "."))
