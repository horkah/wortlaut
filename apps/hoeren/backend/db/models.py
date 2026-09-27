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
    # Ungenutzt und immer 1,0: Vorgespult wird je Modellstand, nicht je
    # Sprecher (`012_ohne_profiltempo.sql`).
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
    # Abgestellt: keine neuen Einheiten in der Warteschlange; Aufgenommenes bleibt.
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
    # Grenzen des Zuschnitts in Sekunden vom Anfang des Originals; NULL heißt
    # ungeschnitten. Der Pfad folgt aus der Kennung (`corpus.zuschnitt_relpfad`).
    zuschnitt_start_s: Mapped[float | None] = mapped_column(default=None)
    zuschnitt_ende_s: Mapped[float | None] = mapped_column(default=None)
    # Leer, außer bei Teilen: Kennung des Originals mit angehängter Nummer.
    sortierschluessel: Mapped[str | None] = mapped_column(default=None)
    erstellt: Mapped[str]


class Erkennung(Basis):
    """Was ein Modell aus einer Aufnahme gemacht hat, samt Maßen dagegen.

    Je Aufnahme, Modell und Fassung eine Zeile; gerechnet in
    `wortlaut/metriken.py`.
    """

    __tablename__ = "erkennungen"

    id: Mapped[str] = mapped_column(primary_key=True)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recordings.id"))
    modell: Mapped[str]
    # `original` oder eine Abwandlung aus `wortlaut/augmentierung.py`.
    variante: Mapped[str]
    text: Mapped[str]
    wer: Mapped[float]
    cer: Mapped[float]
    mer: Mapped[float]
    wil: Mapped[float]
    genauigkeit: Mapped[float]
    rechenzeit_s: Mapped[float]
    # Worauf gerechnet wurde, etwa `cuda/int8_float16` (`wortlaut/rechenwerk.py`);
    # erst damit ist die Rechenzeit eine Auskunft. Leer heißt unbekannt.
    rechenwerk: Mapped[str]
    # Mit welchem Faktor vorgespult war - bei einem Stand der seine.
    tempo: Mapped[float] = mapped_column(default=1.0)
    # Woher die Messung stammt - beide Male von einem Modell, das die Aufnahme
    # nicht kannte:
    #
    # * `gemessen` - hier gerechnet.
    # * `faltung`  - aus der Kreuzvalidierung eines Laufs übernommen; das
    #   Faltungsmodell gibt es nicht mehr, neu rechnen lässt sich die Zeile nie.
    herkunft: Mapped[str] = mapped_column(default="gemessen")
    erstellt: Mapped[str]
