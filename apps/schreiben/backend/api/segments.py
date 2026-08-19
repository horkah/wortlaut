"""Sprechen und nachbessern — der eigentliche Ablauf dieser App.

1. Sprechen: eine Aufnahme, daraus Text mit Segmentgrenzen, daraus Abschnitte.
2. Ein Abschnitt ist falsch: nur diesen neu einsprechen. Das neue Audio ersetzt
   den alten Ausschnitt, alle anderen bleiben stehen.

Die Transkription läuft in einem Arbeitsfaden. Sie dauert je nach Modell
Sekunden, und ein blockierter Ereignisfaden hielte in dieser Zeit auch jede
andere Anfrage auf.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from wortlaut import audio as klang

from ..config import einstellungen
from ..db.models import Abschnitt, jetzt
from ..deps import Ablage, Datenbank, Whisper
from ..services import segmenter
from .sessions import SitzungAntwort, abschnitte_von, als_antwort, hole

router = APIRouter(tags=["Abschnitte"])

# Diktiert wird in Sätzen, nicht in Vorträgen.
MAX_AUDIO_BYTES = 50 * 1024 * 1024


@router.post("/api/sessions/{sitzung_id}/segments", response_model=SitzungAntwort, status_code=201)
async def sprich(
    sitzung_id: str,
    db: Datenbank,
    ablage: Ablage,
    whisper: Whisper,
    audio: UploadFile = File(),
) -> SitzungAntwort:
    """Eine Aufnahme diktieren; die Abschnitte hängen hinten an den Text an."""
    sitzung = hole(db, sitzung_id)
    if sitzung.status != "offen":
        raise HTTPException(status_code=409, detail="Diese Sitzung ist bereits bestätigt.")
    inhalt = await _gelesen(audio)

    konfiguration = einstellungen()
    try:
        roh = await run_in_threadpool(
            segmenter.zerlege,
            inhalt,
            whisper,
            ablage,
            konfiguration.sprache,
            konfiguration.sprecher_id,
        )
    except klang.AudioFehler as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler
    if not roh:
        raise HTTPException(status_code=422, detail="Aus der Aufnahme wurde kein Wort verstanden.")

    position = max((a.position for a in abschnitte_von(db, sitzung_id)), default=0)
    db.add_all(
        Abschnitt(
            id=abschnitt.id,
            session_id=sitzung_id,
            position=position + versatz + 1,
            text=abschnitt.text,
            blob=abschnitt.blob,
            dauer_s=abschnitt.dauer_s,
            herkunft="initial",
            erstellt=jetzt(),
        )
        for versatz, abschnitt in enumerate(roh)
    )
    db.commit()
    return als_antwort(db, sitzung)


@router.post("/api/segments/{abschnitt_id}/neu", response_model=SitzungAntwort)
async def sprich_neu(
    abschnitt_id: str,
    db: Datenbank,
    ablage: Ablage,
    whisper: Whisper,
    audio: UploadFile = File(),
) -> SitzungAntwort:
    """Genau diesen Abschnitt neu einsprechen — der übrige Text bleibt stehen."""
    abschnitt = _hole_abschnitt(db, abschnitt_id)
    sitzung = hole(db, abschnitt.session_id)
    if sitzung.status != "offen":
        raise HTTPException(status_code=409, detail="Diese Sitzung ist bereits bestätigt.")
    inhalt = await _gelesen(audio)

    konfiguration = einstellungen()
    try:
        roh = await run_in_threadpool(
            segmenter.sprich_neu_ein,
            inhalt,
            whisper,
            ablage,
            konfiguration.sprache,
            konfiguration.sprecher_id,
            abschnitt_id,
        )
    except klang.AudioFehler as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler
    if not roh.text:
        # Die alte Fassung steht noch; das neue Audio liegt schon unter
        # derselben Kennung — beides zusammen wäre eine Lüge. Also zurück.
        raise HTTPException(status_code=422, detail="Aus der Aufnahme wurde kein Wort verstanden.")

    abschnitt.text = roh.text
    abschnitt.blob = roh.blob
    abschnitt.dauer_s = roh.dauer_s
    abschnitt.herkunft = "neu"
    db.commit()
    return als_antwort(db, sitzung)


@router.get("/api/segments/{abschnitt_id}/audio")
def hoere_ab(abschnitt_id: str, db: Datenbank, ablage: Ablage) -> FileResponse:
    """Den eigenen Abschnitt anhören — zum Vergleich mit dem, was dasteht."""
    abschnitt = _hole_abschnitt(db, abschnitt_id)
    if abschnitt.blob is None:
        raise HTTPException(status_code=404, detail="Aufnahme ist bereits übergeben.")
    return FileResponse(ablage.pfad(abschnitt.blob), media_type="audio/wav")


def _hole_abschnitt(db: Session, abschnitt_id: str) -> Abschnitt:
    abschnitt = db.get(Abschnitt, abschnitt_id)
    if abschnitt is None:
        raise HTTPException(status_code=404, detail="Unbekannter Abschnitt")
    return abschnitt


async def _gelesen(audio: UploadFile) -> bytes:
    inhalt = await audio.read()
    if not inhalt:
        raise HTTPException(status_code=400, detail="Leere Aufnahme")
    if len(inhalt) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Aufnahme ist zu groß.")
    return inhalt
