# Kameradan görüntü alır, yüzleri tanır, kayıtları veritabanına yazar.
# Kameraya SADECE bu program bağlanır (ESP32-CAM aynı anda tek izleyiciye görüntü verir).
# site.py görüntüyü buradan alır:
#   http://localhost:8082/canli  -> yüzleri işaretlenmiş canlı görüntü
#   http://localhost:8082/kare   -> en son ham kare (kişi eklerken kullanılır)
#   http://localhost:8082/kare?yon=sag -> o yöne bakarken yakalanan son kare (rehberli kayıt)
#   http://localhost:8082/ham    -> işaretsiz canlı görüntü (kayıt ekranı aynalayarak gösterir)
#   http://localhost:8082/poz    -> kameradaki yüzün baş yönü; çağrıldıkça "kayıt modu" açık kalır
# Kayıt modunda giriş olayı yazılmaz (kayıt olan kişiye "Kaydınız yok" denmesin).
#   http://localhost:8082/izleme?test=1 -> görevlinin "Test modu": açıkken de olay yazılmaz.
# yuzler.pkl değişince (siteden kişi eklenince/silinince) yeni yüzleri kendiliğinden yükler.
# Kişiler içeride öğrenci numarasıyla ayırt edilir, ekranda ad soyadıyla gösterilir.
#
# Bir yüz onaylanınca (art arda ONAY_KARE analiz) bir olay yazılır:
#   giris      -> öğrenci bugün ilk kez geldi; boş sıralardan rastgele bir sıra no verilir
#   tekrar     -> öğrenci bugün zaten giriş yapmış ("zaten giriş yaptınız")
#   bilinmeyen -> kayıtlı olmayan yüz
#   listede_yok -> kayıtlı ama aktif sınavın listesinde değil
#   canlilik_yok -> tanındı ama CANLILIK_SURE içinde göz kırpmadı (fotoğraf/ekran olabilir)
# Canlılık: sonuç "giris" olacaksa önce göz kırpması beklenir. Bu sırada ayrı bir iş parçacığı
# kameradan gelen HER karede göz açıklığını ölçer (kare başına ~1,5 ms), kırpmayı kaçırmaz.
# Bekleme durumu /canlilik adresinden okunur; kiosk "Lütfen gözlerinizi kırpın" gösterir.
# Kiosk ekranı (site.py /kiosk) bu olayları okuyup gösterir.

import logging
import os
import threading
import time
from datetime import date, datetime

import cv2
import face_recognition
import numpy as np
from flask import Flask, Response, jsonify, request
from PIL import Image, ImageDraw, ImageFont

from ayarlar import (AYRILMA, CANLILIK, CANLILIK_SURE, GORUNTU_AYNA, KAMERA, KAMERA_DONDUR, KAYIT_DUZ_ESIK,
                     KAYIT_YAN_ESIK, KIRPMA_ORANI, KOLTUK_SAYISI, MARJ, ONAY_KARE, TOLERANS)
from veri import (YUZ_DOSYASI, aktif_sinav, benzerlik, bos_sira_sec, db_ac, giris_durumu, ogrenci_adlari,
                  otomatik_sinav_durumu, sinav_zamani_getir, yuzleri_oku)

ISLEM_ARALIGI = 0.2   # iki yüz analizi arasında en az bu kadar saniye bekle (işlemciyi yormamak için)
BILINMEYEN = "Bilinmeyen"
BELIRSIZ = "?"   # iki kayıtlı kişiye de benziyor; karar verilmez, sonraki kareler beklenir
YAZI_TIPLERI = ["/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/google-noto/NotoSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]

kilit = threading.Lock()
son_kare = None    # kameradan gelen en son kare
son_yuzler = []    # son analizde bulunan yüzler: [(konum, yazı, durum, ayrıntı), ...] (bkz. etiket)
kayit_modu_bitis = 0.0   # /poz çağrıldıkça 3 sn uzar; site kayıt yaparken açık tutar
test_modu_bitis = 0.0    # /izleme?test=1 çağrıldıkça 3 sn uzar; Canlı İzleme sayfası "Test modu" açıkken
                         # açık tutar. Sayfa kapanınca kendiliğinden biter (kiosk yanlışlıkla kilitli kalmaz).
son_poz = {"zaman": 0.0, "yuz": 0, "yon": None, "oran": None}
poz_kareleri = {}        # yon -> (zaman, kare): o yöne bakarken yakalanan son kare
bekleyen = None          # canlılık bekleyen öğrenci (sözlük) ya da None; bkz. canlilik_baslat


def goz_acikligi(nokta):
    """İki gözün ortalama açıklık oranı (göz yüksekliği / göz genişliği). Açık ~0.25, kapalı ~0.08."""
    def oran(g):
        g = np.asarray(g, dtype=float)
        uzaklik = lambda a, b: np.linalg.norm(g[a] - g[b])
        return (uzaklik(1, 5) + uzaklik(2, 4)) / (2 * uzaklik(0, 3) + 1e-6)
    return (oran(nokta["left_eye"]) + oran(nokta["right_eye"])) / 2


def canlilik_baslat(numara, isim, konum, kare, simdi=None):
    global bekleyen
    simdi = simdi if simdi is not None else time.time()
    bekleyen = {"numara": numara, "isim": isim, "konum": konum, "kare": kare,
                "baslangic": simdi, "son_gorulme": simdi, "olcumler": [],
                "acik": None, "goz": None, "kapandi": False, "kirpti": False}
    print(f"{datetime.now():%H:%M:%S} CANLILIK bekleniyor: {isim} ({numara})")


def canlilik_izle():
    """Ayrı iş parçacığı: canlılık bekleyen biri varsa her yeni karede göz açıklığını ölç.
    Göz, kişinin normal açıklığının KIRPMA_ORANI altına iner ve sonra tekrar açılırsa: kırptı."""
    islenen = None
    while True:
        b = bekleyen
        with kilit:
            kare = son_kare
        if b is None or kare is None or kare is islenen or b["kirpti"]:
            time.sleep(0.01)
            continue
        islenen = kare
        try:
            rgb = cv2.cvtColor(kare, cv2.COLOR_BGR2RGB)
            goz = goz_acikligi(face_recognition.face_landmarks(rgb, [b["konum"]])[0])
        except (IndexError, ValueError):
            continue
        goz_olcumu_ekle(b, goz, kare)


def goz_olcumu_ekle(b, goz, kare):
    """Bir göz açıklığı ölçümünü canlılık bekleyen kişiye ekle; kırptıysa b["kirpti"] = True.
    Göz, kişinin normal açıklığının KIRPMA_ORANI altına iner ve sonra tekrar açılırsa: kırptı."""
    b["olcumler"] = (b["olcumler"] + [goz])[-90:]
    if len(b["olcumler"]) < 5:
        return
    acik = float(np.percentile(b["olcumler"], 90))   # kişinin gözü açıkken normal değeri
    b["acik"], b["goz"] = acik, goz
    if goz < acik * KIRPMA_ORANI:
        b["kapandi"] = True
    elif b["kapandi"] and goz > acik * 0.85:
        b["kirpti"] = True
        b["kare"] = kare   # gözler açıkken çekilen kare, giriş fotoğrafı olur


def kayit_modunda():
    return time.time() < kayit_modu_bitis


def test_modunda():
    return time.time() < test_modu_bitis


def bas_yonu(rgb, konum):
    """Tek yüz için baş yönü: ('duz' | 'sag' | 'sol' | None, oran).
    Kamera görüntüsü aynalı değilse kişi kendi sağına dönünce oran eksiye gider.
    (Site sağ/sol karışsa bile çalışacak şekilde yazıldı.)"""
    nokta = face_recognition.face_landmarks(rgb, [konum], model="small")[0]
    burun = np.mean(nokta["nose_tip"], axis=0)
    goz1, goz2 = np.mean(nokta["left_eye"], axis=0), np.mean(nokta["right_eye"], axis=0)
    mesafe = np.linalg.norm(goz2 - goz1)
    if mesafe < 1:
        return None, None
    oran = float((burun[0] - (goz1[0] + goz2[0]) / 2) / mesafe)
    if abs(oran) < KAYIT_DUZ_ESIK:
        return "duz", oran
    if oran <= -KAYIT_YAN_ESIK:
        return "sag", oran
    if oran >= KAYIT_YAN_ESIK:
        return "sol", oran
    return None, oran   # arada: ne düz ne yeterince yan


def yazi_tipi_bul():
    # OpenCV Türkçe harfleri (ç, ş, ğ, ı...) yazamadığı için isimleri Pillow ile yazıyoruz
    for yol in YAZI_TIPLERI:
        if os.path.exists(yol):
            return ImageFont.truetype(yol, 18)
    return ImageFont.load_default(size=18)


YAZI = yazi_tipi_bul()


# ---------- Kamera ----------

DONDURME = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
# baslat.py telefon kamerasına ulaşamazsa webcam'e geçer ve bunu bu ortam değişkenleriyle bildirir
KAMERA = os.environ.get("SINAV_KAMERA") or KAMERA
KAMERA_DONDUR = int(os.environ.get("SINAV_KAMERA_DONDUR", KAMERA_DONDUR))


def kamera_oku():
    global son_kare
    kamera = cv2.VideoCapture(KAMERA)
    while True:
        ok, kare = kamera.read()
        if not ok:
            print("Görüntü yok, 2 sn sonra yeniden bağlanılıyor...")
            time.sleep(2)
            kamera.release()
            kamera = cv2.VideoCapture(KAMERA)
            continue
        if KAMERA_DONDUR in DONDURME:   # ör. telefon dik tutulunca yan gelen görüntüyü düzelt
            kare = cv2.rotate(kare, DONDURME[KAMERA_DONDUR])
        with kilit:
            son_kare = kare


# ---------- Tanıma ----------

numaralar, kodlar, adlar, yuz_dosya_zamani = [], [], {}, None


def yuzleri_yukle():
    """yuzler.pkl değiştiyse yüzleri ve öğrenci adlarını yeniden yükle."""
    global numaralar, kodlar, adlar, yuz_dosya_zamani
    try:
        zaman = os.path.getmtime(YUZ_DOSYASI)
    except FileNotFoundError:
        zaman = None
    if zaman == yuz_dosya_zamani:
        return
    yuz_dosya_zamani = zaman
    numaralar, kodlar = yuzleri_oku()
    adlar = ogrenci_adlari()   # site önce öğrenciyi veritabanına, sonra yüzü yuzler.pkl'ye yazar
    kisiler = ", ".join(f"{adlar.get(n, '?')} ({n})" for n in sorted(set(numaralar))) or "-"
    print(f"{len(kodlar)} kayıtlı yüz yüklendi: {kisiler}")


def olay_turu(db, numara):
    """Bu öğrenci şimdi gelse olay ne olurdu? (isim, tur, sira, sinav_id) — veritabanına yazmaz.
    Aktif sınav varsa: sadece o sınavın listesindekiler girebilir, sadece giriş saatlerinde
    girilebilir (erken / gec), "zaten girdi mi" ve sıra numaraları o sınava göredir.
    Aktif sınav yoksa (serbest mod) saat kuralı yoktur, takvim gününe göredir."""
    sinav = aktif_sinav(db)
    if sinav:
        sinav_id, _, koltuk = sinav
        kapsam, deger = "sinav_id = ?", sinav_id
    else:
        sinav_id, koltuk = None, KOLTUK_SAYISI
        kapsam, deger = "sinav_id IS NULL AND zaman LIKE ?", f"{date.today()}%"
    isim, tur, sira = BILINMEYEN, "bilinmeyen", None

    if numara:
        isim = adlar.get(numara, BILINMEYEN)
        listede = sinav is None or db.execute(
            "SELECT 1 FROM sinav_ogrencileri WHERE sinav_id = ? AND ogrenci_no = ?",
            (sinav_id, numara)).fetchone()
        onceki = db.execute(f"SELECT sira FROM olaylar WHERE ogrenci_no = ? AND tur = 'giris' "
                            f"AND {kapsam}", (numara, deger)).fetchone()
        pencere = giris_durumu(sinav_zamani_getir(db, sinav_id)) if sinav else "acik"
        if not listede:
            tur = "listede_yok"
        elif onceki:                 # zaten içeride: saatten bağımsız "zaten giriş yaptınız"
            tur, sira = "tekrar", onceki[0]
        elif pencere == "erken":     # giriş penceresi henüz açılmadı
            tur = "erken"
        elif pencere == "kapali":    # sınav başladı (ve geç giriş toleransı da bitti)
            tur = "gec"
        else:
            tur = "giris"
            sira = bos_sira_sec(db, kapsam, deger, koltuk)   # salon doluysa None
    return isim, tur, sira, sinav_id


def olay_yaz(db, numara, kare, konum, zorla_tur=None):
    """Onaylanan bir yüz için olayı yaz. zorla_tur="canlilik_yok": göz kırpmadı."""
    simdi = datetime.now()
    zaman = simdi.strftime("%Y-%m-%d %H:%M:%S")
    isim, tur, sira, sinav_id = olay_turu(db, numara)
    if zorla_tur:
        tur, sira = zorla_tur, None

    ust, sag, alt, sol = konum
    # Aynı anda yazılan iki olayın fotoğrafı birbirinin üstüne yazılmasın: ad varsa sonuna -2, -3... eklenir
    kok = f"fotolar/{simdi.strftime('%Y-%m-%d_%H-%M-%S-%f')[:-3]}_{numara or 'bilinmeyen'}"
    foto, ek = f"{kok}.jpg", 1
    while os.path.exists(f"static/{foto}"):
        ek += 1
        foto = f"{kok}-{ek}.jpg"
    cv2.imwrite(f"static/{foto}", kare[max(0, ust - 40):alt + 40, max(0, sol - 40):sag + 40])
    db.execute("INSERT INTO olaylar (isim, ogrenci_no, zaman, foto, tur, sira, sinav_id) "
               "VALUES (?, ?, ?, ?, ?, ?, ?)", (isim, numara, zaman, foto, tur, sira, sinav_id))
    db.commit()
    print(zaman, tur.upper(), isim, f"({numara})" if numara else "", f"sıra {sira}" if sira else "",
          f"[sınav {sinav_id}]" if sinav_id else "")


def poz_guncelle(rgb, kare, konumlar):
    """Kayıt modunda: tek yüz varsa baş yönünü bul, o yöne ait kareyi sakla."""
    global son_poz
    yon, oran = (None, None)
    if len(konumlar) == 1:
        yon, oran = bas_yonu(rgb, konumlar[0])
    simdi = time.time()
    with kilit:
        son_poz = {"zaman": simdi, "yuz": len(konumlar), "yon": yon,
                   "oran": round(oran, 3) if oran is not None else None}
        if yon:
            poz_kareleri[yon] = (simdi, kare)


def canlilik_sonuclandir(db, simdi):
    """Canlılık bekleyen öğrenci: kırptıysa giriş yaz, süre dolduysa canlilik_yok yaz,
    kameradan ayrıldıysa sessizce vazgeç."""
    global bekleyen
    b = bekleyen
    if b is None:
        return
    if b["kirpti"]:
        olay_yaz(db, b["numara"], b["kare"], b["konum"])
    elif simdi - b["baslangic"] > CANLILIK_SURE:
        olay_yaz(db, b["numara"], b["kare"], b["konum"], zorla_tur="canlilik_yok")
    elif simdi - b["son_gorulme"] > 1.5:
        print(f"{datetime.now():%H:%M:%S} CANLILIK vazgeçildi: {b['isim']} kameradan ayrıldı")
    else:
        return
    bekleyen = None


class AkisDurumu:
    """Tanıma döngüsünün kareler arasında hatırladıkları."""
    def __init__(self):
        self.ardisik = {}          # numara -> art arda kaç analizde görüldü
        self.son_gorulme = {}      # numara -> en son ne zaman görüldü
        self.olay_verildi = set()  # kameranın önündeyken olayı zaten yazılmış numaralar


def kare_analiz(rgb):
    """Karedeki yüzleri bul ve tanı. Döner: (konumlar, bulunanlar, etiketler)
    bulunanlar: [(konum, numara | None | BELIRSIZ)], etiketler: [(konum, yazı, durum, ayrıntı)]"""
    konumlar = face_recognition.face_locations(rgb)
    bulunanlar, etiketler = [], []
    for konum, kod in zip(konumlar, face_recognition.face_encodings(rgb, konumlar)):
        numara, siralama = kisi_bul(kod)
        bulunanlar.append((konum, numara))
        etiketler.append((konum, *etiket(numara, siralama)))
    return konumlar, bulunanlar, etiketler


def olaylari_isle(db, kare, rgb, konumlar, bulunanlar, durum, simdi=None):
    """Bir analizin sonucuna göre olay kararlarını ver (yazılacak olay, canlılık bekleme vb.).
    simdi: testlerde sahte saat vermek için."""
    global bekleyen
    simdi = simdi if simdi is not None else time.time()
    # Tek bir karedeki eşleşmeye güvenme: aynı kişi art arda ONAY_KARE analizde
    # görülmediyse kayıt düşme. Arada görülmezse sayaç sıfırlanır.
    durum.ardisik = {numara: durum.ardisik.get(numara, 0) + 1 for _, numara in bulunanlar}
    for _, numara in bulunanlar:
        durum.son_gorulme[numara] = simdi
    # AYRILMA saniyedir görünmeyen kişi kameradan ayrılmış sayılır; geri gelirse yeni olay olur
    durum.olay_verildi = {n for n in durum.olay_verildi if simdi - durum.son_gorulme.get(n, 0) < AYRILMA}

    if kayit_modunda() or test_modunda():
        # Kayıt sırasında ya da görevlinin test modunda olay yazma. Kameradakileri "olayı verilmiş"
        # say ki mod bitince hemen "Hoş geldiniz" çıkmasın; kişi ayrılıp geri gelince normal giriş olur.
        durum.olay_verildi |= {numara for _, numara in bulunanlar}
        if kayit_modunda():
            poz_guncelle(rgb, kare, konumlar)
        bekleyen = None
        return

    # Canlılık bekleyen kişinin yerini güncelle (göz ölçümü doğru yüze baksın)
    if bekleyen:
        for konum, numara in bulunanlar:
            if numara == bekleyen["numara"]:
                bekleyen["konum"], bekleyen["son_gorulme"] = konum, simdi
    canlilik_sonuclandir(db, simdi)

    for konum, numara in bulunanlar:
        if numara == BELIRSIZ:   # emin değilken karar verme, sonraki kareleri bekle
            continue
        if durum.ardisik[numara] < ONAY_KARE or numara in durum.olay_verildi:
            continue
        if CANLILIK and numara:
            isim, tur, _, _ = olay_turu(db, numara)
            if tur == "giris":   # içeri alınacaksa önce göz kırpsın
                if bekleyen is not None:
                    continue     # biri zaten bekliyor; bu kişi sırasını beklesin
                durum.olay_verildi.add(numara)
                canlilik_baslat(numara, isim, konum, kare, simdi)
                continue
        durum.olay_verildi.add(numara)
        olay_yaz(db, numara, kare, konum)


def tani():
    global son_yuzler
    db = db_ac()
    os.makedirs("static/fotolar", exist_ok=True)
    durum = AkisDurumu()
    islenen = None
    son_kontrol = 0.0
    while True:
        yuzleri_yukle()
        if time.time() - son_kontrol > 5:   # sınavları saatine göre kendiliğinden başlat / bitir
            otomatik_sinav_durumu(db)
            son_kontrol = time.time()
        with kilit:
            kare = son_kare
        if kare is None or kare is islenen:
            time.sleep(0.05)
            continue
        islenen = kare
        baslangic = time.time()

        rgb = cv2.cvtColor(kare, cv2.COLOR_BGR2RGB)
        konumlar, bulunanlar, etiketler = kare_analiz(rgb)
        olaylari_isle(db, kare, rgb, konumlar, bulunanlar, durum)

        with kilit:
            son_yuzler = etiketler
        time.sleep(max(0, ISLEM_ARALIGI - (time.time() - baslangic)))


def kisi_bul(kod):
    """Bir yüz kodunu kayıtlı öğrencilerle karşılaştır.
    Döner: (numara | None | BELIRSIZ, [(mesafe, numara), ...] en yakından uzağa)
      numara   -> en yakın öğrenci TOLERANS'tan yakın VE ikinci en yakın öğrenciden en az MARJ daha yakın
      BELIRSIZ -> yeterince yakın biri var ama başka biri de neredeyse o kadar yakın (benzer iki kişi)
      None     -> kimseye yeterince yakın değil (kayıtsız)"""
    if not kodlar:
        return None, []
    mesafeler = face_recognition.face_distance(kodlar, kod)
    en_yakin = {}   # her öğrencinin fotoğraflarından en yakın olanı
    for numara, mesafe in zip(numaralar, mesafeler):
        en_yakin[numara] = min(float(mesafe), en_yakin.get(numara, 9.0))
    siralama = sorted((m, n) for n, m in en_yakin.items())
    d1, n1 = siralama[0]
    if d1 >= TOLERANS:
        return None, siralama
    if len(siralama) > 1 and siralama[1][0] - d1 < MARJ:
        return BELIRSIZ, siralama
    return n1, siralama


def etiket(numara, siralama):
    """Ekranda yüzün üstüne yazılacaklar: (yazı, durum, ayrıntı). Ayrıntı (benzerlik yüzdesi)
    sadece görevlinin Tanıma ekranında görünür; kiosklarda yazmaz."""
    if numara == BELIRSIZ:   # iki kişiye de benziyor: ikisini de yaz ki neden emin olmadığı anlaşılsın
        (d1, n1), (d2, n2) = siralama[:2]
        return "?", "belirsiz", f"{adlar.get(n1, n1)} %{benzerlik(d1)} / {adlar.get(n2, n2)} %{benzerlik(d2)}"
    if numara:
        return adlar.get(numara, BILINMEYEN), "tanindi", f"%{benzerlik(siralama[0][0])} benziyor"
    return BILINMEYEN, "bilinmeyen", ""   # kayıtsız kişide yüzde gösterilmez


# ---------- Yayın (site.py için) ----------

# Kutu ve yazı renkleri (RGB) — sadece PAÜ mavisi tonları:
# tanındı: açık mavi, kayıtsız: lacivert, emin değil: beyaz kutu + lacivert yazı
RENKLER = {"tanindi": (0, 133, 208), "bilinmeyen": (0, 70, 132), "belirsiz": (255, 255, 255)}
YAZI_RENGI = {"tanindi": (255, 255, 255), "bilinmeyen": (255, 255, 255), "belirsiz": (0, 70, 132)}


def isaretle(kare, yuzler, detay=False):
    """Yüzlerin etrafına kutu çiz ve ismini yaz. Tanınan: açık mavi, kayıtsız: lacivert,
    emin değil: beyaz "?". detay=True ise benzerlik yüzdeleri de yazılır (görevli ekranı için)."""
    resim = Image.fromarray(cv2.cvtColor(kare, cv2.COLOR_BGR2RGB))
    ciz = ImageDraw.Draw(resim)
    for (ust, sag, alt, sol), isim, durum, ayrinti in yuzler:
        renk = RENKLER[durum]
        if detay and ayrinti:
            isim = f"{isim} · {ayrinti}" if durum != "belirsiz" else f"? {ayrinti}"
        ciz.rectangle([sol, ust, sag, alt], outline=renk, width=3)
        _, _, gen, yuk = ciz.textbbox((0, 0), isim, font=YAZI)
        y = ust - yuk - 10 if ust - yuk - 10 >= 0 else alt
        ciz.rectangle([sol, y, sol + gen + 12, y + yuk + 10], fill=renk)
        ciz.text((sol + 6, y + 4), isim, font=YAZI, fill=YAZI_RENGI[durum])
    return cv2.cvtColor(np.array(resim), cv2.COLOR_RGB2BGR)


app = Flask(__name__)


def jpeg_parcasi(kare):
    _, jpg = cv2.imencode(".jpg", kare)
    return b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"


def aynala(kare, yuzler):
    """Görüntüyü yatayda çevir (ayna gibi) ve yüz kutularının yerini de ona göre taşı.
    İsimler çevrilmiş görüntünün üstüne yazıldığı için yazılar ters çıkmaz."""
    genislik = kare.shape[1]
    return (cv2.flip(kare, 1),
            [((ust, genislik - sol, alt, genislik - sag), *geri) for (ust, sag, alt, sol), *geri in yuzler])


def yayin(isaretli, detay=False):
    def kareler():
        gonderilen = None
        while True:
            with kilit:
                kare, yuzler = son_kare, list(son_yuzler)
            if kare is None or kare is gonderilen:
                time.sleep(0.03)
                continue
            gonderilen = kare
            if GORUNTU_AYNA:   # sadece gösterim; tanıma kameranın verdiği görüntüyle yapılır
                kare, yuzler = aynala(kare, yuzler)
            yield jpeg_parcasi(isaretle(kare, yuzler, detay) if isaretli and yuzler else kare)
    return Response(kareler(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/canli")
def canli():
    # ?detay=1 -> yüzlerin üstünde mesafeler de yazar (görevlinin Tanıma ekranı, ayar yaparken)
    return yayin(isaretli=True, detay=bool(request.args.get("detay")))


@app.route("/ham")
def ham():
    return yayin(isaretli=False)


@app.route("/kare")
def kare():
    yon = request.args.get("yon")
    with kilit:
        if yon:
            # Rehberli kayıt: o yöne bakarken yakalanan kare (son 1 saniye içindeyse)
            zaman, kare = poz_kareleri.get(yon, (0, None))
            if time.time() - zaman > 1:
                kare = None
        else:
            kare = son_kare
    if kare is None:
        return "Uygun kare yok", 404 if yon else 503
    _, jpg = cv2.imencode(".jpg", kare)
    return Response(jpg.tobytes(), mimetype="image/jpeg")


@app.route("/canlilik")
def canlilik():
    """Kiosk için: göz kırpması beklenen biri var mı, ne kadar süre kaldı, göz ne kadar açık."""
    b = bekleyen
    if b is None:
        return jsonify(bekliyor=False, test_modu=test_modunda())
    goz = round(min(1.2, b["goz"] / b["acik"]), 2) if b["goz"] and b["acik"] else None
    return jsonify(bekliyor=True, isim=b["isim"], kimlik=b["baslangic"], goz=goz,
                   kalan=max(0, round(CANLILIK_SURE - (time.time() - b["baslangic"]), 1)),
                   esik=KIRPMA_ORANI, kirpti=b["kirpti"], test_modu=test_modunda())


@app.route("/izleme")
def izleme():
    """Canlı İzleme sayfası çağırır. ?test=1 -> test modunu 3 sn daha açık tut (olay yazılmaz)."""
    global test_modu_bitis
    if request.args.get("test"):
        test_modu_bitis = time.time() + 3
    return jsonify(test_modu=test_modunda())


@app.route("/poz")
def poz():
    """Baş yönünü döndürür ve kayıt modunu 3 saniye daha açık tutar."""
    global kayit_modu_bitis
    kayit_modu_bitis = time.time() + 3
    with kilit:
        durum = dict(son_poz)
    if time.time() - durum["zaman"] > 1.5:   # henüz analiz yok ya da eski
        durum = {"yuz": 0, "yon": None, "oran": None}
    durum.pop("zaman", None)
    return jsonify(durum)


if __name__ == "__main__":
    threading.Thread(target=kamera_oku, daemon=True).start()
    threading.Thread(target=tani, daemon=True).start()
    threading.Thread(target=canlilik_izle, daemon=True).start()
    print("Kamera dinleniyor... (durdurmak için Ctrl+C)")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)   # her istek için log basmasın
    app.run(host="127.0.0.1", port=8082, threaded=True)
