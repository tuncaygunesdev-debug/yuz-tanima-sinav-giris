# Programların ortak kullandığı veri işlemleri.
#
# Kişiler öğrenci numarasıyla ayırt edilir, ekranda ad soyadıyla gösterilir.
#   kayitlar.db / ogrenciler  -> ogrenci_no, ad_soyad, kvkk_onay (zaman), kayit_zamani
#   kayitlar.db / olaylar     -> kapıdaki her olay (isim, ogrenci_no, zaman, foto, tur, sira, sinav_id)
#        tur: "giris" (ilk giriş, sira = verilen sıra no), "tekrar" (zaten girmiş),
#             "listede_yok" (kayıtlı ama aktif sınavın listesinde değil),
#             "bilinmeyen" (kayıtlı olmayan yüz), "canlilik_yok" (göz kırpmadı),
#             "erken" (sınav girişi henüz açılmadı), "gec" (sınav başladı, giriş kapandı)
#        aciklama: ör. "Görevli onayıyla" (yoklamadan elle verilen giriş)
#   kayitlar.db / sinavlar    -> id, ad, tarih, saat, koltuk_sayisi, durum (hazir / aktif / bitti),
#        sure_dk (sınav süresi), acilis_dk (giriş kaç dk önce açılır), gec_dk (başladıktan sonra
#        kaç dk daha girilebilir). Giriş penceresi: [başlangıç - acilis_dk, başlangıç + gec_dk).
#        Sınav, giriş açılınca kendiliğinden aktif olur, süresi dolunca biter (otomatik_sinav_durumu).
#   kayitlar.db / sinav_ogrencileri -> hangi öğrenci hangi sınava girecek
#   Aktif sınav varsa "zaten girdi mi" ve sıra numarası o sınava göre; yoksa takvim gününe göre.
#   kisiler/<numara>_<sira>.jpg -> öğrencinin kayıt fotoğrafları
#   yuzler.pkl                -> (numaralar, yüz kodları); tani.py bunu okur

import os
import pickle
import random
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

from ayarlar import TOLERANS

DB = "kayitlar.db"
YUZ_DOSYASI = "yuzler.pkl"
KISILER = "kisiler"
UZANTILAR = (".jpg", ".jpeg", ".png")


def db_ac():
    db = sqlite3.connect(DB, timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS olaylar "
               "(id INTEGER PRIMARY KEY, isim TEXT, zaman TEXT, foto TEXT)")
    kolonlar = {k[1] for k in db.execute("PRAGMA table_info(olaylar)")}
    if "ogrenci_no" not in kolonlar:
        db.execute("ALTER TABLE olaylar ADD COLUMN ogrenci_no TEXT")
    if "tur" not in kolonlar:
        db.execute("ALTER TABLE olaylar ADD COLUMN tur TEXT")
        db.execute("ALTER TABLE olaylar ADD COLUMN sira INTEGER")
        db.execute("UPDATE olaylar SET tur = CASE WHEN ogrenci_no IS NULL "
                   "THEN 'bilinmeyen' ELSE 'giris' END")
    if "sinav_id" not in kolonlar:
        db.execute("ALTER TABLE olaylar ADD COLUMN sinav_id INTEGER")
    if "aciklama" not in kolonlar:
        db.execute("ALTER TABLE olaylar ADD COLUMN aciklama TEXT")
    db.execute("CREATE TABLE IF NOT EXISTS ogrenciler ("
               "ogrenci_no TEXT PRIMARY KEY, ad_soyad TEXT NOT NULL, "
               "kvkk_onay TEXT NOT NULL, kayit_zamani TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS sinavlar ("
               "id INTEGER PRIMARY KEY, ad TEXT NOT NULL, tarih TEXT NOT NULL, saat TEXT NOT NULL, "
               "koltuk_sayisi INTEGER NOT NULL, durum TEXT NOT NULL DEFAULT 'hazir', "
               "baslama TEXT, bitis TEXT)")
    sinav_kolonlari = {k[1] for k in db.execute("PRAGMA table_info(sinavlar)")}
    for kolon, varsayilan in (("sure_dk", 60), ("acilis_dk", 30), ("gec_dk", 0)):
        if kolon not in sinav_kolonlari:
            db.execute(f"ALTER TABLE sinavlar ADD COLUMN {kolon} INTEGER NOT NULL DEFAULT {varsayilan}")
    db.execute("CREATE TABLE IF NOT EXISTS sinav_ogrencileri ("
               "sinav_id INTEGER NOT NULL, ogrenci_no TEXT NOT NULL, "
               "PRIMARY KEY (sinav_id, ogrenci_no))")
    db.commit()
    return db


def aktif_sinav(db):
    """(id, ad, koltuk_sayisi) ya da None. Aynı anda en fazla bir sınav aktif olur."""
    return db.execute("SELECT id, ad, koltuk_sayisi FROM sinavlar WHERE durum = 'aktif' "
                      "ORDER BY id DESC LIMIT 1").fetchone()


def sinav_zamani(tarih, saat, sure_dk, acilis_dk, gec_dk):
    """Sınavın önemli anları: giriş açılışı, sınav başlangıcı, giriş kapanışı, sınav bitişi."""
    baslangic = datetime.strptime(f"{tarih} {saat}", "%Y-%m-%d %H:%M")
    return {"acilis": baslangic - timedelta(minutes=acilis_dk), "baslangic": baslangic,
            "kapanis": baslangic + timedelta(minutes=gec_dk), "bitis": baslangic + timedelta(minutes=sure_dk)}


def sinav_zamani_getir(db, sinav_id):
    satir = db.execute("SELECT tarih, saat, sure_dk, acilis_dk, gec_dk FROM sinavlar WHERE id = ?",
                       (sinav_id,)).fetchone()
    return sinav_zamani(*satir) if satir else None


def giris_durumu(zaman, simdi=None):
    """'erken' (giriş henüz açılmadı), 'acik' ya da 'kapali' (sınav başladı / tolerans bitti)."""
    simdi = simdi or datetime.now()
    if simdi < zaman["acilis"]:
        return "erken"
    return "acik" if simdi < zaman["kapanis"] else "kapali"


def otomatik_sinav_durumu(db):
    """Sınavları saatine göre kendiliğinden başlat / bitir:
    - hazır sınav, giriş penceresi açılınca aktif olur (başka aktif sınav yoksa)
    - aktif ya da hazır sınav, süresi dolunca biter"""
    simdi = datetime.now()
    damga = simdi.strftime("%Y-%m-%d %H:%M:%S")
    degisti = False
    for sid, tarih, saat, sure, acilis, gec, durum in db.execute(
            "SELECT id, tarih, saat, sure_dk, acilis_dk, gec_dk, durum FROM sinavlar "
            "WHERE durum IN ('hazir', 'aktif') ORDER BY tarih, saat").fetchall():
        zaman = sinav_zamani(tarih, saat, sure, acilis, gec)
        if simdi >= zaman["bitis"]:
            db.execute("UPDATE sinavlar SET durum = 'bitti', bitis = ? WHERE id = ?", (damga, sid))
            degisti = True
        elif durum == "hazir" and simdi >= zaman["acilis"] and aktif_sinav(db) is None:
            db.execute("UPDATE sinavlar SET durum = 'aktif', baslama = ? WHERE id = ?", (damga, sid))
            degisti = True
    if degisti:
        db.commit()


def bos_sira_sec(db, kapsam, deger, koltuk):
    """Bu sınavda (ya da serbest modda bugün) verilmemiş sıralardan birini rastgele seç; salon doluysa None."""
    dolu = {s for (s,) in db.execute(f"SELECT sira FROM olaylar WHERE tur = 'giris' "
                                     f"AND sira IS NOT NULL AND {kapsam}", (deger,))}
    bos = [s for s in range(1, koltuk + 1) if s not in dolu]
    return random.choice(bos) if bos else None


def benzerlik(mesafe):
    """Yüz mesafesini (küçük = benzer) herkesin anlayacağı bir yüzdeye çevirir (büyük = benzer).
    Tanıma eşiği (TOLERANS) tam %50'ye denk gelir; eşiğin altındaki mesafeler hızla %80-%95'e
    çıkar, farklı kişiler %20-%40 civarında kalır. Örnek (TOLERANS 0.47):
    0.30 -> %94, 0.43 -> %82, 0.47 -> %50, 0.66 -> %32."""
    if mesafe > TOLERANS:
        deger = (1.0 - mesafe) / ((1.0 - TOLERANS) * 2)
    else:
        deger = 1.0 - mesafe / (TOLERANS * 2)
        deger += (1.0 - deger) * ((deger - 0.5) * 2) ** 0.2
    return round(max(0.0, min(1.0, deger)) * 100)


def ogrenci_adlari():
    """{numara: ad soyad}"""
    with closing(db_ac()) as db:
        return dict(db.execute("SELECT ogrenci_no, ad_soyad FROM ogrenciler"))


def dosya_numarasi(dosya):
    """12345_3.jpg -> 12345"""
    return os.path.splitext(dosya)[0].split("_")[0]


def ogrenci_dosyalari():
    """{numara: [dosya, ...]}"""
    dosyalar = {}
    for dosya in sorted(os.listdir(KISILER)):
        if dosya.lower().endswith(UZANTILAR):
            dosyalar.setdefault(dosya_numarasi(dosya), []).append(dosya)
    return dosyalar


def yuzleri_oku():
    if not os.path.exists(YUZ_DOSYASI):
        return [], []
    with open(YUZ_DOSYASI, "rb") as f:
        return pickle.load(f)


def yuzleri_yaz(numaralar, kodlar):
    # Önce geçici dosyaya yazıp sonra yerine koyuyoruz; tani.py yarım dosya okumasın
    with open(YUZ_DOSYASI + ".tmp", "wb") as f:
        pickle.dump((numaralar, kodlar), f)
    os.replace(YUZ_DOSYASI + ".tmp", YUZ_DOSYASI)
