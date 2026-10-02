"""Alle vorhandenen Läufe ins Register der Läufe eintragen.

    uv run python scripts/register.py                        # auf dem Wirt
    docker compose exec wortlaut python scripts/register.py  # im Container

Nötig ist das nur für Läufe, die vor dem Register entstanden, oder wenn der
Läufer beim Eintragen scheiterte (Fehlerprotokoll). Sonst trägt der Läufer
jeden Lauf ein, wenn er endet, und „lernen" jeden, bevor er gelöscht wird
(`apps/lernen/backend/services/register.py`). Ein zweiter Lauf schadet nicht:
Was aus dem Laufverzeichnis kommt, wird ersetzt, der Rest bleibt.

Gelöschte Läufe kann dieses Skript nicht mehr eintragen - ihre Dateien sind weg.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wortlaut import laeufe

from apps.lernen.backend.config import einstellungen
from apps.lernen.backend.services import register


def main() -> int:
    datenverzeichnis = einstellungen().data_dir
    alle = laeufe.alle_laeufe(datenverzeichnis)
    if not alle:
        print(f"Keine Läufe unter {laeufe.wurzel(datenverzeichnis)} - nichts zu tun.")
        return 0

    je_sprecher: dict[str, int] = {}
    for lauf in alle:
        if register.trage_ein(datenverzeichnis, lauf.job_id):
            je_sprecher[lauf.sprecher_id] = je_sprecher.get(lauf.sprecher_id, 0) + 1
            print(f"{lauf.job_id}  {lauf.sprecher_id}  {lauf.status}", flush=True)
    for sprecher_id, anzahl in sorted(je_sprecher.items()):
        print(f"{sprecher_id}: {anzahl} Läufe in {register.pfad(datenverzeichnis, sprecher_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
