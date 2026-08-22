"""Migrationen auf alle vorhandenen Korpus-Datenbanken anwenden.

    uv run python scripts/migrate.py                        # auf dem Wirt
    docker compose exec wortlaut python scripts/migrate.py  # im Container

`make migrate` ist die erste Zeile, nur kürzer. Im Container gibt es sie nicht:
Das Abbild trägt weder den Makefile noch `uv`, sondern Python, `packages/`,
`apps/` und `scripts/` (siehe `Dockerfile`). Pfade oder Umgebung braucht der
Aufruf dort nicht — `WORKDIR` steht auf `/srv/wortlaut`, `WORTLAUT_DATA_DIR`
kommt aus der `compose.yaml`.

Je Sprecher gibt es eine Datenbank. Nötig ist dieses Skript für ein Update
nicht: Neue Sprecher bekommen ihre Migrationen beim Anlegen, bestehende beim
ersten Zugriff auf ihre Datenbank (`deps.engine_fuer`). Es ist der Weg, das für
alle Korpora auf einmal und vor dem ersten Aufruf zu tun — und die Ausgabe
sagt, was offen war. Ein zweiter Lauf tut nichts: Was gelaufen ist, steht in
`schema_migrations`.
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
