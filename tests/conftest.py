# Testlerin ortak hazırlığı.
#
# - Her test BOŞ, geçici bir klasörde çalışır (kayitlar.db, kisiler/, static/fotolar/ orada oluşur);
#   gerçek veritabanına, öğrencilere ve fotoğraflara hiç dokunulmaz. Çalışan sistemi durdurmaya gerek yok.
# - Kamera gerekmez. Yüz tanıma testleri kisiler_eski/ klasöründeki fotoğrafları okur
#   (klasör yoksa yüz testleri atlanır).
# - tani.py'nin Flask uygulaması testlere özel bir portta çalıştırılır; site.py ona bağlanır.

import importlib.util
import os
import socket
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJE = Path(__file__).resolve().parent.parent
FOTOLAR = PROJE / "kisiler_eski"
sys.path.insert(0, str(PROJE))


def _yukle(ad, dosya):
    spec = importlib.util.spec_from_file_location(ad, PROJE / dosya)
    modul = importlib.util.module_from_spec(spec)
    sys.modules[ad] = modul
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="session")
def oturum_klasoru(tmp_path_factory):
    """Modüller bu klasörde yüklenir (site.py ilk açılışta gizli_anahtar.txt oluşturur)."""
    klasor = tmp_path_factory.mktemp("oturum")
    onceki = os.getcwd()
    os.chdir(klasor)
    yield klasor
    os.chdir(onceki)


@pytest.fixture(scope="session")
def tani(oturum_klasoru):
    return _yukle("tani", "tani.py")


@pytest.fixture(scope="session")
def site(tani):
    """site.py (adı Python'un kendi 'site' modülüyle çakışmasın diye 'site_uyg' olarak yüklenir).
    tani.py'nin web uygulaması boş bir portta çalıştırılır ve site.py ona yönlendirilir."""
    from werkzeug.serving import make_server
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    sunucu = make_server("127.0.0.1", port, tani.app, threaded=True)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    modul = _yukle("site_uyg", "site.py")
    modul.TANI = f"http://127.0.0.1:{port}"
    yield modul
    sunucu.shutdown()


@pytest.fixture(autouse=True)
def temiz_klasor(tmp_path, monkeypatch, request):
    """Her test kendi boş klasöründe ve tani.py'nin hafızası sıfırlanmış olarak başlar."""
    (tmp_path / "kisiler").mkdir()
    (tmp_path / "static" / "fotolar").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    if "tani" in sys.modules:
        t = sys.modules["tani"]
        t.numaralar, t.kodlar, t.adlar, t.yuz_dosya_zamani = [], [], {}, None
        t.bekleyen, t.son_kare, t.son_yuzler = None, None, []
        t.test_modu_bitis = t.kayit_modu_bitis = 0.0
        t.son_poz = {"zaman": 0.0, "yuz": 0, "yon": None, "oran": None}
        t.poz_kareleri = {}
    yield tmp_path


@pytest.fixture
def istemci(site):
    """Görevli olarak giriş yapmış tarayıcı."""
    c = site.app.test_client()
    with c.session_transaction() as oturum:
        oturum["giris"] = True
    return c


@pytest.fixture
def db():
    from veri import db_ac
    baglanti = db_ac()
    yield baglanti
    baglanti.close()


# ---------- Yüz fotoğrafları ----------

@pytest.fixture(scope="session")
def yuzler():
    """kisiler_eski/ fotoğraflarından yüz kodları: {"Tuncay_1": {"yol", "rgb", "bgr", "kod", "konum"}, ...}"""
    if not FOTOLAR.is_dir():
        pytest.skip("kisiler_eski/ klasörü yok; yüz testleri atlandı")
    import cv2
    import face_recognition
    sonuc = {}
    for yol in sorted(FOTOLAR.glob("*.jpg")):
        rgb = face_recognition.load_image_file(str(yol))
        konumlar = face_recognition.face_locations(rgb)
        if len(konumlar) != 1:
            continue
        sonuc[yol.stem] = {"yol": yol, "rgb": rgb, "bgr": cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                           "konum": konumlar[0], "kod": face_recognition.face_encodings(rgb, konumlar)[0]}
    gerekli = {"Tuncay_1", "Tuncay_2", "Tuncay_3", "Yağız_1", "kerim_1"}
    if not gerekli <= set(sonuc):
        pytest.skip(f"kisiler_eski/ içinde gerekli fotoğraflar yok: {sorted(gerekli - set(sonuc))}")
    return sonuc


# ---------- Yardımcılar ----------

def ogrenci_ekle(db, numara, ad):
    db.execute("INSERT INTO ogrenciler VALUES (?, ?, '2026-01-01 00:00:00', '2026-01-01 00:00:00')", (numara, ad))
    db.commit()


def yuz_tanit(tani, kayitlar):
    """tani.py'ye kayıtlı yüzleri doğrudan ver: kayitlar = [(numara, ad, yüz kodu), ...]"""
    tani.numaralar = [n for n, _, _ in kayitlar]
    tani.kodlar = [k for _, _, k in kayitlar]
    tani.adlar = {n: a for n, a, _ in kayitlar}


def sinav_ekle(db, ad="Deneme", bas_dk=10, sure=60, acilis=30, gec=0, ogrenciler=(), koltuk=30, durum="aktif"):
    """Şu andan bas_dk dakika sonra başlayan sınav (eksi değer: geçmişte başlamış)."""
    bas = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=bas_dk)
    sinav_id = db.execute(
        "INSERT INTO sinavlar (ad, tarih, saat, koltuk_sayisi, durum, sure_dk, acilis_dk, gec_dk) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ad, bas.strftime("%Y-%m-%d"), bas.strftime("%H:%M"), koltuk, durum, sure, acilis, gec)).lastrowid
    db.executemany("INSERT INTO sinav_ogrencileri VALUES (?, ?)", [(sinav_id, n) for n in ogrenciler])
    db.commit()
    return sinav_id


def olaylar(db, *kolonlar):
    kolonlar = kolonlar or ("tur", "ogrenci_no")
    return db.execute(f"SELECT {', '.join(kolonlar)} FROM olaylar ORDER BY id").fetchall()


BOS_KARE = None


def bos_kare():
    import numpy as np
    return np.zeros((480, 640, 3), np.uint8)


KONUM = (100, 300, 300, 100)   # (üst, sağ, alt, sol): sahte yüz konumu
