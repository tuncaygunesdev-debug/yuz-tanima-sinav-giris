# Web sitesi. Adres: http://BILGISAYAR_IP:5000
#   Tanıma     -> yüzleri işaretlenmiş canlı görüntü + bugünkü giriş kayıtları
#   Öğrenci Kaydı -> numara + ad soyad + KVKK onayı, kameradan ya da dosyadan fotoğraf
# Görüntüyü kameradan değil tani.py'den alır, yani tani.py de çalışıyor olmalı.
#
# Site şifreyle korunur. İlk açılışta şifre bu bilgisayardan (http://localhost:5000)
# belirlenir. Şifreyi unutursan sifre.txt dosyasını sil, siteyi yeniden başlat.

import io
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from datetime import date, datetime, timedelta

import cv2
import face_recognition
import numpy as np
from flask import (Flask, Response, jsonify, redirect, render_template_string,
                   request, send_file, send_from_directory, session)
from werkzeug.security import check_password_hash, generate_password_hash

import ses
from ayarlar import SITE_PORT, TOLERANS
from veri import (KISILER, aktif_sinav, bos_sira_sec, db_ac, giris_durumu, ogrenci_dosyalari,
                  otomatik_sinav_durumu, sinav_zamani, sinav_zamani_getir, yuzleri_oku, yuzleri_yaz)

TANI = "http://127.0.0.1:8082"   # tani.py'nin yayın adresi
SIFRE_DOSYASI = "sifre.txt"            # şifrenin kendisi değil, özeti (hash) saklanır
ANAHTAR_DOSYASI = "gizli_anahtar.txt"  # oturum çerezlerini imzalamak için
KVKK_METNI = ("Yüz fotoğraflarımın, adımın ve öğrenci numaramın sınav girişinde kimlik "
              "doğrulama amacıyla işlenmesine ve saklanmasına izin veriyorum. Kaydımın "
              "silinmesini istediğimde tüm fotoğraflarım silinir.")

app = Flask(__name__)
kilit = threading.Lock()   # aynı anda iki kayıt yuzler.pkl'yi bozmasın


# ---------- Şifre ve oturum ----------

def gizli_dosya_yaz(yol, icerik):
    with open(os.open(yol, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(icerik)


def gizli_anahtar():
    if not os.path.exists(ANAHTAR_DOSYASI):
        gizli_dosya_yaz(ANAHTAR_DOSYASI, secrets.token_hex(32))
    with open(ANAHTAR_DOSYASI) as f:
        return f.read().strip()


def sifre_ozeti():
    if not os.path.exists(SIFRE_DOSYASI):
        return None
    with open(SIFRE_DOSYASI) as f:
        return f.read().strip() or None


def bu_bilgisayardan():
    return request.remote_addr in ("127.0.0.1", "::1")


app.secret_key = gizli_anahtar()
app.permanent_session_lifetime = timedelta(days=30)   # 30 gün boyunca tekrar şifre sorma


@app.before_request
def giris_kontrolu():
    if request.endpoint in ("giris", "cikis") or session.get("giris") or request.path.startswith("/static/marka/"):
        return None
    if request.path.startswith("/api/"):
        return jsonify(ok=False, mesaj="Oturum kapanmış. Sayfayı yenileyip tekrar giriş yapın."), 401
    return redirect("/giris")


# ---------- Ortak tasarım (görevli paneli sayfaları) ----------
# Bütün yönetim sayfaları aynı renkleri, butonları, kartları ve yan menüyü kullanır.
# Dışarıdan yazı tipi ya da kütüphane yüklenmez: internet olmadan da aynı görünür.

ORTAK_STIL = """
<style>
  :root {
    /* Renkler: Pamukkale Üniversitesi Denizli Teknik Bilimler MYO (pau.edu.tr/dtbmyo) */
    --bg: #eef1f5; --panel: #ffffff; --border: #dde3ea; --text: #1b2733; --muted: #5f6f80;
    --brand: #004684; --brand-koyu: #00365f; --brand-acik: #e5f1fa; --vurgu: #0085d0;
    /* Durum renkleri de PAÜ mavisinin tonları: yeşil / sarı / kırmızı kullanılmaz.
       olumlu = açık mavi, uyarı = orta mavi, olumsuz = lacivert; ayrıca ✓ ! ✕ işaretleri. */
    --ok: #0085d0; --ok-acik: #d9ecf9; --warn: #2a6aa3; --warn-acik: #e5f1fa;
    --bad: #004684; --bad-acik: #e3eaf2; --mor: #00284c; --mor-acik: #e3eaf2; --buz: #9cc3e4;
    --yan: #004684; --radius: 12px;
    --golge: 0 1px 2px rgba(16, 24, 40, .05), 0 1px 3px rgba(16, 24, 40, .07);
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  body { font-family: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif;
         background: var(--bg); color: var(--text); font-size: 14.5px; line-height: 1.45; }

  /* Yerleşim: solda menü, sağda içerik */
  .duzen { display: grid; grid-template-columns: 250px minmax(0, 1fr); min-height: 100vh; }
  .yan { background: var(--yan); color: #cbd5e1; display: flex; flex-direction: column; gap: 2px;
         padding: 20px 14px; position: sticky; top: 0; height: 100vh; }
  .marka { display: block; padding: 0 6px 14px; color: #fff; text-decoration: none;
           border-bottom: 1px solid rgba(255, 255, 255, .14); margin-bottom: 4px; }
  .marka img { display: block; width: 100%; max-width: 214px; height: auto; }
  .marka small { display: block; color: #9cc3e4; font-weight: 600; font-size: 12px; margin-top: 8px;
                 letter-spacing: .06em; text-transform: uppercase; }
  .yan-baslik { font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: #8fb6d8;
                padding: 16px 10px 6px; font-weight: 600; }
  .yan a.menu { display: flex; gap: 11px; align-items: center; padding: 9px 10px; border-radius: 8px;
                color: #dbe8f4; text-decoration: none; font-weight: 500; }
  .yan a.menu:hover { background: rgba(255, 255, 255, .09); color: #fff; }
  .yan a.menu.aktif { background: var(--vurgu); color: #fff; box-shadow: 0 1px 2px rgba(0, 0, 0, .15); }
  .yan a.menu svg { width: 18px; height: 18px; stroke: currentColor; fill: none; stroke-width: 2;
                    stroke-linecap: round; stroke-linejoin: round; flex: none; }
  .yan a.menu .dis { margin-left: auto; opacity: .5; font-size: 12px; }
  .yan .alt { margin-top: auto; border-top: 1px solid rgba(255, 255, 255, .14); padding-top: 10px; }
  .icerik { padding: 28px 32px 40px; min-width: 0; max-width: 1400px; }
  @media (max-width: 860px) {
    .duzen { grid-template-columns: 1fr; }
    .yan { position: static; height: auto; flex-direction: row; flex-wrap: wrap; align-items: center; padding: 10px 12px; }
    .marka { padding: 2px 12px 2px 2px; border: 0; margin: 0; } .marka img { width: 150px; }
    .marka small, .yan-baslik { display: none; }
    .yan .alt { margin: 0 0 0 auto; border: 0; padding: 0; }
    .icerik { padding: 20px 16px 32px; }
  }

  /* Sayfa başlığı */
  .sayfa-baslik { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px;
                  margin-bottom: 22px; flex-wrap: wrap; }
  .sayfa-baslik h1 { margin: 0; font-size: 23px; letter-spacing: -.01em; }
  .sayfa-baslik p { margin: 4px 0 0; color: var(--muted); }
  .geri { color: var(--muted); text-decoration: none; font-weight: 500; font-size: 13px; display: inline-block; margin-bottom: 6px; }
  .geri:hover { color: var(--vurgu); }

  /* Kartlar ve ızgara */
  .kart { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
          box-shadow: var(--golge); min-width: 0; }
  .kart-bas { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap;
              padding: 14px 18px; border-bottom: 1px solid var(--border); }
  .kart-bas h2 { margin: 0; font-size: 15px; font-weight: 650; }
  .kart-govde { padding: 18px; }
  .izgara { display: grid; gap: 20px; align-items: start; }
  .iki-sutun { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .genis-dar { grid-template-columns: minmax(0, 1fr) minmax(0, 1.25fr); }
  .dar-genis { grid-template-columns: minmax(0, 400px) minmax(0, 1fr); }
  @media (max-width: 1150px) { .iki-sutun, .genis-dar, .dar-genis { grid-template-columns: 1fr; } }

  /* Özet kutuları */
  .istatistik { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px; }
  @media (max-width: 900px) { .istatistik { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .stat { padding: 15px 18px; }
  .stat .etiket { color: var(--muted); font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 7px; }
  .stat .etiket::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--r, var(--brand)); }
  .stat .deger { font-size: 28px; font-weight: 700; margin-top: 4px; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
  .stat .deger small { font-size: 15px; color: var(--muted); font-weight: 600; }

  /* Form */
  label { display: block; font-weight: 600; margin: 14px 0 6px; font-size: 13.5px; }
  input[type=text], input[type=date], input[type=time], input[type=number], input[type=search], input[type=password] {
    width: 100%; padding: 10px 12px; font: inherit; border: 1px solid #d0d5dd; border-radius: 8px;
    background: #fff; color: var(--text); transition: border-color .15s, box-shadow .15s; }
  input:focus { outline: none; border-color: var(--vurgu); box-shadow: 0 0 0 3px rgba(0, 133, 208, .18); }
  input[type=file] { font: inherit; font-size: 13px; color: var(--muted); max-width: 100%; }
  .yan-yana { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
  .yan-yana.tarih-satir { grid-template-columns: 1.45fr 1fr .8fr; }
  @media (max-width: 520px) { .yan-yana, .yan-yana.tarih-satir { grid-template-columns: 1fr; } }
  .kvkk { display: flex; gap: 10px; align-items: flex-start; margin-top: 16px; padding: 12px; cursor: pointer;
          background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; font-size: 13px;
          font-weight: 400; line-height: 1.45; color: #475569; }
  .kvkk input { margin-top: 2px; width: 17px; height: 17px; flex: none; accent-color: var(--brand); }

  /* Butonlar (eski sınıf adları da aynı görünüme bağlı) */
  button, .buton { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 14px;
                   font: inherit; font-weight: 600; font-size: 14px; border: 1px solid transparent; border-radius: 8px;
                   cursor: pointer; background: var(--brand); color: #fff; text-decoration: none; white-space: nowrap;
                   transition: background .15s, border-color .15s; }
  button:hover, .buton:hover { background: var(--brand-koyu); }
  button:disabled { opacity: .55; cursor: wait; }
  .ikincil, .gri { background: #fff; color: #344054; border-color: #d0d5dd; }
  .ikincil:hover, .gri:hover { background: #f8fafc; }
  .tehlike, .sil, .kirmizi-b { background: #fff; color: var(--brand); border-color: var(--buz); }
  .tehlike:hover, .sil:hover, .kirmizi-b:hover { background: var(--brand-acik); }
  .yesil-b { background: var(--vurgu); } .yesil-b:hover { background: #0072b3; }
  .turuncu-b { background: var(--brand-koyu); } .turuncu-b:hover { background: #00284c; }
  .kucuk, .sil { padding: 6px 11px; font-size: 13px; }
  .tam { width: 100%; padding: 11px; }

  /* Tablolar */
  .tablo-kap { overflow-x: auto; }
  .kaydir { max-height: 560px; overflow: auto; }
  .kaydir th { position: sticky; top: 0; z-index: 1; box-shadow: inset 0 -1px 0 var(--border); }
  table { border-collapse: collapse; width: 100%; }
  th { font-size: 11.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 600;
       background: #f9fafb; white-space: nowrap; }
  th, td { padding: 11px 16px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; }
  tbody tr:hover { background: #fafbff; }
  tbody tr:last-child td { border-bottom: 0; }
  td img { width: 40px; height: 40px; object-fit: cover; border-radius: 50%; display: block; border: 1px solid var(--border); }
  .kisi { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .kisi b { display: block; font-weight: 600; }
  .kisi span { color: var(--muted); font-size: 12.5px; font-variant-numeric: tabular-nums; }
  .avatar-bos { width: 40px; height: 40px; border-radius: 50%; background: var(--brand-acik); color: var(--brand);
                display: grid; place-items: center; font-weight: 700; flex: none; }
  .no { color: var(--muted); font-variant-numeric: tabular-nums; }
  td.bos, .bos { color: var(--muted); text-align: center; padding: 30px 16px; }

  /* Rozetler */
  .rozet { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 999px;
           font-size: 12px; font-weight: 600; white-space: nowrap; }
  .rozet.yesil, .rozet.aktif { background: var(--vurgu); color: #fff; }                     /* olumlu */
  .rozet.turuncu, .rozet.tekrar, .rozet.listede_yok { background: var(--warn-acik); color: var(--brand); }  /* uyarı */
  .rozet.kirmizi, .rozet.bilinmeyen { background: var(--brand); color: #fff; }               /* olumsuz */
  .rozet.mor, .rozet.canlilik_yok { background: #00284c; color: #fff; }
  .rozet.hazir { background: var(--brand-acik); color: var(--brand); }
  .rozet.bitti { background: #f1f5f9; color: #475569; }
  .rozet.mavi, .rozet.erken { background: var(--warn-acik); color: var(--brand); }
  .rozet.gec { background: var(--brand); color: #fff; }

  /* Mesaj, ipucu, canlı görüntü */
  .mesaj { margin-top: 14px; padding: 10px 12px; border-radius: 8px; display: none; font-weight: 500; }
  .mesaj.iyi { display: block; background: var(--brand-acik); color: var(--brand); }
  .mesaj.kotu { display: block; background: #fff; color: #00284c; border: 1px solid var(--buz); border-left: 4px solid var(--brand); }
  .ipucu { color: var(--muted); font-size: 13px; margin: 8px 0 0; }
  .satir { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .canli { width: 100%; aspect-ratio: 4 / 3; background: #00284c; border-radius: 10px; display: block; object-fit: contain; }
  .kamera-kutu { position: relative; border-radius: 10px; background: #00284c; }
  .kamera-yok { position: absolute; inset: 0; display: none; place-items: center; text-align: center; padding: 16px;
                color: #9cc3e4; font-weight: 600; font-size: 14px; }
  .kamera-kutu.yok .canli { visibility: hidden; }
  .kamera-kutu.yok .kamera-yok { display: grid; }
  .canli-rozet { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 700; letter-spacing: .05em;
                 color: var(--brand); background: var(--brand-acik); padding: 3px 10px; border-radius: 999px; }
  .canli-rozet::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--ok); animation: nabiz 1.6s infinite; }
  @keyframes nabiz { 50% { opacity: .3; } }
  .aciklama { display: flex; gap: 16px; flex-wrap: wrap; font-size: 12.5px; color: var(--muted); margin-top: 12px; }
  .aciklama span { display: inline-flex; align-items: center; gap: 6px; }
  .aciklama span::before { content: ""; width: 10px; height: 10px; border-radius: 3px; background: var(--r); }
  .aciklama span.beyaz::before { box-shadow: inset 0 0 0 1px var(--buz); }
  .cubuk { height: 8px; background: #eef0f5; border-radius: 999px; overflow: hidden; }
  .cubuk div { height: 100%; background: var(--vurgu); border-radius: 999px; transition: width .4s; }

  /* Pencere */
  dialog { border: 0; border-radius: 14px; padding: 0; width: min(580px, calc(100vw - 32px)); color: var(--text);
           box-shadow: 0 24px 60px rgba(15, 23, 42, .3); }
  dialog::backdrop { background: rgba(15, 23, 42, .5); }
  dialog .kart-govde { max-height: 70vh; overflow: auto; }
  .pencere-alt { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 18px; border-top: 1px solid var(--border); background: #f9fafb; }
</style>
"""

IKONLAR = {
    "marka": '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/>'
             '<path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/>'
             '<line x1="15" y1="9" x2="15.01" y2="9"/>',
    "tanima": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "kisiler": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
               '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "sinavlar": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
                '<path d="m9 14 2 2 4-4"/>',
    "kayit": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/>',
    "kiosk": '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
    "cikis": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
}

MENU = """
<aside class="yan">
  <a class="marka" href="/tanima" title="Sınav Giriş Sistemi">
    <img src="/static/marka/logoTR.png" alt="Denizli Teknik Bilimler Meslek Yüksekokulu">
    <small>Sınav Giriş Sistemi</small>
  </a>
  <div class="yan-baslik">Yönetim</div>
  <a class="menu {{ 'aktif' if aktif == 'tanima' }}" href="/tanima"><svg viewBox="0 0 24 24">{{ ikon.tanima|safe }}</svg>Canlı İzleme</a>
  <a class="menu {{ 'aktif' if aktif == 'kisiler' }}" href="/kisiler"><svg viewBox="0 0 24 24">{{ ikon.kisiler|safe }}</svg>Öğrenciler</a>
  <a class="menu {{ 'aktif' if aktif == 'sinavlar' }}" href="/sinavlar"><svg viewBox="0 0 24 24">{{ ikon.sinavlar|safe }}</svg>Sınavlar</a>
  <div class="yan-baslik">Kiosk ekranları</div>
  <a class="menu" href="/kayit" target="_blank"><svg viewBox="0 0 24 24">{{ ikon.kayit|safe }}</svg>Kayıt kiosku<span class="dis">↗</span></a>
  <a class="menu" href="/kiosk" target="_blank"><svg viewBox="0 0 24 24">{{ ikon.kiosk|safe }}</svg>Giriş kiosku<span class="dis">↗</span></a>
  <div class="alt">
    <a class="menu" href="/cikis"><svg viewBox="0 0 24 24">{{ ikon.cikis|safe }}</svg>Çıkış</a>
  </div>
</aside>
"""


def menu_ciz(aktif):
    return render_template_string(MENU, aktif=aktif, ikon=IKONLAR)


app.jinja_env.globals.update(ORTAK_STIL=ORTAK_STIL, menu_ciz=menu_ciz, IKONLAR=IKONLAR)


GIRIS_SAYFASI = """
<!doctype html>
<html lang="tr"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Giriş · Sınav Giriş</title>
<link rel="icon" href="/static/marka/amblem.png">
{{ ORTAK_STIL|safe }}
<style>
  body { min-height: 100vh; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .tanitim { background: radial-gradient(circle at 15% 10%, #0085d0 0%, #004684 45%, #00284c 100%); color: #e6f0f8;
             padding: 48px; display: flex; flex-direction: column; justify-content: space-between; }
  .tanitim h2 { font-size: 32px; line-height: 1.2; margin: 0 0 14px; color: #fff; letter-spacing: -.02em; }
  .tanitim p { color: #bfe0f5; margin: 0 0 26px; max-width: 440px; }
  .tanitim ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 12px; max-width: 440px; }
  .tanitim li { display: flex; gap: 10px; align-items: flex-start; color: #dbe8f4; }
  .tanitim li::before { content: "✓"; color: #7fd0ff; font-weight: 800; }
  .tanitim .alt-yazi { color: #9cc3e4; font-size: 12.5px; }
  .tanitim .logo-buyuk { width: min(320px, 80%); height: auto; display: block; }
  .giris-kart .amblem { width: 64px; height: 64px; display: block; margin-bottom: 14px; }
  .form-alan { display: grid; place-items: center; padding: 32px 20px; }
  .giris-kart { width: min(380px, 100%); }
  .giris-kart h1 { font-size: 24px; margin: 0 0 6px; letter-spacing: -.01em; }
  .giris-kart > p { color: var(--muted); margin: 0 0 22px; }
  .hata { background: #fff; color: #00284c; border: 1px solid #9cc3e4; border-left: 4px solid #004684; padding: 10px 12px; border-radius: 8px; margin-bottom: 6px; font-weight: 500; }
  .marka-satir { display: flex; align-items: center; gap: 11px; font-weight: 700; color: #fff; font-size: 16px; }
  @media (max-width: 860px) { body { grid-template-columns: 1fr; } .tanitim { display: none; } }
</style>
</head><body>
<section class="tanitim">
  <img class="logo-buyuk" src="/static/marka/logoTR.png" alt="Denizli Teknik Bilimler Meslek Yüksekokulu">
  <div>
    <h2>Yüz tanımalı sınav<br>giriş sistemi</h2>
    <p>Öğrenciler yüzleriyle sınava girer; görevli yoklamayı canlı izler.</p>
    <ul>
      <li>Rehberli kayıt: düz, sağ ve sol bakışta otomatik fotoğraf</li>
      <li>Göz kırpma ile fotoğraf ve ekranla kandırmaya karşı koruma</li>
      <li>Sınav listesi, rastgele sıra numarası ve sesli karşılama</li>
      <li>Canlı yoklama ve Excel'e aktarma</li>
    </ul>
  </div>
  <div class="alt-yazi">Pamukkale Üniversitesi · Denizli Teknik Bilimler MYO öğrenci projesi ·
    Veriler bu bilgisayarda saklanır</div>
</section>

<section class="form-alan">
{% if durum == 'uzaktan' %}
  <div class="giris-kart kart kart-govde">
    <h1>Şifre henüz belirlenmedi</h1>
    <p style="color:var(--muted)">Güvenlik için ilk şifre sadece sistemin çalıştığı bilgisayardan belirlenebilir.
       O bilgisayarda <b>http://localhost:{{ port }}</b> adresini açın.</p>
  </div>
{% else %}
  <form method="post" class="giris-kart">
    <img class="amblem" src="/static/marka/amblem.png" alt="">
    <h1>{{ 'Şifre belirleyin' if durum == 'yeni' else 'Görevli girişi' }}</h1>
    <p>{{ 'Yönetim paneline girmek için kullanılacak şifreyi belirleyin (en az 6 karakter).' if durum == 'yeni'
          else 'Devam etmek için görevli şifresini girin.' }}</p>
    {% if hata %}<div class="hata">{{ hata }}</div>{% endif %}
    <label for="sifre">Şifre</label>
    <input type="password" id="sifre" name="sifre" required autofocus
           autocomplete="{{ 'new-password' if durum == 'yeni' else 'current-password' }}">
    {% if durum == 'yeni' %}
      <label for="tekrar">Şifre (tekrar)</label>
      <input type="password" id="tekrar" name="tekrar" required autocomplete="new-password">
    {% endif %}
    <button type="submit" class="tam" style="margin-top:20px">{{ 'Kaydet ve gir' if durum == 'yeni' else 'Giriş yap' }}</button>
  </form>
{% endif %}
</section>
</body></html>
"""


@app.route("/giris", methods=["GET", "POST"])
def giris():
    ozet = sifre_ozeti()
    if ozet is None and not bu_bilgisayardan():
        return render_template_string(GIRIS_SAYFASI, durum="uzaktan", port=SITE_PORT)
    durum = "yeni" if ozet is None else "giris"
    hata = None

    if request.method == "POST":
        sifre = request.form.get("sifre", "")
        if durum == "yeni":
            if len(sifre) < 6:
                hata = "Şifre en az 6 karakter olmalı."
            elif sifre != request.form.get("tekrar", ""):
                hata = "İki şifre aynı değil."
            else:
                gizli_dosya_yaz(SIFRE_DOSYASI, generate_password_hash(sifre))
        elif not check_password_hash(ozet, sifre):
            time.sleep(1)   # deneme-yanılmayı yavaşlat
            hata = "Şifre yanlış."

        if hata is None:
            session.clear()
            session.permanent = True
            session["giris"] = True
            return redirect("/tanima")

    return render_template_string(GIRIS_SAYFASI, durum=durum, hata=hata, port=SITE_PORT)


@app.route("/cikis")
def cikis():
    session.clear()
    return redirect("/giris")


# ---------- Yardımcılar ----------

def numara_gecerli(numara):
    return re.fullmatch(r"\d{1,20}", numara) is not None


HARFLER = r"[^\W\d_]+(?:['-][^\W\d_]+)*"   # harflerden oluşan bir kelime (Ali, O'Neil, Ayşe-Nur)


def ad_soyad_gecerli(ad_soyad):
    # En az iki kelime (ad ve soyad), sadece harf; en fazla 60 karakter
    return len(ad_soyad) <= 60 and re.fullmatch(rf"{HARFLER}(?: {HARFLER})+", ad_soyad) is not None


def ogrenci_bul(numara):
    with closing(db_ac()) as db:
        satir = db.execute("SELECT ad_soyad FROM ogrenciler WHERE ogrenci_no = ?", (numara,)).fetchone()
    return satir[0] if satir else None


# ---------- Sayfalar ----------

SAYFA = """
<!doctype html>
<html lang="tr"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ 'Canlı İzleme' if sayfa == 'tanima' else 'Öğrenciler' }} · Sınav Giriş</title>
<link rel="icon" href="/static/marka/amblem.png">
{{ ORTAK_STIL|safe }}
</head><body>
<div class="duzen">
{{ menu_ciz(sayfa)|safe }}
<main class="icerik">

{% if sayfa == 'tanima' %}
  <div class="sayfa-baslik">
    <div><h1>Canlı İzleme</h1><p>Kameradaki yüzler ve bugünkü kapı olayları, 3 saniyede bir yenilenir.</p></div>
    <div class="satir">
      <label class="anahtar" title="Açıkken kamera önündekiler için hiçbir giriş olayı kaydedilmez">
        <input type="checkbox" id="test-modu"><span class="anahtar-kol"></span>Test modu
      </label>
      <button class="tehlike" id="sifirla">Bugünü sıfırla</button>
    </div>
  </div>
  <div class="test-serit" id="test-serit">
    <b>Test modu açık:</b> olaylar kaydedilmiyor, kiosk kimseyi içeri almıyor. Tanımayı ve yüzdeleri
    rahatça deneyebilirsiniz. Sayfadan çıkınca ya da anahtarı kapatınca sistem normale döner.
  </div>
  <div class="test-serit uyari" id="sinav-serit">
    <b>Aktif sınav var (<span id="sinav-adi"></span>):</b> test modu açıkken kiosk bu sınava giriş almaz.
  </div>

  <div class="istatistik">
    <div class="kart stat" style="--r:var(--ok)"><div class="etiket">Giriş yapan</div><div class="deger" id="st-giris">0</div></div>
    <div class="kart stat" style="--r:var(--buz)"><div class="etiket" title="Tekrar deneyen, listede olmayan, erken / geç gelen">Uyarılar</div><div class="deger" id="st-tekrar">0</div></div>
    <div class="kart stat" style="--r:var(--bad)"><div class="etiket">Kayıtsız kişi</div><div class="deger" id="st-kayitsiz">0</div></div>
    <div class="kart stat" style="--r:var(--mor)"><div class="etiket">Canlılık doğrulanamadı</div><div class="deger" id="st-canlilik">0</div></div>
  </div>

  <div class="izgara genis-dar">
    <section class="kart">
      <div class="kart-bas"><h2>Kamera</h2><span class="canli-rozet">CANLI</span></div>
      <div class="kart-govde">
        <div class="kamera-kutu" id="kamera-kutu"><img class="canli" id="canli" src="/canli?detay=1" alt="">
          <div class="kamera-yok">Kamera bağlantısı bekleniyor…</div></div>
        <p class="ipucu" id="canli-durum"></p>
        <div class="aciklama">
          <span style="--r:#0085d0">Tanındı</span>
          <span style="--r:#004684">Kayıtsız</span>
          <span class="beyaz" style="--r:#ffffff">? Emin değil (iki kişiye benziyor)</span>
        </div>
        <p class="ipucu">Yüzde, kişinin kayıtlı fotoğraflarına ne kadar benzediğini gösterir; %50'nin üstü tanınır.</p>
      </div>
    </section>

    <section class="kart">
      <div class="kart-bas"><h2>Bugünkü olaylar</h2><span class="ipucu" style="margin:0" id="kayit-sayisi"></span></div>
      <div class="tablo-kap kaydir">
        <table>
          <thead><tr><th>Kişi</th><th>Durum</th><th>Sıra</th><th>Saat</th></tr></thead>
          <tbody id="kayitlar"><tr><td colspan="4" class="bos">Yükleniyor...</td></tr></tbody>
        </table>
      </div>
    </section>
  </div>

{% else %}
  <div class="sayfa-baslik">
    <div><h1>Öğrenciler</h1><p>Görevli kaydı: kameradan ya da dosyadan fotoğraf ekleme, düzenleme ve silme.</p></div>
    <a class="buton ikincil" href="/kayit" target="_blank">Kayıt kioskunu aç ↗</a>
  </div>

  <div class="izgara dar-genis">
    <section class="kart">
      <div class="kart-bas"><h2>Öğrenci ekle / fotoğraf ekle</h2></div>
      <div class="kart-govde">
        <div class="kamera-kutu" id="kamera-kutu"><img class="canli" id="canli" src="/canli" alt="">
          <div class="kamera-yok">Kamera bağlantısı bekleniyor…</div></div>
        <p class="ipucu" id="canli-durum"></p>
        <label for="numara">Öğrenci numarası</label>
        <input type="text" id="numara" inputmode="numeric" placeholder="ör. 2024123456" maxlength="20" autocomplete="off">
        <label for="ad">Ad Soyad</label>
        <input type="text" id="ad" placeholder="ör. Ayşe Yılmaz" maxlength="60" autocomplete="off">
        <label class="kvkk"><input type="checkbox" id="kvkk"> <span>{{ kvkk }}</span></label>
        <div class="satir" style="margin-top:14px">
          <button id="cek" style="flex:1">Kameradan fotoğraf çek</button>
          <button id="temizle" class="ikincil">Formu temizle</button>
        </div>
        <div class="satir" style="margin-top:10px;flex-wrap:nowrap">
          <input type="file" id="dosya" accept="image/jpeg,image/png" style="flex:1;min-width:0">
          <button id="yukle" class="ikincil">Dosyadan yükle</button>
        </div>
        <p class="ipucu">Her öğrenci için 3–5 fotoğraf: biraz sağa, sola, yukarı bakarak. Aynı numarayla
          tekrar çekilen fotoğraf o öğrenciye eklenir. Karede sadece o kişinin yüzü olmalı.</p>
        <div class="mesaj" id="mesaj"></div>
      </div>
    </section>

    <section class="kart">
      <div class="kart-bas">
        <h2>Kayıtlı öğrenciler <span class="no" id="ogr-sayisi"></span></h2>
        <input type="search" id="ogr-ara" placeholder="Ad ya da numara ara..." style="max-width:240px">
      </div>
      <div class="tablo-kap">
        <table>
          <thead><tr><th>Öğrenci</th><th>Fotoğraf</th><th style="text-align:right">İşlemler</th></tr></thead>
          <tbody id="kisiler"><tr><td colspan="3" class="bos">Yükleniyor...</td></tr></tbody>
        </table>
      </div>
    </section>
  </div>

  <dialog id="duzenle">
    <div class="kart-bas"><h2>Öğrenciyi düzenle</h2><span class="ipucu" style="margin:0" id="d-bilgi"></span></div>
    <div class="kart-govde">
      <div class="yan-yana" style="grid-template-columns:1fr 1.4fr">
        <div><label for="d-numara" style="margin-top:0">Öğrenci numarası</label>
          <input type="text" id="d-numara" inputmode="numeric" maxlength="20" autocomplete="off"></div>
        <div><label for="d-ad" style="margin-top:0">Ad Soyad</label>
          <input type="text" id="d-ad" maxlength="60" autocomplete="off"></div>
      </div>
      <p class="ipucu">Numara değişirse fotoğraflar, sınav listeleri ve geçmiş girişler yeni numaraya taşınır.</p>
      <label>Fotoğraflar</label>
      <div id="d-fotolar" class="fotolar"></div>
      <p class="ipucu" id="d-foto-ipucu"></p>
      <div class="satir" style="margin-top:12px;flex-wrap:nowrap">
        <input type="file" id="d-dosya" accept="image/jpeg,image/png" style="flex:1;min-width:0">
        <button id="d-ekle" class="ikincil">Dosyadan fotoğraf ekle</button>
      </div>
      <div class="mesaj" id="d-mesaj"></div>
    </div>
    <div class="pencere-alt">
      <button id="d-kapat" class="ikincil">Kapat</button>
      <button id="d-kaydet">Kaydet</button>
    </div>
  </dialog>
{% endif %}
</main>
</div>

<style>
  .fotolar { display: flex; gap: 10px; flex-wrap: wrap; }
  .foto-kart { position: relative; }
  .foto-kart img { width: 104px; height: 104px; object-fit: cover; border-radius: 10px; display: block; border: 1px solid var(--border); }
  .foto-kart button { position: absolute; top: 6px; right: 6px; padding: 2px 8px; font-size: 12px;
                      background: rgba(15, 23, 42, .75); border: 0; }
  .foto-kart button:hover { background: var(--brand); }
  .islemler { display: flex; gap: 6px; justify-content: flex-end; }
  .anahtar { display: inline-flex; align-items: center; gap: 9px; margin: 0; font-weight: 600; cursor: pointer;
             padding: 7px 12px; border: 1px solid #d0d5dd; border-radius: 8px; background: #fff; user-select: none; }
  .anahtar input { display: none; }
  .anahtar-kol { width: 34px; height: 20px; border-radius: 999px; background: #cbd5e1; position: relative; transition: background .15s; }
  .anahtar-kol::after { content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
                        background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.2); transition: transform .15s; }
  .anahtar input:checked + .anahtar-kol { background: var(--brand); }
  .anahtar input:checked + .anahtar-kol::after { transform: translateX(14px); }
  .test-serit { display: none; background: none; color: var(--brand); border: 0; padding-left: 2px;
                border-radius: 10px; padding: 11px 14px; margin: -8px 0 18px; font-size: 13.5px; }
  .test-serit.acik { display: block; }
  .test-serit.uyari { background: none; color: #00284c; font-weight: 600; }
  .test-cerceve .canli { outline: 3px dashed var(--buz); outline-offset: 3px; }
</style>

<script>
// Canlı görüntü koparsa (ör. tani.py yeniden başlatıldı) 2 sn'de bir yeniden dene
const canli = document.getElementById("canli");
const canliDurum = document.getElementById("canli-durum");
const kameraKutu = document.getElementById("kamera-kutu");
canli.onerror = () => {
  kameraKutu.classList.add("yok");
  setTimeout(() => { canli.src = "/canli?{{ 'detay=1&' if sayfa == 'tanima' }}" + Date.now(); }, 2000);
};
canli.onload = () => { kameraKutu.classList.remove("yok"); };

function hucre(satir, icerik) {
  const td = satir.insertCell();
  if (icerik instanceof Node) td.appendChild(icerik); else td.textContent = icerik;
  return td;
}
function resim(src) { const img = document.createElement("img"); img.src = src; img.alt = ""; return img; }
function bosSatir(tbody, kolon, yazi) {
  tbody.innerHTML = "";
  const td = tbody.insertRow().insertCell();
  td.colSpan = kolon; td.textContent = yazi; td.className = "bos";
}
function basHarf(ad) { return !ad || ad === "Bilinmeyen" ? "?" : ad.trim().charAt(0).toLocaleUpperCase("tr"); }
// Fotoğraf + ad + numara (alt alta) hücresi
function kisiHucresi(foto, ad, alt) {
  const kutu = document.createElement("div"); kutu.className = "kisi";
  if (foto) kutu.appendChild(resim(foto));
  else { const a = document.createElement("div"); a.className = "avatar-bos"; a.textContent = basHarf(ad); kutu.appendChild(a); }
  const yazi = document.createElement("div");
  const b = document.createElement("b"); b.textContent = ad;
  const s = document.createElement("span"); s.textContent = alt || "";
  yazi.append(b, s); kutu.appendChild(yazi);
  return kutu;
}

{% if sayfa == 'tanima' %}
const DURUMLAR = { giris: ["✓ Giriş", "yesil"], tekrar: ["Tekrar", "turuncu"], bilinmeyen: ["✕ Kayıtsız", "kirmizi"],
                   listede_yok: ["Listede yok", "turuncu"], canlilik_yok: ["✕ Canlılık yok", "mor"],
                   erken: ["Erken geldi", "erken"], gec: ["Geç kaldı", "gec"] };
async function kayitlariYenile() {
  try {
    const kayitlar = await (await fetch("/api/kayitlar")).json();
    const say = (...turler) => kayitlar.filter(k => turler.includes(k.tur)).length;
    document.getElementById("st-giris").textContent = say("giris");
    document.getElementById("st-tekrar").textContent = say("tekrar", "listede_yok", "erken", "gec");
    document.getElementById("st-kayitsiz").textContent = say("bilinmeyen");
    document.getElementById("st-canlilik").textContent = say("canlilik_yok");
    document.getElementById("kayit-sayisi").textContent = kayitlar.length ? `${kayitlar.length} olay` : "";
    const tbody = document.getElementById("kayitlar");
    if (!kayitlar.length) return bosSatir(tbody, 4, "Bugün henüz olay yok.");
    tbody.innerHTML = "";
    for (const k of kayitlar) {
      const tr = tbody.insertRow();
      hucre(tr, kisiHucresi(k.foto ? "/static/" + k.foto : null, k.isim, k.no || "Kayıtsız kişi"));
      const durum = DURUMLAR[k.tur] || DURUMLAR.giris;
      const rozet = document.createElement("span");
      rozet.className = "rozet " + durum[1]; rozet.textContent = durum[0];
      hucre(tr, rozet);
      hucre(tr, k.sira || "—").className = "no";
      hucre(tr, k.zaman.slice(11, 16)).className = "no";
    }
  } catch (e) { /* site kısa süre kapalıysa bir sonrakinde tekrar dener */ }
}
kayitlariYenile();
setInterval(kayitlariYenile, 3000);

// ---- Test modu: açıkken her saniye tani.py'ye "olay yazma" nabzı gönderilir.
// Sayfa kapanınca / başka sekmeye geçilince nabız durur ve 3 sn içinde sistem normale döner.
const testAnahtari = document.getElementById("test-modu");
let aktifSinavAdi = null;
// Görevli test modunu bir sınav aktifken BİLEREK açtıysa o sınavın adı burada tutulur.
// Bunun dışında bir sınav aktif olunca test modu kendiliğinden kapanır (kiosk sınava giriş alabilsin).
let bilerekAcilanSinav = null;
function testGoster() {
  const acik = testAnahtari.checked;
  document.getElementById("test-serit").classList.toggle("acik", acik);
  document.getElementById("sinav-serit").classList.toggle("acik", acik && !!aktifSinavAdi);
  document.getElementById("sinav-adi").textContent = aktifSinavAdi || "";
  document.querySelector(".icerik").classList.toggle("test-cerceve", acik);
}
function testIzinli() {   // aktif sınav yoksa ya da görevli bu sınav sırasında bilerek açtıysa
  return !aktifSinavAdi || bilerekAcilanSinav === aktifSinavAdi;
}
async function nabiz() {
  const test = testAnahtari.checked && testIzinli() && document.visibilityState === "visible";
  try {
    const v = await (await fetch("/api/izleme" + (test ? "?test=1" : ""))).json();
    aktifSinavAdi = v.aktif_sinav;
    if (testAnahtari.checked && !testIzinli()) {
      // Sayfa açıkken bir sınav başladı: test modunu kapat ki kiosk bu sınava giriş alabilsin
      testAnahtari.checked = false;
      document.getElementById("canli-durum").textContent =
        `"${aktifSinavAdi}" sınavı başladı; test modu kendiliğinden kapatıldı, kiosk girişleri kaydediyor.`;
    }
    testGoster();
    return v;
  } catch (e) { return null; }
}
(async () => {
  // Varsayılan: aktif sınav yoksa test modu açık başlar, varsa kapalı (sınav günü kiosk engellenmesin)
  const v = await nabiz();
  testAnahtari.checked = !(v && v.aktif_sinav);
  testGoster();
  nabiz();
  setInterval(nabiz, 1000);
})();
testAnahtari.onchange = () => {
  bilerekAcilanSinav = testAnahtari.checked ? aktifSinavAdi : null;   // sınav sırasında bilerek açıldı
  testGoster(); nabiz();
};

document.getElementById("sifirla").onclick = async () => {
  if (!confirm("Bugünkü tüm giriş kayıtları ve fotoğrafları silinsin mi? Verilen sıra numaraları da boşalır. " +
               "Kayıtlı öğrenciler silinmez.")) return;
  const cevap = await (await fetch("/api/gunu_sifirla", { method: "POST" })).json();
  alert(cevap.mesaj);
  kayitlariYenile();
};
{% else %}
const mesaj = document.getElementById("mesaj");
const numaraKutusu = document.getElementById("numara");
const adKutusu = document.getElementById("ad");
const kvkkKutusu = document.getElementById("kvkk");
const butonlar = [document.getElementById("cek"), document.getElementById("yukle")];

function goster(yazi, iyi) { mesaj.textContent = yazi; mesaj.className = "mesaj " + (iyi ? "iyi" : "kotu"); }

async function kisileriYenile() {
  const kisiler = await (await fetch("/api/kisiler")).json();
  const tbody = document.getElementById("kisiler");
  document.getElementById("ogr-sayisi").textContent = kisiler.length ? `(${kisiler.length})` : "";
  if (!kisiler.length) return bosSatir(tbody, 3, "Henüz kayıtlı öğrenci yok.");
  tbody.innerHTML = "";
  for (const k of kisiler) {
    const tr = tbody.insertRow();
    tr.dataset.ara = (k.ad_soyad + " " + k.no).toLocaleLowerCase("tr");
    hucre(tr, kisiHucresi(k.foto ? "/kisi_foto/" + encodeURIComponent(k.foto) : null, k.ad_soyad, k.no));
    const rozet = document.createElement("span");
    rozet.className = "rozet " + (k.sayi >= 3 ? "yesil" : "turuncu");
    rozet.textContent = k.sayi + " foto";
    rozet.title = k.sayi >= 3 ? "Yeterli" : "Daha fazla fotoğraf tanımayı iyileştirir";
    hucre(tr, rozet);
    const islemler = document.createElement("div"); islemler.className = "islemler";
    const duzenle = document.createElement("button");
    duzenle.textContent = "Düzenle"; duzenle.className = "ikincil kucuk";
    duzenle.onclick = () => duzenleAc(k.no);
    const sil = document.createElement("button");
    sil.className = "sil"; sil.textContent = "Sil";
    sil.onclick = () => kisiSil(k.no, k.ad_soyad);
    islemler.append(duzenle, sil);
    hucre(tr, islemler);
  }
  ogrenciSuz();
}
function ogrenciSuz() {
  const q = document.getElementById("ogr-ara").value.toLocaleLowerCase("tr");
  for (const tr of document.querySelectorAll("#kisiler tr[data-ara]")) tr.style.display = tr.dataset.ara.includes(q) ? "" : "none";
}
document.getElementById("ogr-ara").oninput = ogrenciSuz;

// ---- Öğrenci düzenleme penceresi ----
const pencere = document.getElementById("duzenle");
let duzenlenen = null, duzenlenenAd = "";
async function duzenleAc(numara) {
  const veri = await (await fetch("/api/ogrenci/" + encodeURIComponent(numara))).json();
  if (!veri.ok) { goster(veri.mesaj, false); return; }
  duzenlenen = numara; duzenlenenAd = veri.ad_soyad;
  document.getElementById("d-dosya").value = "";
  document.getElementById("d-numara").value = veri.no;
  document.getElementById("d-ad").value = veri.ad_soyad;
  document.getElementById("d-bilgi").textContent = `Kayıt: ${veri.kayit_zamani.slice(0, 16)} · KVKK onayı alındı`;
  document.getElementById("d-mesaj").className = "mesaj";
  fotolariCiz(veri.fotolar);
  pencere.showModal();
}
function fotolariCiz(fotolar) {
  const kutu = document.getElementById("d-fotolar");
  kutu.innerHTML = "";
  for (const dosya of fotolar) {
    const kart = document.createElement("div"); kart.className = "foto-kart";
    const img = resim("/kisi_foto/" + encodeURIComponent(dosya) + "?" + Date.now());
    const x = document.createElement("button");
    x.textContent = "✕"; x.title = "Bu fotoğrafı sil"; x.disabled = fotolar.length < 2;
    x.onclick = () => fotoSil(dosya);
    kart.append(img, x); kutu.appendChild(kart);
  }
  document.getElementById("d-foto-ipucu").textContent = fotolar.length < 2
    ? "Son fotoğraf silinemez (öğrenci tanınamaz olur). Önce yeni fotoğraf ekleyin."
    : "Bulanık, karanlık ya da başka birinin göründüğü fotoğrafı silmek tanımayı iyileştirir.";
}
function dMesaj(yazi, iyi) { const m = document.getElementById("d-mesaj"); m.textContent = yazi; m.className = "mesaj " + (iyi ? "iyi" : "kotu"); }
async function fotoSil(dosya) {
  if (!confirm("Bu fotoğraf silinsin mi?")) return;
  const f = new FormData(); f.append("dosya", dosya);
  const c = await (await fetch(`/api/ogrenci/${encodeURIComponent(duzenlenen)}/foto_sil`, { method: "POST", body: f })).json();
  dMesaj(c.mesaj, c.ok);
  if (c.ok) { fotolariCiz(c.fotolar); kisileriYenile(); }
}
document.getElementById("d-kaydet").onclick = async () => {
  const f = new FormData();
  f.append("yeni_numara", document.getElementById("d-numara").value.trim());
  f.append("ad_soyad", document.getElementById("d-ad").value.trim().replace(/\\s+/g, " "));
  const c = await (await fetch(`/api/ogrenci/${encodeURIComponent(duzenlenen)}/duzenle`, { method: "POST", body: f })).json();
  dMesaj(c.mesaj, c.ok);
  if (c.ok) { duzenlenen = c.no; kisileriYenile(); setTimeout(() => pencere.close(), 900); }
};
document.getElementById("d-kapat").onclick = () => pencere.close();
// Bu öğrenciye bilgisayardan fotoğraf ekle (KVKK onayı kayıtta zaten alınmış)
document.getElementById("d-ekle").onclick = async () => {
  const dosya = document.getElementById("d-dosya").files[0];
  if (!dosya) { dMesaj("Önce bir fotoğraf dosyası seçin.", false); return; }
  const f = new FormData();
  f.append("numara", duzenlenen); f.append("ad_soyad", duzenlenenAd); f.append("kvkk", "1"); f.append("foto", dosya);
  const b = document.getElementById("d-ekle"); b.disabled = true; dMesaj("İşleniyor...", true);
  try {
    const c = await (await fetch("/api/kisi_ekle", { method: "POST", body: f })).json();
    dMesaj(c.mesaj, c.ok);
    if (c.ok) {
      document.getElementById("d-dosya").value = "";
      const v = await (await fetch("/api/ogrenci/" + encodeURIComponent(duzenlenen))).json();
      if (v.ok) fotolariCiz(v.fotolar);
      kisileriYenile();
    }
  } catch (e) { dMesaj("Sunucuya ulaşılamadı.", false); }
  finally { b.disabled = false; }
};

async function ekle(dosya) {
  const numara = numaraKutusu.value.trim();
  const ad = adKutusu.value.trim().replace(/\\s+/g, " ");
  if (!numara) { goster("Öğrenci numarasını yazın.", false); numaraKutusu.focus(); return; }
  if (!ad) { goster("Ad ve soyadı yazın.", false); adKutusu.focus(); return; }
  if (!kvkkKutusu.checked) { goster("Devam etmek için onay kutusunu işaretleyin.", false); return; }
  const form = new FormData();
  form.append("numara", numara);
  form.append("ad_soyad", ad);
  form.append("kvkk", "1");
  if (dosya) form.append("foto", dosya);
  butonlar.forEach(b => b.disabled = true);
  goster("İşleniyor...", true);
  try {
    const cevap = await (await fetch("/api/kisi_ekle", { method: "POST", body: form })).json();
    goster(cevap.mesaj, cevap.ok);
    if (cevap.ok) kisileriYenile();
  } catch (e) {
    goster("Sunucuya ulaşılamadı.", false);
  } finally {
    butonlar.forEach(b => b.disabled = false);
  }
}

async function kisiSil(numara, ad) {
  if (!confirm(ad + " (" + numara + ") ve tüm fotoğrafları silinsin mi?")) return;
  const form = new FormData();
  form.append("numara", numara);
  const cevap = await (await fetch("/api/kisi_sil", { method: "POST", body: form })).json();
  goster(cevap.mesaj, cevap.ok);
  kisileriYenile();
}

document.getElementById("cek").onclick = () => ekle(null);
document.getElementById("temizle").onclick = () => {
  numaraKutusu.value = ""; adKutusu.value = ""; kvkkKutusu.checked = false;
  document.getElementById("dosya").value = "";
  mesaj.className = "mesaj";
  numaraKutusu.focus();
};
document.getElementById("yukle").onclick = () => {
  const dosya = document.getElementById("dosya").files[0];
  if (!dosya) { goster("Önce bir fotoğraf dosyası seçin.", false); return; }
  ekle(dosya);
};
numaraKutusu.addEventListener("keydown", e => { if (e.key === "Enter") adKutusu.focus(); });
adKutusu.addEventListener("keydown", e => { if (e.key === "Enter") ekle(null); });
kisileriYenile();
{% endif %}
</script>
</body></html>
"""


KIOSK_SAYFASI = """
<!doctype html>
<html lang="tr"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sınav Girişi</title>
<link rel="icon" href="/static/marka/amblem.png">
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: #00284c; color: #fff;
               font-family: system-ui, "Segoe UI", sans-serif; overflow: hidden; }
  body { display: grid; grid-template-rows: auto 1fr auto; }
  header { display: flex; justify-content: space-between; align-items: center; padding: 2vh 3vw; gap: .6em 1.5em; flex-wrap: wrap;
           font-size: clamp(18px, 2.6vw, 34px); font-weight: 700; letter-spacing: .04em; }
  header .saat { font-variant-numeric: tabular-nums; color: #9cc3e4; font-weight: 600; }
  main { display: grid; place-items: center; min-height: 0; padding: 0 3vw; }
  .kamera-kutu { position: relative; height: 100%; max-width: 100%; aspect-ratio: 4 / 3; background: #001f3d;
                 border-radius: 16px; box-shadow: 0 0 0 4px #0a4f8a; overflow: hidden; }
  .canli { width: 100%; height: 100%; object-fit: contain; display: block; }
  .kamera-yok { position: absolute; inset: 0; display: none; place-items: center; color: #9cc3e4;
                font-size: clamp(16px, 2vw, 24px); font-weight: 600; }
  .kamera-kutu.yok .canli { visibility: hidden; }
  .kamera-kutu.yok .kamera-yok { display: grid; }
  footer { text-align: center; padding: 2.5vh 3vw; font-size: clamp(20px, 3vw, 40px); color: #d6e6f5; }
  footer .nokta { display: inline-block; width: .55em; height: .55em; border-radius: 50%;
                  background: #0085d0; margin-right: .4em; animation: nabiz 1.6s infinite; }
  @keyframes nabiz { 50% { opacity: .25; } }

  /* Sonuç ekranı */
  #sonuc { position: fixed; inset: 0; display: none; flex-direction: column; align-items: center;
           justify-content: center; text-align: center; gap: 2.5vh; padding: 4vw; }
  #sonuc.acik { display: flex; }
  @keyframes belir { from { transform: scale(.97); } }   /* saydamlık yok: animasyon durursa bile görünür */
  /* Sonuç ekranları sadece PAÜ mavisi tonlarında: olumlu açık mavi, uyarı orta mavi, olumsuz koyu lacivert */
  #sonuc.giris { background: #0085d0; }
  #sonuc.tekrar, #sonuc.listede_yok, #sonuc.erken { background: #2a6aa3; }
  #sonuc.bilinmeyen, #sonuc.canlilik_yok, #sonuc.gec { background: #001f3d; }
  /* Başlıktaki durum yazıları: arka plansız, sade; satır içinde bölünmez */
  header > span { display: flex; align-items: center; gap: 1.1em; flex-wrap: wrap; }
  header > span:first-child { flex-wrap: nowrap; white-space: nowrap; }
  header > span:last-child { flex-direction: column; align-items: flex-end; gap: .15em; margin-left: auto; }
  header > span:last-child .saat { order: -1; }
  #pencere, #test-rozet, .saat { white-space: nowrap; }
  #pencere { font-size: .6em; font-weight: 600; letter-spacing: 0; }
  #pencere.acik, #pencere.erken, #pencere.kapali { background: none; color: #9cc3e4; }
  #pencere:empty { display: none; }
  #test-rozet { font-size: .6em; font-weight: 600; background: none; color: #9cc3e4; display: none; }
  #test-rozet.acik { display: inline; }
  header .sinav { white-space: nowrap; }
  header .sinav { color: #9cc3e4; }
  .logo { height: 2.3em; width: auto; vertical-align: middle; margin-right: .8em;
          padding-right: .8em; border-right: 1px solid rgba(255,255,255,.25); }

  /* Canlılık: göz kırpması beklenirken alttan çıkan mavi panel (kamera görünmeye devam eder) */
  #kirp { position: fixed; left: 0; right: 0; bottom: 0; background: #0085d0; padding: 2.2vh 4vw 2.6vh;
          display: none; gap: 3vw; align-items: center; box-shadow: 0 -8px 30px rgba(0,0,0,.4); }
  #kirp.acik { display: flex; }
  #kirp .goz-ikon { font-size: clamp(48px, 7vw, 100px); line-height: 1; }
  #kirp .metin { flex: 1; min-width: 0; }
  #kirp-baslik { font-size: clamp(26px, 4.4vw, 64px); font-weight: 800; }
  #kirp-isim { font-size: clamp(18px, 2.4vw, 34px); opacity: .9; }
  .olcer { position: relative; height: 16px; background: rgba(255,255,255,.25); border-radius: 999px; margin-top: 1.4vh; overflow: hidden; }
  .olcer div { height: 100%; background: #fff; border-radius: 999px; transition: width .08s linear; }
  .olcer span { position: absolute; top: -4px; bottom: -4px; width: 3px; background: #00284c; }
  #kirp-kalan { font-size: clamp(32px, 5vw, 72px); font-weight: 800; font-variant-numeric: tabular-nums; }
  .ikon { width: min(28vh, 28vw); height: min(28vh, 28vw); border-radius: 50%; background: rgba(255,255,255,.18);
          display: grid; place-items: center; }
  .ikon svg { width: 62%; height: 62%; stroke: #fff; stroke-width: 3; fill: none; stroke-linecap: round; stroke-linejoin: round; }
  #baslik { font-size: clamp(28px, 5vw, 72px); font-weight: 700; }
  #isim { font-size: clamp(36px, 7vw, 110px); font-weight: 800; line-height: 1.05; }
  #alt { font-size: clamp(24px, 4vw, 60px); font-weight: 700; background: rgba(0,0,0,.22);
         padding: .2em .9em; border-radius: 999px; }
  #alt:empty, #isim:empty { display: none; }

  /* Başlatma ekranı (tam ekran ve ses izni için bir kez dokunmak gerekir) */
  #baslat { position: fixed; inset: 0; background: rgba(0,40,76,.95); display: grid; place-items: center;
            cursor: pointer; text-align: center; font-size: clamp(22px, 3vw, 40px); }
  #baslat small { display: block; margin-top: 1em; font-size: .5em; color: #9cc3e4; }
</style>
</head><body>
<header><span><img class="logo" src="/static/marka/logoTR.png" alt="DTBMYO">SINAV GİRİŞİ<span class="sinav" id="sinav-adi"></span></span><span><span id="test-rozet">Test modu açık · giriş kaydedilmiyor</span><span id="pencere"></span><span class="saat" id="saat"></span></span></header>
<main><div class="kamera-kutu" id="kamera-kutu"><img class="canli" id="canli" src="/canli" alt="">
  <div class="kamera-yok">Kamera bağlantısı bekleniyor…</div></div></main>
<footer><span class="nokta"></span>Lütfen kameraya bakın</footer>

<div id="kirp" role="status" aria-live="polite">
  <div class="goz-ikon"><svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="#fff" stroke-width="2"
       stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/>
       <circle cx="12" cy="12" r="3"/></svg></div>
  <div class="metin">
    <div id="kirp-baslik">Lütfen gözlerinizi kırpın</div>
    <div id="kirp-isim"></div>
    <div class="olcer" title="Göz açıklığı"><div id="kirp-olcer" style="width:100%"></div><span id="kirp-esik"></span></div>
  </div>
  <div id="kirp-kalan"></div>
</div>

<div id="sonuc" role="status" aria-live="assertive">
  <div class="ikon"><svg viewBox="0 0 24 24" id="ikon"></svg></div>
  <div id="baslik"></div>
  <div id="isim"></div>
  <div id="alt"></div>
</div>

<div id="baslat">
  <div>▶ Kiosku başlatmak için dokunun
    <small>Tam ekrana geçer ve sesli karşılamayı açar. Çıkmak için Esc.</small></div>
</div>

<script>
const IKONLAR = {
  giris: '<polyline points="5 12.5 10 17.5 19 7"/>',
  tekrar: '<line x1="12" y1="5" x2="12" y2="14"/><line x1="12" y1="19" x2="12" y2="19"/>',
  bilinmeyen: '<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>',
  listede_yok: '<line x1="12" y1="5" x2="12" y2="14"/><line x1="12" y1="19" x2="12" y2="19"/>',
  canlilik_yok: '<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>',
  erken: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/>',
  gec: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/>',
};
const sonuc = document.getElementById("sonuc");
const kirp = document.getElementById("kirp");
let kirpKimlik = null;   // aynı bekleme için "gözlerinizi kırpın" bir kez söylensin

// Başlıktaki giriş durumu: "Giriş açık · kapanmasına 12 dk", "Giriş açılışı 14:30", "Giriş kapandı"
function pencereYaz(p) {
  const e = document.getElementById("pencere");
  if (!p) { e.textContent = ""; e.className = ""; return; }
  const dk = (sn) => { const d = Math.ceil(sn / 60); return d >= 60 ? `${Math.floor(d / 60)} sa ${d % 60} dk` : `${d} dk`; };
  e.className = p.pencere;
  e.textContent = p.pencere === "acik" ? `Giriş açık · kapanmasına ${dk(p.kapanisa_sn)}`
                : p.pencere === "erken" ? `Giriş açılışı ${p.acilis_saat} · ${dk(p.acilisa_sn)} sonra`
                : `Giriş kapandı (${p.kapanis_saat})`;
}

// Canlılık paneli: tanınan öğrenciden göz kırpması bekleniyorsa göster
function canlilikGoster(c) {
  if (!c || !c.bekliyor || gosteriliyor) { kirp.className = ""; return; }
  kirp.className = "acik";
  document.getElementById("kirp-isim").textContent = c.isim;
  document.getElementById("kirp-kalan").textContent = Math.ceil(c.kalan);
  document.getElementById("kirp-olcer").style.width = (c.goz == null ? 100 : Math.min(100, c.goz * 100)) + "%";
  document.getElementById("kirp-esik").style.left = (c.esik * 100) + "%";
  if (c.kimlik !== kirpKimlik) {
    kirpKimlik = c.kimlik;
    sesCal("/api/ses_cumle?anahtar=kirp", "Lütfen gözlerinizi kırpın.");
  }
}
const $sinav = document.getElementById("sinav-adi");
let son = null, kuyruk = [], gosteriliyor = false, yoklaniyor = false, calan = null;

// Saat
function saatYaz() {
  document.getElementById("saat").textContent =
    new Date().toLocaleString("tr-TR", { weekday: "long", hour: "2-digit", minute: "2-digit" });
}
saatYaz(); setInterval(saatYaz, 10000);

// Canlı görüntü koparsa yeniden dene
const canli = document.getElementById("canli");
const kameraKutu = document.getElementById("kamera-kutu");
canli.onerror = () => { kameraKutu.classList.add("yok"); setTimeout(() => { canli.src = "/canli?" + Date.now(); }, 2000); };
canli.onload = () => kameraKutu.classList.remove("yok");

// Başlat: tam ekran + ses izni
document.getElementById("baslat").onclick = (e) => {
  e.currentTarget.remove();
  document.documentElement.requestFullscreen?.().catch(() => {});
};

// Olayları yokla
async function yokla() {
  if (yoklaniyor) return;
  yoklaniyor = true;
  try {
    const cevap = await fetch(son === null ? "/api/olaylar" : "/api/olaylar?son=" + son);
    if (cevap.status === 401) { location.href = "/giris"; return; }
    const veri = await cevap.json();
    $sinav.textContent = veri.sinav ? " · " + veri.sinav : "";   // aktif sınavın adı
    pencereYaz(veri.pencere);
    document.getElementById("test-rozet").classList.toggle("acik", !!(veri.canlilik && veri.canlilik.test_modu));
    if (son === null) { son = veri.son; return; }   // açılışta eski olayları gösterme
    for (const olay of veri.olaylar) { kuyruk.push(olay); son = Math.max(son, olay.id); }
    if (!gosteriliyor) siradaki();
    canlilikGoster(veri.canlilik);
  } catch (e) { /* bağlantı koptuysa bir sonrakinde tekrar dener */ }
  finally { yoklaniyor = false; }
}
setInterval(yokla, 400);
yokla();

function siradaki() {
  const olay = kuyruk.shift();
  if (!olay) { sonuc.className = ""; gosteriliyor = false; return; }
  gosteriliyor = true;
  kirp.className = "";
  document.getElementById("ikon").innerHTML = IKONLAR[olay.tur] || "";
  document.getElementById("baslik").textContent = olay.baslik;
  document.getElementById("isim").textContent = olay.tur === "bilinmeyen" ? "" : olay.isim;
  document.getElementById("alt").textContent = olay.alt;
  sonuc.className = "acik " + olay.tur;
  seslendir(olay);
  setTimeout(siradaki, kuyruk.length ? 2500 : 4500);   // sırada bekleyen varsa daha kısa göster
}

// Önce sunucudaki Türkçe ses motoru; yoksa tarayıcının kendi sesi; o da yoksa sessiz
function seslendir(olay) { sesCal("/api/ses/" + olay.id, olay.soz); }

async function sesCal(adres, metin) {
  try {
    if (calan) { calan.pause(); calan = null; }
    window.speechSynthesis?.cancel();
    const cevap = await fetch(adres);
    if ((cevap.headers.get("Content-Type") || "").startsWith("audio")) {
      calan = new Audio(URL.createObjectURL(await cevap.blob()));
      await calan.play();
      return;
    }
  } catch (e) { /* ses çalınamadıysa aşağıdakini dene */ }
  if (!window.speechSynthesis) return;
  const soz = new SpeechSynthesisUtterance(metin);
  soz.lang = "tr-TR";
  const turkce = speechSynthesis.getVoices().find(v => v.lang.toLowerCase().startsWith("tr"));
  if (turkce) soz.voice = turkce;
  speechSynthesis.speak(soz);
}
</script>
</body></html>
"""


SINAV_SAYFASI = """
<!doctype html>
<html lang="tr"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ 'Sınavlar' if sayfa == 'liste' else 'Yoklama' }} · Sınav Giriş</title>
<link rel="icon" href="/static/marka/amblem.png">
{{ ORTAK_STIL|safe }}
<style>
  .liste-kutu { max-height: 300px; overflow: auto; border: 1px solid var(--border); border-radius: 8px; }
  .liste-kutu label { display: flex; gap: 10px; align-items: center; font-weight: 500; margin: 0; padding: 9px 12px;
                      border-bottom: 1px solid #f1f3f7; cursor: pointer; font-size: 14px; }
  .liste-kutu label:last-child { border-bottom: 0; }
  .liste-kutu label:hover { background: #fafbff; }
  .liste-kutu input { width: 17px; height: 17px; accent-color: var(--brand); flex: none; }
  .liste-kutu .no { margin-left: auto; font-size: 12.5px; }
  .liste-ust { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
  .liste-ust input { flex: 1; min-width: 160px; }
  .sinav-ad { font-weight: 650; color: var(--text); text-decoration: none; }
  .sinav-ad:hover { color: var(--vurgu); }
  .mini-cubuk { display: flex; align-items: center; gap: 8px; min-width: 84px; }
  .mini-cubuk .cubuk { flex: 1; }
  .islemler { display: flex; gap: 6px; justify-content: flex-end; flex-wrap: nowrap; }
  table:has(#sinavlar) th, #sinavlar td { padding: 11px 10px; }
  #sinavlar td:first-child { min-width: 150px; }
  #sinavlar .no { white-space: nowrap; }
  .bilgi-kutu { background: var(--brand-acik); color: var(--brand); border-radius: 8px; padding: 10px 12px; font-size: 13px; margin: 0 18px 0; }
  details.kart > summary { list-style: none; cursor: pointer; padding: 14px 18px; font-weight: 650; display: flex;
                           justify-content: space-between; align-items: center; }
  details.kart > summary::after { content: "▾"; color: var(--muted); }
  details.kart[open] > summary { border-bottom: 1px solid var(--border); }
  details.kart[open] > summary::after { content: "▴"; }
  .ilerleme-kart { padding: 18px 20px; margin-bottom: 20px; }
  .ilerleme-ust { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
  .buyuk-sayi { font-size: 34px; font-weight: 750; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
  .buyuk-sayi small { font-size: 16px; color: var(--muted); font-weight: 600; letter-spacing: 0; }
  .ilerleme-kart .cubuk { height: 12px; }
</style>
</head><body>
<div class="duzen">
{{ menu_ciz('sinavlar')|safe }}
<main class="icerik">

{% if sayfa == 'liste' %}
  <div class="sayfa-baslik">
    <div><h1>Sınavlar</h1><p>Sınav oluşturun, başlatın ve canlı yoklamayı takip edin.</p></div>
  </div>
  <div class="mesaj" id="mesaj" style="margin:0 0 16px"></div>

  <div class="izgara dar-genis">
    <section class="kart">
      <div class="kart-bas"><h2>Yeni sınav</h2></div>
      <div class="kart-govde">
        <label for="ad" style="margin-top:0">Sınavın adı</label>
        <input type="text" id="ad" maxlength="60" placeholder="ör. Matematik Finali">
        <div class="yan-yana tarih-satir">
          <div><label for="tarih">Tarih</label><input type="date" id="tarih" value="{{ bugun }}"></div>
          <div><label for="saat">Başlangıç</label><input type="time" id="saat" value="10:00"></div>
          <div><label for="koltuk">Sıra sayısı</label><input type="number" id="koltuk" min="1" max="500" value="30"></div>
        </div>
        <div class="yan-yana">
          <div><label for="sure">Süre (dk)</label><input type="number" id="sure" min="5" max="600" value="60"></div>
          <div><label for="acilis">Giriş kaç dk önce</label><input type="number" id="acilis" min="0" max="240" value="30"></div>
          <div><label for="gec">Geç giriş (dk)</label><input type="number" id="gec" min="0" max="120" value="0"></div>
        </div>
        <p class="bilgi-kutu" id="zaman-ozet" style="margin:12px 0 0"></p>
        <label>Sınava girecek öğrenciler <span class="no" id="secim-sayisi"></span></label>
        <div class="liste-ust">
          <input type="search" id="ara" placeholder="Ad ya da numara ara...">
          <button class="ikincil kucuk" id="hepsi">Tümü</button><button class="ikincil kucuk" id="hicbiri">Hiçbiri</button>
        </div>
        <div class="liste-kutu" id="ogrenci-listesi"></div>
        <button id="olustur" class="tam" style="margin-top:16px">Sınavı oluştur</button>
      </div>
    </section>

    <section class="kart">
      <div class="kart-bas"><h2>Tüm sınavlar</h2></div>
      <p class="bilgi-kutu" style="margin-top:14px">Aynı anda tek sınav <b>aktif</b> olur. Aktif sınav varken giriş kiosku
        sadece o sınavın listesindekileri kabul eder; aktif sınav yoksa kayıtlı herkes girebilir (serbest mod).</p>
      <div class="tablo-kap" style="margin-top:10px">
        <table>
          <thead><tr><th>Sınav</th><th>Durum</th><th>Gelen</th><th style="text-align:right">İşlemler</th></tr></thead>
          <tbody id="sinavlar"><tr><td colspan="4" class="bos">Yükleniyor...</td></tr></tbody>
        </table>
      </div>
    </section>
  </div>

{% else %}
  <div class="sayfa-baslik">
    <div>
      <a class="geri" href="/sinavlar">← Sınavlar</a>
      <h1 id="s-ad">Yükleniyor…</h1>
      <p id="s-bilgi"></p>
      <div class="satir" id="s-rozetler" style="margin-top:8px;gap:6px"></div>
    </div>
    <div class="satir" id="s-butonlar"></div>
  </div>
  <div class="mesaj" id="mesaj" style="margin:0 0 16px"></div>

  <section class="kart ilerleme-kart">
    <div class="ilerleme-ust">
      <div class="buyuk-sayi"><span id="gelen">0</span> <small>/ <span id="toplam">0</span> öğrenci giriş yaptı</small></div>
      <div class="no" id="yuzde"></div>
    </div>
    <div class="cubuk"><div id="cubuk" style="width:0"></div></div>
  </section>

  <div class="izgara iki-sutun">
    <section class="kart">
      <div class="kart-bas"><h2>Gelenler</h2><span class="rozet yesil" id="gelen-rozet">0</span></div>
      <div class="tablo-kap">
        <table><thead><tr><th>Öğrenci</th><th>Saat</th><th>Sıra</th></tr></thead><tbody id="gelenler"></tbody></table>
      </div>
    </section>
    <section class="kart">
      <div class="kart-bas"><h2>Gelmeyenler</h2><span class="rozet bitti" id="gelmeyen-rozet">0</span></div>
      <div class="tablo-kap">
        <table><thead><tr><th>Öğrenci</th><th></th></tr></thead><tbody id="gelmeyenler"></tbody></table>
      </div>
    </section>
  </div>

  <section class="kart" style="margin-top:20px">
    <div class="kart-bas"><h2>Diğer girişimler</h2>
      <span class="ipucu" style="margin:0">Tekrar deneyen, listede olmayan, kayıtsız, erken/geç gelen ve canlılığı doğrulanamayanlar</span></div>
    <div class="tablo-kap kaydir" style="max-height:420px">
      <table><thead><tr><th>Kişi</th><th>Durum</th><th>Saat</th></tr></thead><tbody id="diger"></tbody></table>
    </div>
  </section>

  <details class="kart" style="margin-top:20px">
    <summary>Öğrenci listesini düzenle</summary>
    <div class="kart-govde">
      <div class="liste-ust"><input type="search" id="ara" placeholder="Ad ya da numara ara..."></div>
      <div class="liste-kutu" id="ogrenci-listesi"></div>
      <button id="liste-kaydet" style="margin-top:12px">Listeyi kaydet</button>
    </div>
  </details>
{% endif %}
</main>
</div>

<script>
const $ = (id) => document.getElementById(id);
function goster(yazi, iyi) { $("mesaj").textContent = yazi; $("mesaj").className = "mesaj " + (iyi ? "iyi" : "kotu"); }
function hucre(tr, icerik, sinif) {
  const td = tr.insertCell();
  if (icerik instanceof Node) td.appendChild(icerik); else td.textContent = icerik ?? "";
  if (sinif) td.className = sinif;
  return td;
}
function rozet(yazi, sinif) { const s = document.createElement("span"); s.className = "rozet " + sinif; s.textContent = yazi; return s; }
function buton(yazi, sinif, islev) { const b = document.createElement("button"); b.textContent = yazi; b.className = sinif; b.onclick = islev; return b; }
function bos(tbody, kolon, yazi) { tbody.innerHTML = ""; const td = tbody.insertRow().insertCell(); td.colSpan = kolon; td.textContent = yazi; td.className = "bos"; }
function kisiHucresi(foto, ad, alt) {
  const kutu = document.createElement("div"); kutu.className = "kisi";
  if (foto) { const img = document.createElement("img"); img.src = foto; img.alt = ""; kutu.appendChild(img); }
  else { const a = document.createElement("div"); a.className = "avatar-bos"; a.textContent = basHarf(ad); kutu.appendChild(a); }
  const yazi = document.createElement("div");
  const b = document.createElement("b"); b.textContent = ad;
  const s = document.createElement("span"); s.textContent = alt || "";
  yazi.append(b, s); kutu.appendChild(yazi);
  return kutu;
}
const tarihYaz = (t) => t.split("-").reverse().join(".");
function basHarf(ad) { return !ad || ad === "Bilinmeyen" ? "?" : ad.trim().charAt(0).toLocaleUpperCase("tr"); }
function dkYaz(sn) { const dk = Math.ceil(sn / 60); return dk >= 60 ? `${Math.floor(dk / 60)} sa ${dk % 60} dk` : `${dk} dk`; }
function pencereRozeti(s, kisa) {
  if (s.pencere === "acik") return rozet(kisa ? `Açık · ${dkYaz(s.kapanisa_sn)}` : `Giriş açık · ${dkYaz(s.kapanisa_sn)} kaldı`, "aktif");
  if (s.pencere === "erken") return rozet(`Giriş ${s.acilis_saat} itibarıyla`, "erken");
  return rozet("Giriş kapandı", "gec");
}
async function post(adres, veri = {}) {
  const f = new FormData();
  for (const [k, v] of Object.entries(veri)) (Array.isArray(v) ? v : [v]).forEach(x => f.append(k, x));
  const cevap = await fetch(adres, { method: "POST", body: f });
  if (cevap.status === 401) { location.href = "/giris"; throw new Error("oturum"); }
  return cevap.json();
}

// Öğrenci seçim listesi (iki sayfada da)
function listeyiCiz(ogrenciler) {
  const kutu = $("ogrenci-listesi");
  kutu.innerHTML = "";
  if (!ogrenciler.length) { kutu.innerHTML = '<div class="bos">Henüz kayıtlı öğrenci yok.</div>'; return; }
  for (const o of ogrenciler) {
    const etiket = document.createElement("label");
    const kutucuk = document.createElement("input");
    kutucuk.type = "checkbox"; kutucuk.value = o.no; kutucuk.checked = !!o.secili;
    kutucuk.onchange = secimSay;
    etiket.append(kutucuk, o.ad, Object.assign(document.createElement("span"), { className: "no", textContent: o.no }));
    etiket.dataset.ara = (o.ad + " " + o.no).toLocaleLowerCase("tr");
    kutu.appendChild(etiket);
  }
  secimSay();
}
function secilenler() { return [...document.querySelectorAll("#ogrenci-listesi input:checked")].map(k => k.value); }
function secimSay() { const s = $("secim-sayisi"); if (s) s.textContent = `(${secilenler().length} seçili)`; }
$("ara").oninput = () => {
  const q = $("ara").value.toLocaleLowerCase("tr");
  for (const e of document.querySelectorAll("#ogrenci-listesi label")) e.style.display = e.dataset.ara.includes(q) ? "" : "none";
};

{% if sayfa == 'liste' %}
async function yenile(listeyiDeYenile) {
  const veri = await (await fetch("/api/sinavlar")).json();
  if (listeyiDeYenile) listeyiCiz(veri.ogrenciler);
  const tbody = $("sinavlar");
  if (!veri.sinavlar.length) return bos(tbody, 4, "Henüz sınav yok. Soldan bir sınav oluşturun.");
  tbody.innerHTML = "";
  for (const s of veri.sinavlar) {
    const tr = tbody.insertRow();
    const ad = document.createElement("div");
    const a = document.createElement("a"); a.href = "/sinav/" + s.id; a.textContent = s.ad; a.className = "sinav-ad";
    const alt = document.createElement("div"); alt.className = "no"; alt.style.fontSize = "12.5px";
    alt.innerHTML = "";
    alt.append(`${tarihYaz(s.tarih)} · ${s.baslangic_saat}–${s.bitis_saat}`, document.createElement("br"),
               `Giriş ${s.acilis_saat}–${s.kapanis_saat}`);
    ad.append(a, alt);
    hucre(tr, ad);
    const durumKutu = document.createElement("div"); durumKutu.className = "satir"; durumKutu.style.gap = "4px";
    durumKutu.append(rozet(s.durum_adi, s.durum));
    if (s.durum === "aktif") { const r = pencereRozeti(s, true); r.title = "Giriş penceresi"; durumKutu.append(r); }
    hucre(tr, durumKutu);
    const ilerleme = document.createElement("div"); ilerleme.className = "mini-cubuk";
    const cubuk = document.createElement("div"); cubuk.className = "cubuk";
    const dolu = document.createElement("div"); dolu.style.width = (s.toplam ? 100 * s.gelen / s.toplam : 0) + "%";
    cubuk.appendChild(dolu);
    const sayi = document.createElement("span"); sayi.className = "no"; sayi.textContent = `${s.gelen}/${s.toplam}`;
    ilerleme.append(cubuk, sayi);
    hucre(tr, ilerleme);
    const islemler = document.createElement("div"); islemler.className = "islemler";
    const yoklama = document.createElement("a"); yoklama.className = "buton ikincil kucuk"; yoklama.href = "/sinav/" + s.id; yoklama.textContent = "Yoklama";
    islemler.append(yoklama);
    if (s.durum === "aktif") islemler.append(buton("Bitir", "turuncu-b kucuk", () => durum(s.id, "bitir")));
    else if (s.bitise_sn > 0) islemler.append(buton(s.durum === "bitti" ? "Tekrar başlat" : "Başlat", "yesil-b kucuk", () => durum(s.id, "baslat")));
    if (s.durum !== "aktif") {   // aktif sınavda Demo'ya gerek yok
      const demo = buton("Demo", "ikincil kucuk", () => demoBaslat(s.id));
      demo.title = "Sunum/prova için: sınavı 10 dk sonra başlayacak şekilde ayarlar, giriş hemen açılır";
      islemler.append(demo);
    }
    islemler.append(buton("Sil", "sil", () => sil(s)));
    hucre(tr, islemler);
  }
}
async function durum(id, islem) { const c = await post(`/api/sinav/${id}/durum`, { islem }); goster(c.mesaj, c.ok); yenile(); }
async function demoBaslat(id) { const c = await post(`/api/sinav/${id}/demo`); goster(c.mesaj, c.ok); yenile(); }
async function sil(s) {
  if (!confirm(`"${s.ad}" sınavı, öğrenci listesi ve tüm giriş kayıtları silinsin mi? Bu geri alınamaz.`)) return;
  const c = await post(`/api/sinav/${s.id}/sil`); goster(c.mesaj, c.ok); yenile();
}
$("hepsi").onclick = () => { document.querySelectorAll("#ogrenci-listesi label").forEach(e => { if (e.style.display !== "none") e.querySelector("input").checked = true; }); secimSay(); };
$("hicbiri").onclick = () => { document.querySelectorAll("#ogrenci-listesi input").forEach(k => k.checked = false); secimSay(); };
$("olustur").onclick = async () => {
  $("olustur").disabled = true;
  try {
    const c = await post("/api/sinav_olustur", { ad: $("ad").value, tarih: $("tarih").value, saat: $("saat").value,
                                                 koltuk: $("koltuk").value, sure: $("sure").value, acilis: $("acilis").value,
                                                 gec: $("gec").value, ogrenciler: secilenler() });
    goster(c.mesaj, c.ok);
    if (c.ok) { $("ad").value = ""; $("hicbiri").click(); yenile(); }
  } finally { $("olustur").disabled = false; }
};
// Formdaki saatlerin özeti: "Giriş 09:30–10:00 arası açık · sınav 10:00–11:00"
function dakikaEkle(saat, dk) {
  const [h, m] = saat.split(":").map(Number); const t = (h * 60 + m + dk + 1440 * 2) % 1440;
  return String(Math.floor(t / 60)).padStart(2, "0") + ":" + String(t % 60).padStart(2, "0");
}
function zamanOzeti() {
  const saat = $("saat").value; if (!saat) return;
  const ac = +$("acilis").value || 0, gec = +$("gec").value || 0, sure = +$("sure").value || 0;
  $("zaman-ozet").innerHTML = `Giriş <b>${dakikaEkle(saat, -ac)} – ${dakikaEkle(saat, gec)}</b> arası açık · ` +
    `sınav <b>${saat} – ${dakikaEkle(saat, sure)}</b>` + (gec ? "" : " · başladığı an giriş kapanır");
}
["saat", "acilis", "gec", "sure"].forEach(id => $(id).addEventListener("input", zamanOzeti));
zamanOzeti();
yenile(true);
setInterval(() => yenile(false), 5000);
{% else %}
const SINAV = {{ sinav_id }};
const TURLER = { tekrar: "Tekrar deneme", listede_yok: "Listede yok", bilinmeyen: "Kayıtsız",
                 canlilik_yok: "Canlılık yok", erken: "Erken geldi", gec: "Geç kaldı" };
let listeCizildi = false;
async function yenile() {
  let veri;
  try { veri = await (await fetch("/api/sinav/" + SINAV)).json(); } catch (e) { return; }
  if (!veri.ok) { location.href = "/sinavlar"; return; }
  const s = veri.sinav;
  document.title = s.ad + " · Yoklama";
  $("s-ad").textContent = s.ad;
  $("s-bilgi").textContent = `${tarihYaz(s.tarih)} · Sınav ${s.baslangic_saat}–${s.bitis_saat} · ` +
    `Giriş ${s.acilis_saat}–${s.kapanis_saat} · ${s.koltuk} sıra`;
  const rozetler = $("s-rozetler"); rozetler.innerHTML = "";
  rozetler.append(rozet(s.durum_adi, s.durum));
  if (s.durum !== "bitti") rozetler.append(pencereRozeti(s));
  const btn = $("s-butonlar"); btn.innerHTML = "";
  if (s.durum === "aktif") btn.append(buton("Sınavı bitir", "turuncu-b", () => durum("bitir")));
  else if (s.bitise_sn > 0) btn.append(buton(s.durum === "bitti" ? "Tekrar başlat" : "Sınavı başlat", "yesil-b", () => durum("baslat")));
  const excel = document.createElement("a"); excel.className = "buton ikincil"; excel.href = `/sinav/${SINAV}/excel`; excel.textContent = "⬇ Excel'e aktar";
  btn.append(excel);
  if (s.durum !== "aktif") {
    const demo = buton("Demo", "ikincil", demoBaslat);
    demo.title = "Sunum/prova için: sınavı 10 dk sonra başlayacak şekilde ayarlar, giriş hemen açılır";
    btn.append(demo);
  }
  btn.append(buton("Yoklamayı sıfırla", "tehlike", sifirla));

  const toplam = veri.gelenler.length + veri.gelmeyenler.length;
  const oran = toplam ? Math.round(100 * veri.gelenler.length / toplam) : 0;
  $("gelen").textContent = veri.gelenler.length; $("toplam").textContent = toplam;
  $("yuzde").textContent = toplam ? `%${oran} katılım` : "";
  $("cubuk").style.width = oran + "%";
  $("gelen-rozet").textContent = veri.gelenler.length;
  $("gelmeyen-rozet").textContent = veri.gelmeyenler.length;

  const g = $("gelenler");
  if (!veri.gelenler.length) bos(g, 3, "Henüz giriş yapan yok."); else {
    g.innerHTML = "";
    for (const o of veri.gelenler) {
      const tr = g.insertRow();
      const kisi = kisiHucresi(o.foto ? "/static/" + o.foto : null, o.ad, o.no);
      if (o.aciklama) { const r = rozet(o.aciklama, "mavi"); r.style.marginLeft = "4px"; kisi.appendChild(r); }
      hucre(tr, kisi); hucre(tr, o.saat.slice(0, 5), "no"); hucre(tr, o.sira || "—", "no");
    }
  }
  const m = $("gelmeyenler");
  if (!veri.gelmeyenler.length) bos(m, 2, toplam ? "Herkes geldi." : "Listede öğrenci yok."); else {
    m.innerHTML = "";
    for (const o of veri.gelmeyenler) {
      const tr = m.insertRow(); hucre(tr, kisiHucresi(null, o.ad, o.no));
      const b = buton("Elle giriş", "ikincil kucuk", () => elleGiris(o));
      b.title = "Görevli onayıyla içeri al (geç kalan ya da kameranın tanıyamadığı öğrenci)";
      const td = hucre(tr, b); td.style.textAlign = "right";
    }
  }
  const d = $("diger");
  if (!veri.diger.length) bos(d, 3, "Yok."); else {
    d.innerHTML = "";
    for (const o of veri.diger) {
      const tr = d.insertRow();
      hucre(tr, kisiHucresi(o.foto ? "/static/" + o.foto : null, o.isim, o.no || "Kayıtsız kişi"));
      hucre(tr, rozet(TURLER[o.tur] || o.tur, o.tur)); hucre(tr, o.saat.slice(0, 5), "no");
    }
  }
  if (!listeCizildi) { listeyiCiz(veri.ogrenciler); listeCizildi = true; }
}
async function durum(islem) { const c = await post(`/api/sinav/${SINAV}/durum`, { islem }); goster(c.mesaj, c.ok); yenile(); }
async function demoBaslat() { const c = await post(`/api/sinav/${SINAV}/demo`); goster(c.mesaj, c.ok); yenile(); }
async function elleGiris(o) {
  if (!confirm(`${o.ad} (${o.no}) görevli onayıyla içeri alınsın mı? Sıra numarası verilecek ve yoklamada ` +
               `"Görevli onayıyla" yazacak.`)) return;
  const c = await post(`/api/sinav/${SINAV}/elle_giris`, { numara: o.no }); goster(c.mesaj, c.ok); yenile();
}
async function sifirla() {
  if (!confirm("Bu sınavın tüm giriş kayıtları ve fotoğrafları silinsin mi? Verilen sıra numaraları da boşalır. Öğrenci listesi kalır.")) return;
  const c = await post(`/api/sinav/${SINAV}/sifirla`); goster(c.mesaj, c.ok); yenile();
}
$("liste-kaydet").onclick = async () => {
  const c = await post(`/api/sinav/${SINAV}/ogrenciler`, { ogrenciler: secilenler() }); goster(c.mesaj, c.ok); yenile();
};
yenile();
setInterval(yenile, 3000);
{% endif %}
</script>
</body></html>
"""


KAYIT_SAYFASI = """
<!doctype html>
<html lang="tr"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sınav Kaydı</title>
<link rel="icon" href="/static/marka/amblem.png">
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100%; background: #00284c; color: #fff;
               font-family: system-ui, "Segoe UI", sans-serif; }
  body { min-height: 100vh; display: flex; flex-direction: column; }
  header { display: flex; justify-content: space-between; align-items: center; padding: 2vh 3vw;
           font-size: clamp(18px, 2.4vw, 32px); font-weight: 700; letter-spacing: .04em; }
  header button { font-size: 14px; }
  .logo { height: 2.3em; width: auto; vertical-align: middle; margin-right: .8em;
          padding-right: .8em; border-right: 1px solid rgba(255,255,255,.25); }
  .ekran { display: none; flex: 1; padding: 0 3vw 3vh; }
  .ekran.acik { display: flex; }
  button { font: inherit; border: 0; border-radius: 10px; cursor: pointer; padding: .7em 1.4em;
           background: #2a6aa3; color: #fff; }
  button.ana { background: #0085d0; font-size: clamp(18px, 2vw, 26px); font-weight: 700; width: 100%; margin-top: 18px; }
  button:disabled { opacity: .5; cursor: wait; }

  /* 1) Form */
  #form { align-items: center; justify-content: center; }
  .kart { background: #003563; border: 1px solid #0a4f8a; border-radius: 16px; padding: clamp(20px, 3vw, 36px);
          width: min(560px, 100%); }
  .kart h1 { margin: 0 0 6px; font-size: clamp(24px, 3vw, 36px); }
  .kart p { margin: 0 0 18px; color: #9cc3e4; }
  label { display: block; font-weight: 700; margin: 16px 0 6px; }
  input[type=text] { width: 100%; padding: 14px; font-size: 20px; border-radius: 10px; border: 1px solid #2a6aa3;
                     background: #00284c; color: #fff; }
  .kvkk { display: flex; gap: 12px; align-items: flex-start; font-weight: normal; font-size: 15px; line-height: 1.45;
          color: #d6e6f5; background: #00284c; border: 1px solid #2a6aa3; border-radius: 10px; padding: 12px; cursor: pointer; }
  .kvkk input { width: 22px; height: 22px; margin-top: 2px; flex: none; }
  .mesaj { margin-top: 14px; padding: 12px; border-radius: 10px; display: none; }
  .mesaj.kotu { display: block; background: #001f3d; border-left: 4px solid #9cc3e4; }
  .mesaj.bilgi { display: block; background: #0a4f8a; }

  /* 2) Rehberli çekim */
  #cekim { flex-direction: column; align-items: center; gap: 2vh; }
  .kamera { position: relative; height: min(58vh, 70vw); aspect-ratio: 4 / 3; max-width: 100%;
            border-radius: 16px; overflow: hidden; background: #000; }
  .kamera img { width: 100%; height: 100%; object-fit: cover; display: block; } /* aynalama tani.py'de (GORUNTU_AYNA) */
  .oval { position: absolute; left: 50%; top: 50%; width: 42%; height: 72%; transform: translate(-50%, -50%);
          border: 4px dashed rgba(255,255,255,.55); border-radius: 50%; transition: border-color .2s; }
  .oval.tutuyor { border-color: #ffffff; border-style: solid; box-shadow: 0 0 0 4px rgba(0,133,208,.6); }
  .ok { position: absolute; top: 50%; transform: translateY(-50%); font-size: min(14vh, 12vw); font-weight: 900;
        color: #ffffff; text-shadow: 0 2px 14px rgba(0,133,208,.9); display: none; animation: it 1s infinite; }
  .ok.sag { right: 4%; } .ok.sol { left: 4%; }
  @keyframes it { 50% { opacity: .35; } }
  #talimat { font-size: clamp(24px, 3.6vw, 52px); font-weight: 800; text-align: center; min-height: 1.2em; }
  #ipucu { font-size: clamp(16px, 1.8vw, 24px); color: #9cc3e4; min-height: 1.3em; text-align: center; }
  .adimlar { display: flex; gap: 12px; }
  .adim { padding: .5em 1.2em; border-radius: 999px; background: #0a4f8a; color: #9cc3e4;
          font-size: clamp(16px, 1.8vw, 24px); font-weight: 700; }
  .adim.aktif { background: #ffffff; color: #004684; }
  .adim.bitti { background: #0085d0; color: #fff; }
  .adim.bitti::before { content: "✓ "; }

  /* 3) Bitti */
  #bitti { flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 2.5vh;
           background: #0085d0; position: fixed; inset: 0; }
  #bitti .ikon { width: min(26vh, 26vw); height: min(26vh, 26vw); border-radius: 50%; background: rgba(255,255,255,.18);
                 display: grid; place-items: center; }
  #bitti svg { width: 62%; height: 62%; stroke: #fff; stroke-width: 3; fill: none; stroke-linecap: round; stroke-linejoin: round; }
  #bitti h2 { margin: 0; font-size: clamp(28px, 5vw, 72px); }
  #bitti-isim { font-size: clamp(32px, 6vw, 96px); font-weight: 800; }
  #bitti-alt { font-size: clamp(18px, 2.4vw, 32px); opacity: .9; }
</style>
</head><body>
<header><span><img class="logo" src="/static/marka/logoTR.png" alt="DTBMYO">SINAV KAYDI</span><button id="tamekran">⛶ Tam ekran</button></header>

<section class="ekran acik" id="form">
  <div class="kart">
    <h1>Yeni kayıt</h1>
    <p>Bilgilerinizi yazın, ardından kamera sizi yönlendirecek.</p>
    <label for="numara">Öğrenci numarası</label>
    <input type="text" id="numara" inputmode="numeric" maxlength="20" autocomplete="off" placeholder="ör. 2024123456">
    <label for="ad">Ad Soyad</label>
    <input type="text" id="ad" maxlength="60" autocomplete="off" placeholder="ör. Ayşe Yılmaz">
    <label class="kvkk" style="margin-top:18px"><input type="checkbox" id="kvkk"><span>{{ kvkk }}</span></label>
    <button class="ana" id="basla">Kayda başla ▶</button>
    <div class="mesaj" id="mesaj"></div>
  </div>
</section>

<section class="ekran" id="cekim">
  <div class="adimlar"><span class="adim" id="adim0">1 · Düz</span><span class="adim" id="adim1">2 · Sağ</span><span class="adim" id="adim2">3 · Sol</span></div>
  <div class="kamera">
    <img id="canli" alt="Kamera görüntüsü">
    <div class="oval" id="oval"></div>
    <div class="ok sag" id="ok-sag">→</div>
    <div class="ok sol" id="ok-sol">←</div>
  </div>
  <div id="talimat"></div>
  <div id="ipucu"></div>
  <button id="iptal">İptal</button>
</section>

<section class="ekran" id="bitti">
  <div class="ikon"><svg viewBox="0 0 24 24"><polyline points="5 12.5 10 17.5 19 7"/></svg></div>
  <h2>Kaydınız tamamlandı</h2>
  <div id="bitti-isim"></div>
  <div id="bitti-alt"></div>
  <div style="font-size:clamp(14px,1.6vw,20px);opacity:.75;margin-top:2vh">Yeni kayıt için ekrana dokunun</div>
</section>

<script>
const $ = (id) => document.getElementById(id);
const bekle = (ms) => new Promise(r => setTimeout(r, ms));
const ADIM_SURESI = 30000;   // bir poz için en fazla bekleme (ms)
let iptal = false, calan = null;

$("tamekran").onclick = () => document.documentElement.requestFullscreen?.().catch(() => {});

// Bu sayfa ekranda açıkken tani.py kayıt modunda kalsın: formu dolduran (henüz kayıtlı olmayan)
// kişi için "Bilinmeyen" kaydı düşülmesin. Çekim sırasında /api/poz zaten sık çağrılıyor.
setInterval(() => {
  if (document.visibilityState === "visible" && !$("cekim").classList.contains("acik"))
    fetch("/api/poz").catch(() => {});
}, 1000);

function ekran(ad) {
  for (const e of document.querySelectorAll(".ekran")) e.classList.toggle("acik", e.id === ad);
  // Kamera sadece çekim ekranındayken açık (gereksiz yere yayın çekmesin)
  $("canli").src = ad === "cekim" ? "/canli?ham=1&" + Date.now() : "";
}
function mesaj(yazi, tur) { $("mesaj").textContent = yazi; $("mesaj").className = "mesaj " + (yazi ? tur : ""); }

// Hoparlör: sunucudaki Türkçe ses, yoksa tarayıcının sesi
async function soyle(parametre) {
  try {
    if (calan) { calan.pause(); calan = null; }
    window.speechSynthesis?.cancel();
    const cevap = await fetch("/api/ses_cumle?" + new URLSearchParams(parametre));
    if ((cevap.headers.get("Content-Type") || "").startsWith("audio")) {
      calan = new Audio(URL.createObjectURL(await cevap.blob()));
      await calan.play();
    } else if (cevap.ok && window.speechSynthesis) {
      const soz = new SpeechSynthesisUtterance((await cevap.json()).metin);
      soz.lang = "tr-TR";
      speechSynthesis.speak(soz);
    }
  } catch (e) { /* ses çalınamazsa sessiz devam */ }
}

function formVerisi(ekler = {}) {
  const f = new FormData();
  f.append("numara", $("numara").value.trim());
  f.append("ad_soyad", $("ad").value.trim().replace(/\\s+/g, " "));
  f.append("kvkk", $("kvkk").checked ? "1" : "");
  for (const [k, v] of Object.entries(ekler)) f.append(k, v);
  return f;
}
async function postJson(adres, govde) {
  const cevap = await fetch(adres, { method: "POST", body: govde });
  if (cevap.status === 401) { location.href = "/giris"; throw new Error("oturum"); }
  return cevap.json();
}

// 1) Form -> kontrol -> çekim
$("basla").onclick = async () => {
  mesaj("");
  $("basla").disabled = true;
  try {
    const sonuc = await postJson("/api/kayit_kontrol", formVerisi());
    if (!sonuc.ok) { mesaj(sonuc.mesaj, "kotu"); return; }
    rehberliCekim(sonuc.ad_soyad, sonuc.foto_sayisi);
  } catch (e) {
    mesaj("Sunucuya ulaşılamadı.", "kotu");
  } finally {
    $("basla").disabled = false;
  }
};
$("ad").addEventListener("keydown", e => { if (e.key === "Enter") $("basla").click(); });
$("numara").addEventListener("keydown", e => { if (e.key === "Enter") $("ad").focus(); });
$("iptal").onclick = () => { iptal = true; };

// 2) Rehberli çekim: Düz -> bir yan -> diğer yan.
// Kamera aynalı olabilir; bu yüzden 2. adımda hangi yana dönülürse kabul edilir,
// 3. adımda diğer yan beklenir. Böylece "sağ/sol" karışıklığı kaydı bozmaz.
async function rehberliCekim(adSoyad, oncekiFoto) {
  iptal = false;
  ekran("cekim");
  for (let i = 0; i < 3; i++) $("adim" + i).className = "adim";
  let ilkYan = null, cekilen = 0;
  const ADIMLAR = [
    { talimat: "Kameraya düz bakın", cumle: "basla", ok: null },
    { talimat: "Başınızı yavaşça sağa çevirin", cumle: "sag", ok: "sag" },
    { talimat: "Şimdi yavaşça sola çevirin", cumle: "sol", ok: "sol" },
  ];

  for (let i = 0; i < ADIMLAR.length; i++) {
    const adim = ADIMLAR[i];
    const hedef = i === 0 ? ["duz"] : i === 1 ? ["sag", "sol"] : [ilkYan === "sag" ? "sol" : "sag"];
    $("adim" + i).className = "adim aktif";
    $("talimat").textContent = adim.talimat;
    $("ipucu").textContent = "";
    $("ok-sag").style.display = adim.ok === "sag" ? "block" : "none";
    $("ok-sol").style.display = adim.ok === "sol" ? "block" : "none";
    soyle({ anahtar: adim.cumle });
    await bekle(i === 0 ? 1500 : 900);   // talimat duyulsun

    const baslangic = Date.now();
    let sonIpucu = Date.now(), tutuyor = 0, tamam = false;
    while (!tamam) {
      if (iptal) return bitir(false, "Kayıt iptal edildi." + (cekilen ? ` ${cekilen} fotoğraf kaydedildi.` : ""));
      if (Date.now() - baslangic > ADIM_SURESI)
        return bitir(false, "Süre doldu. " + (cekilen ? `${cekilen} fotoğraf kaydedildi; ` : "") + "lütfen tekrar deneyin.");

      let poz = { yuz: 0 };
      try { poz = await (await fetch("/api/poz")).json(); } catch (e) {}
      const uygun = poz.yuz === 1 && hedef.includes(poz.yon);
      tutuyor = uygun ? tutuyor + 1 : 0;
      $("oval").classList.toggle("tutuyor", uygun);

      if (tutuyor >= 2) {   // aynı poz ~0.5 sn korunursa fotoğrafı çek
        const sonuc = await postJson("/api/kisi_ekle", formVerisi({ yon: poz.yon }));
        if (sonuc.ok) {
          if (i === 1) ilkYan = poz.yon;
          cekilen++;
          $("adim" + i).className = "adim bitti";
          $("oval").classList.remove("tutuyor");
          tamam = true;
          break;
        }
        if (["yuz_baska", "numara_baska", "kamera", "numara", "ad", "kvkk"].includes(sonuc.kod))
          return bitir(false, sonuc.mesaj);
        tutuyor = 0;   // kare kaçtıysa yeniden dene
      }

      // Uzun süre olmuyorsa yardımcı ol
      if (Date.now() - sonIpucu > 5000) {
        sonIpucu = Date.now();
        if (poz.yuz === 0) { $("ipucu").textContent = "Yüzünüz görünmüyor — kameraya yaklaşın."; soyle({ anahtar: "yuz_yok" }); }
        else if (poz.yuz > 1) { $("ipucu").textContent = "Karede sadece bir kişi olmalı."; }
        else if (i === 0) { $("ipucu").textContent = "Başınızı düz tutup doğrudan kameraya bakın."; soyle({ anahtar: "duz" }); }
        else { $("ipucu").textContent = "Biraz daha çevirin."; soyle({ anahtar: "biraz" }); }
      }
      await bekle(250);
    }
  }
  bitir(true, adSoyad, oncekiFoto + cekilen);
}

// 3) Sonuç
function bitir(basarili, metin, toplamFoto) {
  $("ok-sag").style.display = $("ok-sol").style.display = "none";
  if (!basarili) {
    ekran("form");
    mesaj(metin, "kotu");
    return;
  }
  // Kayıt tamamlandığı anda formu sıradaki öğrenci için temizle
  $("numara").value = ""; $("ad").value = ""; $("kvkk").checked = false;
  mesaj("");
  ekran("bitti");
  $("bitti-isim").textContent = metin;
  $("bitti-alt").textContent = `${toplamFoto} fotoğraf kaydedildi. Artık sınav girişinde yüzünüzle tanınacaksınız.`;
  soyle({ bitti: metin });
  const kapat = () => {
    if (!$("bitti").classList.contains("acik")) return;
    ekran("form");
    $("numara").focus();
  };
  setTimeout(kapat, 7000);
  $("bitti").onclick = kapat;   // beklemek istemeyen dokunup hemen yeni kayda geçebilir
}
</script>
</body></html>
"""


@app.route("/")
def ana_sayfa():
    return redirect("/tanima")


@app.route("/tanima")
def tanima():
    return render_template_string(SAYFA, sayfa="tanima")


@app.route("/kisiler")
def kisiler():
    return render_template_string(SAYFA, sayfa="kisiler", kvkk=KVKK_METNI)


# ---------- Canlı görüntü (tani.py'den aktarılır) ----------

@app.route("/canli")
def canli():
    # ?ham=1 -> isim kutuları çizilmemiş görüntü (kayıt ekranı bunu aynalayarak gösterir)
    try:
        if request.args.get("ham"):
            adres = f"{TANI}/ham"
        else:   # ?detay=1 -> yüzlerin üstünde tanıma mesafeleri (görevli ekranı)
            adres = f"{TANI}/canli" + ("?detay=1" if request.args.get("detay") else "")
        kaynak = urllib.request.urlopen(adres, timeout=10)
    except OSError:
        return "Tanıma servisi (tani.py) çalışmıyor", 503

    def akis():
        with kaynak:
            while parca := kaynak.read1(65536):
                yield parca
    return Response(akis(), content_type=kaynak.headers["Content-Type"])


# ---------- Kayıtlar ----------

@app.route("/api/kayitlar")
def api_kayitlar():
    with closing(db_ac()) as db:
        satirlar = db.execute("SELECT isim, ogrenci_no, zaman, foto, tur, sira FROM olaylar "
                              "WHERE zaman LIKE ? ORDER BY id DESC LIMIT 100",
                              (f"{date.today()}%",)).fetchall()
    return jsonify([{"isim": i, "no": n, "zaman": z, "foto": f, "tur": t, "sira": s}
                    for i, n, z, f, t, s in satirlar])


# ---------- Rehberli kayıt kiosku ----------

KAYIT_CUMLELERI = {   # kayıt ekranında hoparlörden okunan sabit cümleler
    "basla": "Kayıt başlıyor. Lütfen kameraya düz bakın.",
    "duz": "Lütfen kameraya düz bakın.",
    "sag": "Şimdi başınızı yavaşça sağa çevirin.",
    "sol": "Şimdi başınızı yavaşça sola çevirin.",
    "biraz": "Biraz daha çevirin.",
    "yuz_yok": "Yüzünüzü göremiyorum. Lütfen kameraya yaklaşın.",
    "tamam": "Tamam.",
    "kirp": "Lütfen gözlerinizi kırpın.",   # giriş kioskundaki canlılık kontrolü
}


@app.route("/kayit")
def kayit():
    return render_template_string(KAYIT_SAYFASI, kvkk=KVKK_METNI)


@app.route("/api/poz")
def api_poz():
    """Kameradaki yüzün baş yönü (tani.py'den). Çağrıldıkça tani.py kayıt modunda kalır."""
    try:
        with urllib.request.urlopen(f"{TANI}/poz", timeout=3) as cevap:
            return jsonify(json.load(cevap))
    except OSError:
        return jsonify(yuz=0, yon=None, oran=None, hata="Tanıma servisi çalışmıyor"), 503


@app.route("/api/izleme")
def api_izleme():
    """Canlı İzleme sayfası çağırır: ?test=1 iken tani.py olay yazmaz (3 sn'lik nabız).
    Ayrıca aktif sınav var mı söyler (sayfa açılınca test modunun varsayılanı buna göre seçilir)."""
    try:
        with urllib.request.urlopen(f"{TANI}/izleme" + ("?test=1" if request.args.get("test") else ""),
                                    timeout=2) as cevap:
            test_modu = json.load(cevap)["test_modu"]
    except (OSError, ValueError):
        test_modu = None
    with closing(db_ac()) as db:
        sinav = aktif_sinav(db)
    return jsonify(test_modu=test_modu, aktif_sinav=sinav[1] if sinav else None)


@app.route("/api/ses_cumle")
def api_ses_cumle():
    """?anahtar=sag gibi sabit bir kayıt cümlesi; ?bitti=Ad Soyad -> 'Kaydınız tamamlandı, Ad Soyad.'"""
    bitti = " ".join(request.args.get("bitti", "").split())
    if bitti:
        if not ad_soyad_gecerli(bitti):
            return "", 400
        metin = f"Kaydınız tamamlandı, {bitti}. Teşekkürler."
    else:
        metin = KAYIT_CUMLELERI.get(request.args.get("anahtar", ""))
        if metin is None:
            return "", 404
    wav = ses.konus(metin)
    if wav is None:
        return jsonify(metin=metin)   # ses motoru yok: metni ver, tarayıcı kendi sesiyle okusun
    return Response(wav, mimetype="audio/wav")


@app.route("/api/gunu_sifirla", methods=["POST"])
def api_gunu_sifirla():
    """Bugünkü giriş kayıtlarını ve fotoğraflarını siler (demo/prova öncesi temiz başlangıç)."""
    with closing(db_ac()) as db:
        bugun = f"{date.today()}%"
        fotolar = [f for (f,) in db.execute("SELECT foto FROM olaylar WHERE zaman LIKE ?", (bugun,))]
        db.execute("DELETE FROM olaylar WHERE zaman LIKE ?", (bugun,))
        db.commit()
    for foto in fotolar:
        if foto and os.path.exists(f"static/{foto}"):
            os.remove(f"static/{foto}")
    return jsonify(ok=True, mesaj=f"Bugünkü {len(fotolar)} kayıt silindi.")


# ---------- Kiosk (kapıdaki giriş ekranı) ----------

def olay_mesaji(db, olay_id, isim, numara, tur, sira, sinav_id):
    """Kiosk ekranında görünecek ve hoparlörden okunacak mesaj."""
    if tur == "giris":
        if sira:
            return {"baslik": "Hoş geldiniz", "alt": f"Sıra No {sira}",
                    "soz": f"Hoş geldin {isim}. Sıra numaran {sira}."}
        return {"baslik": "Hoş geldiniz", "alt": "Salon dolu, görevliye başvurun",
                "soz": f"Hoş geldin {isim}. Salon dolu, lütfen görevliye başvur."}
    if tur == "tekrar":
        # İlk girişin saati: aynı sınavda (ya da serbest modda aynı gün) yapılan ilk giriş
        if sinav_id:
            kapsam, deger = "sinav_id = ?", sinav_id
        else:
            kapsam, deger = "sinav_id IS NULL AND zaman LIKE ?", f"{date.today()}%"
        ilk = db.execute(f"SELECT zaman FROM olaylar WHERE ogrenci_no = ? AND tur = 'giris' "
                         f"AND id < ? AND {kapsam} ORDER BY id LIMIT 1",
                         (numara, olay_id, deger)).fetchone()
        saat = ilk[0][11:16] if ilk else "?"
        return {"baslik": "Zaten giriş yaptınız",
                "alt": f"Saat {saat}" + (f" · Sıra No {sira}" if sira else ""),
                "soz": f"{isim}, zaten giriş yaptın." + (f" Sıra numaran {sira}." if sira else "")}
    if tur == "listede_yok":
        return {"baslik": "Bu sınava kaydınız yok", "alt": "Lütfen görevliye başvurun",
                "soz": f"{isim}, bu sınava kaydınız yok. Lütfen görevliye başvurun."}
    if tur in ("erken", "gec") and sinav_id:
        with_z = sinav_zamani_getir(db, sinav_id)
        if tur == "erken":
            return {"baslik": "Giriş henüz açılmadı", "alt": f"Giriş açılışı: {with_z['acilis']:%H:%M}",
                    "soz": f"{isim}, sınav girişi henüz açılmadı. Lütfen daha sonra gelin."}
        return {"baslik": "Giriş kapandı", "alt": f"Sınav başladı ({with_z['baslangic']:%H:%M}) · Görevliye başvurun",
                "soz": f"{isim}, sınav başladı ve giriş kapandı. Lütfen görevliye başvurun."}
    if tur == "canlilik_yok":
        return {"baslik": "Canlılık doğrulanamadı", "alt": "Fotoğraf ya da ekran kabul edilmez · Görevliye başvurun",
                "soz": "Canlılık doğrulanamadı. Lütfen görevliye başvurun."}
    # Sistemde hiç kaydı olmayan kişi (yüzü tanınmadı): sınavdan bahsetme, önce kayıt olsun.
    # "Bu sınava kaydınız yok" sadece kayıtlı olup sınav listesinde olmayana söylenir (yukarıda).
    return {"baslik": "Kaydınız yok", "alt": "Önce kayıt olun · Görevliye başvurun",
            "soz": "Kaydınız yok. Lütfen önce kayıt olun."}


def olay_getir(db, olay_id):
    satir = db.execute("SELECT id, isim, ogrenci_no, tur, sira, sinav_id FROM olaylar WHERE id = ?",
                       (olay_id,)).fetchone()
    if satir is None:
        return None
    oid, isim, numara, tur, sira, sinav_id = satir
    return {"id": oid, "isim": isim, "no": numara, "tur": tur, "sira": sira,
            **olay_mesaji(db, oid, isim, numara, tur, sira, sinav_id)}


@app.route("/kiosk")
def kiosk():
    return render_template_string(KIOSK_SAYFASI)


@app.route("/api/olaylar")
def api_olaylar():
    """?son=<id> -> o id'den sonraki olaylar. son verilmezse sadece en son id döner
    (kiosk açıldığında eski olayları tekrar göstermesin diye)."""
    with closing(db_ac()) as db:
        otomatik_sinav_durumu(db)
        sinav = aktif_sinav(db)
        sinav_adi = sinav[1] if sinav else None   # kiosk başlığında gösterilir
        pencere = None
        if sinav:   # kiosk başlığındaki geri sayım için
            b = sinav_bul(db, sinav[0])
            pencere = {k: b[k] for k in ("pencere", "acilis_saat", "kapanis_saat", "acilisa_sn", "kapanisa_sn")}
        en_son = db.execute("SELECT COALESCE(MAX(id), 0) FROM olaylar").fetchone()[0]
        son = request.args.get("son", type=int)
        if son is None:
            olaylar = None
        else:
            idler = [i for (i,) in db.execute("SELECT id FROM olaylar WHERE id > ? AND zaman LIKE ? "
                                              "ORDER BY id LIMIT 10", (son, f"{date.today()}%"))]
            olaylar = [olay_getir(db, i) for i in idler]
    # Göz kırpması beklenen biri var mı? (tani.py'den)
    try:
        with urllib.request.urlopen(f"{TANI}/canlilik", timeout=0.5) as cevap:
            canlilik = json.load(cevap)
    except (OSError, ValueError):
        canlilik = {"bekliyor": False}
    return jsonify(son=en_son, olaylar=olaylar or [], sinav=sinav_adi, pencere=pencere, canlilik=canlilik)


@app.route("/api/ses/<int:olay_id>")
def api_ses(olay_id):
    with closing(db_ac()) as db:
        olay = olay_getir(db, olay_id)
    if olay is None:
        return "", 404
    wav = ses.konus(olay["soz"])
    if wav is None:   # ses motoru kurulu değil; kiosk tarayıcının sesini dener
        return "", 204
    return Response(wav, mimetype="audio/wav")


# ---------- Öğrenciler ----------

@app.route("/api/kisiler")
def api_kisiler():
    with closing(db_ac()) as db:
        ogrenciler = db.execute("SELECT ogrenci_no, ad_soyad FROM ogrenciler "
                                "ORDER BY ad_soyad COLLATE NOCASE").fetchall()
    dosyalar = ogrenci_dosyalari()
    return jsonify([{"no": no, "ad_soyad": ad, "sayi": len(dosyalar.get(no, [])),
                     "foto": dosyalar.get(no, [None])[0]} for no, ad in ogrenciler])


@app.route("/kisi_foto/<path:dosya>")
def kisi_foto(dosya):
    return send_from_directory(os.path.abspath(KISILER), dosya)   # çalışılan klasöre göre (kodun geri kalanı gibi)


def form_kontrol():
    """Numara, ad soyad ve KVKK onayını kontrol eder.
    Döner: (numara, ad_soyad, kayitli_ad, hata_cevabı ya da None)"""
    numara = request.form.get("numara", "").strip()
    ad_soyad = " ".join(request.form.get("ad_soyad", "").split())
    hata = None
    kayitli_ad = None
    if not numara_gecerli(numara):
        hata = dict(kod="numara", mesaj="Öğrenci numarası sadece rakamlardan oluşmalı.")
    elif not ad_soyad_gecerli(ad_soyad):
        hata = dict(kod="ad", mesaj="Ad ve soyadı harflerle, aralarında boşluk bırakarak yazın (ör. Ayşe Yılmaz).")
    elif request.form.get("kvkk") != "1":
        hata = dict(kod="kvkk", mesaj="Kayıt için onay kutusunun işaretlenmesi gerekiyor.")
    else:
        kayitli_ad = ogrenci_bul(numara)
        if kayitli_ad and kayitli_ad.casefold() != ad_soyad.casefold():
            hata = dict(kod="numara_baska", mesaj=f"{numara} numarası {kayitli_ad} adına kayıtlı. "
                                                  "Numarayı kontrol edin.")
    return numara, ad_soyad, kayitli_ad, (jsonify(ok=False, **hata) if hata else None)


@app.route("/api/kayit_kontrol", methods=["POST"])
def api_kayit_kontrol():
    """Rehberli kayıt başlamadan önce formu kontrol eder (fotoğraf çekmez)."""
    numara, ad_soyad, kayitli_ad, hata = form_kontrol()
    if hata:
        return hata
    return jsonify(ok=True, ad_soyad=kayitli_ad or ad_soyad,
                   foto_sayisi=len(ogrenci_dosyalari().get(numara, [])))


YONLER = ("duz", "sag", "sol")


@app.route("/api/kisi_ekle", methods=["POST"])
def api_kisi_ekle():
    numara, ad_soyad, kayitli_ad, hata = form_kontrol()
    if hata:
        return hata

    yuklenen = request.files.get("foto")
    yon = request.form.get("yon")   # rehberli kayıt: o yöne bakarken yakalanan kare istenir
    if yuklenen:
        veri = yuklenen.read()
    else:
        adres = f"{TANI}/kare" + (f"?yon={yon}" if yon in YONLER else "")
        try:
            with urllib.request.urlopen(adres, timeout=5) as cevap:
                veri = cevap.read()
        except urllib.error.HTTPError:
            return jsonify(ok=False, kod="poz", mesaj="Uygun kare yakalanamadı, tekrar deneniyor.")
        except OSError:
            return jsonify(ok=False, kod="kamera", mesaj="Kameradan görüntü alınamadı. tani.py çalışıyor mu?")

    kare = cv2.imdecode(np.frombuffer(veri, np.uint8), cv2.IMREAD_COLOR)
    if kare is None:
        return jsonify(ok=False, mesaj="Fotoğraf okunamadı (JPG veya PNG olmalı).")
    olcek = 1600 / max(kare.shape[:2])
    if olcek < 1:   # telefon fotoğrafları çok büyük; küçültünce yüz bulma hızlanır
        kare = cv2.resize(kare, None, fx=olcek, fy=olcek)

    with kilit:
        rgb = cv2.cvtColor(kare, cv2.COLOR_BGR2RGB)
        konumlar = face_recognition.face_locations(rgb)
        if len(konumlar) != 1:
            neden = "Yüz bulunamadı" if not konumlar else f"{len(konumlar)} yüz bulundu"
            return jsonify(ok=False, kod="yuz_sayisi",
                           mesaj=f"{neden}. Karede tam olarak bir yüz olmalı, tekrar deneyin.")
        kod = face_recognition.face_encodings(rgb, konumlar)[0]
        numaralar, kodlar = yuzleri_oku()

        # Aynı kişi iki farklı numarayla kaydolamasın
        if kodlar:
            mesafeler = face_recognition.face_distance(kodlar, kod)
            en_iyi = int(np.argmin(mesafeler))
            if mesafeler[en_iyi] < TOLERANS and numaralar[en_iyi] != numara:
                diger = numaralar[en_iyi]
                return jsonify(ok=False, kod="yuz_baska",
                               mesaj=f"Bu yüz zaten {ogrenci_bul(diger) or '?'} ({diger}) "
                                     "adına kayıtlı. Bir kişi tek numarayla kaydolabilir.")

        # Önce öğrenciyi veritabanına, sonra fotoğrafı ve yüzü kaydet
        # (tani.py yuzler.pkl değişince adları veritabanından okur)
        if not kayitli_ad:
            simdi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with closing(db_ac()) as db:
                db.execute("INSERT INTO ogrenciler (ogrenci_no, ad_soyad, kvkk_onay, kayit_zamani) "
                           "VALUES (?, ?, ?, ?)", (numara, ad_soyad, simdi, simdi))
                db.commit()

        dosyalar = ogrenci_dosyalari().get(numara, [])
        siralar = [int(s) for d in dosyalar
                   if (s := os.path.splitext(d)[0].partition("_")[2]).isdigit()]
        sira = max(siralar, default=0) + 1
        cv2.imwrite(f"{KISILER}/{numara}_{sira}.jpg", kare)
        yuzleri_yaz(numaralar + [numara], kodlar + [kod])

    ad = kayitli_ad or ad_soyad
    sayi = len(dosyalar) + 1
    ek = " Birkaç farklı açıdan daha çekmeniz önerilir." if sayi < 3 else ""
    return jsonify(ok=True, sayi=sayi, mesaj=f"{ad} ({numara}) için {sayi}. fotoğraf kaydedildi.{ek}")


# ---------- Öğrenci düzenleme ----------

def ogrenci_kodlarini_yenile(numara, numaralar, kodlar):
    """Bir öğrencinin yüz kodlarını kisiler/ klasöründeki fotoğraflarından yeniden hesapla."""
    yeni = []
    for dosya in ogrenci_dosyalari().get(numara, []):
        bulunan = face_recognition.face_encodings(face_recognition.load_image_file(f"{KISILER}/{dosya}"))
        if len(bulunan) == 1:
            yeni.append(bulunan[0])
    kalan = [(n, k) for n, k in zip(numaralar, kodlar) if n != numara]
    return [n for n, _ in kalan] + [numara] * len(yeni), [k for _, k in kalan] + yeni


@app.route("/api/ogrenci/<numara>")
def api_ogrenci(numara):
    with closing(db_ac()) as db:
        satir = db.execute("SELECT ogrenci_no, ad_soyad, kvkk_onay, kayit_zamani FROM ogrenciler "
                           "WHERE ogrenci_no = ?", (numara,)).fetchone()
    if satir is None:
        return jsonify(ok=False, mesaj=f"{numara} numaralı öğrenci bulunamadı.")
    no, ad, kvkk, kayit = satir
    return jsonify(ok=True, no=no, ad_soyad=ad, kvkk_onay=kvkk, kayit_zamani=kayit,
                   fotolar=ogrenci_dosyalari().get(no, []))


@app.route("/api/ogrenci/<numara>/duzenle", methods=["POST"])
def api_ogrenci_duzenle(numara):
    yeni_no = request.form.get("yeni_numara", "").strip()
    ad_soyad = " ".join(request.form.get("ad_soyad", "").split())
    if not numara_gecerli(yeni_no):
        return jsonify(ok=False, mesaj="Öğrenci numarası sadece rakamlardan oluşmalı.")
    if not ad_soyad_gecerli(ad_soyad):
        return jsonify(ok=False, mesaj="Ad ve soyadı harflerle, aralarında boşluk bırakarak yazın (ör. Ayşe Yılmaz).")
    with kilit:
        eski_ad = ogrenci_bul(numara)
        if eski_ad is None:
            return jsonify(ok=False, mesaj=f"{numara} numaralı öğrenci bulunamadı.")
        if yeni_no == numara and ad_soyad == eski_ad:
            return jsonify(ok=True, no=numara, mesaj="Değişiklik yok.")
        dosyalar = ogrenci_dosyalari()
        if yeni_no != numara:
            if ogrenci_bul(yeni_no) is not None:
                return jsonify(ok=False, mesaj=f"{yeni_no} numarası başka bir öğrenciye ait ({ogrenci_bul(yeni_no)}).")
            if yeni_no in dosyalar:
                return jsonify(ok=False, mesaj=f"kisiler/ klasöründe {yeni_no} numaralı sahipsiz fotoğraflar var; "
                                               "önce onları kaldırın.")
        # 1) Veritabanı: öğrenci, sınav listeleri ve geçmiş girişler
        with closing(db_ac()) as db:
            db.execute("UPDATE ogrenciler SET ogrenci_no = ?, ad_soyad = ? WHERE ogrenci_no = ?",
                       (yeni_no, ad_soyad, numara))
            db.execute("UPDATE sinav_ogrencileri SET ogrenci_no = ? WHERE ogrenci_no = ?", (yeni_no, numara))
            db.execute("UPDATE olaylar SET ogrenci_no = ?, isim = ? WHERE ogrenci_no = ?",
                       (yeni_no, ad_soyad, numara))
            db.commit()
        # 2) Fotoğraf dosyaları: 12345_1.jpg -> 67890_1.jpg
        if yeni_no != numara:
            for dosya in dosyalar.get(numara, []):
                os.rename(f"{KISILER}/{dosya}", f"{KISILER}/{yeni_no}{dosya[len(numara):]}")
        # 3) Yüz kayıtları (tani.py bu dosya değişince adları da yeniden okur)
        numaralar, kodlar = yuzleri_oku()
        yuzleri_yaz([yeni_no if n == numara else n for n in numaralar], kodlar)
    degisen = [x for x, var in (("numara", yeni_no != numara), ("ad soyad", ad_soyad != eski_ad)) if var]
    return jsonify(ok=True, no=yeni_no, mesaj=f"{ad_soyad} ({yeni_no}) güncellendi: {' ve '.join(degisen)}.")


@app.route("/api/ogrenci/<numara>/foto_sil", methods=["POST"])
def api_ogrenci_foto_sil(numara):
    dosya = os.path.basename(request.form.get("dosya", ""))
    with kilit:
        fotolar = ogrenci_dosyalari().get(numara, [])
        if dosya not in fotolar:
            return jsonify(ok=False, mesaj="Fotoğraf bulunamadı.")
        if len(fotolar) < 2:
            return jsonify(ok=False, mesaj="Son fotoğraf silinemez; önce yeni fotoğraf ekleyin.")
        os.remove(f"{KISILER}/{dosya}")
        numaralar, kodlar = ogrenci_kodlarini_yenile(numara, *yuzleri_oku())
        yuzleri_yaz(numaralar, kodlar)
    kalan = ogrenci_dosyalari().get(numara, [])
    return jsonify(ok=True, fotolar=kalan, mesaj=f"Fotoğraf silindi, {len(kalan)} fotoğraf kaldı.")


@app.route("/api/kisi_sil", methods=["POST"])
def api_kisi_sil():
    numara = request.form.get("numara", "").strip()
    with kilit:
        ad = ogrenci_bul(numara)
        if ad is None:
            return jsonify(ok=False, mesaj=f"{numara} numaralı kayıtlı öğrenci yok.")
        for dosya in ogrenci_dosyalari().get(numara, []):
            os.remove(f"{KISILER}/{dosya}")
        numaralar, kodlar = yuzleri_oku()
        kalan = [(n, k) for n, k in zip(numaralar, kodlar) if n != numara]
        with closing(db_ac()) as db:
            db.execute("DELETE FROM ogrenciler WHERE ogrenci_no = ?", (numara,))
            db.execute("DELETE FROM sinav_ogrencileri WHERE ogrenci_no = ?", (numara,))
            db.commit()
        yuzleri_yaz([n for n, _ in kalan], [k for _, k in kalan])
    return jsonify(ok=True, mesaj=f"{ad} ({numara}) ve fotoğrafları silindi.")


# ---------- Sınavlar ve yoklama ----------

DURUM_ADLARI = {"hazir": "Hazır", "aktif": "Aktif", "bitti": "Bitti"}


def zaman_bilgisi(tarih, saat, sure, acilis, gec):
    """Ekranlarda gösterilecek saatler: '14:30', '15:00', '16:00' ve giriş penceresinin durumu."""
    z = sinav_zamani(tarih, saat, sure, acilis, gec)
    saat_yaz = lambda t: t.strftime("%H:%M")
    return {"acilis_saat": saat_yaz(z["acilis"]), "baslangic_saat": saat_yaz(z["baslangic"]),
            "kapanis_saat": saat_yaz(z["kapanis"]), "bitis_saat": saat_yaz(z["bitis"]),
            "pencere": giris_durumu(z),
            "acilisa_sn": int((z["acilis"] - datetime.now()).total_seconds()),
            "kapanisa_sn": int((z["kapanis"] - datetime.now()).total_seconds()),
            "bitise_sn": int((z["bitis"] - datetime.now()).total_seconds())}


def sinav_bul(db, sinav_id):
    satir = db.execute("SELECT id, ad, tarih, saat, koltuk_sayisi, durum, baslama, bitis, "
                       "sure_dk, acilis_dk, gec_dk FROM sinavlar WHERE id = ?", (sinav_id,)).fetchone()
    if satir is None:
        return None
    anahtarlar = ("id", "ad", "tarih", "saat", "koltuk", "durum", "baslama", "bitis", "sure", "acilis", "gec")
    sinav = dict(zip(anahtarlar, satir))
    sinav.update(zaman_bilgisi(sinav["tarih"], sinav["saat"], sinav["sure"], sinav["acilis"], sinav["gec"]))
    return sinav


def yoklama(db, sinav_id):
    """Sınav listesindeki her öğrenci için ilk giriş bilgisi + listede olmayan girişimler."""
    liste = db.execute("SELECT so.ogrenci_no, COALESCE(o.ad_soyad, '(silinmiş öğrenci)') "
                       "FROM sinav_ogrencileri so LEFT JOIN ogrenciler o USING (ogrenci_no) "
                       "WHERE so.sinav_id = ? ORDER BY o.ad_soyad COLLATE NOCASE",
                       (sinav_id,)).fetchall()
    girisler = {}
    for numara, zaman, sira, foto, aciklama in db.execute(
            "SELECT ogrenci_no, zaman, sira, foto, aciklama FROM olaylar WHERE sinav_id = ? AND tur = 'giris' "
            "ORDER BY id", (sinav_id,)):
        girisler.setdefault(numara, (zaman, sira, foto, aciklama))
    gelenler, gelmeyenler = [], []
    for numara, ad in liste:
        if numara in girisler:
            zaman, sira, foto, aciklama = girisler[numara]
            gelenler.append({"no": numara, "ad": ad, "saat": zaman[11:19], "sira": sira, "foto": foto,
                             "aciklama": aciklama})
        else:
            gelmeyenler.append({"no": numara, "ad": ad})
    gelenler.sort(key=lambda g: g["saat"])
    diger = [{"tur": t, "isim": i, "no": n, "saat": z[11:19], "foto": f} for t, i, n, z, f in db.execute(
        "SELECT tur, isim, ogrenci_no, zaman, foto FROM olaylar WHERE sinav_id = ? "
        "AND tur IN ('listede_yok', 'bilinmeyen', 'tekrar', 'canlilik_yok', 'erken', 'gec') "
        "ORDER BY id DESC LIMIT 50", (sinav_id,))]
    return gelenler, gelmeyenler, diger


def secilen_ogrenciler(db):
    """Formdan gelen öğrenci numaralarını kayıtlı öğrencilerle süzer."""
    kayitli = {n for (n,) in db.execute("SELECT ogrenci_no FROM ogrenciler")}
    return sorted({n for n in request.form.getlist("ogrenciler") if n in kayitli})


@app.route("/sinavlar")
def sinavlar_sayfasi():
    return render_template_string(SINAV_SAYFASI, sayfa="liste", bugun=str(date.today()))


@app.route("/sinav/<int:sinav_id>")
def sinav_sayfasi(sinav_id):
    with closing(db_ac()) as db:
        if sinav_bul(db, sinav_id) is None:
            return redirect("/sinavlar")
    return render_template_string(SINAV_SAYFASI, sayfa="yoklama", sinav_id=sinav_id)


@app.route("/api/sinavlar")
def api_sinavlar():
    with closing(db_ac()) as db:
        otomatik_sinav_durumu(db)
        satirlar = db.execute(
            "SELECT s.id, s.ad, s.tarih, s.saat, s.koltuk_sayisi, s.durum, s.sure_dk, s.acilis_dk, s.gec_dk, "
            "(SELECT COUNT(*) FROM sinav_ogrencileri so WHERE so.sinav_id = s.id), "
            "(SELECT COUNT(DISTINCT ogrenci_no) FROM olaylar o WHERE o.sinav_id = s.id AND o.tur = 'giris') "
            "FROM sinavlar s ORDER BY s.tarih DESC, s.saat DESC, s.id DESC").fetchall()
        ogrenciler = db.execute("SELECT ogrenci_no, ad_soyad FROM ogrenciler "
                                "ORDER BY ad_soyad COLLATE NOCASE").fetchall()
    return jsonify(
        sinavlar=[{"id": i, "ad": a, "tarih": t, "saat": s, "koltuk": k, "durum": d,
                   "durum_adi": DURUM_ADLARI.get(d, d), "toplam": top, "gelen": gel,
                   **zaman_bilgisi(t, s, sure, acilis, gec)}
                  for i, a, t, s, k, d, sure, acilis, gec, top, gel in satirlar],
        ogrenciler=[{"no": n, "ad": a} for n, a in ogrenciler])


@app.route("/api/sinav_olustur", methods=["POST"])
def api_sinav_olustur():
    ad = " ".join(request.form.get("ad", "").split())
    tarih = request.form.get("tarih", "")
    saat = request.form.get("saat", "")
    koltuk = request.form.get("koltuk", type=int)
    sure = request.form.get("sure", 60, type=int)
    acilis = request.form.get("acilis", 30, type=int)
    gec = request.form.get("gec", 0, type=int)
    if not 1 <= len(ad) <= 60:
        return jsonify(ok=False, mesaj="Sınava bir ad verin (en fazla 60 karakter).")
    try:
        datetime.strptime(f"{tarih} {saat}", "%Y-%m-%d %H:%M")
    except ValueError:
        return jsonify(ok=False, mesaj="Tarih ve saati seçin.")
    if koltuk is None or not 1 <= koltuk <= 500:
        return jsonify(ok=False, mesaj="Sıra sayısı 1 ile 500 arasında olmalı.")
    if sure is None or not 5 <= sure <= 600:
        return jsonify(ok=False, mesaj="Sınav süresi 5 ile 600 dakika arasında olmalı.")
    if acilis is None or not 0 <= acilis <= 240:
        return jsonify(ok=False, mesaj="Giriş açılışı 0 ile 240 dakika arasında olmalı.")
    if gec is None or not 0 <= gec < sure:
        return jsonify(ok=False, mesaj="Geç giriş toleransı 0 ile sınav süresi arasında olmalı.")
    with closing(db_ac()) as db:
        ogrenciler = secilen_ogrenciler(db)
        if not ogrenciler:
            return jsonify(ok=False, mesaj="Sınava girecek en az bir öğrenci seçin.")
        if koltuk < len(ogrenciler):
            return jsonify(ok=False, mesaj=f"{len(ogrenciler)} öğrenci seçildi ama salonda {koltuk} sıra var. "
                                           "Sıra sayısını artırın.")
        sinav_id = db.execute("INSERT INTO sinavlar (ad, tarih, saat, koltuk_sayisi, sure_dk, acilis_dk, gec_dk) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?)", (ad, tarih, saat, koltuk, sure, acilis, gec)).lastrowid
        db.executemany("INSERT INTO sinav_ogrencileri VALUES (?, ?)", [(sinav_id, n) for n in ogrenciler])
        db.commit()
    return jsonify(ok=True, id=sinav_id, mesaj=f"\"{ad}\" oluşturuldu ({len(ogrenciler)} öğrenci).")


@app.route("/api/sinav/<int:sinav_id>")
def api_sinav(sinav_id):
    with closing(db_ac()) as db:
        otomatik_sinav_durumu(db)
        sinav = sinav_bul(db, sinav_id)
        if sinav is None:
            return jsonify(ok=False, mesaj="Sınav bulunamadı."), 404
        gelenler, gelmeyenler, diger = yoklama(db, sinav_id)
        liste = {n for (n,) in db.execute("SELECT ogrenci_no FROM sinav_ogrencileri WHERE sinav_id = ?",
                                          (sinav_id,))}
        ogrenciler = [{"no": n, "ad": a, "secili": n in liste} for n, a in db.execute(
            "SELECT ogrenci_no, ad_soyad FROM ogrenciler ORDER BY ad_soyad COLLATE NOCASE")]
    return jsonify(ok=True, sinav={**sinav, "durum_adi": DURUM_ADLARI.get(sinav["durum"])},
                   gelenler=gelenler, gelmeyenler=gelmeyenler, diger=diger, ogrenciler=ogrenciler)


@app.route("/api/sinav/<int:sinav_id>/durum", methods=["POST"])
def api_sinav_durum(sinav_id):
    islem = request.form.get("islem")
    simdi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with closing(db_ac()) as db:
        sinav = sinav_bul(db, sinav_id)
        if sinav is None:
            return jsonify(ok=False, mesaj="Sınav bulunamadı.")
        if islem == "baslat":
            if datetime.now() >= sinav_zamani_getir(db, sinav_id)["bitis"]:
                return jsonify(ok=False, mesaj="Bu sınavın süresi dolmuş. Demo için \"Demo\" butonunu "
                                               "kullanın ya da yeni bir sınav oluşturun.")
            diger = aktif_sinav(db)
            if diger and diger[0] != sinav_id:
                return jsonify(ok=False, mesaj=f"Önce aktif sınavı bitirin: \"{diger[1]}\". "
                                               "Aynı anda tek sınav aktif olabilir.")
            db.execute("UPDATE sinavlar SET durum = 'aktif', baslama = COALESCE(baslama, ?), bitis = NULL "
                       "WHERE id = ?", (simdi, sinav_id))
            mesaj = f"\"{sinav['ad']}\" başladı. Kiosk artık bu sınavın listesine göre giriş alıyor."
        elif islem == "bitir":
            db.execute("UPDATE sinavlar SET durum = 'bitti', bitis = ? WHERE id = ?", (simdi, sinav_id))
            mesaj = f"\"{sinav['ad']}\" bitti. Kiosk serbest moda döndü."
        else:
            return jsonify(ok=False, mesaj="Geçersiz işlem.")
        db.commit()
    return jsonify(ok=True, mesaj=mesaj)


@app.route("/api/sinav/<int:sinav_id>/demo", methods=["POST"])
def api_sinav_demo(sinav_id):
    """Sunum/prova kısayolu: sınavı bugün, 10 dakika sonra başlayacak şekilde ayarla ve başlat.
    Böylece giriş penceresi hemen açılır (açılış süresi 10 dakikadan uzunsa) ve kiosk denenebilir."""
    with closing(db_ac()) as db:
        sinav = sinav_bul(db, sinav_id)
        if sinav is None:
            return jsonify(ok=False, mesaj="Sınav bulunamadı.")
        diger = aktif_sinav(db)
        if diger and diger[0] != sinav_id:
            return jsonify(ok=False, mesaj=f"Önce aktif sınavı bitirin: \"{diger[1]}\".")
        basla = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=10)
        acilis = max(sinav["acilis"], 15)   # giriş şimdiden açık olsun
        db.execute("UPDATE sinavlar SET tarih = ?, saat = ?, acilis_dk = ?, durum = 'aktif', "
                   "baslama = ?, bitis = NULL WHERE id = ?",
                   (basla.strftime("%Y-%m-%d"), basla.strftime("%H:%M"), acilis,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sinav_id))
        db.commit()
    return jsonify(ok=True, mesaj=f"Demo: \"{sinav['ad']}\" sınavının başlangıcı {basla:%H:%M} yapıldı; "
                                  "giriş şu an açık.")


@app.route("/api/sinav/<int:sinav_id>/elle_giris", methods=["POST"])
def api_sinav_elle_giris(sinav_id):
    """Görevli onayıyla giriş: geç kalan (mazeretli) ya da kameranın tanıyamadığı öğrenci için."""
    numara = request.form.get("numara", "").strip()
    with closing(db_ac()) as db:
        sinav = sinav_bul(db, sinav_id)
        if sinav is None:
            return jsonify(ok=False, mesaj="Sınav bulunamadı.")
        ad = ogrenci_bul(numara)
        if ad is None or not db.execute("SELECT 1 FROM sinav_ogrencileri WHERE sinav_id = ? AND ogrenci_no = ?",
                                        (sinav_id, numara)).fetchone():
            return jsonify(ok=False, mesaj="Bu öğrenci sınav listesinde değil.")
        if db.execute("SELECT 1 FROM olaylar WHERE sinav_id = ? AND ogrenci_no = ? AND tur = 'giris'",
                      (sinav_id, numara)).fetchone():
            return jsonify(ok=False, mesaj=f"{ad} zaten giriş yapmış.")
        sira = bos_sira_sec(db, "sinav_id = ?", sinav_id, sinav["koltuk"])
        db.execute("INSERT INTO olaylar (isim, ogrenci_no, zaman, foto, tur, sira, sinav_id, aciklama) "
                   "VALUES (?, ?, ?, NULL, 'giris', ?, ?, 'Görevli onayıyla')",
                   (ad, numara, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sira, sinav_id))
        db.commit()
    return jsonify(ok=True, mesaj=f"{ad} görevli onayıyla içeri alındı" + (f", sıra {sira}." if sira else "."))


@app.route("/api/sinav/<int:sinav_id>/ogrenciler", methods=["POST"])
def api_sinav_ogrencileri(sinav_id):
    with closing(db_ac()) as db:
        sinav = sinav_bul(db, sinav_id)
        if sinav is None:
            return jsonify(ok=False, mesaj="Sınav bulunamadı.")
        ogrenciler = secilen_ogrenciler(db)
        if not ogrenciler:
            return jsonify(ok=False, mesaj="En az bir öğrenci seçin.")
        if sinav["koltuk"] < len(ogrenciler):
            return jsonify(ok=False, mesaj=f"Salonda {sinav['koltuk']} sıra var, {len(ogrenciler)} öğrenci seçildi.")
        db.execute("DELETE FROM sinav_ogrencileri WHERE sinav_id = ?", (sinav_id,))
        db.executemany("INSERT INTO sinav_ogrencileri VALUES (?, ?)", [(sinav_id, n) for n in ogrenciler])
        db.commit()
    return jsonify(ok=True, mesaj=f"Liste güncellendi: {len(ogrenciler)} öğrenci.")


def sinav_olaylarini_sil(db, sinav_id):
    fotolar = [f for (f,) in db.execute("SELECT foto FROM olaylar WHERE sinav_id = ?", (sinav_id,))]
    db.execute("DELETE FROM olaylar WHERE sinav_id = ?", (sinav_id,))
    for foto in fotolar:
        if foto and os.path.exists(f"static/{foto}"):
            os.remove(f"static/{foto}")
    return len(fotolar)


@app.route("/api/sinav/<int:sinav_id>/sifirla", methods=["POST"])
def api_sinav_sifirla(sinav_id):
    """Sınavın giriş kayıtlarını siler (prova sonrası temiz başlangıç). Öğrenci listesi kalır."""
    with closing(db_ac()) as db:
        sayi = sinav_olaylarini_sil(db, sinav_id)
        db.commit()
    return jsonify(ok=True, mesaj=f"Yoklama sıfırlandı ({sayi} kayıt silindi).")


@app.route("/api/sinav/<int:sinav_id>/sil", methods=["POST"])
def api_sinav_sil(sinav_id):
    with closing(db_ac()) as db:
        sinav = sinav_bul(db, sinav_id)
        if sinav is None:
            return jsonify(ok=False, mesaj="Sınav bulunamadı.")
        sinav_olaylarini_sil(db, sinav_id)
        db.execute("DELETE FROM sinav_ogrencileri WHERE sinav_id = ?", (sinav_id,))
        db.execute("DELETE FROM sinavlar WHERE id = ?", (sinav_id,))
        db.commit()
    return jsonify(ok=True, mesaj=f"\"{sinav['ad']}\" silindi.")


@app.route("/sinav/<int:sinav_id>/excel")
def sinav_excel(sinav_id):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    with closing(db_ac()) as db:
        sinav = sinav_bul(db, sinav_id)
        if sinav is None:
            return redirect("/sinavlar")
        gelenler, gelmeyenler, _ = yoklama(db, sinav_id)
        olaylar = db.execute("SELECT zaman, tur, isim, ogrenci_no, sira FROM olaylar WHERE sinav_id = ? "
                             "ORDER BY id", (sinav_id,)).fetchall()

    kitap = Workbook()
    sayfa = kitap.active
    sayfa.title = "Yoklama"
    kalin = Font(bold=True)
    sayfa.append([sinav["ad"]])
    sayfa["A1"].font = Font(bold=True, size=14)
    sayfa.append([f"Tarih: {sinav['tarih']}  Sınav: {sinav['baslangic_saat']}-{sinav['bitis_saat']}  "
                  f"Giriş: {sinav['acilis_saat']}-{sinav['kapanis_saat']}  Durum: {DURUM_ADLARI.get(sinav['durum'])}"])
    toplam = len(gelenler) + len(gelmeyenler)
    sayfa.append([f"Gelen: {len(gelenler)} / {toplam}   Gelmeyen: {len(gelmeyenler)}"])
    sayfa.append([])
    basliklar = ["#", "Öğrenci No", "Ad Soyad", "Durum", "Giriş Saati", "Sıra No"]
    sayfa.append(basliklar)
    for hucre in sayfa[sayfa.max_row]:
        hucre.font = kalin
        hucre.fill = PatternFill("solid", fgColor="CFE3F3")
    yesil, kirmizi = PatternFill("solid", fgColor="D9ECF9"), PatternFill("solid", fgColor="EEF1F5")   # geldi / gelmedi
    satirlar = ([(g, "Geldi (görevli onayı)" if g.get("aciklama") else "Geldi") for g in gelenler]
                + [(g, "Gelmedi") for g in gelmeyenler])
    for i, (o, durum) in enumerate(satirlar, 1):
        sayfa.append([i, o["no"], o["ad"], durum, o.get("saat", ""), o.get("sira") or ""])
        sayfa.cell(row=sayfa.max_row, column=4).fill = yesil if durum.startswith("Geldi") else kirmizi
    for sutun, genislik in zip("ABCDEF", (5, 16, 28, 21, 12, 9)):
        sayfa.column_dimensions[sutun].width = genislik
    for satir in sayfa.iter_rows(min_row=5):
        for hucre in satir:
            hucre.alignment = Alignment(horizontal="left")

    detay = kitap.create_sheet("Tüm olaylar")
    detay.append(["Zaman", "Olay", "Ad Soyad", "Öğrenci No", "Sıra No"])
    for hucre in detay[1]:
        hucre.font = kalin
    tur_adlari = {"giris": "Giriş", "tekrar": "Tekrar deneme", "listede_yok": "Listede yok",
                  "bilinmeyen": "Kayıtsız kişi", "canlilik_yok": "Canlılık doğrulanamadı",
                  "erken": "Erken geldi (giriş kapalıydı)", "gec": "Geç kaldı (giriş kapanmıştı)"}
    for zaman, tur, isim, numara, sira in olaylar:
        detay.append([zaman, tur_adlari.get(tur, tur), isim, numara or "", sira or ""])
    for sutun, genislik in zip("ABCDE", (20, 16, 28, 16, 9)):
        detay.column_dimensions[sutun].width = genislik

    tampon = io.BytesIO()
    kitap.save(tampon)
    tampon.seek(0)
    dosya_adi = re.sub(r"[^\w-]+", "_", f"yoklama_{sinav['ad']}_{sinav['tarih']}").strip("_") + ".xlsx"
    return send_file(tampon, as_attachment=True, download_name=dosya_adi,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)   # her istek için log basmasın
    print(f"Site açıldı: http://localhost:{SITE_PORT}")
    print("Sesli karşılama:", "açık" if ses.hazir() else "kapalı (README'deki 'Sesli karşılama' bölümüne bak)")
    ses.isit(list(KAYIT_CUMLELERI.values()) + ["Kaydınız yok. Lütfen önce kayıt olun.",
                                               "Canlılık doğrulanamadı. Lütfen görevliye başvurun."])
    app.run(host="0.0.0.0", port=SITE_PORT, threaded=True)
