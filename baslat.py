# Bütün sistemi tek komutla başlatır:
#     python3 baslat.py              (durdurmak için Ctrl+C)
#     python3 baslat.py --tarayici   (site hazır olunca tarayıcıyı da açar; masaüstü simgesi bunu kullanır)
# venv'i etkinleştirmeye gerek yok; gerekirse kendisi venv'deki Python'a geçer.
#
# Kamera seçimi:
#   - ayarlar.py'deki KAMERA sahte kamerayı (webcam) gösteriyorsa sahte_kamera.py'yi de açar.
#   - KAMERA bir ağ kamerasıysa (telefon / ESP32) önce ona ulaşılabiliyor mu bakar; ulaşılamazsa
#     (ör. telefon kapalı, Wi-Fi değişti) bilgisayarın webcam'ine geçer ve bunu bildirir.
#     Sunumda kamera sorunu yüzünden sistemin hiç açılmaması olmasın diye.

import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

KLASOR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(KLASOR, "venv", "bin", "python")

if __name__ == "__main__":
    os.chdir(KLASOR)
    # venv dışından çalıştırıldıysa venv'deki Python ile yeniden başla
    if sys.prefix == sys.base_prefix and os.path.exists(VENV_PYTHON):
        os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, KLASOR)
from ayarlar import KAMERA, KAMERA_DONDUR, SITE_PORT  # noqa: E402

WEBCAM = "http://localhost:8081/stream"
SITE = f"http://localhost:{SITE_PORT}"


def bildir(baslik, metin=""):
    """Masaüstü bildirimi (varsa) + konsol."""
    print(f"{baslik} {metin}".strip(), flush=True)
    try:
        subprocess.run(["notify-send", "-a", "Sınav Giriş", "-i", os.path.join(KLASOR, "static/marka/amblem.png"),
                        baslik, metin], timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def kameraya_ulasiliyor_mu(adres, sure=4):
    try:
        with urllib.request.urlopen(adres, timeout=sure) as cevap:
            return bool(cevap.read(1024))
    except Exception:
        return False


def kamera_sec(kamera=KAMERA, dondur=KAMERA_DONDUR):
    """Kullanılacak kamera ve döndürme açısı. Ağ kamerasına ulaşılamazsa webcam'e geçer."""
    if not kamera.startswith("http://localhost:8081") and not kameraya_ulasiliyor_mu(kamera):
        bildir("Telefon kamerasına ulaşılamadı",
               f"{kamera} cevap vermiyor; bilgisayarın webcam'i kullanılıyor. "
               "IP Webcam'i açıp sistemi yeniden başlatırsanız telefona geçer.")
        return WEBCAM, 0
    return kamera, dondur


def servis_listesi(kamera):
    """Başlatılacak programlar: (ad, komut). Webcam kullanılıyorsa sahte_kamera.py de açılır."""
    servisler = []
    if kamera.startswith("http://localhost:8081"):
        servisler.append(("kamera", "sahte_kamera.py"))
    servisler += [("tanima", "tani.py"), ("site", "site.py")]
    return [(ad, [sys.executable, "-u", "-W", "ignore", dosya]) for ad, dosya in servisler]


def ciktiyi_aktar(ad, surec):
    for satir in surec.stdout:
        print(f"[{ad}] {satir}", end="", flush=True)


def tarayiciyi_ac():
    """Site cevap verene kadar bekle (en çok 30 sn), sonra tarayıcıda aç."""
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{SITE}/giris", timeout=1).close()
            webbrowser.open(SITE)
            return
        except Exception:
            time.sleep(0.5)
    bildir("Site açılamadı", "loglar/sistem.log dosyasına bakın.")


def durdur(*_):
    raise KeyboardInterrupt


def calistir(servisler, ortam=None, tarayici=False, aralik=1.5):
    """Servisleri sırayla başlat; biri kapanırsa (ya da Ctrl+C / SIGTERM gelirse) hepsini kapat.
    Döner: beklenmedik şekilde kapanan servisin adı ya da None."""
    surecler, kapanan = [], None
    try:
        for ad, komut in servisler:
            surec = subprocess.Popen(komut, env=ortam, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, cwd=KLASOR)
            threading.Thread(target=ciktiyi_aktar, args=(ad, surec), daemon=True).start()
            surecler.append((ad, surec))
            time.sleep(aralik)   # sırayla açılsınlar: önce kamera, sonra tanıma, sonra site

        print(f"\nSistem çalışıyor: {SITE}   (durdurmak için Ctrl+C)\n", flush=True)
        if tarayici:
            threading.Thread(target=tarayiciyi_ac, daemon=True).start()

        while kapanan is None:   # biri kapanırsa hepsini kapat, yarım çalışan sistem kalmasın
            for ad, surec in surecler:
                if surec.poll() is not None:
                    kapanan = ad
                    print(f"\n[{ad}] beklenmedik şekilde durdu (kod {surec.returncode}). "
                          "Hepsi kapatılıyor; yukarıdaki hata mesajına bakın.", flush=True)
                    bildir("Sınav Giriş sistemi durdu", f"{ad} beklenmedik şekilde kapandı; loglar/sistem.log")
                    break
            else:
                time.sleep(min(aralik, 1))
    except KeyboardInterrupt:
        pass
    finally:
        print("\nKapatılıyor...", flush=True)
        for _, surec in surecler:
            if surec.poll() is None:
                surec.terminate()
        for _, surec in surecler:
            try:
                surec.wait(timeout=5)
            except subprocess.TimeoutExpired:
                surec.kill()
        print("Kapatıldı.")
    return kapanan


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, durdur)   # "Sistemi durdur" simgesi ve systemd kapatırken de düzgün dursun
    kamera, dondur = kamera_sec()
    ortam = dict(os.environ, SINAV_KAMERA=kamera, SINAV_KAMERA_DONDUR=str(dondur))   # tani.py bunları okur
    calistir(servis_listesi(kamera), ortam, tarayici="--tarayici" in sys.argv)
