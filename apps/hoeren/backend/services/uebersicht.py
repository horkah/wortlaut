"""Was ein Sprecher an Daten hat - Profil, Textquellen, Sitzungen, Aufnahmen.

Zwei Wege lesen dasselbe: `api/admin.py`, wo die Aufsicht einen fremden
Sprecher ansieht, und `api/konto.py`, wo ein Sprecher seine eigenen Daten
ansieht. Beide zeigen dieselben Zahlen über dieselbe Datenbank - nur wer
fragen darf, unterscheidet sich, und das entscheiden die Wächter der beiden
Router, nicht diese Datei. Sie kennt keinen Zugang und keinen Token, nur eine
offene `Session` und, wo nötig, die `Sprecher`-Zeile selbst.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from wortlaut import storage

from ..db.models import Aufnahme, Sitzung, Sprecher, Textquelle, Vorlage

# Ein Auszug ohne Grenze wäre bei zehntausend Aufnahmen eine Antwort, die
# niemand liest und kein Browser gern darstellt.
SEITE = 200

# Eine Sitzung ohne Aufnahme ist nichts weiter als ein geöffneter Reiter: Sie
# entsteht schon beim Aufrufen der Aufnahmeseite (`Aufnahme.svelte: beginne`),
# bevor irgendjemand gesprochen hat. In der eigenen Ansicht (`api/konto.py`)
# steht sie darum nur zwischen den Sitzungen, in denen wirklich etwas
# entstanden ist, und lässt den eigenen Fleiß kleiner aussehen, als er war.
# Der Aufsicht (`api/admin.py`) bleibt sie erhalten: Dort ist gerade der leere
# Anlauf eine Auskunft - jemand hat es versucht und nichts aufgenommen.
_HAT_AUFNAHMEN = select(1).where(Aufnahme.session_id == Sitzung.id).exists()


class Kennzahlen(BaseModel):
    aufnahmen: int
    verworfen: int
    sekunden: float
    quellen: int
    einheiten: int
    sitzungen: int
    bytes_audio: int


class ProfilAntwort(BaseModel):
    """Ein Sprecherprofil, wie es überall ausgeliefert wird.

    **Die eine Beschreibung dieses Dings.** Es gab sie zweimal: einmal hier für
    die Aufsicht und einmal in `api/speakers.py` für die Verwaltung. Zwei
    Klassen mit denselben Feldern sind so lange harmlos, wie niemand ein Feld
    hinzufügt - und genau das geschah im September 2026 mit `tempo`. Die
    Verwaltung zeigte „2-fach", die Aufsicht „normal", und beide lasen
    dieselbe Datenbankzeile. Kein Fehler im Code, der die Zahl ausrechnet;
    einer in der Buchführung darüber, was ein Profil überhaupt ist.

    Wer hier ein Feld ergänzt, ergänzt es für alle. Das ist der ganze Zweck
    dieser Klasse.
    """

    id: str
    name: str
    sprache: str
    basismodell: str
    erstellt: str
    # Wann der geltende Zugang ausgegeben wurde; None heißt: keiner da. Der
    # Zugang selbst steht hier nie - er ist nur beim Ausgeben zu sehen.
    zugang_erneuert: str | None = None


def profilfelder(sprecher) -> dict:
    """Die Profilfelder eines Sprechers - die eine Stelle, die sie abliest.

    Dasselbe Argument wie bei `ProfilAntwort`: Zwei Stellen, die ein Objekt in
    dieselben sechs Felder übersetzen, sind zwei Gelegenheiten, eines zu
    vergessen.
    """
    return {
        "id": sprecher.id,
        "name": sprecher.name,
        "sprache": sprecher.sprache,
        "basismodell": sprecher.basismodell,
        "erstellt": sprecher.erstellt,
        "zugang_erneuert": sprecher.zugang_erneuert,
    }


class UebersichtAntwort(ProfilAntwort):
    """Ein Sprecher mit dem Umfang seiner Daten - Profil plus Kennzahlen."""

    # Nie die PIN selbst oder ihr Prüfwert - nur, ob eine gesetzt ist (siehe
    # `services/pin.py`).
    pin_gesetzt: bool
    kennzahlen: Kennzahlen


class Umbenennung(BaseModel):
    """Der neue Name - von der Aufsicht vergeben (`api/admin.py`) oder selbst (`api/konto.py`)."""

    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def _nicht_nur_leerzeichen(cls, wert: str) -> str:
        """Sonst käme ein Sprecher namens „ " heraus - eine leere Zeile in der Liste."""
        if not wert.strip():
            raise ValueError("Der Name darf nicht leer sein.")
        return wert.strip()


class QuelleAntwort(BaseModel):
    id: str
    art: str
    titel: str
    parameter: dict
    aktiv: bool
    einheiten: int
    erstellt: str


class SitzungAntwort(BaseModel):
    id: str
    begonnen: str
    zuletzt_aktiv: str
    aufnahmen: int


class SitzungenAntwort(BaseModel):
    gesamt: int
    ab: int
    sitzungen: list[SitzungAntwort]


class AufnahmeAntwort(BaseModel):
    """Eine Aufnahme mit dem Text, zu dem sie gehört - sonst wäre sie stumm."""

    id: str
    prompt_id: str
    text: str
    quelle_art: str
    dauer_s: float
    pegel_dbfs: float
    modus: str
    status: str
    hinweise: list[str]
    externe_id: str | None
    audio_vorhanden: bool
    erstellt: str


class AufnahmenAntwort(BaseModel):
    gesamt: int
    ab: int
    aufnahmen: list[AufnahmeAntwort]


def profil(
    sitzung: Session,
    sprecher: Sprecher,
    ablage: storage.Ablage,
    nur_sitzungen_mit_aufnahmen: bool = False,
) -> UebersichtAntwort:
    """Profil und Kennzahlen eines Sprechers.

    `nur_sitzungen_mit_aufnahmen` zählt die Sitzungen so, wie `sitzungen_seite`
    sie mit `nur_mit_aufnahmen` auflistet - sonst nennte die Kennzahl eine Zahl,
    die sich in der Liste darunter nicht wiederfinden lässt.
    """
    gueltig = Aufnahme.status == "ok"
    sitzungsfilter = (_HAT_AUFNAHMEN,) if nur_sitzungen_mit_aufnahmen else ()
    bloecke = sitzung.scalars(select(Aufnahme.blob).where(gueltig)).all()
    dauer = select(func.coalesce(func.sum(Aufnahme.dauer_s), 0.0)).where(gueltig)
    return UebersichtAntwort(
        **profilfelder(sprecher),
        pin_gesetzt=sprecher.pin_hash is not None,
        kennzahlen=Kennzahlen(
            aufnahmen=_zaehle(sitzung, Aufnahme, gueltig),
            verworfen=_zaehle(sitzung, Aufnahme, Aufnahme.status == "verworfen"),
            sekunden=float(sitzung.scalar(dauer) or 0.0),
            quellen=_zaehle(sitzung, Textquelle),
            einheiten=_zaehle(sitzung, Vorlage),
            sitzungen=_zaehle(sitzung, Sitzung, *sitzungsfilter),
            bytes_audio=_bytes(ablage, bloecke),
        ),
    )


def quellen(sitzung: Session) -> list[QuelleAntwort]:
    anzahl = (
        select(Vorlage.source_id, func.count().label("einheiten"))
        .group_by(Vorlage.source_id)
        .subquery()
    )
    zeilen = sitzung.execute(
        select(Textquelle, func.coalesce(anzahl.c.einheiten, 0))
        .outerjoin(anzahl, anzahl.c.source_id == Textquelle.id)
        .order_by(Textquelle.erstellt)
    ).all()
    return [
        QuelleAntwort(
            id=quelle.id,
            art=quelle.art,
            titel=quelle.titel,
            parameter=json.loads(quelle.parameter),
            aktiv=quelle.aktiv,
            einheiten=einheiten,
            erstellt=quelle.erstellt,
        )
        for quelle, einheiten in zeilen
    ]


def sitzungen_seite(
    sitzung: Session, ab: int = 0, anzahl: int = SEITE, nur_mit_aufnahmen: bool = False
) -> SitzungenAntwort:
    """Die Sitzungen eines Sprechers, jüngste zuerst, seitenweise.

    Mit `nur_mit_aufnahmen` bleiben die leeren Sitzungen draußen - Zeilen wie
    Gesamtzahl, sonst zeigte der Pager Seiten, auf denen nichts steht (siehe
    `_HAT_AUFNAHMEN`).
    """
    gesamt_abfrage = select(func.count()).select_from(Sitzung)
    aufnahmen_pro_sitzung = (
        select(Aufnahme.session_id, func.count().label("aufnahmen"))
        .group_by(Aufnahme.session_id)
        .subquery()
    )
    seite = (
        select(Sitzung, func.coalesce(aufnahmen_pro_sitzung.c.aufnahmen, 0))
        .outerjoin(aufnahmen_pro_sitzung, aufnahmen_pro_sitzung.c.session_id == Sitzung.id)
        .order_by(Sitzung.begonnen.desc())
        .offset(max(ab, 0))
        .limit(min(max(anzahl, 1), SEITE))
    )
    if nur_mit_aufnahmen:
        gesamt_abfrage = gesamt_abfrage.where(_HAT_AUFNAHMEN)
        seite = seite.where(_HAT_AUFNAHMEN)
    gesamt = sitzung.scalar(gesamt_abfrage) or 0
    zeilen = sitzung.execute(seite).all()
    return SitzungenAntwort(
        gesamt=gesamt,
        ab=max(ab, 0),
        sitzungen=[
            SitzungAntwort(
                id=eintrag.id,
                begonnen=eintrag.begonnen,
                zuletzt_aktiv=eintrag.zuletzt_aktiv,
                aufnahmen=aufnahmen_je,
            )
            for eintrag, aufnahmen_je in zeilen
        ],
    )


def aufnahmen_seite(
    sitzung: Session, ablage: storage.Ablage, ab: int = 0, anzahl: int = SEITE
) -> AufnahmenAntwort:
    """Die Aufnahmen eines Sprechers mit ihrem Text, neueste zuerst, seitenweise."""
    gesamt = sitzung.scalar(select(func.count()).select_from(Aufnahme)) or 0
    treffer = sitzung.execute(
        select(Aufnahme, Vorlage, Textquelle)
        .join(Vorlage, Vorlage.id == Aufnahme.prompt_id)
        .join(Textquelle, Textquelle.id == Vorlage.source_id)
        .order_by(Aufnahme.erstellt.desc())
        .offset(max(ab, 0))
        .limit(min(max(anzahl, 1), SEITE))
    ).all()

    return AufnahmenAntwort(
        gesamt=gesamt,
        ab=max(ab, 0),
        aufnahmen=[
            AufnahmeAntwort(
                id=aufnahme.id,
                prompt_id=aufnahme.prompt_id,
                text=vorlage.text,
                quelle_art=quelle.art,
                dauer_s=aufnahme.dauer_s,
                pegel_dbfs=aufnahme.pegel_dbfs,
                modus=aufnahme.modus,
                status=aufnahme.status,
                hinweise=json.loads(aufnahme.hinweise),
                externe_id=aufnahme.externe_id,
                audio_vorhanden=ablage.pfad(aufnahme.blob).is_file(),
                erstellt=aufnahme.erstellt,
            )
            for aufnahme, vorlage, quelle in treffer
        ],
    )


def _zaehle(sitzung: Session, tabelle: type, *bedingungen) -> int:
    return sitzung.scalar(select(func.count()).select_from(tabelle).where(*bedingungen)) or 0


def _bytes(ablage: storage.Ablage, bloecke: list[str]) -> int:
    """Wie viel Platz die Aufnahmen brauchen - die Zahl, die eine Sicherung plant."""
    gesamt = 0
    for relpfad in bloecke:
        pfad = ablage.pfad(relpfad)
        if pfad.is_file():
            gesamt += pfad.stat().st_size
    return gesamt
