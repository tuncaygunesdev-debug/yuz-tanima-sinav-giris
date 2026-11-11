# Geliştirici Rehberi

Bu belge projeyi geliştirmeye devam edecek kişi içindir: sistem nasıl çalışıyor, hangi
kararlar neden böyle alındı, nereden başlamalı. Kurulum ve kullanım için `README.md`, Claude Code kuralları için `CLAUDE.md`,
kullanılan teknolojilerin geniş anlatımı için `Teknoloji_Kitapcigi.pdf`.

Proje Kasım 2026'da Claude Code (yapay zekâ kodlama asistanı) ile birlikte, adım adım
geliştirildi. Aşağıdaki kararların çoğu gerçek denemelerde (webcam, telefon kamerası,
sınıf arkadaşlarının yüzleri) ortaya çıkan sorunlardan doğdu.

---

## 1. Büyük resim

```
 Kamera ──► tani.py (:8082) ──────────────► site.py (:5000) ──► Tarayıcı
 (telefon /  - kameradan okuyan TEK program    - web sitesi, API         - görevli paneli
  webcam /   - yüz bulma + tanıma              - görüntüyü tani.py'den    - giriş kiosku
  ESP32)     - canlılık (göz kırpma)             aktarır (/canli, /kare)  - kayıt kiosku
             - olayları veritabanına yazar     - şifre / oturum
                       │                               │
                       └──── kayitlar.db (SQLite) ─────┘
                             yuzler.pkl (yüz kodları)
                             kisiler/ (kayıt fotoğrafları)
                             static/fotolar/ (giriş anı fotoğrafları)
```

`baslat.py` hepsini birlikte açar; biri kapanırsa hepsini kapatır. Kamera webcam ise
araya `sahte_kamera.py` (:8081) girer: webcam'i okuyup ağ yayını gibi sunar, böylece
`tani.py` her kamerayı aynı şekilde (bir URL olarak) okur.

### Dosyalar

| Dosya | Görevi |
|---|---|
| `ayarlar.py` | Bütün ayarlar: kamera adresi, döndürme, tanıma eşikleri, canlılık, koltuk sayısı. |
| `veri.py` | Ortak veri işlemleri: veritabanı şeması ve göçleri, sınav saatleri, sıra seçimi, benzerlik yüzdesi, yüz dosyası okuma/yazma. Veritabanı tablolarının açıklaması dosyanın başında. |
| `tani.py` | Tanıma servisi. Kamera okuma iş parçacığı, tanıma döngüsü (`tani`), canlılık izleme (`canlilik_izle`), olay kararları (`olaylari_isle`, `olay_turu`, `olay_yaz`), görüntü yayını. |
| `site.py` | Web sitesi. HTML/CSS/JS sayfalar dosyanın içinde Jinja şablonu olarak durur (`ORTAK_STIL`, `MENU`, `GIRIS_SAYFASI`, `SAYFA`, `KIOSK_SAYFASI`, `SINAV_SAYFASI`, `KAYIT_SAYFASI`), altında API adresleri. |
| `ses.py` | Piper ile Türkçe konuşma üretir; üretilen sesleri `sesler/onbellek/` içinde saklar. |
| `kaydet.py` | `kisiler/` fotoğraflarından `yuzler.pkl`'yi baştan kurar (bozulursa kurtarma). |
| `hassasiyet.py` | Kayıtlı öğrencilerle eşik ölçümü yapar, `TOLERANS` için öneri verir. |
| `baslat.py` | Kamera seçimi (telefona ulaşılamazsa webcam), servisleri açma/kapatma. |
| `sahte_kamera.py` | Webcam'i `http://localhost:8081/stream` olarak yayınlar. |
| `sinav_giris.sh` | Tek tık başlatma / durdurma / kiosk (masaüstü simgesi bunu çalıştırır). |
| `masaustu_kur.sh`, `ses_indir.sh` | Simge kurulumu, ses modeli indirme. |
| `tests/` | 166 test (pytest). |

---

## 2. Önemli tasarım kararları

### Kamerayı sadece tani.py okur
İlk sürümde site de kamerayı ayrıca açıyordu; telefon kamerası iki bağlantıda takılıyor,
webcam ise ikinci programa hiç açılmıyordu. Şimdi görüntü tek yerden okunur, site
`/canli` ve `/kare` adreslerini `tani.py`'den aktarır. Yeni bir sayfa görüntü isterse
site üzerinden istemeli, kameraya doğrudan bağlanmamalı.

### Bir yüzü tanımak için üç şart
`tani.py` → `kisi_bul`, `olaylari_isle`:
1. En yakın kayıtlı yüzün mesafesi `TOLERANS`'tan (0.47) küçük olmalı.
2. En yakın kişi, ikinci en yakın **farklı** kişiden en az `MARJ` (0.05) daha yakın olmalı.
   Değilse sonuç `BELIRSIZ`: ekranda "?" ve iki aday adı görünür, olay yazılmaz.
   Bu kural, birbirine benzeyen iki öğrencinin karışmasını engellemek için eklendi.
3. Aynı kişi art arda `ONAY_KARE` (3) analizde görülmeli. Tek karelik yanlış eşleşmeler
   böylece kayda geçmez.

Eşikler 9 Kasım'da 4 kişi / 19 fotoğrafla ölçüldü (aynı kişi 0.26–0.59, farklı kişiler
0.51–0.85). Yeni bir sınıfta `venv/bin/python hassasiyet.py` ile yeniden ölçün.

Ekranda gösterilen yüzde `veri.benzerlik` ile hesaplanır: eşik tam %50'ye denk gelir.
Ham mesafe insanlara anlamsız geldiği için bu dönüşüm yapıldı; tanıma kararını etkilemez.

### Canlılık: göz kırpma
Fotoğrafla ya da telefon ekranıyla kandırmayı engellemek için tanınan öğrenci içeri
alınmadan önce gözünü kırpmalı. Ayrı bir iş parçacığı (`canlilik_izle`) her karede iki
gözün açıklık oranını (EAR) ölçer; oran kişinin kendi normal açıklığının `KIRPMA_ORANI`
(%72) altına inip geri açılırsa kırpma sayılır. `CANLILIK_SURE` (7 sn) içinde kırpmazsa
`canlilik_yok` olayı yazılır. Tanıma döngüsü yavaş (saniyede birkaç kare) olduğu için kırpma onunla
yakalanamıyordu; bu yüzden göz ölçümü ayrı ve hızlı (~1,5 ms) bir döngüde yapılır.

### Olay türleri ve sınav saatleri
Her kapı olayı `olaylar` tablosuna bir `tur` ile yazılır: `giris`, `tekrar`, `listede_yok`,
`bilinmeyen`, `canlilik_yok`, `erken`, `gec`. Karar `tani.olay_turu`'nda verilir:

- **Aktif sınav varsa:** sadece o sınavın listesindekiler girebilir; giriş penceresi
  `[başlangıç − acilis_dk, başlangıç + gec_dk)` aralığıdır (varsayılan: 30 dk önce açılır,
  başlangıçta kapanır). "Zaten girdi mi" ve sıra numaraları o sınava göredir.
- **Aktif sınav yoksa (serbest mod):** saat kuralı yok, kayıtlı herkes girer, takvim gününe göre.
- Sınavlar saatine göre kendiliğinden başlar ve biter (`veri.otomatik_sinav_durumu`).
  Sunum için sınav sayfasında "Demo" düğmesi sınavı hemen şimdiye göre başlatır.
- Görevli, yoklama listesinden bir öğrenciye elle giriş verebilir (açıklama: "Görevli onayıyla").

Sıra numarası boş sıralardan **rastgele** seçilir (`veri.bos_sira_sec`), kopya
çekmeye karşı yan yana oturmayı zorlaştırmak için.

### Kayıt modu ve test modu (heartbeat)
- **Kayıt modu:** kayıt kiosku açıkken `/poz` adresi sürekli sorgulanır. `tani.py` bu
  sorguları "kayıt yapılıyor" sinyali sayar ve o sırada giriş olayı yazmaz (formu dolduran
  öğrenciye "Kaydınız yok" denmesin diye).
- **Test modu:** Canlı İzleme'de görevli test modunu açınca `/izleme?test=1` sorgulanır;
  sinyal 3 sn gelmezse mod kendiliğinden kapanır. Tarayıcı kapanırsa sistem kilitli kalmaz.
- İki modda da kameradaki kişiler "olayı verilmiş" sayılır; mod bitince hemen "Hoş geldiniz"
  çıkmaz, kişi ayrılıp gelince normal giriş olur.

### Yönlendirmeli kayıt
Öğrenci düz, sağa, sola bakarken fotoğrafı sistem kendisi çeker. Baş yönü yüz
noktalarından hesaplanır: burnun iki göz ortasından sapması / göz arası mesafe
(`tani.bas_yonu`, eşikler `KAYIT_DUZ_ESIK`, `KAYIT_YAN_ESIK`). Kamera aynalı olabileceği
için ilk yan pozda hangi yana dönülürse kabul edilir.

### Görüntü yönü
- `KAMERA_DONDUR`: kameradan gelen görüntüyü döndürür (telefon dik/yatay tutulursa).
  Tanıma döndürülmüş görüntü üzerinde yapılır.
- `GORUNTU_AYNA`: sadece **ekranda** ayna görüntüsü. Tanıma ve kayıt fotoğrafları
  kameranın verdiği gibi kalır.

### Türkçe yazı
OpenCV'nin `putText` fonksiyonu Türkçe harfleri (ğ, ş, İ…) çizemez; görüntüdeki
isimler Pillow ile sistemdeki bir TrueType yazı tipiyle çizilir (`tani.yazi_tipi_bul`).

### Görünüm
Arayüz Pamukkale Üniversitesi DTBMYO renkleriyle, **yalnızca mavi tonlarıyla** tasarlandı:
`--brand #004684` (lacivert), `--vurgu #0085d0` (açık mavi). Yeşil, sarı, kırmızı
kullanılmaz; durumlar mavinin tonlarıyla ve simgelerle (✓ ! ✕ ?) ayırt edilir.
Renkler `site.py` → `ORTAK_STIL` içinde CSS değişkeni olarak, görüntü üzerindeki kutu
renkleri `tani.py` → `RENKLER` içinde tanımlı.

### Güvenlik ve KVKK
- Site şifrelidir; şifre ilk açılışta, sadece sistemin çalıştığı bilgisayardan belirlenir.
  Şifre özeti `sifre.txt`, oturum anahtarı `gizli_anahtar.txt` dosyasındadır.
- Kayıt KVKK onay kutusu işaretlenmeden yapılamaz; onay zamanı kaydedilir.
- **Kişisel veriler depoya asla girmez:** `kisiler/`, `static/fotolar/`, `kayitlar.db`,
  `yuzler.pkl`, `sesler/onbellek/` (içinde öğrenci adları geçen sesler var), şifre ve anahtar
  dosyaları `.gitignore`'dadır. Hata bildirirken ya da örnek verirken gerçek öğrenci
  verisi paylaşmayın.

---

## 3. Testler

```bash
venv/bin/python -m pytest              # hepsi (~30 sn)
venv/bin/python -m pytest tests/test_sinav.py -v
venv/bin/python -m coverage run -m pytest && venv/bin/python -m coverage report
```

- Testler kamera istemez ve gerçek sistemin portlarına (5000, 8081, 8082) dokunmaz;
  her test geçici bir klasörde boş bir veritabanıyla çalışır (`tests/conftest.py`).
- Yüz tanıma testleri `kisiler_eski/` klasöründeki örnek fotoğrafları kullanır. Bu klasör
  kişisel veri olduğu için depoda yoktur; yoksa o testler **atlanır**. Kendi testleriniz
  için `kisiler_eski/` içine `Ad_1.jpg` biçiminde, izni alınmış fotoğraflar koyabilirsiniz
  (gereken adlar `conftest.py`'de).
- Saat ve kamera gerektiren davranışlar sahte saat (`simdi=`) ve sahte kamera sınıflarıyla
  test edilir. Yeni bir kural eklerken aynı yolu izleyin.

Elle denenmesi gerekenler: tek tık simgesi, gerçek kamerayla kayıt/giriş, sesli karşılama.

---

## 4. Yeni bir şey eklerken

- **Ayar:** `ayarlar.py`'ye açıklamalı ekleyin; varsayılan değer güvenli olsun.
- **Veritabanı sütunu:** `veri.db_ac` içinde `ALTER TABLE` ile göç ekleyin, mevcut
  `kayitlar.db` dosyaları bozulmasın.
- **Yeni olay türü:** `tani.olay_turu` → kiosk mesajı (`KIOSK_SAYFASI`) → ses cümlesi →
  Canlı İzleme listesi → Excel çıktısı → test.
- **Yeni sayfa:** `site.py`'de şablon + route; `ORTAK_STIL` ve `menu_ciz` kullanın,
  renkleri CSS değişkenlerinden alın. Görüntü gerekiyorsa `/canli` ya da `/kare`.
- Kod, değişken adları ve yorumlar Türkçedir; bu düzeni koruyun.

---

## 5. Yapılabilecekler

- **ESP32-CAM:** `ayarlar.py`'deki ESP32 satırını açmak yeterli olmalı (`/stream` MJPEG).
  Henüz gerçek kartla denenmedi; çözünürlük ve kare hızı ayarı gerekebilir.
- **Tek dosyalık site.py'yi bölmek:** şablonlar `templates/`, statik CSS/JS `static/`
  klasörüne taşınabilir; Flask Blueprint'lerle API bölümlenebilir.
- **Daha güçlü canlılık:** göz kırpmaya ek olarak baş hareketi isteme ya da derinlik kamerası.
- **Daha hızlı tanıma:** `face_recognition` CPU'da saniyede birkaç kare işler; çok kalabalık girişte
  GPU'lu dlib ya da daha hafif bir model denenebilir.
- **Bildirimler:** görevliye giriş bildirimi (ör. Telegram) — tartışıldı, henüz yapılmadı.
- **Birden çok salon / kapı:** şu an tek kamera, tek aktif sınav varsayılıyor.
- **Veri saklama süresi:** KVKK gereği eski giriş fotoğraflarını belli bir süre sonra
  otomatik silme.
