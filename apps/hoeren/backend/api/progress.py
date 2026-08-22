"""Gesammelte Minuten gegen zwei Marken.

Ab etwa 1,5 Stunden wird ein sprecherspezifisches Modell brauchbar, ab etwa
20 Stunden gut; danach flacht der Gewinn ab. Mehr Marken wären eine
Scheingenauigkeit.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from ..db.models import Aufnahme, Textquelle, Vorlage
from ..deps import Datenbank, SprecherId
from ..services import prompt_queue

router = APIRouter(prefix="/api/progress", tags=["Fortschritt"])

MARKE_BRAUCHBAR_S = 1.5 * 3600
MARKE_GUT_S = 20 * 3600


class FortschrittAntwort(BaseModel):
    sekunden: float
    aufnahmen: int
    offene_einheiten: int
    # Aufnahmen nach Modus und nach Herkunft der Vorlage: Nachgesprochenes und
    # Korrekturen sind schwächere Daten und werden im Training anders gewichtet.
    nach_modus: dict[str, int]
    nach_quelle: dict[str, int]
    marke_brauchbar_s: float = MARKE_BRAUCHBAR_S
    marke_gut_s: float = MARKE_GUT_S


@router.get("", response_model=FortschrittAntwort)
def fortschritt(sprecher: SprecherId, db: Datenbank) -> FortschrittAntwort:
    gueltig = (Aufnahme.speaker_id == sprecher, Aufnahme.status == "ok")

    sekunden = db.scalar(select(func.coalesce(func.sum(Aufnahme.dauer_s), 0.0)).where(*gueltig))
    aufnahmen = db.scalar(select(func.count()).select_from(Aufnahme).where(*gueltig))

    # Offen ist, was noch vorzusprechen ist — dieselbe Menge, die auch die
    # Warteschlange meint (`prompt_queue.aus_aktiven_quellen`). Direkt gezählt
    # und nicht als Differenz: Sonst geriete die Zahl ins Minus, sobald eine
    # Quelle mit Aufnahmen abgestellt wird.
    erledigte_vorlagen = select(Aufnahme.prompt_id).where(*gueltig)
    offene = prompt_queue.aus_aktiven_quellen(sprecher).where(
        Vorlage.id.not_in(erledigte_vorlagen)
    )
    einheiten_offen = db.scalar(select(func.count()).select_from(offene.subquery()))

    nach_modus = dict(
        db.execute(
            select(Aufnahme.modus, func.count()).where(*gueltig).group_by(Aufnahme.modus)
        ).all()
    )
    nach_quelle = dict(
        db.execute(
            select(Textquelle.art, func.count())
            .join(Vorlage, Vorlage.source_id == Textquelle.id)
            .join(Aufnahme, Aufnahme.prompt_id == Vorlage.id)
            .where(*gueltig)
            .group_by(Textquelle.art)
        ).all()
    )

    return FortschrittAntwort(
        sekunden=float(sekunden or 0.0),
        aufnahmen=aufnahmen or 0,
        offene_einheiten=einheiten_offen or 0,
        nach_modus=nach_modus,
        nach_quelle=nach_quelle,
    )
