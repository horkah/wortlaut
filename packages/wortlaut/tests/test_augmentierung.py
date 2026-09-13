"""Die abgewandelte Fassung einer Aufnahme.

Geprüft wird, was die eine verbliebene Abwandlung zusichert - dass das Rauschen
hörbar ist, die Sprache aber vorn bleibt, und dass es jede Aufnahme gleich hart
trifft - und die eine Eigenschaft, ohne die eine Messung keine Messung wäre:
dass dasselbe zweimal dasselbe ergibt.

`pegel` und `lauter` standen hier bis September 2026 und sind verworfen: Eine
gleichmäßige Verstärkung ist an Whisper nahezu wirkungslos (siehe
`wortlaut/augmentierung.py`). Was sie geprüft haben, prüft niemand mehr, weil
es niemand mehr rechnet.
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


def _rms(werte: array.array) -> float:
    return math.sqrt(sum(wert * wert for wert in werte) / len(werte))


def _wandle(quelle: Path, ziel: Path, name: str, keim: str = "rec_test") -> array.array:
    augmentierung.wandle_ab(quelle, ziel, name, keim=keim)
    return _werte(ziel)


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
            augmentierung.wandle_ab(quelle, tmp_path / "b.wav", "rauschen", keim="rec_test")
