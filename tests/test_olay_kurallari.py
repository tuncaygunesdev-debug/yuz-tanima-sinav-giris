# Kapıdaki olay kuralları: giriş / tekrar / listede yok / kayıtsız / erken / geç,
# sıra numaraları, serbest mod ve sınav modu. (tani.olay_turu ve tani.olay_yaz)

import os

from conftest import KONUM, bos_kare, ogrenci_ekle, olaylar, sinav_ekle


def hazirla(tani, db, *ogrenciler):
    for numara, ad in ogrenciler:
        ogrenci_ekle(db, numara, ad)
    tani.adlar = dict(ogrenciler)


def tur(tani, db, numara):
    return tani.olay_turu(db, numara)[1]


# ---------- Serbest mod (aktif sınav yok) ----------

def test_serbest_mod_ilk_giris_sonra_tekrar(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    assert tur(tani, db, "101") == "giris"
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    assert tur(tani, db, "101") == "tekrar"


def test_kayitsiz_kisi(tani, db):
    assert tani.olay_turu(db, None)[:2] == (tani.BILINMEYEN, "bilinmeyen")


def test_serbest_modda_saat_kurali_yok(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    sinav_ekle(db, bas_dk=-300, ogrenciler=["101"], durum="bitti")   # bitmiş sınav serbest modu etkilemez
    assert tur(tani, db, "101") == "giris"


def test_olay_yaz_kayit_ve_fotograf(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    satir = db.execute("SELECT isim, ogrenci_no, tur, sira, foto, sinav_id FROM olaylar").fetchone()
    assert satir[:3] == ("Ayşe", "101", "giris")
    assert 1 <= satir[3] <= 30 and satir[5] is None
    assert os.path.exists(f"static/{satir[4]}")


def test_ayni_saniyede_iki_fotograf_cakismaz(tani, db):
    for _ in range(3):
        tani.olay_yaz(db, None, bos_kare(), KONUM)
    fotolar = [f for (f,) in db.execute("SELECT foto FROM olaylar")]
    assert len(set(fotolar)) == 3 and all(os.path.exists(f"static/{f}") for f in fotolar)


def test_zorla_canlilik_yok(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    tani.olay_yaz(db, "101", bos_kare(), KONUM, zorla_tur="canlilik_yok")
    assert olaylar(db, "tur", "sira") == [("canlilik_yok", None)]
    assert tur(tani, db, "101") == "giris"   # canlılık yok bir giriş sayılmaz


# ---------- Sınav modu ----------

def test_listede_olmayan(tani, db):
    hazirla(tani, db, ("101", "Ayşe"), ("102", "Mehmet"))
    sinav_ekle(db, bas_dk=10, ogrenciler=["101"])
    assert tur(tani, db, "102") == "listede_yok"


def test_giris_penceresi_acik(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    sinav_ekle(db, bas_dk=10, acilis=30, ogrenciler=["101"])   # giriş 20 dk önce açıldı
    assert tur(tani, db, "101") == "giris"


def test_erken_gelen(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    sinav_ekle(db, bas_dk=40, acilis=30, ogrenciler=["101"])   # giriş 10 dk sonra açılacak
    assert tur(tani, db, "101") == "erken"


def test_gec_kalan_tolerans_yok(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    sinav_ekle(db, bas_dk=-5, gec=0, ogrenciler=["101"])   # sınav 5 dk önce başladı
    assert tur(tani, db, "101") == "gec"


def test_gec_giris_toleransi(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    sinav_ekle(db, bas_dk=-5, gec=10, ogrenciler=["101"])   # 10 dk tolerans var
    assert tur(tani, db, "101") == "giris"


def test_zaten_girmis_ogrenci_saatten_bagimsiz_tekrar(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    sid = sinav_ekle(db, bas_dk=10, ogrenciler=["101"])
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    db.execute("UPDATE sinavlar SET saat = '00:00', tarih = '2000-01-01' WHERE id = ?", (sid,))   # giriş çoktan kapandı
    db.commit()
    assert tur(tani, db, "101") == "tekrar"


def test_tekrar_ayni_sira_numarasini_gosterir(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    sinav_ekle(db, bas_dk=10, ogrenciler=["101"])
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    ilk_sira = db.execute("SELECT sira FROM olaylar").fetchone()[0]
    _, t, sira, _ = tani.olay_turu(db, "101")
    assert (t, sira) == ("tekrar", ilk_sira)


def test_sinav_olayi_sinava_baglanir(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    sid = sinav_ekle(db, bas_dk=10, ogrenciler=["101"])
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    assert olaylar(db, "tur", "sinav_id") == [("giris", sid)]


def test_iki_sinav_ayni_gun_ayri_sayilir(tani, db):
    hazirla(tani, db, ("101", "Ayşe"))
    ilk = sinav_ekle(db, ad="Sabah", bas_dk=10, ogrenciler=["101"])
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    db.execute("UPDATE sinavlar SET durum = 'bitti' WHERE id = ?", (ilk,))
    db.commit()
    sinav_ekle(db, ad="Öğle", bas_dk=10, ogrenciler=["101"])
    assert tur(tani, db, "101") == "giris"   # yeni sınavda yeniden girebilir


# ---------- Sıra numaraları ----------

def test_sira_numaralari_cakismaz_ve_salon_dolunca_verilmez(tani, db):
    ogrenciler = [(str(100 + i), f"Öğrenci {i}") for i in range(4)]
    hazirla(tani, db, *ogrenciler)
    sinav_ekle(db, bas_dk=10, koltuk=3, ogrenciler=[n for n, _ in ogrenciler])
    for numara, _ in ogrenciler:
        tani.olay_yaz(db, numara, bos_kare(), KONUM)
    siralar = [s for (s,) in db.execute("SELECT sira FROM olaylar ORDER BY id")]
    assert sorted(siralar[:3]) == [1, 2, 3]
    assert siralar[3] is None   # salon dolu
