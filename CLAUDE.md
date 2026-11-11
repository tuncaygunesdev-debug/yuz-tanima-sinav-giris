# CLAUDE.md

Yüz tanımalı sınav giriş sistemi (Python, Flask, face_recognition/dlib, OpenCV, SQLite).
Mimari, tasarım kararları ve gerekçeleri: `GELISTIRME.md` — değişiklik yapmadan önce oku.

## Komutlar

```bash
venv/bin/python -m pytest -q          # bütün testler (~30 sn, kamera gerekmez)
venv/bin/python baslat.py             # sistemi ön planda çalıştır (Ctrl+C)
./sinav_giris.sh / ./sinav_giris.sh durdur
venv/bin/python hassasiyet.py         # tanıma eşiği ölçümü (kayıtlı öğrenci gerekir)
```

## Kurallar

- **Kişisel veri (KVKK):** `kisiler/`, `kisiler_eski/`, `static/fotolar/`, `kayitlar.db`,
  `yuzler.pkl`, `sesler/`, `sifre.txt`, `gizli_anahtar.txt` asla commit'lenmez, paylaşılmaz,
  çıktıya dökülmez. `.gitignore`'u gevşetme.
- **Kamerayı sadece `tani.py` okur.** Site görüntüyü `tani.py`'den aktarır (`/canli`, `/kare`).
  Başka bir programa kamera açtırma.
- **Renkler:** yalnızca PAÜ mavi tonları (`--brand #004684`, `--vurgu #0085d0` ve türevleri).
  Yeşil, sarı, kırmızı kullanma; durumları simge ve ton farkıyla ayır.
- **Dil:** arayüz, değişken/fonksiyon adları ve yorumlar Türkçe. Bu düzeni koru.
- Gerçek sistem 5000 / 8081 / 8082 portlarında çalışıyor olabilir; testler ve denemeler bu
  portlara dokunmamalı, sistemi (`baslat.py`) izinsiz kapatma.
- Her davranış değişikliğine test ekle (`tests/`, sahte saat `simdi=` ve sahte kamera
  kalıplarını kullan). Commit'ten önce bütün testler geçmeli.
- Yeni ayar `ayarlar.py`'ye açıklamasıyla; yeni veritabanı sütunu `veri.db_ac` içinde göçle.
