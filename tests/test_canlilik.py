# Canlılık kontrolü (göz kırpma): fotoğraf saldırısı reddedilir, göz kırpan içeri alınır,
# kırpmadan ayrılan için kayıt yazılmaz. Zaten içeride olandan göz kırpma istenmez.

import pytest

from conftest import KONUM, bos_kare, ogrenci_ekle, olaylar


# ---------- Göz açıklığı ölçümü ----------

def test_gercek_fotografta_goz_acik_olculur(tani, yuzler):
    import face_recognition
    y = yuzler["Tuncay_1"]
    goz = tani.goz_acikligi(face_recognition.face_landmarks(y["rgb"], [y["konum"]])[0])
    assert 0.18 < goz < 0.40


def yeni_bekleyen(tani):
    tani.canlilik_baslat("101", "Ayşe", KONUM, bos_kare(), simdi=1000.0)
    return tani.bekleyen


def test_goz_kirpma_algilanir(tani):
    b = yeni_bekleyen(tani)
    for goz in [0.26, 0.27, 0.26, 0.25, 0.26, 0.26, 0.08, 0.07, 0.26]:   # açık ... kapalı ... açık
        tani.goz_olcumu_ekle(b, goz, bos_kare())
    assert b["kirpti"]


def test_sabit_fotograf_kirpmis_sayilmaz(tani):
    b = yeni_bekleyen(tani)
    for _ in range(60):
        tani.goz_olcumu_ekle(b, 0.26, bos_kare())
    assert not b["kirpti"]


def test_kucuk_titremeler_kirpma_sayilmaz(tani):
    b = yeni_bekleyen(tani)
    for i in range(60):
        tani.goz_olcumu_ekle(b, 0.26 * (1 + 0.05 * (-1) ** i), bos_kare())   # ±%5 ölçüm gürültüsü
    assert not b["kirpti"]


def test_kapanip_acilmayan_goz_kirpma_sayilmaz(tani):
    b = yeni_bekleyen(tani)
    for goz in [0.26] * 6 + [0.08] * 10:   # gözünü kapatıp öyle bekliyor
        tani.goz_olcumu_ekle(b, goz, bos_kare())
    assert not b["kirpti"]


def test_gercek_fotograf_karelerinde_kirpma_yok(tani, yuzler):
    """Fotoğraf saldırısı: aynı fotoğraf her karede ölçülür, göz açıklığı değişmez."""
    import face_recognition
    y = yuzler["Tuncay_1"]
    b = yeni_bekleyen(tani)
    for _ in range(20):
        goz = tani.goz_acikligi(face_recognition.face_landmarks(y["rgb"], [y["konum"]])[0])
        tani.goz_olcumu_ekle(b, goz, y["bgr"])
    assert not b["kirpti"]


# ---------- Akış içinde canlılık ----------

@pytest.fixture
def akis(tani, db, monkeypatch):
    monkeypatch.setattr(tani, "CANLILIK", True)
    ogrenci_ekle(db, "101", "Ayşe")
    tani.adlar = {"101": "Ayşe"}
    durum = tani.AkisDurumu()
    saat = {"t": 1000.0}

    def kare(*numaralar, sn=0.3):
        saat["t"] += sn
        tani.olaylari_isle(db, bos_kare(), None, [], [(KONUM, n) for n in numaralar], durum, simdi=saat["t"])
    return kare


def test_giris_icin_once_goz_kirpma_beklenir(tani, db, akis):
    for _ in range(3):
        akis("101")
    assert tani.bekleyen is not None and tani.bekleyen["isim"] == "Ayşe"
    assert olaylar(db) == []        # henüz giriş yok


def test_goz_kirpinca_giris(tani, db, akis):
    for _ in range(3):
        akis("101")
    tani.bekleyen["kirpti"] = True  # göz kırpıldı (ölçüm testleri yukarıda)
    akis("101")
    assert olaylar(db) == [("giris", "101")]
    assert tani.bekleyen is None


def test_fotograf_saldirisi_canlilik_yok(tani, db, akis):
    from ayarlar import CANLILIK_SURE
    for _ in range(3):
        akis("101")
    akis("101", sn=CANLILIK_SURE + 1)   # süre doldu, göz kırpılmadı
    assert olaylar(db) == [("canlilik_yok", "101")]
    assert tani.bekleyen is None


def test_kirpmadan_ayrilan_icin_kayit_yok(tani, db, akis):
    for _ in range(3):
        akis("101")
    akis(sn=2.0)                    # kameradan ayrıldı
    assert olaylar(db) == []
    assert tani.bekleyen is None


def test_zaten_iceride_olandan_kirpma_istenmez(tani, db, akis):
    tani.olay_yaz(db, "101", bos_kare(), KONUM)   # daha önce girmiş
    for _ in range(3):
        akis("101")
    assert tani.bekleyen is None
    assert olaylar(db) == [("giris", "101"), ("tekrar", "101")]


def test_kayitsiz_kisiden_kirpma_istenmez(tani, db, akis):
    for _ in range(3):
        akis(None)
    assert tani.bekleyen is None
    assert olaylar(db) == [("bilinmeyen", None)]


def test_biri_beklerken_digeri_sirasini_bekler(tani, db, akis):
    ogrenci_ekle(db, "102", "Mehmet")
    tani.adlar["102"] = "Mehmet"
    for _ in range(3):
        akis("101", "102")
    assert tani.bekleyen["numara"] == "101"
    tani.bekleyen["kirpti"] = True
    akis("101", "102")              # 101 girdi; 102 için bekleme başlar
    assert olaylar(db) == [("giris", "101")]
    assert tani.bekleyen["numara"] == "102"


def test_test_modu_bekleyeni_iptal_eder(tani, db, akis):
    import time
    for _ in range(3):
        akis("101")
    tani.test_modu_bitis = time.time() + 60
    akis("101")
    assert tani.bekleyen is None and olaylar(db) == []
