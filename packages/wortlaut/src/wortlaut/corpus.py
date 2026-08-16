"""Das Korpus-Layout — ein Verzeichnis, kein Dienst.

    data/korpus/<sprecher_id>/
    ├── audio/<aufnahme_id>.wav     16 kHz mono, PCM 16 bit
    └── hoeren.sqlite               Vorlagen, Aufnahmen, Sitzungen

Je Sprecher eine Datenbank: „lernen" liest damit genau eine Datei, und die
vollständige Löschung eines Sprechers ist das Entfernen eines Verzeichnisses.
Diese Datei ist die einzige Stelle, die das Layout kennt.
"""

from __future__ import annotations

from pathlib import Path

KORPUS = "korpus"
DATENBANKNAME = "hoeren.sqlite"


def sprecher_relpfad(sprecher_id: str) -> str:
    return f"{KORPUS}/{sprecher_id}"


def audio_relpfad(sprecher_id: str, aufnahme_id: str) -> str:
    return f"{KORPUS}/{sprecher_id}/audio/{aufnahme_id}.wav"


def datenbank_pfad(datenverzeichnis: Path, sprecher_id: str) -> Path:
    return datenverzeichnis / KORPUS / sprecher_id / DATENBANKNAME


def sprecher_ids(datenverzeichnis: Path) -> list[str]:
    """Alle Sprecher, für die ein Korpus existiert — sortiert, also nach Alter."""
    wurzel = datenverzeichnis / KORPUS
    if not wurzel.is_dir():
        return []
    return sorted(
        eintrag.name for eintrag in wurzel.iterdir() if (eintrag / DATENBANKNAME).is_file()
    )
