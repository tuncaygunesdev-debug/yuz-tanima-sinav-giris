# Sitenin geri kalan adresleri: canlı görüntü aktarımı, tanıma servisi kapalıyken davranış,
# ses adresleri, olmayan kayıtlar için hata cevapları, büyük fotoğrafın küçültülmesi.

import io
import socket

import cv2
import numpy as np
import pytest

from conftest import KONUM, bos_kare, ogrenci_ekle, sinav_ekle


@pytest.fixture
def tani_kapali(site, monkeypatch):
    """Tanıma servisi (tani.py) çalışmıyormuş gibi: site boş bir porta yönlendirilir."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setattr(site, "TANI", f"http://127.0.0.1:{port}")


# ---------- Canlı görüntü aktarımı ----------

def test_canli_goruntu_tani_dan_aktarilir(istemci, tani):
    tani.son_kare = np.zeros((480, 640, 3), np.uint8)
    cevap = istemci.get("/canli?ham=1")
    assert cevap.mimetype == "multipart/x-mixed-replace"
    ilk = next(iter(cevap.response))
    assert b"--frame" in ilk and b"image/jpeg" in ilk
    cevap.close()


def test_tani_kapaliyken(istemci, tani_kapali):
    assert istemci.get("/canli").status_code == 503
    assert istemci.get("/api/poz").status_code == 503
    assert istemci.get("/api/izleme").get_json()["test_modu"] is None
    assert istemci.get("/api/olaylar").get_json()["canlilik"] == {"bekliyor": False}
    cevap = istemci.post("/api/kisi_ekle", data={"numara": "101", "ad_soyad": "Ali Veli", "kvkk": "1"}).get_json()
    assert cevap["kod"] == "kamera"


# ---------- Ses adresleri ----------

def test_ses_cumle_motor_yoksa_metin_doner(istemci, site, monkeypatch):
    monkeypatch.setattr(site.ses, "konus", lambda metin: None)
    assert istemci.get("/api/ses_cumle?anahtar=sag").get_json()["metin"].startswith("Şimdi başınızı")
    assert "Ayşe Yılmaz" in istemci.get("/api/ses_cumle?bitti=Ayşe Yılmaz").get_json()["metin"]
    assert istemci.get("/api/ses_cumle?anahtar=yok").status_code == 404
    assert istemci.get("/api/ses_cumle?bitti=<script>").status_code == 400


def test_ses_cumle_motor_varsa_wav(istemci, site, monkeypatch):
    monkeypatch.setattr(site.ses, "konus", lambda metin: b"RIFF....WAVE")
    cevap = istemci.get("/api/ses_cumle?anahtar=kirp")
    assert cevap.mimetype == "audio/wav" and cevap.data.startswith(b"RIFF")


def test_olay_sesi(istemci, site, db, tani, monkeypatch):
    tani.olay_yaz(db, None, bos_kare(), KONUM)
    monkeypatch.setattr(site.ses, "konus", lambda metin: None)
    assert istemci.get("/api/ses/1").status_code == 204           # motor yok: kiosk tarayıcı sesini kullanır
    monkeypatch.setattr(site.ses, "konus", lambda metin: b"RIFF")
    assert istemci.get("/api/ses/1").mimetype == "audio/wav"
    assert istemci.get("/api/ses/999").status_code == 404


# ---------- Sayfalar ve olmayan kayıtlar ----------

def test_ana_sayfa_canli_izlemeye_yonlenir(istemci):
    assert istemci.get("/").headers["Location"].endswith("/tanima")


def test_olmayan_sinav(istemci):
    assert istemci.get("/sinav/999").status_code == 302
    assert istemci.get("/api/sinav/999").status_code == 404
    assert istemci.get("/sinav/999/excel").status_code == 302
    for adres in ("durum", "ogrenciler", "sil", "demo", "elle_giris"):
        assert istemci.post(f"/api/sinav/999/{adres}", data={"islem": "baslat"}).get_json()["ok"] is False


def test_gecersiz_sinav_islemi(istemci, db):
    sid = sinav_ekle(db)
    assert istemci.post(f"/api/sinav/{sid}/durum", data={"islem": "patlat"}).get_json()["ok"] is False


def test_olmayan_ogrenci(istemci):
    assert istemci.get("/api/ogrenci/999").get_json()["ok"] is False
    assert istemci.post("/api/kisi_sil", data={"numara": "999"}).get_json()["ok"] is False
    assert istemci.post("/api/ogrenci/999/foto_sil", data={"dosya": "999_1.jpg"}).get_json()["ok"] is False


def test_degisiklik_yoksa_duzenleme_bir_sey_yapmaz(istemci, db):
    ogrenci_ekle(db, "101", "Ayşe Yılmaz")
    cevap = istemci.post("/api/ogrenci/101/duzenle", data={"yeni_numara": "101", "ad_soyad": "Ayşe Yılmaz"}).get_json()
    assert cevap["ok"] and cevap["mesaj"] == "Değişiklik yok."


def test_kayit_fotografi_sunulur(istemci, tmp_path):
    cv2.imwrite(str(tmp_path / "kisiler" / "101_1.jpg"), np.zeros((10, 10, 3), np.uint8))
    assert istemci.get("/kisi_foto/101_1.jpg").mimetype == "image/jpeg"
    assert istemci.get("/kisi_foto/../kayitlar.db").status_code == 404


def test_kayitlar_listesi_alanlari(istemci, db, tani):
    ogrenci_ekle(db, "101", "Ayşe")
    tani.adlar = {"101": "Ayşe"}
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    kayit = istemci.get("/api/kayitlar").get_json()[0]
    assert {"isim", "no", "zaman", "foto", "tur", "sira"} <= set(kayit) and kayit["tur"] == "giris"


def test_buyuk_telefon_fotografi_kucultulur(istemci, yuzler):
    buyuk = cv2.resize(yuzler["Tuncay_1"]["bgr"], None, fx=5, fy=5)   # ~3200 piksel
    _, jpg = cv2.imencode(".jpg", buyuk)
    cevap = istemci.post("/api/kisi_ekle", content_type="multipart/form-data",
                         data={"numara": "101", "ad_soyad": "Tuncay Test", "kvkk": "1",
                               "foto": (io.BytesIO(jpg.tobytes()), "buyuk.jpg")}).get_json()
    assert cevap["ok"], cevap
    assert max(cv2.imread("kisiler/101_1.jpg").shape[:2]) <= 1600


# ---------- Ses ön yüklemesi ----------

def test_ses_on_yukleme(monkeypatch, tmp_path):
    import time
    import ses
    uretilen = []
    monkeypatch.setattr(ses, "hazir", lambda: True)
    monkeypatch.setattr(ses, "_yukle", lambda: None)
    monkeypatch.setattr(ses, "konus", lambda metin: uretilen.append(metin))
    ses.isit(["bir", "iki"])
    for _ in range(50):
        if len(uretilen) == 2:
            break
        time.sleep(0.02)
    assert uretilen == ["bir", "iki"]
