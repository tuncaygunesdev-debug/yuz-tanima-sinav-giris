# Web sitesi: şifre ve oturum, kiosk mesajları, test modu, "Bugünü sıfırla", sayfa kodları.

import re
import shutil
import subprocess
import time

import pytest

from conftest import KONUM, bos_kare, ogrenci_ekle, sinav_ekle


# ---------- Şifre ve oturum ----------

def test_sifresiz_erisim_engellenir(site):
    c = site.app.test_client()
    for sayfa in ("/tanima", "/kisiler", "/sinavlar", "/kiosk", "/kayit", "/canli", "/static/fotolar/x.jpg"):
        assert c.get(sayfa).status_code == 302, sayfa
    assert c.get("/api/kisiler").status_code == 401
    assert c.post("/api/kisi_sil", data={"numara": "1"}).status_code == 401
    assert c.post("/api/gunu_sifirla").status_code == 401


def test_logo_sifresiz_acilir_ama_digerleri_acilmaz(site, tmp_path):
    (tmp_path / "static" / "marka").mkdir()
    (tmp_path / "static" / "marka" / "amblem.png").write_bytes(b"\x89PNG")
    (tmp_path / "static" / "fotolar" / "gizli.jpg").write_bytes(b"x")
    c = site.app.test_client()
    assert c.get("/static/marka/amblem.png").status_code != 302      # giriş ekranında logo görünsün
    assert c.get("/static/fotolar/gizli.jpg").status_code == 302      # yüz fotoğrafları şifreli kalsın
    assert c.get("/static/marka/../fotolar/gizli.jpg").status_code in (302, 404)


def test_ilk_sifre_sadece_bu_bilgisayardan(site, monkeypatch):
    monkeypatch.setattr(site, "SIFRE_DOSYASI", "sifre.txt")   # her test kendi klasöründe: şifre yok
    uzak = site.app.test_client().get("/giris", environ_base={"REMOTE_ADDR": "192.168.1.20"})
    assert "henüz belirlenmedi" in uzak.get_data(as_text=True)
    yerel = site.app.test_client().get("/giris")
    assert "Şifre belirleyin" in yerel.get_data(as_text=True)


def test_sifre_belirleme_ve_giris(site):
    c = site.app.test_client()
    assert "en az 6" in c.post("/giris", data={"sifre": "abc", "tekrar": "abc"}).get_data(as_text=True)
    assert "aynı değil" in c.post("/giris", data={"sifre": "gizli123", "tekrar": "gizli124"}).get_data(as_text=True)
    assert c.post("/giris", data={"sifre": "gizli123", "tekrar": "gizli123"}).status_code == 302
    assert c.get("/tanima").status_code == 200          # oturum açıldı
    c.get("/cikis")
    assert c.get("/tanima").status_code == 302          # çıkış yapıldı
    yanlis = site.app.test_client().post("/giris", data={"sifre": "yanlis1"})
    assert "Şifre yanlış" in yanlis.get_data(as_text=True)
    dogru = site.app.test_client()
    assert dogru.post("/giris", data={"sifre": "gizli123"}).status_code == 302
    assert dogru.get("/tanima").status_code == 200
    assert open("sifre.txt").read().startswith(("scrypt", "pbkdf2"))   # şifrenin kendisi saklanmaz


# ---------- Kiosk mesajları ----------

@pytest.mark.parametrize("tur, baslik", [
    ("giris", "Hoş geldiniz"), ("tekrar", "Zaten giriş yaptınız"), ("bilinmeyen", "Kaydınız yok"),
    ("listede_yok", "Bu sınava kaydınız yok"), ("canlilik_yok", "Canlılık doğrulanamadı"),
    ("erken", "Giriş henüz açılmadı"), ("gec", "Giriş kapandı"),
])
def test_kiosk_mesajlari(site, db, tur, baslik):
    sid = sinav_ekle(db, bas_dk=10)
    db.execute("INSERT INTO olaylar (isim, ogrenci_no, zaman, tur, sira, sinav_id) VALUES "
               "('Ayşe', ?, datetime('now', 'localtime'), ?, 5, ?)", (None if tur == "bilinmeyen" else "101", tur, sid))
    db.commit()
    olay = site.olay_getir(db, 1)
    assert olay["baslik"] == baslik and olay["soz"]
    if tur == "bilinmeyen":
        assert "sınav" not in olay["baslik"].lower()   # kayıtsız kişiye sınavdan bahsedilmez


def test_kiosk_ilk_acilista_eski_olaylari_gostermez(istemci, db, tani):
    tani.olay_yaz(db, None, bos_kare(), KONUM)
    ilk = istemci.get("/api/olaylar").get_json()
    assert ilk["olaylar"] == [] and ilk["son"] == 1
    tani.olay_yaz(db, None, bos_kare(), KONUM)
    yeni = istemci.get(f"/api/olaylar?son={ilk['son']}").get_json()
    assert [o["id"] for o in yeni["olaylar"]] == [2]


def test_kiosk_aktif_sinav_ve_giris_penceresi(istemci, db):
    sinav_ekle(db, ad="Fizik", bas_dk=10, acilis=30)
    v = istemci.get("/api/olaylar").get_json()
    assert v["sinav"] == "Fizik" and v["pencere"]["pencere"] == "acik" and v["pencere"]["kapanisa_sn"] > 0


# ---------- Test modu ----------

def test_izleme_test_modunu_acar_ve_kiosk_gorur(istemci, tani):
    assert istemci.get("/api/izleme").get_json()["test_modu"] is False
    assert istemci.get("/api/izleme?test=1").get_json()["test_modu"] is True
    assert tani.test_modunda()
    assert istemci.get("/api/olaylar").get_json()["canlilik"]["test_modu"] is True


def test_test_modu_nabiz_kesilince_kendiliginden_biter(istemci, tani):
    istemci.get("/api/izleme?test=1")
    tani.test_modu_bitis = time.time() - 0.1   # 3 sn geçti, yeni nabız gelmedi
    assert istemci.get("/api/izleme").get_json()["test_modu"] is False


def test_izleme_aktif_sinavi_bildirir(istemci, db):
    assert istemci.get("/api/izleme").get_json()["aktif_sinav"] is None
    sinav_ekle(db, ad="Kimya")
    assert istemci.get("/api/izleme").get_json()["aktif_sinav"] == "Kimya"


# ---------- Bugünü sıfırla ----------

def test_bugunu_sifirla_sadece_bugunu_siler(istemci, db, tani):
    ogrenci_ekle(db, "101", "Ayşe")
    tani.adlar = {"101": "Ayşe"}
    tani.olay_yaz(db, "101", bos_kare(), KONUM)
    db.execute("INSERT INTO olaylar (isim, zaman, tur) VALUES ('Dün', '2000-01-01 10:00:00', 'giris')")
    db.commit()
    assert istemci.post("/api/gunu_sifirla").get_json()["ok"]
    assert db.execute("SELECT isim FROM olaylar").fetchall() == [("Dün",)]
    assert db.execute("SELECT COUNT(*) FROM ogrenciler").fetchone()[0] == 1


# ---------- Sayfa kodları ----------

@pytest.mark.skipif(shutil.which("node") is None, reason="node yok, sayfa kodu kontrolü atlandı")
@pytest.mark.parametrize("sayfa", ["/tanima", "/kisiler", "/sinavlar", "/sinav/1", "/kiosk", "/kayit"])
def test_sayfa_kodlarinda_hata_yok(istemci, db, tmp_path, sayfa):
    sinav_ekle(db)
    html = istemci.get(sayfa).get_data(as_text=True)
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    dosya = tmp_path / "sayfa.js"
    dosya.write_text(js, encoding="utf-8")
    sonuc = subprocess.run(["node", "--check", str(dosya)], capture_output=True, text=True)
    assert sonuc.returncode == 0, sonuc.stderr


# ---------- Renkler: sadece PAÜ mavisi ----------

def test_sitede_yesil_sari_kirmizi_renk_yok(site, tani):
    """Bütün ekranlar PAÜ DTBMYO mavisinin tonlarını kullanır; yeşil / sarı / kırmızı / mor yok."""
    import colorsys
    from pathlib import Path

    def mavi_tonu_mu(r, g, b):
        ton, _, doygunluk = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        return doygunluk < 0.15 or 0.50 <= ton <= 0.65      # gri/beyaz/siyah ya da mavi aralığı

    kod = (Path(site.__file__).read_text(encoding="utf-8"))
    yasakli = []
    for onaltilik in re.findall(r"#([0-9a-fA-F]{6})\b", kod):
        r, g, b = (int(onaltilik[i:i + 2], 16) for i in (0, 2, 4))
        if not mavi_tonu_mu(r, g, b):
            yasakli.append("#" + onaltilik)
    assert not yasakli, f"mavi olmayan renkler: {sorted(set(yasakli))}"
    for renk in tani.RENKLER.values():
        assert mavi_tonu_mu(*renk), renk
