# Sınavlar: oluşturma kuralları, tek aktif sınav, otomatik başlatma/bitirme, ⚡ Demo,
# elle giriş, yoklama, sıfırlama, silme, Excel.

import io

from conftest import KONUM, bos_kare, ogrenci_ekle, sinav_ekle
from veri import otomatik_sinav_durumu


def olustur(istemci, **ek):
    veri = {"ad": "Matematik", "tarih": "2030-01-01", "saat": "10:00", "koltuk": 30,
            "sure": 60, "acilis": 30, "gec": 0, "ogrenciler": ["101"], **ek}
    return istemci.post("/api/sinav_olustur", data=veri).get_json()


def durumu(db, sid):
    return db.execute("SELECT durum FROM sinavlar WHERE id = ?", (sid,)).fetchone()[0]


# ---------- Oluşturma ----------

def test_gecerli_sinav_saatleriyle_kaydedilir(istemci, db):
    ogrenci_ekle(db, "101", "Ayşe")
    cevap = olustur(istemci, sure=90, acilis=20, gec=5)
    assert cevap["ok"]
    s = istemci.get(f"/api/sinav/{cevap['id']}").get_json()["sinav"]
    assert (s["acilis_saat"], s["baslangic_saat"], s["kapanis_saat"], s["bitis_saat"]) == ("09:40", "10:00", "10:05", "11:30")


def test_olusturma_kurallari(istemci, db):
    ogrenci_ekle(db, "101", "Ayşe")
    ogrenci_ekle(db, "102", "Mehmet")
    assert not olustur(istemci, ad="")["ok"]                                      # adsız
    assert not olustur(istemci, ogrenciler=[])["ok"]                              # öğrencisiz
    assert not olustur(istemci, ogrenciler=["999"])["ok"]                         # kayıtsız öğrenci süzülür
    assert not olustur(istemci, koltuk=1, ogrenciler=["101", "102"])["ok"]        # sıra az
    assert not olustur(istemci, sure=2)["ok"]                                     # süre çok kısa
    assert not olustur(istemci, sure=30, gec=30)["ok"]                            # tolerans >= süre
    assert not olustur(istemci, tarih="yanlış")["ok"]


# ---------- Başlatma / bitirme ----------

def test_ayni_anda_tek_aktif_sinav(istemci, db):
    a = sinav_ekle(db, ad="A", bas_dk=10, durum="aktif")
    b = sinav_ekle(db, ad="B", bas_dk=20, durum="hazir")
    cevap = istemci.post(f"/api/sinav/{b}/durum", data={"islem": "baslat"}).get_json()
    assert cevap["ok"] is False and "A" in cevap["mesaj"]
    istemci.post(f"/api/sinav/{a}/durum", data={"islem": "bitir"})
    assert istemci.post(f"/api/sinav/{b}/durum", data={"islem": "baslat"}).get_json()["ok"]


def test_suresi_dolmus_sinav_elle_baslatilamaz(istemci, db):
    sid = sinav_ekle(db, bas_dk=-120, sure=60, durum="hazir")
    assert istemci.post(f"/api/sinav/{sid}/durum", data={"islem": "baslat"}).get_json()["ok"] is False


def test_otomatik_baslatma_ve_bitirme(db):
    gecmis = sinav_ekle(db, ad="Geçmiş", bas_dk=-120, sure=60, durum="aktif")
    simdi_acik = sinav_ekle(db, ad="Şimdi", bas_dk=10, acilis=30, durum="hazir")
    yarin = sinav_ekle(db, ad="Yarın", bas_dk=24 * 60, durum="hazir")
    otomatik_sinav_durumu(db)
    assert (durumu(db, gecmis), durumu(db, simdi_acik), durumu(db, yarin)) == ("bitti", "aktif", "hazir")


def test_otomatik_baslatma_aktif_sinav_varken_beklemez(db):
    sinav_ekle(db, ad="Aktif", bas_dk=5, durum="aktif")
    sonraki = sinav_ekle(db, ad="Sonraki", bas_dk=10, durum="hazir")
    otomatik_sinav_durumu(db)
    assert durumu(db, sonraki) == "hazir"


def test_demo_girisi_hemen_acar(istemci, db):
    sid = sinav_ekle(db, bas_dk=24 * 60, durum="hazir")
    assert istemci.post(f"/api/sinav/{sid}/demo").get_json()["ok"]
    s = istemci.get(f"/api/sinav/{sid}").get_json()["sinav"]
    assert s["durum"] == "aktif" and s["pencere"] == "acik"


def test_demo_baska_aktif_sinav_varken_reddedilir(istemci, db):
    sinav_ekle(db, ad="Aktif", durum="aktif")
    sid = sinav_ekle(db, ad="Diğer", durum="hazir")
    assert istemci.post(f"/api/sinav/{sid}/demo").get_json()["ok"] is False


# ---------- Elle giriş ve yoklama ----------

def test_elle_giris(istemci, db):
    ogrenci_ekle(db, "101", "Ayşe")
    ogrenci_ekle(db, "102", "Mehmet")
    sid = sinav_ekle(db, bas_dk=-30, ogrenciler=["101"])   # giriş çoktan kapandı
    assert istemci.post(f"/api/sinav/{sid}/elle_giris", data={"numara": "101"}).get_json()["ok"]
    assert istemci.post(f"/api/sinav/{sid}/elle_giris", data={"numara": "101"}).get_json()["ok"] is False  # tekrar
    assert istemci.post(f"/api/sinav/{sid}/elle_giris", data={"numara": "102"}).get_json()["ok"] is False  # listede yok
    gelen = istemci.get(f"/api/sinav/{sid}").get_json()["gelenler"][0]
    assert gelen["no"] == "101" and gelen["aciklama"] == "Görevli onayıyla" and gelen["sira"]


def test_yoklama_gelen_gelmeyen_diger(istemci, db, tani):
    for n, a in (("101", "Ayşe"), ("102", "Mehmet"), ("103", "Zeynep")):
        ogrenci_ekle(db, n, a)
    tani.adlar = {"101": "Ayşe", "102": "Mehmet", "103": "Zeynep"}
    sid = sinav_ekle(db, bas_dk=10, ogrenciler=["101", "102"])
    tani.olay_yaz(db, "101", bos_kare(), KONUM)   # giriş
    tani.olay_yaz(db, "101", bos_kare(), KONUM)   # tekrar
    tani.olay_yaz(db, "103", bos_kare(), KONUM)   # listede yok
    tani.olay_yaz(db, None, bos_kare(), KONUM)    # kayıtsız
    v = istemci.get(f"/api/sinav/{sid}").get_json()
    assert [g["no"] for g in v["gelenler"]] == ["101"]
    assert [g["no"] for g in v["gelmeyenler"]] == ["102"]
    assert sorted(d["tur"] for d in v["diger"]) == ["bilinmeyen", "listede_yok", "tekrar"]
    liste = istemci.get("/api/sinavlar").get_json()["sinavlar"][0]
    assert (liste["gelen"], liste["toplam"]) == (1, 2)


def test_excel(istemci, db, tani):
    from openpyxl import load_workbook
    for n, a in (("101", "Ayşe"), ("102", "Mehmet")):
        ogrenci_ekle(db, n, a)
    tani.adlar = {"101": "Ayşe"}
    sid = sinav_ekle(db, ad="Fizik Finali", bas_dk=10, ogrenciler=["101", "102"])
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    cevap = istemci.get(f"/sinav/{sid}/excel")
    assert cevap.status_code == 200 and "yoklama_Fizik_Finali" in cevap.headers["Content-Disposition"]
    kitap = load_workbook(io.BytesIO(cevap.data))
    satirlar = [r for r in kitap["Yoklama"].iter_rows(min_row=6, values_only=True)]
    assert [(r[1], r[3]) for r in satirlar] == [("101", "Geldi"), ("102", "Gelmedi")]
    assert kitap["Tüm olaylar"].max_row == 2


# ---------- Liste düzenleme, sıfırlama, silme ----------

def test_liste_duzenleme_sira_sayisini_asamaz(istemci, db):
    for n in ("101", "102", "103"):
        ogrenci_ekle(db, n, f"Öğrenci {n}")
    sid = sinav_ekle(db, koltuk=2, ogrenciler=["101"])
    assert istemci.post(f"/api/sinav/{sid}/ogrenciler", data={"ogrenciler": ["101", "102", "103"]}).get_json()["ok"] is False
    assert istemci.post(f"/api/sinav/{sid}/ogrenciler", data={"ogrenciler": ["102", "103"]}).get_json()["ok"]


def test_yoklamayi_sifirla_sadece_o_sinav(istemci, db, tani):
    ogrenci_ekle(db, "101", "Ayşe")
    tani.adlar = {"101": "Ayşe"}
    a = sinav_ekle(db, ad="A", bas_dk=10, ogrenciler=["101"])
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    db.execute("UPDATE sinavlar SET durum = 'bitti' WHERE id = ?", (a,))
    db.commit()
    sinav_ekle(db, ad="B", bas_dk=10, ogrenciler=["101"])
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    istemci.post(f"/api/sinav/{a}/sifirla")
    assert [s for (s,) in db.execute("SELECT sinav_id FROM olaylar")] != [a]
    assert db.execute("SELECT COUNT(*) FROM olaylar WHERE sinav_id = ?", (a,)).fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM olaylar").fetchone()[0] == 1


def test_sinav_silme(istemci, db):
    ogrenci_ekle(db, "101", "Ayşe")
    sid = sinav_ekle(db, ogrenciler=["101"])
    assert istemci.post(f"/api/sinav/{sid}/sil").get_json()["ok"]
    assert db.execute("SELECT COUNT(*) FROM sinavlar").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM sinav_ogrencileri").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM ogrenciler").fetchone()[0] == 1   # öğrenci silinmez
