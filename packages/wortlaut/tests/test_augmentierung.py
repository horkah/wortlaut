"""Die abgewandelten Fassungen einer Aufnahme.

Geprüft wird, was die drei Abwandlungen zusichern - dass die Aussteuerung den
Bereich ausschöpft, ohne ihn zu verlassen; dass „lauter" für jede Aufnahme
derselbe Faktor ist; dass das Rauschen hörbar ist, die Sprache aber vorn
bleibt - und die eine Eigenschaft, ohne die eine Messung keine Messung wäre:
dass dasselbe zweimal dasselbe ergibt.
"""

from __future__ import annotations

import array
import math
import wave
from pathlib import Path

import pytest
from wortlaut import audio, augmentierung


def _werte(wav: Path) -> array.array:
    with wave.open(str(wav), "rb") as datei:
        werte = array.array("h")
        werte.frombytes(datei.readframes(datei.getnframes()))
    return werte


def _spitze(werte: array.array) -> int:
    return max(max(werte), -min(werte))


def _rms(werte: array.array) -> float:
    return math.sqrt(sum(wert * wert for wert in werte) / len(werte))


def _wandle(quelle: Path, ziel: Path, name: str, keim: str = "rec_test") -> array.array:
    augmentierung.wandle_ab(quelle, ziel, name, keim=keim)
    return _werte(ziel)


class TestAussteuern:
    def test_schoepft_den_bereich_aus(self, tmp_path: Path, wav_schreiben) -> None:
        leise = wav_schreiben(tmp_path / "leise.wav", amplitude=2000)
        werte = _wandle(leise, tmp_path / "pegel.wav", "pegel")

        erwartet = audio.VOLLAUSSCHLAG * 10 ** (augmentierung.ZIEL_SPITZE_DBFS / 20)
        assert _spitze(werte) == pytest.approx(erwartet, rel=0.01)

    def test_verlaesst_ihn_nicht(self, tmp_path: Path, wav_schreiben) -> None:
        # Eine Aufnahme am Anschlag wird dabei leiser. „Optimal ausnutzen"
        # heißt auch, den Bereich nicht zu verlassen.
        laut = wav_schreiben(tmp_path / "laut.wav", amplitude=32_700)
        werte = _wandle(laut, tmp_path / "pegel.wav", "pegel")
        assert _spitze(werte) < 32_700

    def test_stille_bleibt_stille(self, tmp_path: Path, wav_schreiben) -> None:
        # Kein lautester Punkt, durch den sich teilen ließe.
        still = wav_schreiben(tmp_path / "still.wav", amplitude=0)
        assert set(_wandle(still, tmp_path / "pegel.wav", "pegel")) == {0}

    def test_laesst_das_verhaeltnis_der_stellen_stehen(
        self, tmp_path: Path, wav_schreiben
    ) -> None:
        # Ein Faktor über die ganze Aufnahme, keine Kompression: Laut und leise
        # stehen hinterher im selben Verhältnis zueinander wie vorher.
        quelle = wav_schreiben(tmp_path / "a.wav", amplitude=3000)
        vorher = _werte(quelle)
        nachher = _wandle(quelle, tmp_path / "pegel.wav", "pegel")
        faktor = _spitze(nachher) / _spitze(vorher)
        assert _rms(nachher) == pytest.approx(_rms(vorher) * faktor, rel=0.01)


class TestLauter:
    def test_derselbe_faktor_fuer_jede_aufnahme(self, tmp_path: Path, wav_schreiben) -> None:
        for amplitude in (1000, 8000):
            quelle = wav_schreiben(tmp_path / f"{amplitude}.wav", amplitude=amplitude)
            lauter = _wandle(quelle, tmp_path / f"{amplitude}-lauter.wav", "lauter")
            assert _rms(lauter) == pytest.approx(
                _rms(_werte(quelle)) * augmentierung.LAUTER_FAKTOR, rel=0.01
            )

    def test_wer_schon_am_anschlag_stand_stoesst_daran(
        self, tmp_path: Path, wav_schreiben
    ) -> None:
        # Genau der Fall, den diese Abwandlung herstellen soll - und nicht der
        # Fall, den `pegel` herstellt.
        quelle = wav_schreiben(tmp_path / "laut.wav", amplitude=32_000)
        lauter = _wandle(quelle, tmp_path / "lauter.wav", "lauter")
        # Hart abgeschnitten, an beiden Enden des Wertebereichs: Ein Überlauf
        # klänge nicht laut, sondern kaputt.
        assert max(lauter) == augmentierung.GROESSTER
        assert min(lauter) == augmentierung.KLEINSTER
        assert audio.untersuche(tmp_path / "lauter.wav").clipping_anteil > 0


class TestRauschen:
    def test_ist_zu_hoeren_und_deckt_nicht_zu(self, tmp_path: Path, wav_schreiben) -> None:
        quelle = wav_schreiben(tmp_path / "a.wav", amplitude=6000)
        vorher = _werte(quelle)
        nachher = _wandle(quelle, tmp_path / "rauschen.wav", "rauschen")

        # Das Rauschen allein, Stelle für Stelle.
        rauschen = array.array("h", (neu - alt for alt, neu in zip(vorher, nachher)))
        abstand_db = 20 * math.log10(_rms(vorher) / _rms(rauschen))
        assert abstand_db == pytest.approx(augmentierung.RAUSCHABSTAND_DB, abs=1.0)

    def test_liegt_auch_bei_leiser_aufnahme_gleich_weit_darunter(
        self, tmp_path: Path, wav_schreiben
    ) -> None:
        # Ein absoluter Rauschpegel träfe eine leise Aufnahme viel härter - die
        # Abwandlung wäre dann für jede Aufnahme eine andere.
        abstaende = []
        for amplitude in (1500, 12_000):
            quelle = wav_schreiben(tmp_path / f"{amplitude}.wav", amplitude=amplitude)
            vorher = _werte(quelle)
            nachher = _wandle(quelle, tmp_path / f"{amplitude}-r.wav", "rauschen")
            rauschen = array.array("h", (neu - alt for alt, neu in zip(vorher, nachher)))
            abstaende.append(20 * math.log10(_rms(vorher) / _rms(rauschen)))
        assert abstaende[0] == pytest.approx(abstaende[1], abs=1.0)

    def test_derselbe_keim_ergibt_dasselbe_rauschen(
        self, tmp_path: Path, wav_schreiben
    ) -> None:
        # Ohne das wäre eine Wiederholung der Messung keine Wiederholung.
        quelle = wav_schreiben(tmp_path / "a.wav")
        eins = _wandle(quelle, tmp_path / "1.wav", "rauschen", keim="rec_gleich")
        zwei = _wandle(quelle, tmp_path / "2.wav", "rauschen", keim="rec_gleich")
        drei = _wandle(quelle, tmp_path / "3.wav", "rauschen", keim="rec_anders")
        assert eins == zwei
        assert eins != drei


class TestJedeFassung:
    @pytest.mark.parametrize("name", [a.name for a in augmentierung.ABWANDLUNGEN])
    def test_laenge_und_format_bleiben(self, name: str, tmp_path: Path, wav_schreiben) -> None:
        # Abgewandelt werden die Abtastwerte, nicht die Datei: Nur so ist die
        # Fassung zur Aufnahme Punkt für Punkt dieselbe Stelle.
        quelle = wav_schreiben(tmp_path / "a.wav", sekunden=2.0)
        ziel = tmp_path / f"{name}.wav"
        augmentierung.wandle_ab(quelle, ziel, name, keim="rec_test")

        with wave.open(str(quelle), "rb") as alt, wave.open(str(ziel), "rb") as neu:
            assert neu.getparams() == alt.getparams()

    @pytest.mark.parametrize("name", [a.name for a in augmentierung.ABWANDLUNGEN])
    def test_klingt_wirklich_anders(self, name: str, tmp_path: Path, wav_schreiben) -> None:
        quelle = wav_schreiben(tmp_path / "a.wav", amplitude=6000)
        assert _wandle(quelle, tmp_path / f"{name}.wav", name) != _werte(quelle)

    def test_das_original_ist_keine_abwandlung(self, tmp_path: Path, wav_schreiben) -> None:
        quelle = wav_schreiben(tmp_path / "a.wav")
        with pytest.raises(audio.AudioFehler):
            augmentierung.wandle_ab(quelle, tmp_path / "b.wav", "original", keim="rec_test")

    def test_stereo_wird_abgewiesen(self, tmp_path: Path, wav_schreiben) -> None:
        quelle = wav_schreiben(tmp_path / "stereo.wav", kanaele=2)
        with pytest.raises(audio.AudioFehler):
            augmentierung.wandle_ab(quelle, tmp_path / "b.wav", "pegel", keim="rec_test")
