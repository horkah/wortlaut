"""Textquellen: LLM-Thema, hochgeladener Text, fotografierte Vorlage.

Alle Wege enden gleich: Text → `chunker.schneide()` → Vorlagen hinten an der
Warteschlange. Herkunft und Parameter stehen in `text_sources.parameter`.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from wortlaut import ids
from wortlaut.text import chunker, llm, ocr, upload

from ..config import einstellungen
from ..db.models import Aufnahme, Textquelle, Vorlage, jetzt
from ..deps import Datenbank, Sprache, SprecherId
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


class ErkannterText(BaseModel):
    """Was aus einer Datei herausgelesen wurde - noch nichts davon gespeichert."""

    text: str
    # `gelesen` (Textebene) oder `erkannt` (aus dem Bild geraten) - wie genau
    # jemand hinsehen muss.
    herkunft: str
    seiten: int | None = None


class EigenerText(BaseModel):
    """Text, den ein Mensch gesehen und so gewollt hat."""

    text: str = Field(min_length=1)
    titel: str = Field(default="", max_length=200)
    # Woher er kam - nur fürs Protokoll.
    herkunft: str = Field(default="eingefügt", max_length=40)


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
def aus_llm(
    sprecher: SprecherId, sprache: Sprache, auftrag: LLMAuftrag, db: Datenbank
) -> QuellenAntwort:
    konfiguration = einstellungen()
    try:
        text = llm.erzeuge_text(
            llm.Auftrag(auftrag.thema, auftrag.altersspanne, auftrag.umfang, sprache),
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
        sprache=sprache,
    )


@router.post("/upload", response_model=QuellenAntwort, status_code=201)
async def aus_upload(
    sprecher: SprecherId, sprache: Sprache, db: Datenbank, datei: UploadFile = File()
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
        sprache=sprache,
    )


@router.get("/erkennung", response_model=dict)
def erkennung_moeglich() -> dict:
    """Ob dieser Server Bilder lesen kann - damit die Oberfläche nichts verspricht.

    Ohne Wächter: keine Auskunft über einen Menschen.
    """
    return {"moeglich": ocr.verfuegbar(), "formate": list(ocr.UNTERSTUETZT)}


@router.post("/erkennen", response_model=ErkannterText)
async def erkenne(
    sprecher: SprecherId, sprache: Sprache, datei: UploadFile = File()
) -> ErkannterText:
    """Eine Datei lesen und den Text **zurückgeben**, ohne etwas zu speichern.

    Getrennt vom Anlegen, weil Erkanntes geraten ist: Ein Fehler wanderte
    sonst über Vorlage und Aufnahme ins Training und zählte als Abweichung
    des Sprechers. Ein PDF mit Textebene wird gelesen, eines ohne und jedes
    Bild erkannt; `herkunft` sagt, was geschah.
    """
    inhalt = await datei.read()
    if len(inhalt) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Datei ist zu groß (Grenze: 10 MB).")

    name = datei.filename or ""

    # Am Inhalt entschieden, nicht am Namen - aus der Zwischenablage kommt ein
    # Bild oft als `image` ohne Endung.
    if inhalt[:5] == b"%PDF-":
        if upload.pdf_hat_text(inhalt):
            return ErkannterText(text=upload.lies_text(inhalt, "x.pdf"), herkunft="gelesen")
        return ErkannterText(text=_erkannt(lambda: ocr.aus_pdf(inhalt, sprache)), herkunft="erkannt")

    if ocr.ist_bild(inhalt):
        return ErkannterText(
            text=_erkannt(lambda: ocr.aus_bild(inhalt, sprache)), herkunft="erkannt"
        )

    # Textformate nach Endung: Ob ein ZIP `docx` oder `epub` ist, sagt der Name
    # billiger als der Inhalt.
    try:
        return ErkannterText(text=upload.lies_text(inhalt, name), herkunft="gelesen")
    except upload.UploadFehler as fehler:
        if not ocr.verfuegbar():
            # Ohne Zeichenerkennung ist das fast immer ein Bild, das sich nicht
            # einmal als solches erkennen lässt - also sagen, was fehlt.
            raise HTTPException(
                status_code=409,
                detail=(
                    "Auf diesem Server ist keine Zeichenerkennung eingerichtet - "
                    "er liest txt, md, pdf, epub und docx."
                ),
            ) from fehler
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler


def _erkannt(arbeit) -> str:
    """Die Zeichenerkennung aufrufen und ihre Fehler in Antworten übersetzen.

    409, wenn sie fehlt - eine fehlende Möglichkeit, kein Serverfehler.
    """
    try:
        text = arbeit()
    except ocr.OcrFehler as fehler:
        schluessel = 409 if not ocr.verfuegbar() else 400
        raise HTTPException(status_code=schluessel, detail=str(fehler)) from fehler
    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="Auf dieser Vorlage war kein Text zu erkennen. Schärfer, gerader, heller?",
        )
    return text


@router.post("/text", response_model=QuellenAntwort, status_code=201)
def aus_text(
    sprecher: SprecherId, sprache: Sprache, eingabe: EigenerText, db: Datenbank
) -> QuellenAntwort:
    """Text übernehmen, den ein Mensch vor sich gesehen hat.

    Das Gegenstück zu `/erkennen` und der Weg für einen eingefügten Text.
    """
    if not eingabe.text.strip():
        raise HTTPException(status_code=400, detail="Der Text ist leer.")
    return _lege_quelle_an(
        db,
        sprecher,
        art="upload",
        titel=eingabe.titel.strip() or "Eigener Text",
        parameter={"herkunft": eingabe.herkunft, "zeichen": len(eingabe.text)},
        text=eingabe.text,
        sprache=sprache,
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
    """Der Text, wie er in der Warteschlange steht - eine Einheit je Absatz.

    Das Geschnittene, denn das wird vorgesprochen.
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
    """Quelle stilllegen oder wieder aufnehmen - ohne Datenverlust."""
    quelle = _hole(db, sprecher, quelle_id)
    quelle.aktiv = aenderung.aktiv
    db.commit()

    einheiten = db.scalar(
        select(func.count()).select_from(Vorlage).where(Vorlage.source_id == quelle.id)
    )
    return _als_antwort(quelle, einheiten or 0)


@router.delete("/{quelle_id}", status_code=204)
def loesche(sprecher: SprecherId, quelle_id: str, db: Datenbank) -> None:
    """Quelle mitsamt ihren Einheiten löschen - solange nichts daran hängt.

    Mit gültigen Aufnahmen daran nicht - die Quelle ist ihre Herkunft; dann
    wird sie abgestellt. Verworfene Aufnahmen gehen mit.
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
                "Sie lässt sich deshalb nicht löschen - stelle sie stattdessen ab."
            ),
        )

    # Reihenfolge zählt: SQLite prüft die Fremdschlüssel (PRAGMA foreign_keys).
    db.execute(delete(Aufnahme).where(Aufnahme.prompt_id.in_(vorlagen)))
    db.execute(delete(Vorlage).where(Vorlage.source_id == quelle.id))
    db.delete(quelle)
    db.commit()


def _lege_quelle_an(
    db: Session,
    sprecher_id: str,
    *,
    art: str,
    titel: str,
    parameter: dict,
    text: str,
    sprache: str,
) -> QuellenAntwort:
    """Quelle speichern, Text schneiden, Vorlagen hinten anhängen.

    `sprache` steuert den Schnitt (`text/chunker.py`).
    """
    einheiten = chunker.schneide(text, sprache)
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
