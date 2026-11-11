# Canlı yayın ve arka plan döngüleri: kameradan okuma (döndürme, yeniden bağlanma),
# işaretli / ham yayın, ayna görüntüsü, tek kare adresi, göz ölçüm döngüsü, ana tanıma döngüsü.

import time

import cv2
import numpy as np
import pytest

from conftest import yuz_tanit


class Dur(Exception):
    """Sonsuz döngüleri testte durdurmak için."""


def ilk_kare(cevap):
    """multipart/x-mixed-replace yayınından ilk JPEG'i çöz."""
    parca = next(iter(cevap.response))
    assert parca.startswith(b"--frame")
    jpg = parca[parca.index(b"\r\n\r\n") + 4:].rstrip(b"\r\n")
    return cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)


@pytest.fixture
def kare():
    k = np.zeros((480, 640, 3), np.uint8)
    k[:, :320] = (255, 255, 255)   # sol yarı beyaz: ayna testleri için
    return k


# ---------- Tek kare ve yayın adresleri ----------

def test_kare_yokken_503(tani):
    assert tani.app.test_client().get("/kare").status_code == 503


def test_kare_jpeg_doner(tani, kare):
    tani.son_kare = kare
    cevap = tani.app.test_client().get("/kare")
    assert cevap.mimetype == "image/jpeg"
    assert cv2.imdecode(np.frombuffer(cevap.data, np.uint8), 1).shape == (480, 640, 3)


def test_yon_karesi_yoksa_404(tani, kare):
    tani.son_kare = kare
    assert tani.app.test_client().get("/kare?yon=sag").status_code == 404


def test_ham_yayin_aynali(tani, kare, monkeypatch):
    monkeypatch.setattr(tani, "GORUNTU_AYNA", True)
    tani.son_kare = kare
    cevap = tani.app.test_client().get("/ham")
    assert cevap.mimetype == "multipart/x-mixed-replace"
    goruntu = ilk_kare(cevap)
    assert goruntu[240, 600].mean() > 200 and goruntu[240, 40].mean() < 50   # beyaz yarı sağa geçti


def test_ham_yayin_aynasiz(tani, kare, monkeypatch):
    monkeypatch.setattr(tani, "GORUNTU_AYNA", False)
    tani.son_kare = kare
    goruntu = ilk_kare(tani.app.test_client().get("/ham"))
    assert goruntu[240, 40].mean() > 200   # beyaz yarı solda kaldı


def test_isaretli_yayin_kutu_cizer(tani, monkeypatch):
    monkeypatch.setattr(tani, "GORUNTU_AYNA", False)
    tani.son_kare = np.zeros((480, 640, 3), np.uint8)
    tani.son_yuzler = [((100, 300, 300, 100), "Ayşe", "tanindi", "%90 benziyor")]
    goruntu = ilk_kare(tani.app.test_client().get("/canli?detay=1"))
    b, g, r = goruntu[200, 100].astype(int)          # kutunun sol kenarı: açık mavi (0, 133, 208)
    assert b > 150 and r < 60


def test_canlilik_adresi(tani):
    c = tani.app.test_client()
    assert c.get("/canlilik").get_json()["bekliyor"] is False
    tani.canlilik_baslat("101", "Ayşe", (1, 2, 3, 4), None)
    v = c.get("/canlilik").get_json()
    assert v["bekliyor"] and v["isim"] == "Ayşe" and 0 < v["kalan"] <= 7


# ---------- Kameradan okuma döngüsü ----------

class SahteKamera:
    """cv2.VideoCapture yerine: önce verilen sonuçları döndürür, sonra döngüyü durdurur."""
    acilis = 0

    def __init__(self, sonuclar):
        self.sonuclar = sonuclar   # bütün açılışlar aynı listeyi tüketir (yeniden bağlanınca baştan başlamasın)
        SahteKamera.acilis += 1

    def read(self):
        if not self.sonuclar:
            raise Dur
        return self.sonuclar.pop(0)

    def release(self):
        pass


def kamera_oku_calistir(tani, monkeypatch, sonuclar):
    SahteKamera.acilis = 0
    sonuclar = list(sonuclar)
    monkeypatch.setattr(tani.cv2, "VideoCapture", lambda adres: SahteKamera(sonuclar))
    monkeypatch.setattr(tani.time, "sleep", lambda s: None)
    with pytest.raises(Dur):
        tani.kamera_oku()


@pytest.mark.parametrize("aci, boyut", [(0, (480, 640)), (90, (640, 480)), (180, (480, 640)), (270, (640, 480))])
def test_kamera_goruntusu_dondurulur(tani, monkeypatch, aci, boyut):
    kare = np.zeros((480, 640, 3), np.uint8)
    kare[0, 0] = 255   # sol üst köşe işaretli
    monkeypatch.setattr(tani, "KAMERA_DONDUR", aci)
    kamera_oku_calistir(tani, monkeypatch, [(True, kare)])
    assert tani.son_kare.shape[:2] == boyut
    if aci == 180:
        assert tani.son_kare[-1, -1].any()   # köşe karşı köşeye geçti


def test_kamera_koparsa_yeniden_baglanir(tani, monkeypatch):
    kamera_oku_calistir(tani, monkeypatch, [(False, None)])
    assert SahteKamera.acilis == 2   # ilk açılış + bir yeniden bağlanma


# ---------- Göz ölçüm döngüsü (gerçek fotoğrafla) ----------

def test_goz_olcum_dongusu_gercek_fotograf(tani, yuzler, monkeypatch):
    y = yuzler["Tuncay_1"]
    tani.son_kare = y["bgr"]
    tani.canlilik_baslat("101", "Tuncay", y["konum"], y["bgr"])
    olcumler = []

    def yakala(b, goz, kare):
        olcumler.append(goz)
        raise Dur
    monkeypatch.setattr(tani, "goz_olcumu_ekle", yakala)
    with pytest.raises(Dur):
        tani.canlilik_izle()
    assert 0.18 < olcumler[0] < 0.40


# ---------- Ana tanıma döngüsü (bir tur) ----------

def test_ana_dongu_bir_kareyi_isler(tani, yuzler, monkeypatch):
    yuz_tanit(tani, [("101", "Tuncay", yuzler["Tuncay_1"]["kod"])])
    monkeypatch.setattr(tani, "yuzleri_yukle", lambda: None)   # elle verilen yüzler kalsın
    tani.son_kare = yuzler["Tuncay_3"]["bgr"]

    def uyku(s):
        if tani.son_yuzler:   # kare işlendi
            raise Dur
    monkeypatch.setattr(tani.time, "sleep", uyku)
    with pytest.raises(Dur):
        tani.tani()
    assert tani.son_yuzler[0][1:3] == ("Tuncay", "tanindi")


# ---------- Yüz dosyasının yeniden yüklenmesi ----------

def test_yuz_dosyasi_degisince_yeniden_yuklenir(tani, db):
    from conftest import ogrenci_ekle
    from veri import yuzleri_yaz
    ogrenci_ekle(db, "101", "Ayşe")
    tani.yuzleri_yukle()
    assert tani.numaralar == []
    yuzleri_yaz(["101"], [np.zeros(128)])
    tani.yuzleri_yukle()
    assert tani.numaralar == ["101"] and tani.adlar == {"101": "Ayşe"}
    time.sleep(0.01)
    yuzleri_yaz([], [])
    tani.yuzleri_yukle()
    assert tani.numaralar == []


def test_yazi_tipi_bulunamazsa_varsayilan(tani, monkeypatch):
    monkeypatch.setattr(tani, "YAZI_TIPLERI", ["/yok/yazi.ttf"])
    assert tani.yazi_tipi_bul() is not None
