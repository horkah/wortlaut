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


class TestSchneideAusschnitt:
    """Der Schnitt an Whisper-Segmentgrenzen — Grundlage der App „schreiben"."""

    def test_schneidet_den_gewuenschten_bereich(self, tmp_path: Path, wav_schreiben) -> None:
        quelle = wav_schreiben(tmp_path / "ganz.wav", sekunden=6.0)
        ziel = tmp_path / "teil" / "stueck.wav"

        audio.schneide_ausschnitt(quelle, ziel, 2.0, 3.5)

        befund = audio.untersuche(ziel)
        assert befund.dauer_s == pytest.approx(1.5, abs=0.01)

    def test_behaelt_format_und_pegel(self, tmp_path: Path, wav_schreiben) -> None:
        quelle = wav_schreiben(tmp_path / "ganz.wav", sekunden=4.0, amplitude=8000)
        ziel = tmp_path / "stueck.wav"

        audio.schneide_ausschnitt(quelle, ziel, 1.0, 3.0)

        with wave.open(str(ziel), "rb") as datei:
            assert datei.getframerate() == 16_000
            assert datei.getnchannels() == 1
            assert datei.getsampwidth() == 2
        # Geschnitten wird ohne Umkodieren; der Pegel bleibt, wie er war.
        assert audio.untersuche(ziel).spitze_dbfs == pytest.approx(
            audio.untersuche(quelle).spitze_dbfs, abs=0.5
        )

    def test_stutzt_grenzen_hinter_dem_dateiende(self, tmp_path: Path, wav_schreiben) -> None:
        # Whisper meldet gelegentlich ein Ende hinter dem letzten Abtastwert.
        quelle = wav_schreiben(tmp_path / "ganz.wav", sekunden=2.0)
        ziel = tmp_path / "stueck.wav"

        audio.schneide_ausschnitt(quelle, ziel, 1.0, 9.0)

        assert audio.untersuche(ziel).dauer_s == pytest.approx(1.0, abs=0.01)

    def test_lehnt_leeren_ausschnitt_ab(self, tmp_path: Path, wav_schreiben) -> None:
        quelle = wav_schreiben(tmp_path / "ganz.wav", sekunden=2.0)
        with pytest.raises(audio.AudioFehler):
            audio.schneide_ausschnitt(quelle, tmp_path / "leer.wav", 1.0, 1.0)
