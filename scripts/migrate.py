"""Migrationen auf alle vorhandenen Korpus-Datenbanken anwenden.

    uv run python scripts/migrate.py

Je Sprecher gibt es eine Datenbank; neue Sprecher bekommen ihre Migrationen
beim Anlegen. Dieses Skript ist für den Fall, dass nach einem Update Migrationen
für bestehende Sprecher offen sind.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ausführbar ohne Installation: Repository-Wurzel in den Suchpfad legen.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wortlaut import corpus, db

from apps.hoeren.backend.config import einstellungen


def main() -> int:
    konfiguration = einstellungen()
    sprecher = corpus.sprecher_ids(konfiguration.data_dir)
    if not sprecher:
        print(f"Keine Korpora unter {konfiguration.data_dir / corpus.KORPUS} — nichts zu tun.")
        return 0

    for sprecher_id in sprecher:
        pfad = corpus.datenbank_pfad(konfiguration.data_dir, sprecher_id)
        angewendet = db.wende_migrationen_an(pfad, konfiguration.migrationsverzeichnis)
        zustand = ", ".join(angewendet) if angewendet else "aktuell"
        print(f"{sprecher_id}: {zustand}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
