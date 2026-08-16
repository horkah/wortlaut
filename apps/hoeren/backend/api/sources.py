"""Textquellen: LLM-Thema oder hochgeladener Text.

Beide Wege enden gleich: Text → `chunker.schneide()` → Vorlagen, die hinten an
die Warteschlange angehängt werden. Herkunft und Erzeugungsparameter werden in
`text_sources.parameter` festgehalten, damit später nachvollziehbar ist, woher
eine Vorlage stammt.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from wortlaut import ids
from wortlaut.text import chunker, llm, upload

from ..config import einstellungen
from ..db.models import Textquelle, Vorlage, jetzt
from ..deps import Datenbank
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
    erstellt: str


@router.post("/llm", response_model=QuellenAntwort, status_code=201)
def aus_llm(sprecher: str, auftrag: LLMAuftrag, db: Datenbank) -> QuellenAntwort:
    konfiguration = einstellungen()
    try:
        text = llm.erzeuge_text(
            llm.Auftrag(auftrag.thema, auftrag.altersspanne, auftrag.umfang),
            anbieter=konfiguration.llm_provider,
            api_schluessel=konfiguration.llm_api_key,
            modell=konfiguration.llm_model,
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
async def aus_upload(sprecher: str, db: Datenbank, datei: UploadFile = File()) -> QuellenAntwort:
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
def liste(sprecher: str, db: Datenbank) -> list[QuellenAntwort]:
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
    return [
        QuellenAntwort(
            id=quelle.id,
            art=quelle.art,
            titel=quelle.titel,
            einheiten=einheiten,
            erstellt=quelle.erstellt,
        )
        for quelle, einheiten in zeilen
    ]


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

    return QuellenAntwort(
        id=quelle.id,
        art=quelle.art,
        titel=quelle.titel,
        einheiten=len(einheiten),
        erstellt=quelle.erstellt,
    )
