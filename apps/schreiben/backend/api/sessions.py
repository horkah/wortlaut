"""Diktiersitzungen: anlegen, ansehen, bestätigen.

Eine Sitzung ist ein Text im Entstehen: gesprochen, abschnittsweise
korrigiert, am Ende bestätigt. Erst das Bestätigen macht daraus Daten für
„hören" — vorher ist alles Arbeitsstand.

Die Wege heißen englisch wie die Tabellen (`sessions`, `segments`, `outbox`),
die Handlungen daran deutsch wie der übrige Code (`…/bestaetigen`).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from wortlaut import ids

from ..config import einstellungen
from ..db.models import Abschnitt, Sitzung, jetzt
from ..deps import Ablage, Datenbank
from ..services import outbox

router = APIRouter(prefix="/api/sessions", tags=["Sitzungen"])


class AbschnittAntwort(BaseModel):
    id: str
    position: int
    text: str
    herkunft: str  # initial | neu
    dauer_s: float
    # False heißt: schon an „hören" übergeben und hier gelöscht.
    hat_audio: bool


class SitzungAntwort(BaseModel):
    id: str
    status: str  # offen | bestaetigt
    erstellt: str
    bestaetigt: str | None
    abschnitte: list[AbschnittAntwort]


class VersandAntwort(BaseModel):
    """Was aus dem Bestätigen geworden ist — Zahlen, keine Protokollzeilen."""

    eingestellt: int
    gesendet: int
    offen: int
    fehler: str | None


@router.post("", response_model=SitzungAntwort, status_code=201)
def beginne(db: Datenbank) -> SitzungAntwort:
    sitzung = Sitzung(id=ids.neue_id("dik"), status="offen", erstellt=jetzt(), bestaetigt=None)
    db.add(sitzung)
    db.commit()
    return als_antwort(db, sitzung)


@router.get("/{sitzung_id}", response_model=SitzungAntwort)
def zeige(sitzung_id: str, db: Datenbank) -> SitzungAntwort:
    return als_antwort(db, hole(db, sitzung_id))


@router.post("/{sitzung_id}/bestaetigen", response_model=VersandAntwort)
async def bestaetige(sitzung_id: str, db: Datenbank, ablage: Ablage) -> VersandAntwort:
    """Text abnicken: jeder Abschnitt geht als Korrekturpaar an „hören".

    Eingestellt wird immer, gesendet wird gleich versucht. Klappt das Senden
    nicht, bleibt der Eintrag im Postausgang und die Antwort sagt, warum.
    """
    sitzung = hole(db, sitzung_id)
    abschnitte = abschnitte_von(db, sitzung_id)
    if not abschnitte:
        raise HTTPException(status_code=400, detail="Diese Sitzung hat noch keinen Text.")

    eingestellt = outbox.stelle_ein(db, abschnitte)
    sitzung.status = "bestaetigt"
    sitzung.bestaetigt = jetzt()
    db.commit()

    # Der Versand spricht über das Netz und blockiert; deshalb nicht im
    # Ereignisfaden von uvicorn, sondern in einem Arbeitsfaden.
    bericht = await run_in_threadpool(outbox.sende_offene, db, ablage, einstellungen())
    return VersandAntwort(
        eingestellt=eingestellt,
        gesendet=bericht.gesendet,
        offen=bericht.offen,
        fehler=bericht.fehler,
    )


# ── von den anderen Endpunkten mitbenutzt ───────────────────────────────────


def hole(db: Session, sitzung_id: str) -> Sitzung:
    sitzung = db.get(Sitzung, sitzung_id)
    if sitzung is None:
        raise HTTPException(status_code=404, detail="Unbekannte Sitzung")
    return sitzung


def abschnitte_von(db: Session, sitzung_id: str) -> list[Abschnitt]:
    return list(
        db.scalars(
            select(Abschnitt).where(Abschnitt.session_id == sitzung_id).order_by(Abschnitt.position)
        )
    )


def als_antwort(db: Session, sitzung: Sitzung) -> SitzungAntwort:
    return SitzungAntwort(
        id=sitzung.id,
        status=sitzung.status,
        erstellt=sitzung.erstellt,
        bestaetigt=sitzung.bestaetigt,
        abschnitte=[
            AbschnittAntwort(
                id=abschnitt.id,
                position=abschnitt.position,
                text=abschnitt.text,
                herkunft=abschnitt.herkunft,
                dauer_s=abschnitt.dauer_s,
                hat_audio=abschnitt.blob is not None,
            )
            for abschnitt in abschnitte_von(db, sitzung.id)
        ],
    )
