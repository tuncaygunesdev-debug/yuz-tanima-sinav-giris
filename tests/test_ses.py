# Sesli karşılama: Türkçe cümle WAV olarak üretilir ve önbelleğe alınır.
# Piper ya da ses modeli yoksa bu testler atlanır.

import wave
from pathlib import Path

import pytest

PROJE = Path(__file__).resolve().parent.parent
MODEL = PROJE / "sesler" / "tr_TR-dfki-medium.onnx"


@pytest.fixture
def ses(monkeypatch, tmp_path):
    pytest.importorskip("piper")
    if not MODEL.exists():
        pytest.skip("ses modeli yok (sesler/tr_TR-dfki-medium.onnx)")
    import ses as modul
    monkeypatch.setattr(modul, "MODEL", str(MODEL))
    monkeypatch.setattr(modul, "ONBELLEK", str(tmp_path / "onbellek"))
    return modul


def test_turkce_cumle_wav_uretir(ses, tmp_path):
    veri = ses.konus("Hoş geldin Şükrü Öztürk. Sıra numaran 12.")
    assert veri[:4] == b"RIFF"
    yol = tmp_path / "ses.wav"
    yol.write_bytes(veri)
    with wave.open(str(yol)) as w:
        assert w.getnframes() / w.getframerate() > 1.0   # en az 1 saniyelik konuşma


def test_ayni_cumle_onbellekten_gelir(ses, tmp_path):
    ilk = ses.konus("Kaydınız yok. Lütfen önce kayıt olun.")
    assert len(list((tmp_path / "onbellek").glob("*.wav"))) == 1
    assert ses.konus("Kaydınız yok. Lütfen önce kayıt olun.") == ilk
    assert len(list((tmp_path / "onbellek").glob("*.wav"))) == 1


def test_model_yoksa_ses_uretilmez(monkeypatch, tmp_path):
    import ses as modul
    monkeypatch.setattr(modul, "MODEL", str(tmp_path / "yok.onnx"))
    assert modul.hazir() is False and modul.konus("deneme") is None
