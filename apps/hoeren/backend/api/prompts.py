"""Die nächste Sprecheinheit ausliefern — samt Sitzungsverwaltung.

Eine Sitzung ist nicht mehr als ein Zeitstempelpaar: Sie hält fest, dass
aufgenommen wird, aber nicht wo. Die Position ergibt sich aus den vorhandenen
Aufnahmen (siehe `services/prompt_queue.py`), deshalb ist jede Sitzung
jederzeit unterbrechbar und an derselben Stelle fortsetzbar.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from wortlaut import ids

from ..db.models import Sitzung, Vorlage, jetzt
from ..deps import Datenbank
from ..services import prompt_queue

router = APIRouter(tags=["Vorlagen"])


class SitzungAntwort(BaseModel):
    id: str
    begonnen: str


class EinheitAntwort(BaseModel):
    id: str
    text: str
    dauer_geschaetzt_s: float


class NaechsteAntwort(BaseModel):
    """Eine Einheit groß, davor und dahinter je eine blass."""

    vorher: EinheitAntwort | None
    aktuell: EinheitAntwort | None  # None heißt: nichts mehr offen
    nachher: EinheitAntwort | None
    erledigt: int
    gesamt: int


@router.post("/api/sessions", response_model=SitzungAntwort, status_code=201)
def beginne_sitzung(sprecher: str, db: Datenbank) -> SitzungAntwort:
    sitzung = Sitzung(
        id=ids.neue_id("ses"), speaker_id=sprecher, begonnen=jetzt(), zuletzt_aktiv=jetzt()
    )
    db.add(sitzung)
    db.commit()
    return SitzungAntwort(id=sitzung.id, begonnen=sitzung.begonnen)


@router.get("/api/prompts/next", response_model=NaechsteAntwort)
def naechste_einheit(sprecher: str, db: Datenbank, session: str | None = None) -> NaechsteAntwort:
    if session is not None:
        sitzung = db.get(Sitzung, session)
        if sitzung is None or sitzung.speaker_id != sprecher:
            raise HTTPException(status_code=404, detail="Unbekannte Sitzung")
        sitzung.zuletzt_aktiv = jetzt()
        db.commit()

    ausschnitt = prompt_queue.naechste(db, sprecher)
    return NaechsteAntwort(
        vorher=_als_antwort(ausschnitt.vorher),
        aktuell=_als_antwort(ausschnitt.aktuell),
        nachher=_als_antwort(ausschnitt.nachher),
        erledigt=ausschnitt.erledigt,
        gesamt=ausschnitt.gesamt,
    )


def _als_antwort(vorlage: Vorlage | None) -> EinheitAntwort | None:
    if vorlage is None:
        return None
    return EinheitAntwort(
        id=vorlage.id, text=vorlage.text, dauer_geschaetzt_s=vorlage.dauer_geschaetzt_s
    )
