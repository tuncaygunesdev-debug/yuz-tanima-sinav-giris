# Yüz Tanıma Giriş Sistemi

Pamukkale Üniversitesi Denizli Teknik Bilimler MYO için hazırlanmış, yüz tanımalı sınav
giriş sistemi: öğrenci kaydı (KVKK onaylı, yönlendirmeli poz çekimi), kapıda giriş kiosku
(canlılık kontrolü, rastgele sıra numarası, sesli karşılama), görevli paneli (sınavlar,
canlı yoklama, Excel). Teknolojilerin ayrıntılı anlatımı: `Teknoloji_Kitapcigi.pdf`.
Geliştirmeye katkı: **`GELISTIRME.md`** (mimari, tasarım kararları, yapılabilecekler).

> **Kişisel veri yoktur.** Öğrenci fotoğrafları, giriş fotoğrafları, veritabanı, yüz kodları,
> şifre ve gizli anahtar depoya girmez (`.gitignore`); her kurulum kendi verisini oluşturur.

## Kurulum (bir kez)

```bash
sudo dnf install cmake gcc-c++ python3-devel      # Debian/Ubuntu: sudo apt install cmake g++ python3-dev
git clone <depo-adresi> yuz-tanima
cd yuz-tanima
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./masaustu_kur.sh                                 # menüye ve masaüstüne "Sınav Giriş Sistemi" simgesi
```

- Kamera adresi `ayarlar.py` içindeki `KAMERA` satırıdır (telefon IP Webcam, webcam veya ESP32-CAM).
- Sesli karşılama için: `./ses_indir.sh` (Türkçe ses modeli, ~66 MB; isteğe bağlı).
- Testler: `venv/bin/python -m pytest` (yüz testleri `kisiler_eski/` klasöründe örnek
  fotoğraf yoksa atlanır).

## Kullanım

1. **Tek tıkla başlat:** uygulamalar menüsünde (Super tuşu → "Sınav") **Sınav Giriş Sistemi**
   simgesine tıkla. Sistem arka planda açılır, hazır olunca tarayıcı kendiliğinden açılır.
   Zaten çalışıyorsa sadece tarayıcıyı açar. Simgeye **sağ tıkla**: "Giriş kioskunu aç",
   "Sistemi durdur". Kolay erişim için simgeyi Dock'a sabitle (sağ tık → Sık kullanılanlara ekle).
   - Telefon kamerasına ulaşılamazsa (IP Webcam kapalı, bilgisayar başka Wi-Fi'da) sistem
     bilgisayarın webcam'iyle açılır ve bildirim gösterir. Telefon ile bilgisayar **aynı ağda**
     olmalı (en sağlamı: bilgisayarı telefonun hotspot'una bağlamak).
   - Çıktılar `loglar/sistem.log` dosyasına yazılır.
   - Komut satırından da olur: `./sinav_giris.sh` (başlat), `./sinav_giris.sh durdur`,
     `./sinav_giris.sh kiosk`. Ya da çıktıyı görmek için: `python3 baslat.py` (Ctrl+C ile durur).
   - Simgeyi `./masaustu_kur.sh` kurar; proje klasörünü taşırsan bu betiği yeniden çalıştır.
2. Tarayıcıda: http://localhost:5000
   - İlk açılışta site şifresini belirle. Bu sadece sistemin çalıştığı bilgisayardan yapılabilir.
   - Şifreyi unutursan `sifre.txt` dosyasını sil ve sistemi yeniden başlat.
3. **Öğrenci Kaydı** sekmesi: öğrenci numarası ve ad soyad yaz, KVKK onay kutusunu
   işaretle, kameraya bak, "Kameradan fotoğraf çek"e bas. Her öğrenci için farklı
   açılardan 3–5 fotoğraf çek (aynı numarayla çekilen her fotoğraf o öğrenciye eklenir).
   Dosyadan da yüklenebilir.
4. **Tanıma** sekmesi: canlı görüntüde yüzler işaretlenir (tanınan açık mavi kutu + ad soyad,
   kayıtsız lacivert), yanda bugünkü girişler numarasıyla listelenir.

5. **Kayıt kiosku** (menüde "Kayıt kiosku ↗", adres `/kayit`): öğrenci kendi kendine kaydolur.
   Numara + ad soyad + KVKK onayı → "Kayda başla" → kamera ve hoparlör yönlendirir:
   **Düz** bak → başını **sağa** çevir → **sola** çevir. Sistem baş yönünü yüzdeki noktalardan
   (gözler, burun) anlar ve doğru açıyı ~0,5 sn koruyunca fotoğrafı kendisi çeker.
   Görüntü ayna gibi gösterilir. Kamera aynalı olsa da çalışır: ilk yan pozda hangi yana
   dönülürse kabul edilir, sonra diğer yan beklenir. Her poz için 30 sn süre var; takılırsa
   "biraz daha çevirin / yüzünüz görünmüyor" diye yardım eder. Kayıt sayfası ekranda
   açık olduğu sürece giriş olayı yazılmaz (form dolduran kişiye "Kaydınız yok" denmez);
   bu yüzden giriş için kayıt sayfasını kapatıp giriş kioskunu açın. Kayıt bitince form
   hemen temizlenir; bitiş ekranına dokununca yeni kayda geçilir. Eşikler `ayarlar.py`'de (`KAYIT_DUZ_ESIK`,
   `KAYIT_YAN_ESIK`).
   **Öğrenci Kaydı** sekmesi görevli içindir (elle fotoğraf çekme, dosyadan yükleme, silme).
   Listedeki **Düzenle** ile ad soyad ve numara düzeltilir (numara değişince fotoğraflar,
   sınav listeleri ve geçmiş girişler yeni numaraya taşınır) ve kötü fotoğraflar tek tek silinir
   (son fotoğraf silinemez).
6. **Giriş kiosku** (menüde "Giriş kiosku ↗", adres `/kiosk`): kapıdaki ekranda açılır.
   Bir kez dokununca tam ekrana geçer ve sesli karşılamayı açar (çıkmak için Esc).
   - ✓ açık mavi: "Hoş geldiniz, Ad Soyad, Sıra No 12" (ilk giriş, boş sıralardan rastgele sıra verilir)
   - ! orta mavi: "Zaten giriş yaptınız, saat 09:12 · Sıra No 12"
   - ✕ lacivert: "Kaydınız yok, önce kayıt olun" (sistemde hiç kaydı olmayan kişi; sınavdan bahsedilmez)
   - Salon doluysa (`KOLTUK_SAYISI`) giriş kabul edilir ama sıra verilmez.
   - **Canlılık kontrolü (fotoğrafla kandırmaya karşı):** tanınan öğrenci içeri alınmadan önce
     ekranın altında mavi panel çıkar: "Lütfen gözlerinizi kırpın" (+ sesli). Panelde göz
     açıklığı çubuğu ve geri sayım var. Sistem kameradan gelen her karede iki gözün açıklık oranını
     ölçer (göz noktaları, kare başına ~1,5 ms); göz kişinin normal açıklığının %72'sinin altına inip
     tekrar açılırsa ✅ giriş. 7 sn içinde kırpılmazsa mor ❌ **"Canlılık doğrulanamadı"**: bir
     fotoğraf ya da duran bir ekran görüntüsü göz kırpamaz. Kayıt kaydı yoklamada "Canlılık yok"
     olarak görünür. Zaten girmiş, listede olmayan ya da kayıtsız kişilerden göz kırpma istenmez.
     Ayarlar: `CANLILIK`, `CANLILIK_SURE`, `KIRPMA_ORANI`.
     *Sınırı:* göz kırpan birinin **videosu** oynatılırsa bu basit kontrol aşılabilir;
     daha güçlü yöntemler (rastgele hareket isteme, derinlik kamerası) sonraki adım olabilir.
   - Kişi kameranın önünde durdukça mesaj tekrarlanmaz; ayrılıp geri gelince yeni olay sayılır.
7. **Sınavlar** sekmesi (görevli paneli):
   - **Yeni sınav:** ad, tarih, saat, salondaki sıra sayısı ve sınava girecek öğrenciler
     (arama + "Tümünü seç"). Sıra sayısı öğrenci sayısından az olamaz.
   - **Giriş saatleri:** sınav oluştururken başlangıç saati, süre, "giriş kaç dk önce açılsın"
     (varsayılan 30) ve "geç giriş toleransı" (varsayılan 0) girilir. Örnek 15:00 sınav, 30/0:
     giriş **14:30–15:00** arası açık; sınav başladığı an giriş kapanır. Önce gelen "Giriş henüz
     açılmadı", sonra gelen "Giriş kapandı" görür; ikisi de yoklamada "Erken geldi / Geç kaldı"
     olarak kaydedilir. Zaten içeri girmiş öğrenci saatten bağımsız "zaten giriş yaptınız" görür.
   - **Otomatik başlatma/bitirme:** sınav giriş penceresi açılınca kendiliğinden aktif olur,
     süresi dolunca kendiliğinden biter (elle Başlat/Bitir de çalışır; süresi dolmuş sınav başlatılamaz).
   - **Demo:** sunum/prova için sınavın başlangıcını "10 dk sonra" yapar ve başlatır; giriş hemen açılır.
   - **Elle giriş:** yoklamada gelmeyenlerin yanındaki buton; geç kalan (mazeretli) ya da kameranın
     tanıyamadığı öğrenci görevli onayıyla içeri alınır, sıra verilir, kayıtta "Görevli onayıyla" yazar.
   - Giriş kioskunun başlığında "Giriş açık · kapanmasına 12 dk" / "Giriş açılışı 14:30" görünür.
   - **Başlat / Bitir:** aynı anda tek sınav aktif olur. Aktif sınav varken giriş kiosku
     başlıkta sınavın adını gösterir ve sadece listedekileri kabul eder:
     listede olmayan kayıtlı öğrenciye turuncu **"Bu sınava kaydınız yok"** der.
     "Zaten giriş yaptınız" ve sıra numaraları o sınava göredir (aynı gün birden çok sınav olabilir).
     Aktif sınav yoksa kiosk **serbest modda** çalışır (kayıtlı herkes, takvim gününe göre).
   - **Yoklama** sayfası (sınavın adına tıkla): "2 / 30 öğrenci giriş yaptı" sayacı,
     ✅ gelenler (saat, sıra no, fotoğraf), ⏳ gelmeyenler, diğer girişimler (tekrar deneyen,
     listede olmayan, kayıtsız). 3 saniyede bir kendiliğinden yenilenir.
     **"⬇ Excel'e aktar"** yoklamayı `.xlsx` olarak indirir (Yoklama + Tüm olaylar sayfaları).
     **"Öğrenci listesini düzenle"** ile sonradan öğrenci eklenip çıkarılabilir;
     **"Yoklamayı sıfırla"** prova sonrası o sınavın girişlerini temizler.
8. Prova/demo öncesi **Tanıma** sayfasındaki **"Bugünü sıfırla"** bugünkü girişleri ve
   verilen sıraları temizler (kayıtlı öğrenciler silinmez).

### Sesli karşılama

Ses bilgisayardan çıkar; Bluetooth hoparlörü bilgisayara bağlayıp varsayılan ses çıkışı
yapman yeterli. Konuşma Piper ile internetsiz üretilir:

```bash
./ses_indir.sh
```

Betik Türkçe ses modelini (Piper `tr_TR-dfki-medium`, ~66 MB) [piper-voices](https://huggingface.co/rhasspy/piper-voices)
deposundan `sesler/` klasörüne indirir ve gerekirse `piper-tts`'i kurar. Model boyutu ve
başkasına ait olduğu için depoda tutulmaz.

Bunlar yoksa kiosk tarayıcının kendi Türkçe sesini dener; o da yoksa sessiz çalışır.

Kişiler içeride **öğrenci numarasıyla** ayırt edilir (aynı isimde iki kişi karışmaz),
ekranda **ad soyadıyla** gösterilir. Aynı yüz iki farklı numarayla kaydedilemez;
bir numara başka bir isimle tekrar kullanılamaz.

Öğrenci eklenince/silinince `tani.py` yeni yüzleri kendiliğinden yükler, yeniden başlatmaya gerek yok.

Bir yüz art arda 3 analizde (yaklaşık 1 saniye) aynı kişi çıkmadan kayıt düşülmez;
tek karelik yanlış eşleşmeler kaydedilmez. "Bugün zaten girdi mi?" kontrolü takvim gününe
göredir (sınav oturumları Aşama 4'te gelecek).

## Renkler

Bütün ekranlar Pamukkale Üniversitesi Denizli Teknik Bilimler MYO'nun renklerini kullanır
(lacivert `#004684`, açık mavi `#0085D0`); yeşil / sarı / kırmızı kullanılmaz. Durumlar mavinin
tonlarıyla ve ✓ ! ✕ işaretleriyle ayrılır: olumlu açık mavi, uyarı orta mavi, olumsuz koyu lacivert.
Logo: `static/marka/logoTR.png` (lacivert zeminde), amblem: `static/marka/amblem.png`.

## Ayarlar

Bütün ayarlar `ayarlar.py` içinde: kamera adresi, tanıma toleransı, onay için gereken
kare sayısı, kişinin "ayrıldı" sayılması için gereken süre, salondaki sıra sayısı, site portu.

### Tanıma hassasiyeti

İki yüz arasındaki "mesafe" ne kadar küçükse o kadar benzerler. Bir yüz şu kurala göre tanınır:

- En yakın öğrenci `TOLERANS`'tan (0.47) yakın olmalı, **ve**
- ikinci en yakın öğrenciden en az `MARJ` (0.05) daha yakın olmalı.
- İkinci şart sağlanmazsa (birbirine çok benzeyen iki öğrenci) sistem **sarı "?"** gösterir ve
  karar vermez: ne yanlış kişiye giriş verir ne de "Kaydınız yok" der; sonraki kareleri bekler.

Ölçüm (4 kişi, 19 foto): aynı kişinin fotoğrafları 0.26–0.59, farklı kişiler 0.51–0.85.

Ekranda mesafe yerine herkesin anlayacağı **benzerlik yüzdesi** gösterilir (`veri.benzerlik`):
eşik (`TOLERANS`) tam **%50**'ye denk gelir; tanınan kişi genelde %80–%95, farklı kişiler %15–%45.
Görevlinin **Tanıma** sekmesinde yüzlerin üstünde yazar (kiosklarda yazmaz):
"Tuncay Güneş · %91 benziyor", "? Tuncay %70 / Yağız %62"; kayıtsız kişide sadece "Bilinmeyen".

Sınıf kaydolduktan sonra bu sınıf için ölçmek (sistemi durdurmadan, hiçbir şeyi değiştirmez):

```bash
venv/bin/python hassasiyet.py
```

Birbirine en çok benzeyen öğrenci çiftlerini, tek fotoğraflı ya da kötü fotoğraflı öğrencileri ve
"her fotoğrafı diğerleriyle tanıma" provasının sonucunu gösterir, gerekirse ayar önerir.

### Nasıl bağlı?

```
Kamera ──► tani.py (8082) ──► site.py (5000) ──► tarayıcı
                 └──► kayitlar.db ◄──┘
```

| Dosya | İçinde ne var |
|---|---|
| `kayitlar.db` | `ogrenciler` (numara, ad soyad, KVKK onay zamanı) ve `olaylar` (giriş kayıtları) |
| `kisiler/<numara>_<sıra>.jpg` | Öğrencilerin kayıt fotoğrafları |
| `yuzler.pkl` | Fotoğraflardan çıkarılan yüz kodları (numarayla birlikte) |
| `veri.py` | Bu dosyaları okuyup yazan ortak kod |

Kameraya sadece `tani.py` bağlanır (ESP32-CAM aynı anda tek izleyiciye görüntü verir).
Site görüntüyü ve kişi eklerken çekilen kareyi `tani.py`'den alır.

### Elle fotoğraf eklemek (isteğe bağlı)

Öğrenci önce sitede kayıtlı olmalı. Sonra `kisiler/` klasörüne
`<numara>_1.jpg`, `<numara>_2.jpg`... koyup `python kaydet.py` çalıştır.
`kaydet.py` yüz veritabanını klasördeki fotoğraflardan baştan oluşturur.

## Gerçek ESP32-CAM gelince

`ayarlar.py` içindeki `KAMERA` satırını kameranın adresiyle değiştir.
`baslat.py` sahte kamerayı artık kendiliğinden açmaz.

Servisler istenirse hâlâ ayrı ayrı da çalıştırılabilir
(`source venv/bin/activate`, sonra `python sahte_kamera.py`, `python tani.py`, `python site.py`).

## Ağdaki başka cihazlardan erişim

```bash
sudo firewall-cmd --add-port=5000/tcp --permanent
sudo firewall-cmd --reload
```

## Testler

Bütün mekanizmalar için 166 otomatik test var (`tests/` klasörü, ~35 saniye):

```bash
cd ~/Claude/esp32/yuz-tanima
venv/bin/python -m pytest
```

Hangi kodun testlerde çalıştığını ölçmek için (kapsam, ~%87):

```bash
venv/bin/python -m coverage run --source=. --omit="tests/*,venv/*" -m pytest -q
venv/bin/python -m coverage report
```

- Her test boş, geçici bir klasörde çalışır: gerçek veritabanına, öğrencilere ve fotoğraflara
  dokunulmaz; çalışan sistemi durdurmaya gerek yoktur, gerçek portlar (5000, 8081, 8082) kullanılmaz.
  Kamera gerekmez.
- Yüz testleri `kisiler_eski/` klasöründeki fotoğrafları okur (yoksa o testler atlanır);
  ses testleri Piper ve ses modeli yoksa atlanır; sayfa kodu kontrolü `node` yoksa atlanır.

| Dosya | Neyi test eder |
|---|---|
| `test_tanima.py` | doğru kişi, kayıtsız kişi, "emin değilim" (?), benzerlik %, baş yönü, ayna görüntüsü |
| `test_olay_kurallari.py` | giriş / tekrar / listede yok / kayıtsız / erken / geç / tolerans, sıra numaraları, salon dolu |
| `test_akis.py` | art arda 3 kare onayı, ayrılma kuralı, kayıt modu, test modu |
| `test_canlilik.py` | göz kırpma ölçümü, fotoğraf saldırısı, kırpmadan ayrılma, sıra bekleme |
| `test_yayin.py` | canlı yayın, ayna, kamera okuma (döndürme, yeniden bağlanma), göz ölçüm ve ana tanıma döngüsü |
| `test_kayit.py` | form ve KVKK kuralları, aynı yüz iki numara, rehberli kayıt, düzenleme, fotoğraf ekleme/silme |
| `test_sinav.py` | oluşturma kuralları, tek aktif sınav, otomatik başlat/bitir, Demo, elle giriş, yoklama, Excel |
| `test_site.py` | şifre ve oturum, kiosk mesajları, test modu, "Bugünü sıfırla", sayfa kodları, sadece mavi renkler |
| `test_site_ek.py` | canlı görüntü aktarımı, tanıma servisi kapalıyken, ses adresleri, hata cevapları |
| `test_araclar.py` | kaydet.py, hassasiyet.py, sahte_kamera.py, baslat.py (telefon yoksa webcam, biri kapanınca hepsi) |
| `test_ses.py` | Türkçe ses üretimi ve önbellek |

Bir değişiklikten sonra testleri çalıştırmak, bir şeyin bozulup bozulmadığını hemen gösterir.
Elle denenenler (otomatik test yok): tek tık simgesi / `sinav_giris.sh` (başlat, ikinci tık, durdur),
gerçek göz kırpma, telefon kamerası.
