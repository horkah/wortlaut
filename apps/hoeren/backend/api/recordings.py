"""Upload, Prüfung, Verwerfen.

Ablauf einer Aufnahme: Browser schickt Opus → ffmpeg macht 16 kHz Mono-WAV →
Messung → Ablage → Datensatz. Alles synchron: die Dateien sind Sekunden lang,
und ein Ergebnis, das erst später eintrudelt, würde die Bedienung nur
verkomplizieren.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from wortlaut import audio as klang
from wortlaut import corpus, ids

from ..db.models import Aufnahme, Vorlage, jetzt
from ..deps import Ablage, Datenbank
from ..services import quality

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
    hinweise: list[str]  # aus services/quality.py — Hinweise, keine Ablehnung


@router.post("", response_model=AufnahmeAntwort, status_code=201)
async def nimm_auf(
    sprecher: str,
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

    with tempfile.TemporaryDirectory() as verzeichnis:
        eingang = Path(verzeichnis) / "eingang"
        eingang.write_bytes(inhalt)
        wav = Path(verzeichnis) / "aufnahme.wav"
        try:
            klang.wandle_in_wav(eingang, wav)
            befund = klang.untersuche(wav)
        except klang.AudioFehler as fehler:
            raise HTTPException(status_code=400, detail=str(fehler)) from fehler
        # Erst prüfen, dann ablegen: eine unlesbare Datei landet nie im Korpus.
        ablage.lege_ab(relpfad, wav)

    hinweise = quality.pruefe(befund, vorlage.dauer_geschaetzt_s)
    aufnahme = Aufnahme(
        id=aufnahme_id,
        prompt_id=prompt_id,
        speaker_id=sprecher,
        session_id=session,
        blob=relpfad,
        dauer_s=befund.dauer_s,
        pegel_dbfs=befund.pegel_dbfs,
        spitze_dbfs=befund.spitze_dbfs,
        clipping_anteil=befund.clipping_anteil,
        stille_vorn_s=befund.stille_vorn_s,
        stille_hinten_s=befund.stille_hinten_s,
        modus=modus,
        status="ok",
        hinweise=json.dumps(hinweise, ensure_ascii=False),
        externe_id=None,
        erstellt=jetzt(),
    )
    db.add(aufnahme)
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
def hoere_ab(sprecher: str, aufnahme_id: str, db: Datenbank, ablage: Ablage) -> FileResponse:
    """Die eigene Aufnahme anhören, bevor man sie behält."""
    aufnahme = db.get(Aufnahme, aufnahme_id)
    if aufnahme is None or aufnahme.speaker_id != sprecher or aufnahme.status != "ok":
        raise HTTPException(status_code=404, detail="Unbekannte Aufnahme")
    return FileResponse(ablage.pfad(aufnahme.blob), media_type="audio/wav")


@router.delete("/{aufnahme_id}", status_code=204)
def verwirf(sprecher: str, aufnahme_id: str, db: Datenbank, ablage: Ablage) -> None:
    """Verwerfen heißt: Audio löschen, Datensatz als `verworfen` behalten.

    Die Vorlage wird dadurch wieder offen (die Warteschlange zählt nur
    Aufnahmen mit Status `ok`). Das Audio selbst wird wirklich gelöscht —
    verworfene Stimmaufnahmen werden nicht gebraucht, und weniger
    Gesundheitsdaten sind besser als mehr.
    """
    aufnahme = db.get(Aufnahme, aufnahme_id)
    if aufnahme is None or aufnahme.speaker_id != sprecher:
        raise HTTPException(status_code=404, detail="Unbekannte Aufnahme")

    if aufnahme.status == "ok":
        ablage.loesche(aufnahme.blob)
        aufnahme.status = "verworfen"
        db.commit()
