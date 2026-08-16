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


class Sprecher(Basis):
    __tablename__ = "speakers"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    sprache: Mapped[str]
    basismodell: Mapped[str]
    erstellt: Mapped[str]


class Textquelle(Basis):
    __tablename__ = "text_sources"

    id: Mapped[str] = mapped_column(primary_key=True)
    speaker_id: Mapped[str] = mapped_column(ForeignKey("speakers.id"))
    art: Mapped[str]  # llm | upload | korrektur
    titel: Mapped[str]
    parameter: Mapped[str]  # JSON
    erstellt: Mapped[str]


class Vorlage(Basis):
    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("text_sources.id"))
    speaker_id: Mapped[str] = mapped_column(ForeignKey("speakers.id"))
    position: Mapped[int]
    text: Mapped[str]
    dauer_geschaetzt_s: Mapped[float]
    erstellt: Mapped[str]


class Sitzung(Basis):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(primary_key=True)
    speaker_id: Mapped[str] = mapped_column(ForeignKey("speakers.id"))
    begonnen: Mapped[str]
    zuletzt_aktiv: Mapped[str]


class Aufnahme(Basis):
    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(primary_key=True)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id"))
    speaker_id: Mapped[str] = mapped_column(ForeignKey("speakers.id"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"))
    blob: Mapped[str]
    dauer_s: Mapped[float]
    pegel_dbfs: Mapped[float]
    spitze_dbfs: Mapped[float]
    clipping_anteil: Mapped[float]
    stille_vorn_s: Mapped[float]
    stille_hinten_s: Mapped[float]
    modus: Mapped[str]  # gelesen | nachgesprochen | frei
    status: Mapped[str]  # ok | verworfen
    hinweise: Mapped[str]  # JSON-Liste
    externe_id: Mapped[str | None]
    erstellt: Mapped[str]
