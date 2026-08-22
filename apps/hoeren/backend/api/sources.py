"""Textquellen: LLM-Thema oder hochgeladener Text.

Beide Wege enden gleich: Text → `chunker.schneide()` → Vorlagen, die hinten an
die Warteschlange angehängt werden. Herkunft und Erzeugungsparameter werden in
`text_sources.parameter` festgehalten, damit später nachvollziehbar ist, woher
eine Vorlage stammt.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from wortlaut import ids
from wortlaut.text import chunker, llm, upload

from ..config import einstellungen
from ..db.models import Aufnahme, Textquelle, Vorlage, jetzt
from ..deps import Datenbank, SprecherId
from ..services.prompt_queue import naechste_position

router = APIRouter(prefix="/api/sources", tags=["Textquellen"])

# Hochgeladene Texte sind Textdateien, keine Mediensammlungen.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class LLMAuftrag(BaseModel):
    thema: str = Field(min_length=1, max_length=500)
    altersspanne: str = Field(default="Erwachsene", max_length=100)
    umfang: int = Field(default=300, ge=50, le=3000)  # ungefähre Wortzahl


class QuellenAntwort(BaseModel):
    id: str
    art: str
    titel: str
    einheiten: int
    aktiv: bool
    erstellt: str


class AktivAenderung(BaseModel):
    aktiv: bool


def _als_antwort(quelle: Textquelle, einheiten: int) -> QuellenAntwort:
    """Die eine Stelle, an der eine Quelle zur Antwort wird."""
    return QuellenAntwort(
        id=quelle.id,
        art=quelle.art,
        titel=quelle.titel,
        einheiten=einheiten,
        aktiv=quelle.aktiv,
        erstellt=quelle.erstellt,
    )


@router.post("/llm", response_model=QuellenAntwort, status_code=201)
def aus_llm(sprecher: SprecherId, auftrag: LLMAuftrag, db: Datenbank) -> QuellenAntwort:
    konfiguration = einstellungen()
    try:
        text = llm.erzeuge_text(
            llm.Auftrag(auftrag.thema, auftrag.altersspanne, auftrag.umfang),
            anbieter=konfiguration.llm_provider,
            api_schluessel=konfiguration.llm_api_key,
            modell=konfiguration.llm_model,
            basis_url=konfiguration.llm_base_url,
        )
    except ValueError as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler

    return _lege_quelle_an(
        db,
        sprecher,
        art="llm",
        titel=auftrag.thema.strip(),
        parameter={
            **auftrag.model_dump(),
            "anbieter": konfiguration.llm_provider,
            "modell": konfiguration.llm_model,
        },
        text=text,
    )


@router.post("/upload", response_model=QuellenAntwort, status_code=201)
async def aus_upload(
    sprecher: SprecherId, db: Datenbank, datei: UploadFile = File()
) -> QuellenAntwort:
    inhalt = await datei.read()
    if len(inhalt) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Datei ist zu groß (Grenze: 10 MB).")

    try:
        text = upload.lies_text(inhalt, datei.filename or "")
    except upload.UploadFehler as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler
    if not text.strip():
        raise HTTPException(status_code=400, detail="Die Datei enthält keinen lesbaren Text.")

    return _lege_quelle_an(
        db,
        sprecher,
        art="upload",
        titel=datei.filename or "Hochgeladener Text",
        parameter={"dateiname": datei.filename, "bytes": len(inhalt)},
        text=text,
    )


@router.get("", response_model=list[QuellenAntwort])
def liste(sprecher: SprecherId, db: Datenbank) -> list[QuellenAntwort]:
    anzahl = (
        select(Vorlage.source_id, func.count().label("einheiten"))
        .group_by(Vorlage.source_id)
        .subquery()
    )
    zeilen = db.execute(
        select(Textquelle, func.coalesce(anzahl.c.einheiten, 0))
        .outerjoin(anzahl, anzahl.c.source_id == Textquelle.id)
        .where(Textquelle.speaker_id == sprecher)
        .order_by(Textquelle.erstellt)
    ).all()
    return [_als_antwort(quelle, einheiten) for quelle, einheiten in zeilen]


def _hole(db: Session, sprecher: str, quelle_id: str) -> Textquelle:
    quelle = db.get(Textquelle, quelle_id)
    if quelle is None or quelle.speaker_id != sprecher:
        raise HTTPException(status_code=404, detail="Unbekannte Textquelle")
    return quelle


@router.get("/{quelle_id}/text", response_class=PlainTextResponse)
def text_ansehen(sprecher: SprecherId, quelle_id: str, db: Datenbank) -> str:
    """Der Text, wie er in der Warteschlange steht — eine Einheit je Absatz.

    Nicht das Original, sondern das Geschnittene: Genau das wird vorgesprochen,
    und genau das will nachsehen, wer prüft, ob eine Quelle taugt.
    """
    quelle = _hole(db, sprecher, quelle_id)
    einheiten = db.scalars(
        select(Vorlage.text).where(Vorlage.source_id == quelle.id).order_by(Vorlage.position)
    ).all()
    return f"{quelle.titel}\n\n" + "\n\n".join(einheiten)


@router.patch("/{quelle_id}", response_model=QuellenAntwort)
def stelle_um(
    sprecher: SprecherId, quelle_id: str, aenderung: AktivAenderung, db: Datenbank
) -> QuellenAntwort:
    """Quelle stilllegen oder wieder aufnehmen — ohne Datenverlust."""
    quelle = _hole(db, sprecher, quelle_id)
    quelle.aktiv = aenderung.aktiv
    db.commit()

    einheiten = db.scalar(
        select(func.count()).select_from(Vorlage).where(Vorlage.source_id == quelle.id)
    )
    return _als_antwort(quelle, einheiten or 0)


@router.delete("/{quelle_id}", status_code=204)
def loesche(sprecher: SprecherId, quelle_id: str, db: Datenbank) -> None:
    """Quelle mitsamt ihren Einheiten löschen — solange nichts daran hängt.

    Gibt es zu einer Einheit eine gültige Aufnahme, wird nicht gelöscht: Das
    Audio ist der Ertrag der ganzen Arbeit, und die Quelle ist seine Herkunft
    (`parameter` hält fest, woher der Text stammt). Wer sie loswerden will,
    legt sie stattdessen still — dafür gibt es den Schalter.

    Verworfene Aufnahmen stehen dem nicht im Weg: Ihr Audio ist schon gelöscht,
    die Zeile ist nur noch ein Vermerk und geht mit.
    """
    quelle = _hole(db, sprecher, quelle_id)
    vorlagen = select(Vorlage.id).where(Vorlage.source_id == quelle.id)

    gueltige = db.scalar(
        select(func.count())
        .select_from(Aufnahme)
        .where(Aufnahme.prompt_id.in_(vorlagen), Aufnahme.status == "ok")
    )
    if gueltige:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Zu dieser Quelle gibt es {gueltige} Aufnahme(n). "
                "Sie lässt sich deshalb nicht löschen — stelle sie stattdessen ab."
            ),
        )

    # Reihenfolge zählt: SQLite prüft die Fremdschlüssel (PRAGMA foreign_keys).
    db.execute(delete(Aufnahme).where(Aufnahme.prompt_id.in_(vorlagen)))
    db.execute(delete(Vorlage).where(Vorlage.source_id == quelle.id))
    db.delete(quelle)
    db.commit()


def _lege_quelle_an(
    db: Session, sprecher_id: str, *, art: str, titel: str, parameter: dict, text: str
) -> QuellenAntwort:
    """Quelle speichern, Text schneiden, Vorlagen hinten anhängen."""
    einheiten = chunker.schneide(text)
    if not einheiten:
        raise HTTPException(status_code=400, detail="Aus dem Text ließ sich keine Einheit bilden.")

    quelle = Textquelle(
        id=ids.neue_id("src"),
        speaker_id=sprecher_id,
        art=art,
        titel=titel[:200],
        parameter=json.dumps(parameter, ensure_ascii=False),
        erstellt=jetzt(),
    )
    db.add(quelle)

    position = naechste_position(db, sprecher_id)
    db.add_all(
        Vorlage(
            id=ids.neue_id("prm"),
            source_id=quelle.id,
            speaker_id=sprecher_id,
            position=position + versatz,
            text=einheit.text,
            dauer_geschaetzt_s=einheit.dauer_geschaetzt_s,
            erstellt=jetzt(),
        )
        for versatz, einheit in enumerate(einheiten)
    )
    db.commit()

    return _als_antwort(quelle, len(einheiten))
