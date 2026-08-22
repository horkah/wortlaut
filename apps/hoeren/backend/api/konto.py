"""Ein Sprecher sieht sich selbst an — dieselben Daten, die die Aufsicht sieht.

Der Unterschied zu `api/admin.py`: Hier steht kein Sprecher in der Adresse.
Es gibt keinen — die Kennung kommt wie bei jedem anderen Weg dieser App aus
dem vorgelegten Zugang (`SprecherId`/`Datenbank`, siehe `deps.py`). Wer hier
ruft, kann also von vornherein nur die eigene Datenbank öffnen, nie eine
fremde; ein Sprecher, der versucht, eine andere Kennung hineinzuschreiben,
hat dafür in dieser Datei gar kein Feld.

Zum Anhören und Verwerfen einer eigenen Aufnahme gibt es hier bewusst keine
eigenen Wege: `api/recordings.py` hat sie längst, ebenso selbstbezogen, und
ein zweiter Weg mit anderer Löschsemantik wäre eine zweite Vorstellung davon,
was „diese Aufnahme loswerden" heißt.

Was ein Sprecher hier **nicht** kann, anders als die Aufsicht: alle Aufnahmen
auf einmal löschen, sich selbst vollständig löschen, umbenennen, eine
Sicherung oder einen Datensatz ziehen. Das bleibt der Aufsicht vorbehalten
(`api/admin.py`) — diese Ansicht zeigt, was da ist, und lässt einzelne
Aufnahmen loswerden, mehr nicht.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..db.models import Sprecher
from ..deps import Ablage, Datenbank, SprecherId
from ..services import uebersicht
from ..services.uebersicht import (
    AufnahmenAntwort,
    QuelleAntwort,
    SitzungenAntwort,
    UebersichtAntwort,
)

router = APIRouter(prefix="/api/konto", tags=["Konto"])


class KontoAntwort(BaseModel):
    sprecher: UebersichtAntwort
    quellen: list[QuelleAntwort]


@router.get("", response_model=KontoAntwort)
def konto(sprecher: SprecherId, db: Datenbank, ablage: Ablage) -> KontoAntwort:
    """Profil, Kennzahlen und Textquellen — die eigenen, wie die Aufsicht sie sieht."""
    person = db.get(Sprecher, sprecher)
    assert person is not None  # `SprecherId` hat die Datenbank schon geöffnet.
    return KontoAntwort(
        sprecher=uebersicht.profil(db, person, ablage),
        quellen=uebersicht.quellen(db),
    )


@router.get("/sessions", response_model=SitzungenAntwort)
def sitzungen(db: Datenbank, ab: int = 0, anzahl: int = 10) -> SitzungenAntwort:
    """Die eigenen Sitzungen, jüngste zuerst, seitenweise."""
    return uebersicht.sitzungen_seite(db, ab, anzahl)


@router.get("/recordings", response_model=AufnahmenAntwort)
def aufnahmen(db: Datenbank, ablage: Ablage, ab: int = 0, anzahl: int = 10) -> AufnahmenAntwort:
    """Die eigenen Aufnahmen mit ihrem Text, neueste zuerst, seitenweise.

    Anhören und Verwerfen bleiben bei `api/recordings.py` — beides sind
    bereits sprecherbezogene Wege und brauchen keinen zweiten hier.
    """
    return uebersicht.aufnahmen_seite(db, ablage, ab, anzahl)
