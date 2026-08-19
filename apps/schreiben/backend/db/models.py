"""Typisierte Modelle zum Schema aus `migrations/`.

Die Migrationen sind die Wahrheit über das Schema; diese Klassen bilden es für
den Zugriff ab. Wer eine Spalte hinzufügt, ändert beides — eine neue
`.sql`-Datei und die passende Zeile hier.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def jetzt() -> str:
    """Zeitstempel für alle Tabellen: ISO 8601 in UTC, sekundengenau."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class Basis(DeclarativeBase):
    pass


class Sitzung(Basis):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(primary_key=True)
    status: Mapped[str]  # offen | bestaetigt
    erstellt: Mapped[str]
    bestaetigt: Mapped[str | None]


class Abschnitt(Basis):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    position: Mapped[int]
    text: Mapped[str]
    # NULL, sobald die Aufnahme an „hören" übergeben und hier gelöscht ist.
    blob: Mapped[str | None]
    dauer_s: Mapped[float]
    herkunft: Mapped[str]  # initial | neu
    erstellt: Mapped[str]


class Postausgang(Basis):
    __tablename__ = "outbox"

    id: Mapped[str] = mapped_column(primary_key=True)
    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"))
    status: Mapped[str]  # offen | gesendet
    versuche: Mapped[int]
    letzter_fehler: Mapped[str | None]
    erstellt: Mapped[str]
    zuletzt: Mapped[str | None]
