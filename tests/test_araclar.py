# Yardımcı programlar: kaydet.py (yüz veritabanını baştan kurma), hassasiyet.py (ölçüm aracı),
# sahte_kamera.py (webcam yayını), baslat.py (kamera seçimi, telefon yoksa webcam, servisleri yönetme).
# Gerçek sistemin portlarına (5000, 8081, 8082) dokunulmaz.

import http.server
import os
import pickle
import shutil
import subprocess
import sys
import threading

import cv2
import numpy as np
import pytest

from conftest import FOTOLAR, PROJE, ogrenci_ekle

PYTHON = sys.executable


def betik(ad, *arg):
    """Projedeki bir betiği bu test klasöründe çalıştır."""
    ortam = dict(os.environ, PYTHONPATH=str(PROJE), PYTHONWARNINGS="ignore")
    return subprocess.run([PYTHON, str(PROJE / ad), *arg], capture_output=True, text=True, timeout=180, env=ortam)


# ---------- kaydet.py ----------

def test_kaydet_kayitli_ogrencilerin_fotograflarindan_kurar(db, yuzler):
    ogrenci_ekle(db, "101", "Tuncay Test")
    shutil.copy(FOTOLAR / "Tuncay_1.jpg", "kisiler/101_1.jpg")
    shutil.copy(FOTOLAR / "Tuncay_3.jpg", "kisiler/101_2.jpg")
    shutil.copy(FOTOLAR / "kerim_1.jpg", "kisiler/999_1.jpg")      # sitede kayıtlı değil
    cv2.imwrite("kisiler/101_3.jpg", np.zeros((200, 200, 3), np.uint8))   # yüzsüz
    sonuc = betik("kaydet.py")
    assert sonuc.returncode == 0, sonuc.stderr
    assert "999: sitede kayıtlı öğrenci değil" in sonuc.stdout
    assert "101_3.jpg: 0 yüz bulundu" in sonuc.stdout
    numaralar, kodlar = pickle.load(open("yuzler.pkl", "rb"))
    assert numaralar == ["101", "101"] and len(kodlar) == 2


# ---------- hassasiyet.py ----------

def test_hassasiyet_raporu(db, yuzler):
    ogrenci_ekle(db, "101", "Tuncay Test")
    ogrenci_ekle(db, "202", "Yağız Test")
    for kaynak, hedef in (("Tuncay_1", "101_1"), ("Tuncay_3", "101_2"), ("Yağız_1", "202_1"), ("Yağız_2", "202_2")):
        shutil.copy(FOTOLAR / f"{kaynak}.jpg", f"kisiler/{hedef}.jpg")
    sonuc = betik("hassasiyet.py")
    assert sonuc.returncode == 0, sonuc.stderr
    for bolum in ("1) AYNI ÖĞRENCİ", "2) FARKLI ÖĞRENCİLER", "3) TANIMA PROVASI", "ÖNERİ"):
        assert bolum in sonuc.stdout
    assert "YANLIŞ KİŞİ: 0" in sonuc.stdout


def test_hassasiyet_tek_ogrenciyle_calismaz(db, yuzler):
    ogrenci_ekle(db, "101", "Tuncay Test")
    shutil.copy(FOTOLAR / "Tuncay_1.jpg", "kisiler/101_1.jpg")
    sonuc = betik("hassasiyet.py")
    assert sonuc.returncode != 0 and "en az 2" in sonuc.stderr


# ---------- sahte_kamera.py ----------

class SahteKaynak:
    def __init__(self, kareler):
        self.kareler, self.basa_sarildi = list(kareler), 0

    def read(self):
        return self.kareler.pop(0) if self.kareler else (False, None)

    def set(self, ozellik, deger):
        self.basa_sarildi += 1
        self.kareler.append((True, np.zeros((720, 1280, 3), np.uint8)))


def test_sahte_kamera_640x480_jpeg_yayinlar(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("sahte_kamera_t", PROJE / "sahte_kamera.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)   # içe aktarınca kameraya bağlanmaz / sunucu açmaz
    assert modul.kaynak is None
    modul.kaynak = SahteKaynak([(True, np.zeros((1080, 1920, 3), np.uint8)), (False, None)])
    uretec = modul.kareler()
    for _ in range(2):   # ikinci karede video bitti -> başa sarar
        parca = next(uretec)
        jpg = parca[parca.index(b"\r\n\r\n") + 4:].rstrip(b"\r\n")
        assert cv2.imdecode(np.frombuffer(jpg, np.uint8), 1).shape == (480, 640, 3)
    assert modul.kaynak.basa_sarildi == 1
    cevap = modul.app.test_client().get("/stream")
    assert cevap.mimetype == "multipart/x-mixed-replace"


# ---------- baslat.py ----------

@pytest.fixture
def baslat(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("baslat_t", PROJE / "baslat.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)   # içe aktarınca hiçbir şey başlatmaz
    bildirimler = []
    monkeypatch.setattr(modul, "bildir", lambda baslik, metin="": bildirimler.append(baslik))
    modul.bildirimler = bildirimler
    return modul


@pytest.fixture
def ag_kamerasi():
    """Telefonun yerine geçen küçük bir HTTP sunucusu (boş bir port)."""
    class Isleyici(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"--frame\r\n" + b"x" * 2000)

        def log_message(self, *a):
            pass
    sunucu = http.server.HTTPServer(("127.0.0.1", 0), Isleyici)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{sunucu.server_address[1]}/video"
    sunucu.shutdown()


def test_telefona_ulasilinca_telefon_kullanilir(baslat, ag_kamerasi):
    assert baslat.kamera_sec(ag_kamerasi, 90) == (ag_kamerasi, 90)
    assert baslat.bildirimler == []


def test_telefon_yoksa_webcame_gecer_ve_bildirir(baslat):
    kamera, dondur = baslat.kamera_sec("http://127.0.0.1:9/video", 90)   # kapalı port
    assert (kamera, dondur) == (baslat.WEBCAM, 0)
    assert baslat.bildirimler == ["Telefon kamerasına ulaşılamadı"]


def test_webcam_ayarliyken_kontrol_edilmez(baslat):
    assert baslat.kamera_sec(baslat.WEBCAM, 0) == (baslat.WEBCAM, 0)


def test_servis_listesi(baslat):
    assert [ad for ad, _ in baslat.servis_listesi(baslat.WEBCAM)] == ["kamera", "tanima", "site"]
    assert [ad for ad, _ in baslat.servis_listesi("http://10.0.0.5:8080/video")] == ["tanima", "site"]


def test_biri_kapaninca_hepsi_kapatilir(baslat, tmp_path):
    uzun = tmp_path / "uzun.py"
    uzun.write_text("import time\ntime.sleep(60)\n")
    kisa = tmp_path / "kisa.py"
    kisa.write_text("import sys\nprint('kisa calisti')\nsys.exit(3)\n")
    baslangic = __import__("time").time()
    kapanan = baslat.calistir([("uzun", [PYTHON, str(uzun)]), ("kisa", [PYTHON, str(kisa)])], aralik=0.3)
    assert kapanan == "kisa"
    assert __import__("time").time() - baslangic < 15               # 60 sn'lik süreç beklenmeden kapatıldı
    assert "Sınav Giriş sistemi durdu" in baslat.bildirimler
    out = subprocess.run(["pgrep", "-f", str(uzun)], capture_output=True, text=True).stdout
    assert out.strip() == ""                                         # uzun süreç de kapatılmış


def test_tani_kamera_secimini_ortamdan_alir(tmp_path):
    """baslat.py'nin seçtiği kamera tani.py'ye ortam değişkeniyle geçer."""
    kod = ("import sys; sys.path.insert(0, %r); import tani; print(tani.KAMERA, tani.KAMERA_DONDUR)" % str(PROJE))
    ortam = dict(os.environ, SINAV_KAMERA="http://localhost:8081/stream", SINAV_KAMERA_DONDUR="0",
                 PYTHONWARNINGS="ignore")
    sonuc = subprocess.run([PYTHON, "-c", kod], capture_output=True, text=True, timeout=120, env=ortam, cwd=tmp_path)
    assert sonuc.stdout.strip() == "http://localhost:8081/stream 0", sonuc.stderr
