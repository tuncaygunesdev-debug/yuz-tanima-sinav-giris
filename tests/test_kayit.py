# Öğrenci kaydı: numara / ad soyad / KVKK kuralları, aynı yüzün iki numarayla kaydolamaması,
# kameradan ve dosyadan fotoğraf, rehberli kayıt (düz-sağ-sol), düzenleme, fotoğraf silme, öğrenci silme.

import io
import os
import time

import pytest

from conftest import KONUM, bos_kare, ogrenci_ekle, sinav_ekle


def foto_dosyasi(yuzler, ad):
    return (io.BytesIO(yuzler[ad]["yol"].read_bytes()), "foto.jpg")


def ekle(istemci, numara, ad_soyad, foto=None, kvkk="1", **ek):
    veri = {"numara": numara, "ad_soyad": ad_soyad, "kvkk": kvkk, **ek}
    if foto:
        veri["foto"] = foto
    return istemci.post("/api/kisi_ekle", data=veri, content_type="multipart/form-data").get_json()


def kayitli_numaralar():
    from veri import yuzleri_oku
    return yuzleri_oku()[0]


# ---------- Form kuralları ----------

@pytest.mark.parametrize("numara, ad, kvkk, kod", [
    ("12a", "Ayşe Yılmaz", "1", "numara"),     # numarada harf
    ("", "Ayşe Yılmaz", "1", "numara"),
    ("123", "Ayşe", "1", "ad"),                # soyad yok
    ("123", "Ayşe 123", "1", "ad"),            # isimde rakam
    ("123", "Ayşe Yılmaz", "", "kvkk"),        # KVKK onayı yok
])
def test_hatali_form_reddedilir(istemci, numara, ad, kvkk, kod):
    cevap = istemci.post("/api/kayit_kontrol", data={"numara": numara, "ad_soyad": ad, "kvkk": kvkk}).get_json()
    assert cevap["ok"] is False and cevap["kod"] == kod


def test_numara_baskasina_aitse_reddedilir(istemci, db):
    ogrenci_ekle(db, "123", "Ayşe Yılmaz")
    cevap = istemci.post("/api/kayit_kontrol", data={"numara": "123", "ad_soyad": "Mehmet Demir", "kvkk": "1"}).get_json()
    assert cevap["kod"] == "numara_baska"


def test_ayni_kisi_buyuk_kucuk_harf_farki_kabul(istemci, db):
    ogrenci_ekle(db, "123", "Ayşe Yılmaz")
    cevap = istemci.post("/api/kayit_kontrol", data={"numara": "123", "ad_soyad": "ayşe   yılmaz", "kvkk": "1"}).get_json()
    assert cevap["ok"] and cevap["ad_soyad"] == "Ayşe Yılmaz"


# ---------- Fotoğrafla kayıt ----------

def test_dosyadan_kayit_ve_ikinci_fotograf(istemci, db, yuzler):
    assert ekle(istemci, "101", "Tuncay Test", foto_dosyasi(yuzler, "Tuncay_1"))["ok"]
    assert ekle(istemci, "101", "Tuncay Test", foto_dosyasi(yuzler, "Tuncay_3"))["sayi"] == 2
    assert sorted(os.listdir("kisiler")) == ["101_1.jpg", "101_2.jpg"]
    assert kayitli_numaralar() == ["101", "101"]
    satir = db.execute("SELECT ad_soyad, kvkk_onay FROM ogrenciler WHERE ogrenci_no = '101'").fetchone()
    assert satir[0] == "Tuncay Test" and satir[1]   # KVKK onay zamanı kaydedildi


def test_kameradan_kayit(istemci, tani, yuzler):
    tani.son_kare = yuzler["Tuncay_1"]["bgr"]
    assert ekle(istemci, "101", "Tuncay Test")["ok"]
    assert os.listdir("kisiler") == ["101_1.jpg"]


def test_yuzsuz_fotograf_reddedilir(istemci, tani):
    tani.son_kare = bos_kare()
    cevap = ekle(istemci, "101", "Tuncay Test")
    assert cevap["kod"] == "yuz_sayisi" and os.listdir("kisiler") == []


def test_bozuk_dosya_reddedilir(istemci):
    cevap = ekle(istemci, "101", "Tuncay Test", (io.BytesIO(b"bozuk"), "x.jpg"))
    assert cevap["ok"] is False and "okunamadı" in cevap["mesaj"]


def test_ayni_yuz_iki_numarayla_kaydolamaz(istemci, yuzler):
    assert ekle(istemci, "101", "Tuncay Test", foto_dosyasi(yuzler, "Tuncay_1"))["ok"]
    cevap = ekle(istemci, "202", "Sahte Kişi", foto_dosyasi(yuzler, "Tuncay_3"))
    assert cevap["kod"] == "yuz_baska"
    assert kayitli_numaralar() == ["101"]


def test_kayit_tani_tarafindan_hemen_yuklenir(istemci, tani, yuzler):
    ekle(istemci, "101", "Tuncay Test", foto_dosyasi(yuzler, "Tuncay_1"))
    tani.yuzleri_yukle()
    assert tani.numaralar == ["101"] and tani.adlar == {"101": "Tuncay Test"}
    assert tani.kisi_bul(yuzler["Tuncay_3"]["kod"])[0] == "101"


# ---------- Rehberli kayıt (düz - sağ - sol) ----------

def test_rehberli_kayit_uc_poz(istemci, tani, yuzler):
    tani.kayit_modu_bitis = time.time() + 60
    for foto, yon in (("Tuncay_1", "duz"), ("Tuncay_2", "sag"), ("Tuncay_3", "sol")):
        y = yuzler[foto]
        tani.poz_guncelle(y["rgb"], y["bgr"], [y["konum"]])
        assert istemci.get("/api/poz").get_json()["yon"] == yon
        assert ekle(istemci, "101", "Tuncay Test", yon=yon)["ok"], yon
    assert len(os.listdir("kisiler")) == 3


def test_rehberli_kayit_eski_poz_karesi_kullanilmaz(istemci, tani, yuzler):
    y = yuzler["Tuncay_1"]
    tani.poz_guncelle(y["rgb"], y["bgr"], [y["konum"]])
    tani.poz_kareleri["duz"] = (time.time() - 5, y["bgr"])   # 5 sn önceki kare
    cevap = ekle(istemci, "101", "Tuncay Test", yon="duz")
    assert cevap["kod"] == "poz"


def test_poz_istegi_kayit_modunu_acar(istemci, tani):
    assert not tani.kayit_modunda()
    istemci.get("/api/poz")
    assert tani.kayit_modunda()


# ---------- Düzenleme ----------

def kayitli_ogrenci(istemci, yuzler, numara="101", ad="Tuncay Yanlış", fotolar=("Tuncay_1", "Tuncay_3")):
    for f in fotolar:
        assert ekle(istemci, numara, ad, foto_dosyasi(yuzler, f))["ok"]


def test_ad_duzeltme_gecmis_kayitlari_da_gunceller(istemci, db, tani, yuzler):
    kayitli_ogrenci(istemci, yuzler)
    tani.adlar = {"101": "Tuncay Yanlış"}
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    cevap = istemci.post("/api/ogrenci/101/duzenle", data={"yeni_numara": "101", "ad_soyad": "Tuncay Güneş"}).get_json()
    assert cevap["ok"]
    assert db.execute("SELECT isim FROM olaylar").fetchone()[0] == "Tuncay Güneş"


def test_numara_degisince_her_sey_tasinir(istemci, db, tani, yuzler):
    kayitli_ogrenci(istemci, yuzler)
    sid = sinav_ekle(db, ogrenciler=["101"])
    tani.adlar = {"101": "Tuncay Yanlış"}
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    cevap = istemci.post("/api/ogrenci/101/duzenle", data={"yeni_numara": "999", "ad_soyad": "Tuncay Güneş"}).get_json()
    assert cevap["ok"] and cevap["no"] == "999"
    assert sorted(os.listdir("kisiler")) == ["999_1.jpg", "999_2.jpg"]
    assert db.execute("SELECT ogrenci_no FROM sinav_ogrencileri WHERE sinav_id = ?", (sid,)).fetchall() == [("999",)]
    assert db.execute("SELECT ogrenci_no FROM olaylar").fetchall() == [("999",)]
    assert kayitli_numaralar() == ["999", "999"]
    tani.yuz_dosya_zamani = None
    tani.yuzleri_yukle()
    assert tani.kisi_bul(yuzler["Tuncay_2"]["kod"])[0] == "999"   # yeni numarayla tanınıyor


@pytest.mark.parametrize("yeni_numara, ad, beklenen", [
    ("10a", "Tuncay Güneş", "rakam"), ("101", "Tuncay", "Ad ve soyadı"), ("202", "Tuncay Güneş", "başka bir öğrenciye"),
])
def test_hatali_duzenleme_reddedilir(istemci, db, yuzler, yeni_numara, ad, beklenen):
    kayitli_ogrenci(istemci, yuzler)
    ogrenci_ekle(db, "202", "Yağız Test")
    cevap = istemci.post("/api/ogrenci/101/duzenle", data={"yeni_numara": yeni_numara, "ad_soyad": ad}).get_json()
    assert cevap["ok"] is False and beklenen in cevap["mesaj"]


# ---------- Fotoğraf silme / ekleme / öğrenci silme ----------

def test_fotograf_silinince_yuz_kodlari_yeniden_hesaplanir(istemci, yuzler):
    kayitli_ogrenci(istemci, yuzler)
    cevap = istemci.post("/api/ogrenci/101/foto_sil", data={"dosya": "101_2.jpg"}).get_json()
    assert cevap["ok"] and cevap["fotolar"] == ["101_1.jpg"]
    assert kayitli_numaralar() == ["101"]


def test_son_fotograf_silinemez(istemci, yuzler):
    kayitli_ogrenci(istemci, yuzler, fotolar=("Tuncay_1",))
    cevap = istemci.post("/api/ogrenci/101/foto_sil", data={"dosya": "101_1.jpg"}).get_json()
    assert cevap["ok"] is False and os.listdir("kisiler") == ["101_1.jpg"]


def test_klasor_disindaki_dosya_silinemez(istemci, yuzler):
    kayitli_ogrenci(istemci, yuzler)
    open("onemli.txt", "w").write("x")
    cevap = istemci.post("/api/ogrenci/101/foto_sil", data={"dosya": "../onemli.txt"}).get_json()
    assert cevap["ok"] is False and os.path.exists("onemli.txt")


def test_duzenleme_penceresinden_dosyayla_fotograf_ekleme(istemci, yuzler):
    kayitli_ogrenci(istemci, yuzler, fotolar=("Tuncay_1",))
    assert ekle(istemci, "101", "Tuncay Yanlış", foto_dosyasi(yuzler, "Tuncay_2"))["ok"]
    assert istemci.get("/api/ogrenci/101").get_json()["fotolar"] == ["101_1.jpg", "101_2.jpg"]


def test_ogrenci_silinince_her_yerden_kalkar(istemci, db, yuzler):
    kayitli_ogrenci(istemci, yuzler)
    sinav_ekle(db, ogrenciler=["101"])
    cevap = istemci.post("/api/kisi_sil", data={"numara": "101"}).get_json()
    assert cevap["ok"]
    assert os.listdir("kisiler") == [] and kayitli_numaralar() == []
    assert db.execute("SELECT COUNT(*) FROM ogrenciler").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM sinav_ogrencileri").fetchone()[0] == 0
