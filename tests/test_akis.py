# Tanıma akışı (tani.olaylari_isle): art arda 3 kare onayı, "emin değilim", ayrılma kuralı,
# kayıt modu ve test modu. Yüz bulma yerine "bu karede şu kişi görüldü" bilgisi doğrudan verilir;
# saat de sahte verilir, böylece testler hızlı ve her seferinde aynı sonucu verir.

import time

import pytest

from conftest import KONUM, bos_kare, ogrenci_ekle, olaylar


@pytest.fixture
def akis(tani, db, monkeypatch):
    """Canlılık (göz kırpma) kapalı; o ayrı test dosyasında. Kayıtlı öğrenci: 101 Ayşe."""
    monkeypatch.setattr(tani, "CANLILIK", False)
    ogrenci_ekle(db, "101", "Ayşe")
    tani.adlar = {"101": "Ayşe"}
    durum = tani.AkisDurumu()
    saat = {"t": 1000.0}

    def kare(*numaralar, sn=0.3):
        """Bir analiz: karede bu numaralar görüldü (None = kayıtsız, tani.BELIRSIZ = emin değil)."""
        saat["t"] += sn
        bulunanlar = [(KONUM, n) for n in numaralar]
        tani.olaylari_isle(db, bos_kare(), None, [], bulunanlar, durum, simdi=saat["t"])
    return kare


def test_tek_kare_yetmez_uc_kare_gerekir(tani, db, akis):
    akis("101")
    akis("101")
    assert olaylar(db) == []
    akis("101")
    assert olaylar(db) == [("giris", "101")]


def test_arada_gorulmezse_sayac_sifirlanir(tani, db, akis):
    akis("101"); akis("101")
    akis()                    # bir karede görülmedi
    akis("101"); akis("101")
    assert olaylar(db) == []
    akis("101")
    assert olaylar(db) == [("giris", "101")]


def test_emin_degilken_hic_olay_yazilmaz(tani, db, akis):
    for _ in range(10):
        akis(tani.BELIRSIZ)
    assert olaylar(db) == []


def test_kayitsiz_kisi_icin_olay(tani, db, akis):
    for _ in range(3):
        akis(None)
    assert olaylar(db) == [("bilinmeyen", None)]


def test_kamerada_durdukca_tekrar_yazilmaz(tani, db, akis):
    for _ in range(40):           # ~12 saniye kamerada
        akis("101")
    assert olaylar(db) == [("giris", "101")]


def test_ayrilip_geri_gelince_yeni_olay(tani, db, akis):
    from ayarlar import AYRILMA
    for _ in range(3):
        akis("101")
    akis(sn=AYRILMA + 1)          # AYRILMA'dan uzun süre kimse yok
    for _ in range(3):
        akis("101")
    assert olaylar(db) == [("giris", "101"), ("tekrar", "101")]


def test_kisa_sure_kaybolmak_ayrilma_sayilmaz(tani, db, akis):
    for _ in range(3):
        akis("101")
    akis(sn=1.0)                  # 1 sn görünmedi (AYRILMA 3 sn)
    for _ in range(5):
        akis("101")
    assert olaylar(db) == [("giris", "101")]


def test_kayit_modunda_olay_yazilmaz(tani, db, akis):
    tani.kayit_modu_bitis = time.time() + 60
    for _ in range(5):
        akis("101")
    assert olaylar(db) == []


def test_test_modunda_olay_yazilmaz(tani, db, akis):
    tani.test_modu_bitis = time.time() + 60
    for _ in range(5):
        akis(None)
        akis("101")
    assert olaylar(db) == []


def test_mod_bitince_kamerada_duran_icin_hemen_olay_yazilmaz(tani, db, akis):
    from ayarlar import AYRILMA
    tani.test_modu_bitis = time.time() + 60
    for _ in range(3):
        akis("101")
    tani.test_modu_bitis = 0.0    # test modu kapandı, öğrenci hâlâ kamerada
    for _ in range(5):
        akis("101")
    assert olaylar(db) == []
    akis(sn=AYRILMA + 1)          # ayrılıp geri geldi
    for _ in range(3):
        akis("101")
    assert olaylar(db) == [("giris", "101")]


def test_mod_suresi_dolunca_kendiliginden_biter(tani):
    tani.test_modu_bitis = time.time() - 0.1
    tani.kayit_modu_bitis = time.time() - 0.1
    assert not tani.test_modunda() and not tani.kayit_modunda()


def test_ayni_karede_iki_kisi(tani, db, akis):
    ogrenci_ekle(db, "102", "Mehmet")
    tani.adlar["102"] = "Mehmet"
    for _ in range(3):
        akis("101", "102")
    assert sorted(olaylar(db)) == [("giris", "101"), ("giris", "102")]
