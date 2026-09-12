"""Typisierte Modelle zum Schema aus `migrations/`.

Die Migrationen sind die Wahrheit über das Schema; diese Klassen bilden es für
den Zugriff ab. Wer eine Spalte hinzufügt, ändert beides - eine neue
`.sql`-Datei und die passende Zeile hier.

Es ist genau eine Tabelle, und der Grund dafür steht in `001_init.sql`.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Basis(DeclarativeBase):
    pass


class Zuteilung(Basis):
    """Wohin eine Aufnahme gehört: lernen, steuern oder prüfen.

    Einmal vergeben, nie wieder geändert. Eine Aufnahme, die einmal geprüft
    hat, darf nie trainieren - sonst misst der Test, was das Modell auswendig
    gelernt hat.
    """

    __tablename__ = "aufteilung"

    recording_id: Mapped[str] = mapped_column(primary_key=True)
    teil: Mapped[str]
    nummer: Mapped[int]
    zugeteilt: Mapped[str]
