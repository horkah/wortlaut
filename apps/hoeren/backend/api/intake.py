"""Korrekturen von „schreiben" annehmen.

Bestätigt die Zielperson dort einen Abschnitt, wandert er als Audio-Text-Paar
hierher. Diese Paare sind schwächere Daten: Der Text ist keine Vorgabe, sondern
eine vom Nutzer abgenickte Maschinenausgabe. Deshalb bekommen sie eine eigene
Quelle (`art = 'korrektur'`) und im Rezept ein niedrigeres Gewicht — wer sie
gleichrangig einspeist, trainiert dem Modell seine eigenen Fehler an.

Die Outbox von „schreiben" wiederholt bei Netzfehlern. `externe_id` sorgt
dafür, dass eine Wiederholung nicht zu einem zweiten Datensatz führt.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import audio as klang
from wortlaut import corpus, ids
from wortlaut.text import chunker

from ..db.models import Aufnahme, Textquelle, Vorlage, jetzt
from ..deps import Ablage, Datenbank
from ..services.prompt_queue import naechste_position

router = APIRouter(prefix="/api/korpus", tags=["Korpus"])

KORREKTUR_TITEL = "Korrekturen aus „schreiben“"


class IntakeAntwort(BaseModel):
    aufnahme_id: str
    prompt_id: str
    neu: bool  # False = Wiederholung, es wurde nichts angelegt


@router.post("/intake", response_model=IntakeAntwort, status_code=201)
async def nimm_korrektur_an(
    sprecher: str,
    db: Datenbank,
    ablage: Ablage,
    audio: UploadFile = File(),
    text: str = Form(),
    externe_id: str = Form(),
) -> IntakeAntwort:
    vorhanden = db.scalars(select(Aufnahme).where(Aufnahme.externe_id == externe_id)).first()
    if vorhanden is not None:
        return IntakeAntwort(aufnahme_id=vorhanden.id, prompt_id=vorhanden.prompt_id, neu=False)

    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Leerer Text")

    aufnahme_id = ids.neue_id("rec")
    relpfad = corpus.audio_relpfad(sprecher, aufnahme_id)
    with tempfile.TemporaryDirectory() as verzeichnis:
        eingang = Path(verzeichnis) / "eingang"
        eingang.write_bytes(await audio.read())
        wav = Path(verzeichnis) / "aufnahme.wav"
        try:
            klang.wandle_in_wav(eingang, wav)
            befund = klang.untersuche(wav)
        except klang.AudioFehler as fehler:
            raise HTTPException(status_code=400, detail=str(fehler)) from fehler
        ablage.lege_ab(relpfad, wav)

    vorlage = Vorlage(
        id=ids.neue_id("prm"),
        source_id=_korrekturquelle(db, sprecher).id,
        speaker_id=sprecher,
        position=naechste_position(db, sprecher),
        text=text,
        dauer_geschaetzt_s=chunker.dauer(text),
        erstellt=jetzt(),
    )
    # Erst die Vorlage schreiben: die Aufnahme verweist per Fremdschlüssel auf sie.
    db.add(vorlage)
    db.flush()
    db.add(
        Aufnahme(
            id=aufnahme_id,
            prompt_id=vorlage.id,
            speaker_id=sprecher,
            session_id=None,
            blob=relpfad,
            dauer_s=befund.dauer_s,
            pegel_dbfs=befund.pegel_dbfs,
            spitze_dbfs=befund.spitze_dbfs,
            clipping_anteil=befund.clipping_anteil,
            stille_vorn_s=befund.stille_vorn_s,
            stille_hinten_s=befund.stille_hinten_s,
            # Frei gesprochen: weder abgelesen noch nachgesprochen.
            modus="frei",
            status="ok",
            hinweise=json.dumps([], ensure_ascii=False),
            externe_id=externe_id,
            erstellt=jetzt(),
        )
    )
    db.commit()

    return IntakeAntwort(aufnahme_id=aufnahme_id, prompt_id=vorlage.id, neu=True)


def _korrekturquelle(db: Session, sprecher_id: str) -> Textquelle:
    """Eine Sammelquelle je Sprecher — Korrekturen haben keine eigene Herkunft."""
    quelle = db.scalars(
        select(Textquelle).where(
            Textquelle.speaker_id == sprecher_id, Textquelle.art == "korrektur"
        )
    ).first()
    if quelle is None:
        quelle = Textquelle(
            id=ids.neue_id("src"),
            speaker_id=sprecher_id,
            art="korrektur",
            titel=KORREKTUR_TITEL,
            parameter=json.dumps({"herkunft": "schreiben"}, ensure_ascii=False),
            erstellt=jetzt(),
        )
        db.add(quelle)
        db.flush()
    return quelle
