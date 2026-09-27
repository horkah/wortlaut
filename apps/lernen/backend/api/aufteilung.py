"""Wie der Korpus gemessen wird - die Zahlen dazu, nicht die Aufnahmen.

In wie viele Faltungen der Korpus zerfällt und wie viele Aufnahmen auf jede
entfallen. Die Aufnahmen selbst stehen in „Meine Daten".
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from wortlaut import laeufe

from ..deps import Korpus, SprecherId
from ..services import aufteilung

router = APIRouter(prefix="/lernen/api/aufteilung", tags=["Aufteilung"])


class AufteilungAntwort(BaseModel):
    """Wie viele Aufnahmen es gibt und wie sie sich auf die Faltungen verteilen."""

    # Vom Server, damit die Oberfläche die Zahl nicht selbst kennt.
    faltungen: int
    aufnahmen: int
    sekunden: float
    # Faltung (als Zeichenkette) → Anzahl.
    je_faltung: dict[str, int]
    # Ob sich damit kreuzvalidieren lässt: mindestens eine Aufnahme je Faltung.
    genug: bool


@router.get("", response_model=AufteilungAntwort)
def uebersicht(korpus: Korpus, sprecher: SprecherId) -> AufteilungAntwort:
    proben = aufteilung.proben(korpus)
    gezaehlt = aufteilung.zaehle(proben)
    return AufteilungAntwort(
        faltungen=laeufe.FALTUNGEN,
        aufnahmen=len(proben),
        sekunden=round(sum(probe.aufnahme.dauer_s for probe in proben), 1),
        je_faltung={str(faltung): anzahl for faltung, anzahl in gezaehlt.items()},
        genug=aufteilung.genug(proben),
    )
