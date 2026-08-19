"""Der Postausgang von außen: nachsehen und noch einmal senden.

Zwei Endpunkte, weil zwei Fragen offenbleiben können, wenn „hören" gerade
nicht erreichbar war: Wie viel liegt noch? Und: geht es jetzt?
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..config import einstellungen
from ..db.models import Postausgang
from ..deps import Ablage, Datenbank
from ..services import outbox as postausgang

router = APIRouter(prefix="/api/outbox", tags=["Postausgang"])


class PostausgangAntwort(BaseModel):
    offen: int
    gesendet: int
    letzter_fehler: str | None


class VersandAntwort(BaseModel):
    gesendet: int
    offen: int
    fehler: str | None


@router.get("", response_model=PostausgangAntwort)
def stand(db: Datenbank) -> PostausgangAntwort:
    zeilen = list(db.scalars(select(Postausgang)))
    offene = [zeile for zeile in zeilen if zeile.status == "offen"]
    letzte_meldung = next(
        (zeile.letzter_fehler for zeile in reversed(offene) if zeile.letzter_fehler), None
    )
    return PostausgangAntwort(
        offen=len(offene),
        gesendet=len(zeilen) - len(offene),
        letzter_fehler=letzte_meldung,
    )


@router.post("/senden", response_model=VersandAntwort)
async def sende(db: Datenbank, ablage: Ablage) -> VersandAntwort:
    """Noch einmal versuchen. Wiederholen ist gefahrlos (siehe services/outbox.py)."""
    bericht = await run_in_threadpool(postausgang.sende_offene, db, ablage, einstellungen())
    return VersandAntwort(gesendet=bericht.gesendet, offen=bericht.offen, fehler=bericht.fehler)
