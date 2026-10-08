"""Selbsttraining - was das Modell sicher genug hört, lernt mit (`training/selbsttraining.py`).

Ohne Karte: Ein Erkenner, der je Datei Text und Sicherheit nennt, steht für
das freigegebene Modell.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wortlaut import corpus, laeufe
from wortlaut.whisper import Transkript

from apps.lernen.training.selbsttraining import beschrifte

SPRECHER = "spr_test"


class Erkenner:
    def __init__(self, gehoert: dict[str, tuple[str, float | None]]) -> None:
        self.gehoert = gehoert
        self.gefragt: list[str] = []

    def transkribiere(self, wav: Path, sprache: str) -> Transkript:
        self.gefragt.append(wav.name)
        text, sicherheit = self.gehoert[wav.name]
        return Transkript(text=text, abschnitte=[], sicherheit=sicherheit)


class Bericht:
    def __init__(self) -> None:
        self.stufen: list[str] = []
        self.gemerkt: dict = {}

    def stufe(self, name: str, **_weiteres) -> None:
        self.stufen.append(name)

    def sage(self, _text: str) -> None:
        pass

    def schritt(self, _schritt: int, _gesamt: int) -> None:
        pass

    def merke(self, **felder) -> None:
        self.gemerkt.update(felder)


@pytest.fixture
def lauf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("WORTLAUT_DATA_DIR", str(tmp_path))
    diktate = tmp_path / "diktate" / SPRECHER / "audio"
    diktate.mkdir(parents=True)
    (tmp_path / corpus.sprecher_relpfad(SPRECHER)).mkdir(parents=True)
    verzeichnis = laeufe.lauf_verzeichnis(tmp_path, "job_1")
    verzeichnis.mkdir(parents=True)
    zeilen = []
    for name in ("seg_sicher", "seg_unsicher", "seg_leer", "seg_weg"):
        if name != "seg_weg":
            (diktate / f"{name}.wav").write_bytes(b"RIFF")
        zeilen.append(
            {"audio": f"../../diktate/{SPRECHER}/audio/{name}.wav", "text": "",
             "quelle": "selbst", "faltung": None, "recording_id": name}
        )
    (verzeichnis / laeufe.MANIFEST).write_text(
        "".join(json.dumps(zeile) + "\n" for zeile in zeilen), encoding="utf-8"
    )
    return tmp_path, verzeichnis


AUFTRAG = {
    "sprecher_id": SPRECHER,
    "basismodell": "openai/whisper-small",
    "sprache": "de",
    "selbsttraining": "an",
}


def test_aufgenommen_wird_ab_der_schwelle(lauf: tuple[Path, Path]) -> None:
    datenverzeichnis, verzeichnis = lauf
    erkenner = Erkenner(
        {
            "seg_sicher.wav": ("Guten Morgen", 0.9),
            "seg_unsicher.wav": ("Guten Abend", 0.4),
            "seg_leer.wav": ("", 0.95),
        }
    )
    bericht = Bericht()
    beschrifte(
        verzeichnis, datenverzeichnis, AUFTRAG, {"selbst_mindestsicherheit": 0.7}, bericht, erkenner
    )

    inhalt = laeufe.lies_json(verzeichnis / laeufe.SELBSTBESCHRIFTUNG)
    # Ohne Freigabe beschriftet das Grundmodell.
    assert inhalt["modell"] == "small"
    # Was seit dem Auftrag verschwand, wird nicht gehört.
    assert sorted(erkenner.gefragt) == ["seg_leer.wav", "seg_sicher.wav", "seg_unsicher.wav"]
    assert laeufe.selbstbeschriftung_aus(verzeichnis) == {
        f"../../diktate/{SPRECHER}/audio/seg_sicher.wav": "Guten Morgen"
    }
    assert bericht.gemerkt == {"selbst_aufgenommen": 1, "selbst_kandidaten": 3}
    assert bericht.stufen == ["selbsttraining"]


def test_eine_vorhandene_beschriftung_bleibt(lauf: tuple[Path, Path]) -> None:
    datenverzeichnis, verzeichnis = lauf
    laeufe.schreibe_json(verzeichnis / laeufe.SELBSTBESCHRIFTUNG, {"modell": "x", "zeilen": {}})
    erkenner = Erkenner({})
    beschrifte(verzeichnis, datenverzeichnis, AUFTRAG, {}, Bericht(), erkenner)
    assert erkenner.gefragt == []


def test_ohne_die_achse_geschieht_nichts(lauf: tuple[Path, Path]) -> None:
    datenverzeichnis, verzeichnis = lauf
    beschrifte(
        verzeichnis, datenverzeichnis, {**AUFTRAG, "selbsttraining": "aus"}, {}, Bericht(), Erkenner({})
    )
    assert not (verzeichnis / laeufe.SELBSTBESCHRIFTUNG).exists()
