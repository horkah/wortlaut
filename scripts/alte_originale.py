"""Originale wegräumen, die noch neben ihren eigenen Teilen stehen.

    uv run python scripts/alte_originale.py [<sprecher_id>] [--loeschen]
    docker compose exec wortlaut python scripts/alte_originale.py [<sprecher_id>] [--loeschen]

Teilen in „Editieren" ersetzt das Original (`api/zuschnitt.teilen`). Ältere
Bestände können geteilte Aufnahmen noch neben ihren Teilen führen; dieses
Skript nimmt sie heraus, wie `teilen` es tut (`zuschnitt.entferne`): Zeile,
Datei, Messwerte und Vorlage, samt verworfenen Aufnahmen desselben Satzes.
Die Teile bleiben und gelten als Originale.

Ohne `--loeschen` zeigt es nur, was es löschen würde. Ohne Sprecher geht es
über alle Korpora.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ausführbar ohne Installation: Repository-Wurzel in den Suchpfad legen.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session
from wortlaut import corpus, db, storage

from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.db.models import Vorlage
from apps.hoeren.backend.services import zuschnitt


def raeume(sprecher_id: str, loeschen: bool) -> int:
    """Die alten Originale eines Korpus zeigen oder löschen; gibt ihre Zahl zurück."""
    konfiguration = einstellungen()
    pfad = corpus.datenbank_pfad(konfiguration.data_dir, sprecher_id)
    if not pfad.is_file():
        raise SystemExit(f"Kein Korpus für {sprecher_id}.")
    db.wende_migrationen_an(pfad, konfiguration.migrationsverzeichnis)
    ablage = storage.LokaleAblage(konfiguration.data_dir)

    with Session(db.verbinde(pfad)) as sitzung:
        originale = zuschnitt.geteilte_originale(sitzung)
        for original in originale:
            vorlage = sitzung.get(Vorlage, original.prompt_id)
            text = original.text_zu(vorlage) if vorlage is not None else ""
            print(f"{sprecher_id}  {original.id}  {original.erstellt}  {text[:60]}")
        if not loeschen or not originale:
            return len(originale)

        dateien = [zuschnitt.entferne(sitzung, original) for original in originale]
        sitzung.commit()
    # Die Dateien erst, wenn die Zeilen sicher weg sind.
    for datei in dateien:
        ablage.loesche(datei)
    return len(originale)


def main() -> int:
    argumente = [argument for argument in sys.argv[1:] if argument != "--loeschen"]
    loeschen = "--loeschen" in sys.argv[1:]
    if len(argumente) > 1:
        print(__doc__.strip().splitlines()[2])
        return 2
    sprecher = argumente or corpus.sprecher_ids(einstellungen().data_dir)

    gesamt = sum(raeume(sprecher_id, loeschen) for sprecher_id in sprecher)
    if loeschen:
        print(f"{gesamt} Original(e) gelöscht.")
    else:
        print(f"{gesamt} Original(e) zu löschen - mit --loeschen ausführen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
