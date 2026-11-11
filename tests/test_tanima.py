# Yüz tanıma: doğru kişi, kayıtsız kişi, "emin değilim", benzerlik yüzdesi, baş yönü, ayna görüntüsü.

import numpy as np
import pytest

from conftest import yuz_tanit
from veri import benzerlik

# ---------- Benzerlik yüzdesi ----------

def test_benzerlik_esik_yuzde_elli():
    from ayarlar import TOLERANS
    assert benzerlik(TOLERANS) == 50


def test_benzerlik_sinirlari_ve_sirasi():
    assert benzerlik(0.0) == 100
    assert benzerlik(1.5) == 0
    degerler = [benzerlik(m) for m in (0.2, 0.3, 0.4, 0.45, 0.5, 0.6, 0.8)]
    assert degerler == sorted(degerler, reverse=True)   # mesafe büyüdükçe benzerlik azalır


def test_benzerlik_taninan_kisi_yuksek_farkli_kisi_dusuk():
    assert benzerlik(0.35) >= 85   # aynı kişi
    assert benzerlik(0.66) <= 40   # farklı kişiler


# ---------- Kişi bulma ----------

def test_dogru_kisiyi_tanir(tani, yuzler):
    yuz_tanit(tani, [("1", "Tuncay", yuzler["Tuncay_1"]["kod"]), ("2", "Yağız", yuzler["Yağız_1"]["kod"])])
    numara, siralama = tani.kisi_bul(yuzler["Tuncay_3"]["kod"])
    assert numara == "1"
    assert siralama[0][1] == "1"


def test_kayitsiz_yuz_bilinmeyen(tani, yuzler):
    yuz_tanit(tani, [("1", "Tuncay", yuzler["Tuncay_1"]["kod"]), ("2", "Yağız", yuzler["Yağız_1"]["kod"])])
    numara, _ = tani.kisi_bul(yuzler["kerim_1"]["kod"])
    assert numara is None


def test_kayitli_yuz_yokken_bilinmeyen(tani, yuzler):
    yuz_tanit(tani, [])
    assert tani.kisi_bul(yuzler["Tuncay_1"]["kod"]) == (None, [])


def test_iki_kisiye_benzerse_emin_degil(tani, yuzler):
    # Aynı insan iki farklı numarada kayıtlı: sistem karar vermemeli
    yuz_tanit(tani, [("A", "Tuncay A", yuzler["Tuncay_1"]["kod"]), ("B", "Tuncay B", yuzler["Tuncay_2"]["kod"]),
                     ("Y", "Yağız", yuzler["Yağız_1"]["kod"])])
    numara, _ = tani.kisi_bul(yuzler["Tuncay_3"]["kod"])
    assert numara == tani.BELIRSIZ


def test_ogrencinin_en_yakin_fotografi_kullanilir(tani, yuzler):
    # Aynı öğrencinin birden çok fotoğrafı: en yakını sayılır, öğrenci tek aday olarak kalır
    yuz_tanit(tani, [("1", "Tuncay", yuzler["Tuncay_1"]["kod"]), ("1", "Tuncay", yuzler["Tuncay_2"]["kod"]),
                     ("2", "Yağız", yuzler["Yağız_1"]["kod"])])
    numara, siralama = tani.kisi_bul(yuzler["Tuncay_3"]["kod"])
    assert numara == "1"
    assert [n for _, n in siralama] == ["1", "2"]


# ---------- Ekrandaki etiketler ----------

def test_etiket_taninan_kisi_sadece_kendi_yuzdesi(tani):
    tani.adlar = {"1": "Tuncay Güneş", "2": "Yağız Demir"}
    yazi, durum, ayrinti = tani.etiket("1", [(0.33, "1"), (0.66, "2")])
    assert (yazi, durum) == ("Tuncay Güneş", "tanindi")
    assert ayrinti.startswith("%") and ayrinti.endswith("benziyor")
    assert "Yağız" not in ayrinti   # 2. en benzer kişi yazılmaz


def test_etiket_kayitsiz_kiside_yuzde_yok(tani):
    assert tani.etiket(None, [(0.62, "1")]) == (tani.BILINMEYEN, "bilinmeyen", "")


def test_etiket_emin_degilken_iki_isim(tani):
    tani.adlar = {"1": "Tuncay", "2": "Yağız"}
    yazi, durum, ayrinti = tani.etiket(tani.BELIRSIZ, [(0.44, "1"), (0.46, "2")])
    assert (yazi, durum) == ("?", "belirsiz")
    assert "Tuncay" in ayrinti and "Yağız" in ayrinti


def test_kare_analiz_gercek_fotograf(tani, yuzler):
    yuz_tanit(tani, [("1", "Tuncay", yuzler["Tuncay_1"]["kod"]), ("2", "Yağız", yuzler["Yağız_1"]["kod"])])
    konumlar, bulunanlar, etiketler = tani.kare_analiz(yuzler["Tuncay_3"]["rgb"])
    assert len(konumlar) == 1
    assert bulunanlar[0][1] == "1"
    assert etiketler[0][1] == "Tuncay" and etiketler[0][2] == "tanindi"


# ---------- Ayna görüntüsü ----------

def test_aynala_goruntu_ve_kutu(tani):
    kare = np.zeros((480, 640, 3), np.uint8)
    kare[100:300, 100:300] = 255   # yüz solda
    ayna, yuzler_ = tani.aynala(kare, [((100, 300, 300, 100), "Ad", "tanindi", "")])
    ust, sag, alt, sol = yuzler_[0][0]
    beyaz = np.where(ayna[200] == 255)[0]
    assert (sol, sag) == (340, 540) == (beyaz.min(), beyaz.max() + 1)   # kutu, yüzle birlikte sağa geçer
    assert yuzler_[0][1:] == ("Ad", "tanindi", "")


def test_isaretle_yazili_kare_uretir(tani):
    kare = np.zeros((480, 640, 3), np.uint8)
    cizili = tani.isaretle(kare, [((100, 300, 300, 100), "Şükrü Öztürk", "tanindi", "%90 benziyor")], detay=True)
    assert cizili.shape == kare.shape and cizili.any()   # Türkçe isim hatasız çizildi


# ---------- Baş yönü (rehberli kayıt) ----------

@pytest.mark.parametrize("foto, beklenen", [("Tuncay_1", "duz"), ("Tuncay_2", "sag"), ("Tuncay_3", "sol")])
def test_bas_yonu(tani, yuzler, foto, beklenen):
    yon, oran = tani.bas_yonu(yuzler[foto]["rgb"], yuzler[foto]["konum"])
    assert yon == beklenen, f"oran={oran}"
