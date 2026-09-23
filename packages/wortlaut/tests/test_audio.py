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


class TestDauer:
    def test_liest_die_laenge_aus_dem_kopf(self, tmp_path: Path, wav_schreiben) -> None:
        wav = wav_schreiben(tmp_path / "a.wav", sekunden=3.5)
        assert audio.dauer(wav) == pytest.approx(3.5, abs=0.01)
        assert audio.dauer(wav) == pytest.approx(audio.untersuche(wav).dauer_s, abs=0.01)


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
    """Der Schnitt an Whisper-Segmentgrenzen - Grundlage der App „schreiben"."""

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


class TestVerlauf:
    """Die Kurve, aus der die Zuschnittansicht zeichnet und ihre Grenzen zieht."""

    def test_deckt_die_ganze_datei_ab(self, tmp_path: Path, wav_schreiben) -> None:
        quelle = wav_schreiben(tmp_path / "ganz.wav", sekunden=4.0)

        kurve = audio.verlauf(quelle)

        assert kurve.dauer_s == pytest.approx(4.0, abs=0.01)
        assert kurve.fenster_s == pytest.approx(0.02)
        # 20-ms-Fenster über vier Sekunden: zweihundert Stück.
        assert len(kurve.werte) == 200
        # Bezogen auf den Vollausschlag, also zwischen null und eins.
        assert all(0.0 <= wert <= 1.0 for wert in kurve.werte)

    def test_liegt_auf_demselben_raster_wie_die_messung(
        self, tmp_path: Path, wav_schreiben
    ) -> None:
        """Sonst läge die eingezeichnete Grenze neben dem Ausschlag.

        `untersuche` misst die Randstille in denselben Fenstern; beide
        Rechnungen müssen dieselben Zahlen ergeben, sonst zeigt die Ansicht
        etwas anderes an, als der Vorschlag meint.
        """
        quelle = wav_schreiben(tmp_path / "ganz.wav", sekunden=3.0, stille_vorn_s=0.5)

        befund = audio.untersuche(quelle)
        start, _ = audio.stimmgrenzen(audio.verlauf(quelle), rand_s=0.0)

        assert start == pytest.approx(befund.stille_vorn_s, abs=0.021)

    def test_findet_die_stimme_mit_luft_an_beiden_enden(
        self, tmp_path: Path, wav_schreiben
    ) -> None:
        quelle = wav_schreiben(tmp_path / "ganz.wav", sekunden=3.0, stille_vorn_s=1.0)

        start, ende = audio.stimmgrenzen(audio.verlauf(quelle))

        # Die Stimme setzt bei 1,0 s ein; der Vorschlag steht davor - und zwar
        # um den Rand, nicht darüber hinaus.
        assert 1.0 - audio.RAND_S - 0.02 <= start <= 1.0
        assert ende == pytest.approx(3.0, abs=0.01)
        assert start >= 0.0

    def test_stille_ergibt_die_ganze_aufnahme(self, tmp_path: Path, wav_schreiben) -> None:
        """Lieber nichts vorschlagen als etwas wegschneiden."""
        quelle = wav_schreiben(tmp_path / "leise.wav", sekunden=2.0, amplitude=0)

        assert audio.stimmgrenzen(audio.verlauf(quelle)) == pytest.approx((0.0, 2.0), abs=0.01)


class TestSchnittNachAussen:
    """Ein Rahmen zu viel ist Stille, ein Rahmen zu wenig ist ein Anlaut."""

    def test_rundet_anfang_ab_und_ende_auf(self, tmp_path: Path, wav_schreiben) -> None:
        quelle = wav_schreiben(tmp_path / "ganz.wav", sekunden=4.0)
        # Grenzen mitten zwischen zwei Abtastwerten (16 kHz → 62,5 µs).
        gewuenscht = (1.000_03, 2.000_03)

        erreicht = audio.schneide_ausschnitt(
            quelle, tmp_path / "aussen.wav", *gewuenscht, nach_aussen=True
        )

        assert erreicht[0] <= gewuenscht[0]
        assert erreicht[1] >= gewuenscht[1]
        # Und zwar um höchstens einen Rahmen, nicht großzügiger.
        assert gewuenscht[0] - erreicht[0] < 1 / 16_000
        assert erreicht[1] - gewuenscht[1] < 1 / 16_000

    def test_ohne_den_schalter_bleibt_es_beim_abschneiden(
        self, tmp_path: Path, wav_schreiben
    ) -> None:
        """Das Verhalten, auf das sich „schreiben" seit jeher verlässt."""
        quelle = wav_schreiben(tmp_path / "ganz.wav", sekunden=4.0)

        erreicht = audio.schneide_ausschnitt(quelle, tmp_path / "innen.wav", 1.000_03, 2.000_03)

        assert erreicht[1] <= 2.000_03

    def test_meldet_die_wirklich_erreichten_grenzen(
        self, tmp_path: Path, wav_schreiben
    ) -> None:
        """Wer sie aufbewahrt, bewahrt auf, was in der Datei steht."""
        quelle = wav_schreiben(tmp_path / "ganz.wav", sekunden=2.0)

        start, ende = audio.schneide_ausschnitt(
            quelle, tmp_path / "gestutzt.wav", 1.0, 9.0, nach_aussen=True
        )

        assert (start, ende) == pytest.approx((1.0, 2.0), abs=0.001)
