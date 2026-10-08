"""Das Korpus-Layout - ein Verzeichnis, kein Dienst.

    data/korpus/<sprecher_id>/
    ├── audio/<aufnahme_id>.wav                  16 kHz mono, PCM 16 bit
    ├── hoeren.sqlite                            Vorlagen, Aufnahmen, Sitzungen

    └── vorlesen/<vorlage>.<stimme>.wav          vom Server vorgelesen

Je Sprecher eine Datenbank: „lernen" liest genau eine Datei, eine Löschung
entfernt ein Verzeichnis. Diese Datei ist die einzige Stelle, die das Layout
kennt.

In `audio/` liegt genau, was `recordings.blob` nennt - was ein Mensch
gesprochen hat. Alles Abgeleitete liegt daneben und lässt sich neu rechnen;
seine Pfade folgen aus Kennung und Name und stehen in keiner Tabelle.
"""

from __future__ import annotations

from pathlib import Path

KORPUS = "korpus"
DATENBANKNAME = "hoeren.sqlite"


def sprecher_relpfad(sprecher_id: str) -> str:
    return f"{KORPUS}/{sprecher_id}"


def audio_relpfad(sprecher_id: str, aufnahme_id: str) -> str:
    return f"{KORPUS}/{sprecher_id}/audio/{aufnahme_id}.wav"


VORLESENORDNER = "vorlesen"


def vorlesen_relpfad(sprecher_id: str) -> str:
    """Wo die vorgelesenen Vorlagen eines Sprechers liegen - was eine Maschine
    gesprochen hat, neben `audio/`; nicht in der Sicherung."""
    return f"{KORPUS}/{sprecher_id}/{VORLESENORDNER}"


def vorlesung_relpfad(sprecher_id: str, vorlage_id: str, stimme: str) -> str:
    """Wo die vorgelesene Fassung einer Vorlage liegt - je Stimme eine Datei."""
    return f"{KORPUS}/{sprecher_id}/{VORLESENORDNER}/{vorlage_id}.{stimmenname(stimme)}.wav"


def stimmenname(stimme: str) -> str:
    """Ein Stimmenschlüssel als Teil eines Dateinamens.

    `piper/de_DE-thorsten-high` wird zu `piper-de_DE-thorsten-high`: Weder der
    Schrägstrich noch der Punkt, der Vorlage und Stimme trennt, darf hinein.
    """
    return stimme.replace("/", "-").replace(".", "-")


def datenbank_pfad(datenverzeichnis: Path, sprecher_id: str) -> Path:
    return datenverzeichnis / KORPUS / sprecher_id / DATENBANKNAME


def sprecher_ids(datenverzeichnis: Path) -> list[str]:
    """Alle Sprecher, für die ein Korpus existiert - sortiert, also nach Alter."""
    wurzel = datenverzeichnis / KORPUS
    if not wurzel.is_dir():
        return []
    return sorted(
        eintrag.name for eintrag in wurzel.iterdir() if (eintrag / DATENBANKNAME).is_file()
    )
