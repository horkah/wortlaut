"""Typisierte Modelle zum Schema aus `migrations/`.

Die Migrationen sind die Wahrheit über das Schema; diese Klassen bilden es für
den Zugriff ab. Wer eine Spalte hinzufügt, ändert beides - eine neue
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
    erstellt: Mapped[str]
    # Um welchen Faktor die Aufnahmen dieses Sprechers vorgespult werden,
    # bevor irgendein Modell sie hört (siehe `011_tempo.sql` und
    # `wortlaut/tempo.py`). 1,0 heißt: gar nicht - der Normalfall.
    tempo: Mapped[float] = mapped_column(default=1.0)
    # Prüfwert des Sprecherzugangs, siehe `wortlaut.zugang`. NULL heißt:
    # zurückgezogen - dann kommt niemand an diesen Korpus heran.
    zugang_hash: Mapped[str | None] = mapped_column(default=None)
    zugang_erneuert: Mapped[str | None] = mapped_column(default=None)
    # Prüfwert der PIN vor „Meine Daten", siehe `services/pin.py`. NULL heißt:
    # keine PIN gesetzt, die Ansicht öffnet sich ohne Umweg.
    pin_hash: Mapped[str | None] = mapped_column(default=None)


class Textquelle(Basis):
    __tablename__ = "text_sources"

    id: Mapped[str] = mapped_column(primary_key=True)
    speaker_id: Mapped[str] = mapped_column(ForeignKey("speakers.id"))
    art: Mapped[str]  # llm | upload | korrektur
    titel: Mapped[str]
    parameter: Mapped[str]  # JSON
    # Stillgelegt heißt: keine neuen Einheiten mehr in der Warteschlange.
    # Was schon aufgenommen wurde, bleibt im Korpus.
    aktiv: Mapped[bool] = mapped_column(default=True)
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


class Erkennung(Basis):
    """Was ein Modell aus einer Aufnahme gemacht hat, samt Maßen dagegen.

    Je Aufnahme, Modell und Fassung eine Zeile (siehe `005_auswertung.sql`
    und `007_varianten.sql`). Die Fehlerraten sind Maße gegen die Vorlage,
    `genauigkeit` fasst sie zu einer Zahl zusammen - beides gerechnet in
    `wortlaut/metriken.py`, hier nur aufbewahrt.
    """

    __tablename__ = "erkennungen"

    id: Mapped[str] = mapped_column(primary_key=True)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recordings.id"))
    modell: Mapped[str]
    # Welche Fassung der Aufnahme gemessen wurde: `original` oder eine der
    # Abwandlungen aus `wortlaut/augmentierung.py` (siehe `007_varianten.sql`).
    variante: Mapped[str]
    text: Mapped[str]
    wer: Mapped[float]
    cer: Mapped[float]
    mer: Mapped[float]
    wil: Mapped[float]
    genauigkeit: Mapped[float]
    rechenzeit_s: Mapped[float]
    # Worauf diese Zeile gerechnet wurde: `cuda/int8_float16` oder `cpu/int8`
    # (siehe `008_rechenwerk.sql` und `wortlaut/rechenwerk.py`). Ohne diese
    # Angabe ist die Rechenzeit daneben keine Auskunft, sondern eine Zahl.
    # Leer heißt „unbekannt" - gemessen, bevor es die Spalte gab.
    rechenwerk: Mapped[str]
    # Mit welchem Faktor vorgespult war, was hier gemessen wurde. Teil des
    # Schlüssels wie `rechenwerk`: Eine Zahl aus vorgespulter Sprache ist mit
    # einer aus ungespulter nicht zu vergleichen (siehe `011_tempo.sql`).
    tempo: Mapped[float] = mapped_column(default=1.0)
    # Woher diese Messung stammt (siehe `014_erkennungen_aus_faltungen.sql`):
    #
    # * `gemessen` - hier gerechnet, von einem Modell, das die Aufnahme nie
    #   gehört hatte. Der Normalfall und die Vorgabe.
    # * `faltung`  - aus der Kreuzvalidierung eines Trainingslaufs übernommen.
    #   Ebenfalls von einem Modell, das die Aufnahme nicht kannte - nur ist es
    #   inzwischen gelöscht, also lässt sich diese Zeile nie neu rechnen.
    herkunft: Mapped[str] = mapped_column(default="gemessen")
    erstellt: Mapped[str]
