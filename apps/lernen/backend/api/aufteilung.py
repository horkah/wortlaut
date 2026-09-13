"""Wie der Korpus gemessen wird - die Zahlen dazu, nicht die Aufnahmen.

Ein einziger, lesender Weg. Er nennt, in wie viele Faltungen der Korpus
zerfällt und wie viele Aufnahmen auf jede entfallen - mehr nicht.

**Warum hier keine Liste der Aufnahmen mehr steht.** Sie stand hier, solange es
ein Testdrittel gab: Wer wissen wollte, ob seine Prüfaufnahmen wirklich
ungesehen sind, musste sie sehen können. Diese Zusage gibt es nicht mehr - seit
der Kreuzvalidierung trainiert jede Aufnahme in fünf von sechs Faltungen und
misst in der sechsten. Es gibt also keine besondere Teilmenge mehr, die man
nachzählen müsste.

Die Aufnahmen selbst stehen in „Meine Daten", einmal und vollständig. Sie hier
ein zweites Mal aufzuzählen hieße, dieselbe Sache an zwei Stellen zu pflegen -
und die zweite ist die, die irgendwann nicht mehr stimmt.
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

    # Wie viele Faltungen die Kreuzvalidierung rechnet - sechs, und die Zahl
    # kommt vom Server, damit die Oberfläche sie nicht zweitens kennt.
    faltungen: int
    aufnahmen: int
    sekunden: float
    # Faltung (als Zeichenkette, damit JSON es mag) → wie viele Aufnahmen.
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
