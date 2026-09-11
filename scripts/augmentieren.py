"""Die abgewandelten Fassungen aller Aufnahmen herstellen.

    uv run python scripts/augmentieren.py                        # auf dem Wirt
    docker compose exec wortlaut python scripts/augmentieren.py  # im Container

Zu jeder brauchbaren Aufnahme gehören drei abgewandelte Fassungen -
ausgesteuert, pauschal lauter, mit Grundrauschen (`wortlaut/augmentierung.py`).
Sie entstehen von selbst: beim Hochladen einer neuen Aufnahme und spätestens,
wenn die Auswertung sie braucht. Nötig ist dieses Skript deshalb nicht.

Es ist der Weg, das für alle Korpora auf einmal und **vorher** zu tun - vor
einer Auswertung, die sonst zwischen den Modellläufen rechnet, oder vor einer
Sicherung, die den vollständigen Datensatz enthalten soll. Ein zweiter Lauf tut
nichts: Was da ist, wird nicht neu gerechnet.

Verworfene Aufnahmen bleiben außen vor. Sie haben kein Audio mehr (siehe
`api/recordings.py`), und drei Fassungen von nichts sind nichts.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ausführbar ohne Installation: Repository-Wurzel in den Suchpfad legen.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import audio, corpus, db, storage

from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.db.models import Aufnahme
from apps.hoeren.backend.services import augmentierung


def main() -> int:
    konfiguration = einstellungen()
    ablage = storage.oeffne_ablage(konfiguration.storage, konfiguration.data_dir)
    sprecher = corpus.sprecher_ids(konfiguration.data_dir)
    if not sprecher:
        print(f"Keine Korpora unter {konfiguration.data_dir / corpus.KORPUS} - nichts zu tun.")
        return 0

    fehlgeschlagen = 0
    for sprecher_id in sprecher:
        pfad = corpus.datenbank_pfad(konfiguration.data_dir, sprecher_id)
        # Wie überall vor dem ersten Zugriff: Die Spalte `variante` kommt aus
        # einer Migration, und eine Datenbank, die sie noch nicht hat, ließe
        # sich hier nicht lesen.
        db.wende_migrationen_an(pfad, konfiguration.migrationsverzeichnis)

        neu = 0
        with Session(db.verbinde(pfad)) as sitzung:
            aufnahmen = sitzung.scalars(
                select(Aufnahme).where(Aufnahme.status == "ok").order_by(Aufnahme.erstellt)
            ).all()
            for aufnahme in aufnahmen:
                try:
                    neu += len(augmentierung.stelle_alle_her(ablage, aufnahme))
                except audio.AudioFehler as ursache:
                    # Eine Aufnahme ohne Datei hält die übrigen nicht auf - das
                    # ist ein Befund und kein Grund abzubrechen.
                    print(f"  {aufnahme.id}: {ursache}")
                    fehlgeschlagen += 1

        print(f"{sprecher_id}: {len(aufnahmen)} Aufnahmen, {neu} Fassungen neu gerechnet")

    return 1 if fehlgeschlagen else 0


if __name__ == "__main__":
    raise SystemExit(main())
