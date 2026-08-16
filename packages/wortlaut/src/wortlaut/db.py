"""SQLite-Verbindung und Migrationsläufer.

Zwei Aufgaben, bewusst getrennt:

* `verbinde()` liefert eine SQLAlchemy-Engine mit den Einstellungen, die für
  diesen Anwendungsfall wichtig sind — vor allem WAL, damit „lernen" lesen
  kann, während „hören" schreibt.
* `wende_migrationen_an()` spielt nummerierte `.sql`-Dateien ein und merkt sich
  in `schema_migrations`, welche schon liefen. Kein Alembic: bei fünf Tabellen
  wäre die Migrationsmaschinerie größer als das Schema.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, create_engine, event


def verbinde(datenbank: Path) -> Engine:
    """Engine für eine SQLite-Datei; legt fehlende Verzeichnisse an."""
    datenbank.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{datenbank}")

    @event.listens_for(engine, "connect")
    def _pragmas(verbindung, _verbindungsdaten) -> None:
        zeiger = verbindung.cursor()
        zeiger.execute("PRAGMA journal_mode = WAL")  # gleichzeitige Leser
        zeiger.execute("PRAGMA foreign_keys = ON")  # SQLite prüft sonst nicht
        zeiger.execute("PRAGMA busy_timeout = 5000")  # statt sofortigem Fehler warten
        zeiger.execute("PRAGMA synchronous = NORMAL")  # mit WAL ausreichend sicher
        zeiger.close()

    return engine


def wende_migrationen_an(datenbank: Path, verzeichnis: Path) -> list[str]:
    """Wendet alle noch offenen `.sql`-Dateien an und gibt deren Namen zurück.

    Für Schemaänderungen wird bewusst das rohe `sqlite3`-Modul benutzt: es kann
    mit `executescript` mehrere Anweisungen am Stück ausführen, was SQLAlchemy
    nicht anbietet.
    """
    datenbank.parent.mkdir(parents=True, exist_ok=True)
    angewendet: list[str] = []

    with sqlite3.connect(datenbank) as verbindung:
        verbindung.execute("PRAGMA journal_mode = WAL")
        verbindung.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  version TEXT PRIMARY KEY,"
            "  angewendet TEXT NOT NULL)"
        )
        bekannt = {
            zeile[0] for zeile in verbindung.execute("SELECT version FROM schema_migrations")
        }

        for datei in sorted(verzeichnis.glob("*.sql")):
            if datei.stem in bekannt:
                continue
            verbindung.executescript(datei.read_text(encoding="utf-8"))
            verbindung.execute(
                "INSERT INTO schema_migrations (version, angewendet) VALUES (?, ?)",
                (datei.stem, datetime.now(UTC).isoformat()),
            )
            verbindung.commit()
            angewendet.append(datei.stem)

    return angewendet
