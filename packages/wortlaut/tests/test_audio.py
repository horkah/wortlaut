"""Umwandlung und Vermessung von Aufnahmen.

Die Messwerte selbst werden hier geprüft, ihre Bewertung in
`apps/hoeren/tests/test_aufnahmen.py`.
"""

from __future__ import annotations

import shutil
import wave
from pathlib import Path

import pytest
from wortlaut import audio

ohne_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fehlt")


class TestUntersuche:
    def test_misst_dauer_und_randstille(self, tmp_path: Path, wav_schreiben) -> None:
        befund = audio.untersuche(
            wav_schreiben(tmp_path / "a.wav", sekunden=4.0, stille_vorn_s=0.5)
        )
        assert befund.dauer_s == pytest.approx(4.0, abs=0.05)
        assert befund.stille_vorn_s == pytest.approx(0.5, abs=0.1)
        assert befund.stille_hinten_s == pytest.approx(0.0, abs=0.1)

    def test_leiser_ist_leiser(self, tmp_path: Path, wav_schreiben) -> None:
        laut = audio.untersuche(wav_schreiben(tmp_path / "laut.wav", amplitude=20_000))
        leise = audio.untersuche(wav_schreiben(tmp_path / "leise.wav", amplitude=200))
        assert leise.pegel_dbfs < laut.pegel_dbfs
        # dBFS ist eine Dämpfung gegenüber Vollaussteuerung, also immer negativ.
        assert laut.pegel_dbfs < 0

    def test_erkennt_uebersteuerung(self, tmp_path: Path, wav_schreiben) -> None:
        sauber = audio.untersuche(wav_schreiben(tmp_path / "sauber.wav", amplitude=6000))
        anschlag = audio.untersuche(wav_schreiben(tmp_path / "voll.wav", amplitude=32_767))
        assert sauber.clipping_anteil == 0.0
        assert anschlag.clipping_anteil > 0.0

    def test_lehnt_stereo_ab(self, tmp_path: Path, wav_schreiben) -> None:
        # Umgewandelt wird an genau einer Stelle; alles andere ist ein Fehler.
        with pytest.raises(audio.AudioFehler):
            audio.untersuche(wav_schreiben(tmp_path / "stereo.wav", kanaele=2))

    def test_lehnt_leere_datei_ab(self, tmp_path: Path, wav_schreiben) -> None:
        with pytest.raises(audio.AudioFehler):
            audio.untersuche(wav_schreiben(tmp_path / "nichts.wav", sekunden=0.0))


class TestWandleInWav:
    @ohne_ffmpeg
    def test_macht_16khz_mono_daraus(self, tmp_path: Path, wav_schreiben) -> None:
        quelle = wav_schreiben(tmp_path / "quelle.wav", abtastrate=44_100, kanaele=2)
        ziel = tmp_path / "unter" / "ziel.wav"

        audio.wandle_in_wav(quelle, ziel)

        with wave.open(str(ziel), "rb") as datei:
            assert datei.getframerate() == audio.ABTASTRATE
            assert datei.getnchannels() == 1
            assert datei.getsampwidth() == 2

    @ohne_ffmpeg
    def test_meldet_unlesbares_material(self, tmp_path: Path) -> None:
        kaputt = tmp_path / "kaputt.webm"
        kaputt.write_bytes(b"das ist kein Audio")
        with pytest.raises(audio.AudioFehler):
            audio.wandle_in_wav(kaputt, tmp_path / "ziel.wav")
