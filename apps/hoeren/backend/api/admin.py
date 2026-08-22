"""Die Aufsicht: über alle Korpora sehen, sichern, umbenennen, löschen.

Alles hier hängt an `WORTLAUT_ADMIN_TOKEN` (siehe `deps.py`). Ohne gesetzten
Token ist dieser ganze Router zu — auch in der Entwicklung.

Der Unterschied zu jedem anderen Weg dieser App: Hier steht der Sprecher
**in der Adresse**. Er ist nicht abgeleitet, weil die Aufsicht keinen eigenen
hat; sie sieht über alle hinweg. Damit das nicht die stille Verwechslung
zurückholt, gegen die der Zugang als Kennung angetreten ist, liegen diese Wege
unter einem eigenen Präfix und nirgends sonst: Wer `/api/admin/…` liest, sieht
sofort, dass hier jemand von außen auf einen fremden Korpus schaut.

**Eine Grenze gibt es, und sie ist absichtlich hart:** Es gibt keinen Weg, der
mehr als einen Sprecher löscht. Sichern über alle geht, löschen nur einzeln,
und auch das nur mit der Kennung als Bestätigung im Aufruf. Ein Versehen soll
höchstens eine Person kosten, nie den ganzen Bestand.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from wortlaut import corpus, sicherung, storage

from ..config import einstellungen
from ..db.models import Aufnahme, Sitzung, Sprecher, Textquelle, Vorlage
from ..deps import Ablage, Aufsicht, engine_fuer, vergiss_engine
from ..services import export, loeschung

router = APIRouter(prefix="/api/admin", tags=["Aufsicht"], dependencies=[Aufsicht])

# Ein Auszug ohne Grenze wäre bei zehntausend Aufnahmen eine Antwort, die
# niemand liest und kein Browser gern darstellt.
SEITE = 200

Bestaetigung = Annotated[
    str,
    Query(
        description=(
            "Zur Bestätigung die Kennung des Sprechers wiederholen. "
            "Löschen ist nicht rückgängig zu machen."
        )
    ),
]


# ── Ansehen ─────────────────────────────────────────────────────────────────


class Kennzahlen(BaseModel):
    aufnahmen: int
    verworfen: int
    sekunden: float
    quellen: int
    einheiten: int
    sitzungen: int
    bytes_audio: int


class UebersichtAntwort(BaseModel):
    """Ein Sprecher in der Liste der Aufsicht — Profil plus Umfang."""

    id: str
    name: str
    sprache: str
    basismodell: str
    erstellt: str
    zugang_erneuert: str | None
    kennzahlen: Kennzahlen


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


class AufnahmeAntwort(BaseModel):
    """Eine Aufnahme mit dem Text, zu dem sie gehört — sonst wäre sie stumm."""

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


class EinsichtAntwort(BaseModel):
    sprecher: UebersichtAntwort
    quellen: list[QuelleAntwort]
    sitzungen: list[SitzungAntwort]


class AufnahmenAntwort(BaseModel):
    gesamt: int
    ab: int
    aufnahmen: list[AufnahmeAntwort]


class Umbenennung(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def _nicht_nur_leerzeichen(cls, wert: str) -> str:
        """Sonst käme ein Sprecher namens „ " heraus — eine leere Zeile in der Liste."""
        if not wert.strip():
            raise ValueError("Der Name darf nicht leer sein.")
        return wert.strip()


@router.get("/speakers", response_model=list[UebersichtAntwort])
def uebersicht(ablage: Ablage) -> list[UebersichtAntwort]:
    """Alle Sprecher mit dem Umfang ihrer Daten — die Startseite der Aufsicht."""
    antworten = []
    for sprecher_id in corpus.sprecher_ids(einstellungen().data_dir):
        with Session(engine_fuer(sprecher_id)) as sitzung:
            sprecher = sitzung.get(Sprecher, sprecher_id)
            if sprecher is not None:
                antworten.append(_uebersicht(sitzung, sprecher, ablage))
    return antworten


@router.get("/speakers/{sprecher_id}", response_model=EinsichtAntwort)
def einsicht(sprecher_id: str, ablage: Ablage) -> EinsichtAntwort:
    """Was in der Datenbank **eines** Sprechers steht: Quellen und Sitzungen.

    Die Aufnahmen stehen nicht darin, sondern hinter einem eigenen Weg: Es sind
    Tausende, und sie sind das Einzige, was seitenweise geholt werden muss.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        return EinsichtAntwort(
            sprecher=_uebersicht(sitzung, sprecher, ablage),
            quellen=_quellen(sitzung),
            sitzungen=_sitzungen(sitzung),
        )


@router.get("/speakers/{sprecher_id}/recordings", response_model=AufnahmenAntwort)
def aufnahmen(
    sprecher_id: str, ablage: Ablage, ab: int = 0, anzahl: int = SEITE
) -> AufnahmenAntwort:
    """Die Aufnahmen eines Sprechers, neueste zuerst, seitenweise."""
    with Session(engine_fuer(sprecher_id)) as sitzung:
        _hole(sitzung, sprecher_id)
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


@router.get("/speakers/{sprecher_id}/recordings/{aufnahme_id}/audio")
def abhoeren(sprecher_id: str, aufnahme_id: str, ablage: Ablage) -> FileResponse:
    """Hineinhören, bevor gelöscht wird — sonst löscht die Aufsicht blind."""
    with Session(engine_fuer(sprecher_id)) as sitzung:
        _hole(sitzung, sprecher_id)
        aufnahme = _hole_aufnahme(sitzung, aufnahme_id)
        pfad = ablage.pfad(aufnahme.blob)
    if not pfad.is_file():
        raise HTTPException(status_code=404, detail="Zu dieser Aufnahme liegt kein Audio mehr.")
    return FileResponse(pfad, media_type="audio/wav")


# ── Umbenennen ──────────────────────────────────────────────────────────────


@router.patch("/speakers/{sprecher_id}", response_model=UebersichtAntwort)
def benenne_um(sprecher_id: str, aenderung: Umbenennung, ablage: Ablage) -> UebersichtAntwort:
    """Nur der Name ändert sich.

    Die Kennung bleibt, was sie ist: Sie steckt in jedem ausgegebenen Zugang,
    in den Pfaden der Ablage und in der `.env` von „schreiben". Ein Name ist
    eine Beschriftung, eine Kennung ist eine Zusage.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        sprecher.name = aenderung.name
        sitzung.commit()
        return _uebersicht(sitzung, sprecher, ablage)


# ── Sichern und ausleiten ───────────────────────────────────────────────────


@router.get("/speakers/{sprecher_id}/sicherung")
def sicherung_eines(sprecher_id: str) -> FileResponse:
    """Der vollständige Stand eines Sprechers als `.tgz` — zum Zurückspielen.

    Enthält Korpus und Diktate, wie sie im Datenverzeichnis liegen, mit einer
    in sich stimmigen Kopie der Datenbank. Zurück kommt der Stand mit
    `scripts/restore.py` oder schlicht mit `tar xzf` (siehe
    `wortlaut/sicherung.py`).
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        beschreibung = {"umfang": "sprecher", "sprecher": [_kurz(sprecher)]}

    return _archiv(
        f"wortlaut-{sprecher_id}-{sicherung.zeitmarke()}.tgz",
        lambda ziel: sicherung.schreibe_archiv(
            einstellungen().data_dir,
            loeschung.datenverzeichnisse(sprecher_id),
            ziel,
            beschreibung=beschreibung,
        ),
        "application/gzip",
    )


@router.get("/sicherung")
def sicherung_aller() -> FileResponse:
    """Der ganze Bestand als **eine** `.tgz` — alle Korpora, alle Diktate.

    Das ist die Sicherung, die man wegträgt: Ein Server weniger, und dieses
    eine Archiv stellt alles wieder her. Modellstände sind nicht darin — sie
    sind groß und lassen sich aus dem Korpus neu rechnen; die Aufnahmen sind
    das, was unwiederbringlich ist.
    """
    konfiguration = einstellungen()
    sprecher_liste = []
    verzeichnisse: list[str] = []
    for sprecher_id in corpus.sprecher_ids(konfiguration.data_dir):
        verzeichnisse.extend(loeschung.datenverzeichnisse(sprecher_id))
        with Session(engine_fuer(sprecher_id)) as sitzung:
            sprecher = sitzung.get(Sprecher, sprecher_id)
            if sprecher is not None:
                sprecher_liste.append(_kurz(sprecher))

    beschreibung = {"umfang": "gesamt", "sprecher": sprecher_liste}
    return _archiv(
        f"wortlaut-gesamt-{sicherung.zeitmarke()}.tgz",
        lambda ziel: sicherung.schreibe_archiv(
            konfiguration.data_dir, verzeichnisse, ziel, beschreibung=beschreibung
        ),
        "application/gzip",
    )


@router.get("/speakers/{sprecher_id}/datensatz")
def datensatz(sprecher_id: str, ablage: Ablage) -> FileResponse:
    """Text-Audio-Paare als `.zip` — für Training und Ansehen von außen.

    Keine Sicherung, sondern ein Auszug in Ordnerform (siehe
    `services/export.py`).
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        return _archiv(
            f"wortlaut-{sprecher_id}-datensatz-{sicherung.zeitmarke()}.zip",
            lambda ziel: export.datensatz_zip(sitzung, sprecher, ablage, ziel),
            "application/zip",
        )


# ── Löschen ─────────────────────────────────────────────────────────────────
#
# Drei Stufen, jede enger als die vorige: eine Aufnahme, alle Aufnahmen einer
# Person, die Person. Eine vierte Stufe „alle Personen" gibt es nicht und soll
# es nicht geben — sie wäre ein Knopf, der einmal im Leben gedrückt wird, und
# dann versehentlich.


@router.delete("/speakers/{sprecher_id}/recordings/{aufnahme_id}", status_code=204)
def loesche_aufnahme(sprecher_id: str, aufnahme_id: str, ablage: Ablage) -> None:
    """Eine Aufnahme wirklich löschen: Audio und Datensatz.

    Der Unterschied zum Verwerfen durch den Sprecher (`api/recordings.py`):
    Dort bleibt die Zeile als Spur stehen, damit die Warteschlange die Vorlage
    wieder anbietet. Hier räumt jemand auf — dann soll auch nichts stehen
    bleiben. Die Vorlage wird dadurch ebenfalls wieder offen.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        _hole(sitzung, sprecher_id)
        aufnahme = _hole_aufnahme(sitzung, aufnahme_id)
        ablage.loesche(aufnahme.blob)
        sitzung.delete(aufnahme)
        sitzung.commit()


@router.delete("/speakers/{sprecher_id}/recordings", status_code=200)
def loesche_alle_aufnahmen(
    sprecher_id: str, bestaetigung: Bestaetigung, ablage: Ablage
) -> dict[str, int]:
    """Alle Aufnahmen eines Sprechers — Profil, Quellen und Vorlagen bleiben.

    Danach steht die Warteschlange wieder ganz am Anfang: Der Text ist noch da,
    gesprochen ist nichts mehr. Das ist der Fall „neu anfangen", nicht der Fall
    „Person löschen" — dafür gibt es den Weg darunter.
    """
    _pruefe_bestaetigung(sprecher_id, bestaetigung)
    with Session(engine_fuer(sprecher_id)) as sitzung:
        _hole(sitzung, sprecher_id)
        alle = sitzung.scalars(select(Aufnahme)).all()
        for aufnahme in alle:
            ablage.loesche(aufnahme.blob)
        sitzung.execute(delete(Aufnahme))
        sitzung.commit()
        return {"geloescht": len(alle)}


@router.delete("/speakers/{sprecher_id}", status_code=200)
def loesche_sprecher(sprecher_id: str, bestaetigung: Bestaetigung) -> dict[str, list[str]]:
    """Eine Person vollständig löschen — Korpus, Diktate, Modelle, Schnappschüsse.

    Dasselbe, was `scripts/purge_speaker.py` auf der Kommandozeile tut; beide
    fragen `services/loeschung.py`, damit es nicht zwei Vorstellungen davon
    gibt, was zu einer Person gehört.

    Es gibt hier bewusst keine Mehrzahl: Der Weg nimmt genau eine Kennung, und
    die muss zur Bestätigung ein zweites Mal dastehen. Wer zwei Personen
    löschen will, tut es zweimal — und denkt dabei zweimal nach.
    """
    _pruefe_bestaetigung(sprecher_id, bestaetigung)
    konfiguration = einstellungen()
    if not corpus.datenbank_pfad(konfiguration.data_dir, sprecher_id).is_file():
        raise HTTPException(status_code=404, detail="Unbekannter Sprecher")

    # Erst die Verbindung aus dem Zwischenspeicher nehmen: Eine offene Engine
    # auf eine gelöschte Datei legte die Datei beim nächsten Zugriff wieder an.
    vergiss_engine(sprecher_id)
    entfernt = loeschung.loesche(konfiguration.data_dir, sprecher_id)
    return {
        "geloescht": [str(pfad) for pfad in entfernt],
        "zu_pruefen": [str(pfad) for pfad in loeschung.ohne_marke(konfiguration.data_dir)],
    }


# ── Innereien ───────────────────────────────────────────────────────────────


def _hole(sitzung: Session, sprecher_id: str) -> Sprecher:
    sprecher = sitzung.get(Sprecher, sprecher_id)
    if sprecher is None:
        raise HTTPException(status_code=404, detail="Unbekannter Sprecher")
    return sprecher


def _hole_aufnahme(sitzung: Session, aufnahme_id: str) -> Aufnahme:
    aufnahme = sitzung.get(Aufnahme, aufnahme_id)
    if aufnahme is None:
        raise HTTPException(status_code=404, detail="Unbekannte Aufnahme")
    return aufnahme


def _pruefe_bestaetigung(sprecher_id: str, bestaetigung: str) -> None:
    """Die Kennung muss zweimal dastehen — einmal als Ziel, einmal als Absicht."""
    if bestaetigung != sprecher_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Zum Löschen muss `bestaetigung` die Kennung des Sprechers wiederholen "
                f"({sprecher_id})."
            ),
        )


def _kurz(sprecher: Sprecher) -> dict[str, str]:
    return {"id": sprecher.id, "name": sprecher.name}


def _uebersicht(
    sitzung: Session, sprecher: Sprecher, ablage: storage.Ablage
) -> UebersichtAntwort:
    gueltig = Aufnahme.status == "ok"
    bloecke = sitzung.scalars(select(Aufnahme.blob).where(gueltig)).all()
    dauer = select(func.coalesce(func.sum(Aufnahme.dauer_s), 0.0)).where(gueltig)
    return UebersichtAntwort(
        id=sprecher.id,
        name=sprecher.name,
        sprache=sprecher.sprache,
        basismodell=sprecher.basismodell,
        erstellt=sprecher.erstellt,
        zugang_erneuert=sprecher.zugang_erneuert,
        kennzahlen=Kennzahlen(
            aufnahmen=_zaehle(sitzung, Aufnahme, gueltig),
            verworfen=_zaehle(sitzung, Aufnahme, Aufnahme.status == "verworfen"),
            sekunden=float(sitzung.scalar(dauer) or 0.0),
            quellen=_zaehle(sitzung, Textquelle),
            einheiten=_zaehle(sitzung, Vorlage),
            sitzungen=_zaehle(sitzung, Sitzung),
            bytes_audio=_bytes(ablage, bloecke),
        ),
    )


def _zaehle(sitzung: Session, tabelle: type, *bedingungen) -> int:
    return sitzung.scalar(select(func.count()).select_from(tabelle).where(*bedingungen)) or 0


def _bytes(ablage: storage.Ablage, bloecke: list[str]) -> int:
    """Wie viel Platz die Aufnahmen brauchen — die Zahl, die eine Sicherung plant."""
    gesamt = 0
    for relpfad in bloecke:
        pfad = ablage.pfad(relpfad)
        if pfad.is_file():
            gesamt += pfad.stat().st_size
    return gesamt


def _quellen(sitzung: Session) -> list[QuelleAntwort]:
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


def _sitzungen(sitzung: Session) -> list[SitzungAntwort]:
    anzahl = (
        select(Aufnahme.session_id, func.count().label("aufnahmen"))
        .group_by(Aufnahme.session_id)
        .subquery()
    )
    zeilen = sitzung.execute(
        select(Sitzung, func.coalesce(anzahl.c.aufnahmen, 0))
        .outerjoin(anzahl, anzahl.c.session_id == Sitzung.id)
        .order_by(Sitzung.begonnen.desc())
    ).all()
    return [
        SitzungAntwort(
            id=eintrag.id,
            begonnen=eintrag.begonnen,
            zuletzt_aktiv=eintrag.zuletzt_aktiv,
            aufnahmen=aufnahmen_je,
        )
        for eintrag, aufnahmen_je in zeilen
    ]


def _archiv(dateiname: str, baue: Callable[[Path], Path], medientyp: str) -> FileResponse:
    """Ein Archiv bauen, ausliefern und danach wieder wegräumen.

    Gebaut wird in eine temporäre Datei und nicht in den Arbeitsspeicher: Ein
    Korpus kann Gigabyte groß sein. Aufgeräumt wird über eine
    Hintergrundaufgabe — sie läuft, nachdem die Antwort durch ist, denn vorher
    liest Starlette noch aus genau dieser Datei.
    """
    verzeichnis = Path(tempfile.mkdtemp(prefix="wortlaut-ausleitung-"))
    try:
        baue(verzeichnis / dateiname)
    except Exception:
        shutil.rmtree(verzeichnis, ignore_errors=True)
        raise
    return FileResponse(
        verzeichnis / dateiname,
        media_type=medientyp,
        filename=dateiname,
        background=BackgroundTask(shutil.rmtree, verzeichnis, ignore_errors=True),
    )
