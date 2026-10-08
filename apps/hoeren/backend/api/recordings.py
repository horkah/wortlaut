"""Upload, Prüfung, Verwerfen.

Opus aus dem Browser → ffmpeg → 16 kHz mono WAV → Messung → Ablage → Zeile.
Synchron, denn die Dateien sind Sekunden lang.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete
from wortlaut import audio as klang
from wortlaut import corpus, ids

from ..db.models import Aufnahme, Erkennung, Vorlage, jetzt
from ..deps import Ablage, Datenbank, SprecherId
from ..services import aufnahmen, faltungen, quality

router = APIRouter(prefix="/api/recordings", tags=["Aufnahmen"])

# Eine Einheit dauert 3–12 Sekunden; alles darüber ist ein Versehen.
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MODI = ("gelesen", "nachgesprochen")


class AufnahmeAntwort(BaseModel):
    id: str
    prompt_id: str
    dauer_s: float
    pegel_dbfs: float
    modus: str
    status: str
    hinweise: list[str]  # aus services/quality.py - Hinweise, keine Ablehnung


@router.post("", response_model=AufnahmeAntwort, status_code=201)
async def nimm_auf(
    sprecher: SprecherId,
    db: Datenbank,
    ablage: Ablage,
    audio: UploadFile = File(),
    prompt_id: str = Form(),
    modus: str = Form(default="gelesen"),
    session: str | None = Form(default=None),
) -> AufnahmeAntwort:
    if modus not in MODI:
        raise HTTPException(status_code=400, detail=f"Modus muss einer von {MODI} sein.")

    vorlage = db.get(Vorlage, prompt_id)
    if vorlage is None or vorlage.speaker_id != sprecher:
        raise HTTPException(status_code=404, detail="Unbekannte Vorlage")

    inhalt = await audio.read()
    if not inhalt:
        raise HTTPException(status_code=400, detail="Leere Aufnahme")
    if len(inhalt) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Aufnahme ist zu groß.")

    aufnahme_id = ids.neue_id("rec")
    relpfad = corpus.audio_relpfad(sprecher, aufnahme_id)

    try:
        befund = aufnahmen.nimm_an(inhalt, ablage, relpfad)
    except klang.AudioFehler as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler

    hinweise = quality.pruefe(befund, vorlage.dauer_geschaetzt_s)
    aufnahme = Aufnahme(
        id=aufnahme_id,
        prompt_id=prompt_id,
        speaker_id=sprecher,
        session_id=session,
        blob=relpfad,
        **asdict(befund),
        modus=modus,
        status="ok",
        hinweise=json.dumps(hinweise, ensure_ascii=False),
        externe_id=None,
        erstellt=jetzt(),
    )
    db.add(aufnahme)
    faltungen.vergib(db, aufnahme)
    db.commit()

    return AufnahmeAntwort(
        id=aufnahme.id,
        prompt_id=prompt_id,
        dauer_s=befund.dauer_s,
        pegel_dbfs=befund.pegel_dbfs,
        modus=modus,
        status=aufnahme.status,
        hinweise=hinweise,
    )


@router.get("/{aufnahme_id}/audio")
def hoere_ab(
    sprecher: SprecherId,
    aufnahme_id: str,
    db: Datenbank,
    ablage: Ablage,
) -> FileResponse:
    """Die eigene Aufnahme anhören."""
    aufnahme = db.get(Aufnahme, aufnahme_id)
    if aufnahme is None or aufnahme.speaker_id != sprecher or aufnahme.status != "ok":
        raise HTTPException(status_code=404, detail="Unbekannte Aufnahme")

    pfad = ablage.pfad(aufnahme.blob)
    if not pfad.is_file():
        raise HTTPException(status_code=404, detail="Zu dieser Aufnahme liegt kein Audio mehr.")
    return FileResponse(pfad, media_type="audio/wav")


@router.delete("/{aufnahme_id}", status_code=204)
def verwirf(sprecher: SprecherId, aufnahme_id: str, db: Datenbank, ablage: Ablage) -> None:
    """Verwerfen: Audio und Messwerte löschen, die Zeile
    als `verworfen` behalten. Die Vorlage wird wieder offen.

    Der erkannte Text ist dieselbe Äußerung in Schrift und geht mit, auch
    übernommene Faltungen. Ein trainiertes Modell bleibt unberührt; seine
    Zahlen stehen auf dem Korpus, wie er ist.
    """
    aufnahme = db.get(Aufnahme, aufnahme_id)
    if aufnahme is None or aufnahme.speaker_id != sprecher:
        raise HTTPException(status_code=404, detail="Unbekannte Aufnahme")

    if aufnahme.status == "ok":
        ablage.loesche(aufnahme.blob)
        db.execute(delete(Erkennung).where(Erkennung.recording_id == aufnahme_id))
        aufnahme.status = "verworfen"
        db.commit()
