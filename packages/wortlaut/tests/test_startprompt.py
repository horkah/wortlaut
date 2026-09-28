"""Ein Stand bringt seinen Startprompt mit (`wortlaut/whisper/local.py`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from wortlaut.whisper import local


@dataclass
class Segment:
    start: float
    end: float
    text: str
    tokens: list[int]
    avg_logprob: float


@dataclass
class Modell:
    gefragt: list[dict] = field(default_factory=list)

    def transcribe(self, wav: str, **optionen):
        self.gefragt.append(optionen)
        return iter([Segment(0.0, 1.0, " Hallo", [1, 2], -0.1)]), None


def _erkenner(modell: Path | str, geladen: Modell) -> local.LokalerTranskriptor:
    erkenner = local.LokalerTranskriptor(modell, geraet="cpu", rechenart="int8")
    erkenner._lade = lambda: geladen
    return erkenner


def test_ein_stand_mit_startprompt_beginnt_damit(tmp_path: Path) -> None:
    (tmp_path / local.STARTPROMPT).write_text("Physiotherapeut, Logopädin\n", encoding="utf-8")
    geladen = Modell()
    transkript = _erkenner(tmp_path, geladen).transkribiere(tmp_path / "a.wav", "de")
    assert geladen.gefragt[0]["initial_prompt"] == "Physiotherapeut, Logopädin"
    assert transkript.text == "Hallo"


def test_ohne_datei_und_bei_einem_namen_ohne(tmp_path: Path) -> None:
    for modell in (tmp_path, "small"):
        geladen = Modell()
        _erkenner(modell, geladen).transkribiere(tmp_path / "a.wav", "de")
        assert geladen.gefragt[0]["initial_prompt"] is None


def test_die_sicherheit_kommt_aus_den_markenwahrscheinlichkeiten(tmp_path: Path) -> None:
    transkript = _erkenner("small", Modell()).transkribiere(tmp_path / "a.wav", "de")
    assert transkript.sicherheit == pytest.approx(0.9048, abs=1e-4)
