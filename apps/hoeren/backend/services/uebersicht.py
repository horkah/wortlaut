"""Was ein Sprecher an Daten hat - Profil, Textquellen, Sitzungen, Aufnahmen.

Die Aufsicht (`api/admin.py`) und der Sprecher selbst (`api/konto.py`) lesen
hier dasselbe. Wer fragen darf, entscheiden ihre Wächter; diese Datei kennt
nur eine offene `Session`.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session
from wortlaut import laeufe, registry, storage

from apps.schreiben.backend.config import einstellungen as schreiben_einstellungen
from apps.schreiben.backend.deps import aktive_ref

from ..config import einstellungen
from ..db.models import (
    GUELTIG,
    VERWORFEN,
    Aufnahme,
    Erkennung,
    Sitzung,
    Sprecher,
    Textquelle,
    Vorlage,
)
from . import zuschnitt

# Höchstens so viele Zeilen je Seite.
SEITE = 200

# ── Die Aufnahmenliste ──────────────────────────────────────────────────────
#
# Sortiert nach dem Datum der Aufnahme, nach dem der letzten Änderung in
# „Editieren" (ohne Änderung: das der Aufnahme) oder nach der Genauigkeit, mit
# der das Modell von „schreiben" sie gehört hat - nicht gemessene zählen still
# als 0, editierte still als 100 (`EDITIERT_QUALITAET`). Vorgabe: zuletzt
# editiert zuerst.
NACH_AUFNAHME = "aufgenommen"
NACH_AENDERUNG = "geaendert"
NACH_QUALITAET = "qualitaet"
SORTIERUNGEN = (NACH_AUFNAHME, NACH_AENDERUNG, NACH_QUALITAET)

# Welche Aufnahmen: nach ihrer Art, überschneidungsfrei - jede Aufnahme gehört
# zu genau einer (`_art`). Verworfen ist eine Art für sich, gleich wie sie
# gesprochen war. Eine gültige Korrektur aus „schreiben" ist geprüft oder
# nicht (`recordings.validiert`); jede andere gültige Aufnahme zählt nach
# ihrem Modus. Vorgabe: alle außer den verworfenen.
GELESEN = "gelesen"
NACHGESPROCHEN = "nachgesprochen"
FREI = "frei"
KORREKTUR_GEPRUEFT = "korrektur_geprueft"
KORREKTUR_UNGEPRUEFT = "korrektur_ungeprueft"
ARTEN = (GELESEN, NACHGESPROCHEN, FREI, KORREKTUR_GEPRUEFT, KORREKTUR_UNGEPRUEFT, VERWORFEN)

# **Editiert** ist eine Aufnahme, die in „Editieren" gespeichert wurde und auf
# der das Modell von „schreiben" seitdem nicht gelernt hat (`_editiert`). Ein
# Mensch hat sie gehört und berichtigt; beim Sortieren nach Genauigkeit zählt
# sie still als 100. Angezeigt wird statt der Zahl die Marke „editiert" - gemessen
# ist an ihr nichts. Lernt ein neuer Stand auf ihr und wird er freigegeben,
# gilt wieder, was gemessen ist.
EDITIERT_QUALITAET = 100.0
VORGABE_ARTEN = tuple(art for art in ARTEN if art != VERWORFEN)

# Die Farbskala der Genauigkeit an den Karten: Rot am 10-%-, Dunkelgrün am
# 90-%-Quantil dessen, was das Modell bei diesem Sprecher gemessen hat. Rot
# liegt nie über 50, Dunkelgrün nie unter 85 - sonst wäre bei einem schwer
# verständlichen Sprecher alles grün und bei einem leichten alles rot.
ROT_HOECHSTENS = 50.0
GRUEN_MINDESTENS = 85.0

# Eine Sitzung entsteht beim Öffnen der Aufnahmeseite, vor dem ersten Wort.
# Die eigene Ansicht zeigt nur Sitzungen mit Aufnahmen; die Aufsicht alle -
# dort ist der leere Anlauf eine Auskunft.
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
    """Ein Sprecherprofil, wie es überall ausgeliefert wird - die eine
    Beschreibung für Verwaltung und Aufsicht; ein neues Feld erreicht beide."""

    id: str
    name: str
    sprache: str
    erstellt: str
    # Wann der geltende Zugang ausgegeben wurde; None heißt keiner.
    zugang_erneuert: str | None = None


def profilfelder(sprecher) -> dict:
    """Die Profilfelder eines Sprechers - die eine Stelle, die sie abliest."""
    return {
        "id": sprecher.id,
        "name": sprecher.name,
        "sprache": sprecher.sprache,
        "erstellt": sprecher.erstellt,
        "zugang_erneuert": sprecher.zugang_erneuert,
    }


class UebersichtAntwort(ProfilAntwort):
    """Ein Sprecher mit dem Umfang seiner Daten - Profil plus Kennzahlen."""

    # Nur, ob eine PIN gesetzt ist.
    pin_gesetzt: bool
    kennzahlen: Kennzahlen


class Umbenennung(BaseModel):
    """Der neue Name - von der Aufsicht vergeben (`api/admin.py`) oder selbst (`api/konto.py`)."""

    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def _nicht_nur_leerzeichen(cls, wert: str) -> str:
        """Kein Name aus Leerzeichen."""
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
    # Wann zuletzt in „Editieren" gespeichert; leer heißt nie.
    geaendert: str | None = None
    quelle_id: str = ""
    quelle_titel: str = ""
    validiert: bool = False
    # Die Genauigkeit (0 bis 100), mit der das Modell von „schreiben" diese
    # Aufnahme gehört hat; leer, solange nicht gemessen.
    qualitaet: float | None = None
    # Editiert und seitdem nicht gelernt (`EDITIERT_QUALITAET`) - dann steht die
    # Marke statt der Zahl.
    editiert: bool = False


class Skala(BaseModel):
    """Wo die Farbskala der Genauigkeit rot und wo sie dunkelgrün ist."""

    rot: float = ROT_HOECHSTENS
    gruen: float = GRUEN_MINDESTENS


class QuelleWahl(BaseModel):
    """Eine Textquelle, nach der sich die Liste filtern lässt."""

    id: str
    titel: str
    art: str


class AufnahmenAntwort(BaseModel):
    gesamt: int
    ab: int
    aufnahmen: list[AufnahmeAntwort]
    # Wonach sich filtern lässt - die Textquellen mit Aufnahmen.
    quellen: list[QuelleWahl] = []
    # Das Modell, dessen Genauigkeit `qualitaet` ist, und seine Farbskala.
    modell: str = ""
    skala: Skala = Skala()
    # Jede Art mit ihrer Zahl, in der Reihenfolge von `ARTEN`.
    arten: list[ArtZahl] = []


class ArtZahl(BaseModel):
    """Eine Art und wie viele Aufnahmen sie hat - mit dem Filter nach Quelle."""

    art: str
    anzahl: int


class Eintrag(BaseModel):
    """Eine Aufnahme in der Reihenfolge der Liste - ohne alles Übrige."""

    id: str
    status: str


def profil(
    sitzung: Session,
    sprecher: Sprecher,
    ablage: storage.Ablage,
    nur_sitzungen_mit_aufnahmen: bool = False,
) -> UebersichtAntwort:
    """Profil und Kennzahlen eines Sprechers.

    `nur_sitzungen_mit_aufnahmen` lässt leere Sitzungen aus der Zahl.
    """
    gueltig = Aufnahme.status == GUELTIG
    sitzungsfilter = (_HAT_AUFNAHMEN,) if nur_sitzungen_mit_aufnahmen else ()
    bloecke = sitzung.scalars(select(Aufnahme.blob).where(gueltig)).all()
    dauer = select(func.coalesce(func.sum(Aufnahme.dauer_s), 0.0)).where(gueltig)
    return UebersichtAntwort(
        **profilfelder(sprecher),
        pin_gesetzt=sprecher.pin_hash is not None,
        kennzahlen=Kennzahlen(
            aufnahmen=_zaehle(sitzung, Aufnahme, gueltig),
            verworfen=_zaehle(sitzung, Aufnahme, Aufnahme.status == VERWORFEN),
            sekunden=float(sitzung.scalar(dauer) or 0.0),
            quellen=_zaehle(sitzung, Textquelle),
            einheiten=_zaehle(sitzung, Vorlage),
            sitzungen=_zaehle(sitzung, Sitzung, *sitzungsfilter),
            bytes_audio=_bytes(ablage, bloecke),
        ),
    )


def quellen_mit_einheiten(sitzung: Session, *bedingungen) -> list[tuple[Textquelle, int]]:
    """Die Textquellen mit der Zahl ihrer Vorlagen, älteste zuerst."""
    anzahl = (
        select(Vorlage.source_id, func.count().label("einheiten"))
        .group_by(Vorlage.source_id)
        .subquery()
    )
    return list(
        sitzung.execute(
            select(Textquelle, func.coalesce(anzahl.c.einheiten, 0))
            .outerjoin(anzahl, anzahl.c.source_id == Textquelle.id)
            .where(*bedingungen)
            .order_by(Textquelle.erstellt)
        ).tuples()
    )


def quellen(sitzung: Session) -> list[QuelleAntwort]:
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
        for quelle, einheiten in quellen_mit_einheiten(sitzung)
    ]


def sitzungen_seite(sitzung: Session, ab: int = 0, anzahl: int = SEITE) -> SitzungenAntwort:
    """Die Sitzungen eines Sprechers, jüngste zuerst, seitenweise - auch die leeren."""
    gesamt = sitzung.scalar(select(func.count()).select_from(Sitzung)) or 0
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


def aufnahmezeiten(sitzung: Session) -> list[str]:
    """Wann jede gültige Aufnahme entstand, älteste zuerst - für den Kalender.

    Nur die Zeitpunkte, roh in UTC: Auf welchen Tag eine Aufnahme fällt,
    hängt von der Zeitzone des Betrachters ab, und die kennt nur der Browser
    (`packages/ui/zeit.ts`). Gezählt wird wie in den Kennzahlen - verworfene
    Aufnahmen nicht.
    """
    abfrage = (
        select(Aufnahme.erstellt).where(Aufnahme.status == GUELTIG).order_by(Aufnahme.erstellt)
    )
    return list(sitzung.scalars(abfrage))


AUFSTEIGEND = "auf"
ABSTEIGEND = "ab"


def wahl_aus(quelle: str, arten: str, sortierung: str, richtung: str) -> dict:
    """Die Wahl der Liste aus den Parametern einer Anfrage; `ValueError` bei Unbekanntem.

    `arten` durch Kommas getrennt; leer heißt keine.
    """
    if richtung not in (AUFSTEIGEND, ABSTEIGEND):
        raise ValueError(f"Unbekannte Richtung: {richtung}")
    if sortierung not in SORTIERUNGEN:
        raise ValueError(f"Unbekannte Sortierung: {sortierung}")
    gewaehlt = tuple(art for art in arten.split(",") if art)
    if unbekannt := [art for art in gewaehlt if art not in ARTEN]:
        raise ValueError(f"Unbekannte Art: {', '.join(unbekannt)}")
    return {
        "quelle": quelle,
        "arten": gewaehlt,
        "sortierung": sortierung,
        "absteigend": richtung == ABSTEIGEND,
    }


def art_von(aufnahme: Aufnahme, korrektur: bool) -> str:
    """Die Art einer einzelnen Aufnahme - dieselbe Regel wie `_art`."""
    if aufnahme.status == VERWORFEN:
        return VERWORFEN
    if korrektur:
        return KORREKTUR_GEPRUEFT if aufnahme.validiert else KORREKTUR_UNGEPRUEFT
    return aufnahme.modus


@dataclass(frozen=True)
class Gelernt:
    """Worauf ein Stand gelernt hat: die Aufnahmen und wann sein Lauf sie einfror."""

    seit: str
    aufnahmen: frozenset[str]


def gelernt_von(modell: str) -> Gelernt | None:
    """Was das Modell von „schreiben" gelernt hat - `None` bei einem Grundmodell."""
    if not registry.ist_stand(modell):
        return None
    datenverzeichnis = einstellungen().data_dir
    try:
        job = str(registry.lies_ref(datenverzeichnis, modell).get("job_id") or "")
    except (OSError, ValueError):
        return None
    lauf = laeufe.lies_lauf(datenverzeichnis, job) if job else None
    if lauf is None:
        return None
    return Gelernt(
        seit=str(lauf.auftrag.get("erstellt") or ""),
        aufnahmen=frozenset(
            str(zeile.get("recording_id") or "") for zeile in laeufe.manifestzeilen(lauf.verzeichnis)
        ),
    )


def _editiert(gelernt: Gelernt | None):
    """Ob eine Aufnahme editiert ist, als Ausdruck der Abfrage (siehe `EDITIERT_QUALITAET`)."""
    gespeichert = Aufnahme.geaendert.is_not(None)
    if gelernt is None:
        return gespeichert
    seitdem_gelernt = and_(
        Aufnahme.id.in_(gelernt.aufnahmen), Aufnahme.geaendert < gelernt.seit
    )
    return and_(gespeichert, ~seitdem_gelernt)


def ist_editiert(aufnahme: Aufnahme, gelernt: Gelernt | None) -> bool:
    """Dieselbe Regel wie `_editiert`, für eine einzelne Aufnahme."""
    if not aufnahme.geaendert:
        return False
    return not (
        gelernt is not None
        and aufnahme.id in gelernt.aufnahmen
        and aufnahme.geaendert < gelernt.seit
    )


def _qualitaet(gelernt: Gelernt | None):
    """Die Genauigkeit zum Sortieren: editiert 100, sonst gemessen."""
    return case((_editiert(gelernt), EDITIERT_QUALITAET), else_=Erkennung.genauigkeit)


def _art():
    """Die Art einer Aufnahme als Ausdruck der Abfrage (siehe `ARTEN`)."""
    korrektur = Textquelle.art == "korrektur"
    return case(
        (Aufnahme.status == VERWORFEN, VERWORFEN),
        (and_(korrektur, Aufnahme.validiert), KORREKTUR_GEPRUEFT),
        (korrektur, KORREKTUR_UNGEPRUEFT),
        else_=Aufnahme.modus,
    )


def diktiermodell(sprecher_id: str) -> str:
    """Womit „schreiben" für diesen Menschen diktiert - der Name, unter dem es misst."""
    konfiguration = schreiben_einstellungen()
    return aktive_ref(konfiguration, sprecher_id) or konfiguration.asr_modell


def _liste(
    modell: str,
    quelle: str = "",
    arten: tuple[str, ...] = VORGABE_ARTEN,
    sortierung: str = NACH_AENDERUNG,
    absteigend: bool = True,
):
    """Die Abfrage hinter Seite und Reihenfolge: gefiltert, sortiert, mit
    Genauigkeit und ob editiert.

    Die Wahl ist geprüft (`wahl_aus`).
    """
    gelernt = gelernt_von(modell)
    abfrage = (
        select(Aufnahme, Vorlage, Textquelle, Erkennung.genauigkeit, _editiert(gelernt))
        .join(Vorlage, Vorlage.id == Aufnahme.prompt_id)
        .join(Textquelle, Textquelle.id == Vorlage.source_id)
        .outerjoin(
            Erkennung, and_(Erkennung.recording_id == Aufnahme.id, Erkennung.modell == modell)
        )
    )
    if quelle:
        abfrage = abfrage.where(Textquelle.id == quelle)
    abfrage = abfrage.where(_art().in_(arten))
    erstes = {
        NACH_AUFNAHME: Aufnahme.erstellt,
        NACH_AENDERUNG: func.coalesce(Aufnahme.geaendert, Aufnahme.erstellt),
        NACH_QUALITAET: func.coalesce(_qualitaet(gelernt), 0.0),
    }[sortierung]
    merkmale = (erstes, *zuschnitt.reihenfolge())
    return abfrage.order_by(*(m.desc() if absteigend else m.asc() for m in merkmale))


def skala(sitzung: Session, modell: str) -> Skala:
    """Die Farbskala aus allen gemessenen gültigen Aufnahmen dieses Sprechers."""
    werte = list(
        sitzung.scalars(
            select(Erkennung.genauigkeit)
            .join(Aufnahme, Aufnahme.id == Erkennung.recording_id)
            .where(Erkennung.modell == modell, Aufnahme.status == GUELTIG)
        )
    )
    if len(werte) < 2:
        return Skala()
    stufen = statistics.quantiles(werte, n=10, method="inclusive")
    return Skala(
        rot=round(min(stufen[0], ROT_HOECHSTENS), 2),
        gruen=round(max(stufen[-1], GRUEN_MINDESTENS), 2),
    )


def reihenfolge(sitzung: Session, modell: str, **wahl) -> list[Eintrag]:
    """Alle Aufnahmen in der Reihenfolge der Liste - für das Weiterblättern im Editor."""
    return [
        Eintrag(id=aufnahme.id, status=aufnahme.status)
        for aufnahme, *_ in sitzung.execute(_liste(modell, **wahl)).all()
    ]


def aufnahmen_seite(
    sitzung: Session,
    ablage: storage.Ablage,
    ab: int = 0,
    anzahl: int = SEITE,
    *,
    modell: str = "",
    **wahl,
) -> AufnahmenAntwort:
    """Die Aufnahmen eines Sprechers mit ihrem Text, gefiltert und sortiert, seitenweise.

    `wahl` sind `quelle`, `arten`, `sortierung` und `absteigend` (`_liste`).
    """
    abfrage = _liste(modell, **wahl)
    gesamt = sitzung.scalar(select(func.count()).select_from(abfrage.subquery())) or 0
    treffer = sitzung.execute(abfrage.offset(max(ab, 0)).limit(min(max(anzahl, 1), SEITE))).all()
    zaehlung = (
        select(_art(), func.count())
        .select_from(Aufnahme)
        .join(Vorlage, Vorlage.id == Aufnahme.prompt_id)
        .join(Textquelle, Textquelle.id == Vorlage.source_id)
        .group_by(_art())
    )
    if wahl.get("quelle"):
        zaehlung = zaehlung.where(Textquelle.id == wahl["quelle"])
    je_art = dict(sitzung.execute(zaehlung).tuples().all())
    quellen = sitzung.execute(
        select(Textquelle)
        .where(Textquelle.id.in_(select(Vorlage.source_id).join(Aufnahme)))
        .order_by(Textquelle.erstellt)
    ).scalars()

    return AufnahmenAntwort(
        gesamt=gesamt,
        ab=max(ab, 0),
        modell=modell,
        skala=skala(sitzung, modell),
        arten=[ArtZahl(art=art, anzahl=je_art.get(art, 0)) for art in ARTEN],
        quellen=[QuelleWahl(id=quelle.id, titel=quelle.titel, art=quelle.art) for quelle in quellen],
        aufnahmen=[
            AufnahmeAntwort(
                id=aufnahme.id,
                prompt_id=aufnahme.prompt_id,
                text=aufnahme.text_zu(vorlage),
                quelle_art=quelle.art,
                dauer_s=aufnahme.dauer_s,
                pegel_dbfs=aufnahme.pegel_dbfs,
                modus=aufnahme.modus,
                status=aufnahme.status,
                hinweise=json.loads(aufnahme.hinweise),
                externe_id=aufnahme.externe_id,
                audio_vorhanden=ablage.pfad(aufnahme.blob).is_file(),
                erstellt=aufnahme.erstellt,
                geaendert=aufnahme.geaendert,
                quelle_id=quelle.id,
                quelle_titel=quelle.titel,
                validiert=bool(aufnahme.validiert),
                qualitaet=genauigkeit,
                editiert=bool(editiert),
            )
            for aufnahme, vorlage, quelle, genauigkeit, editiert in treffer
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
