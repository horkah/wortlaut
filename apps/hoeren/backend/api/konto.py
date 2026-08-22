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

Wer eine PIN gesetzt hat (siehe `services/pin.py`), braucht sie zusätzlich zum
Zugang, um hereinzusehen — als `X-Pin`-Kopfzeile an den drei lesenden Wegen.
`GET .../pin` bleibt absichtlich ungeschützt (sonst könnte die Oberfläche gar
nicht erst fragen, ob sie nach einer PIN fragen soll), ebenso `PATCH .../pin`:
Die eigene PIN zu ändern ist nicht das Versehen, gegen das sie schützt.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from ..db.models import Sprecher
from ..deps import Ablage, Datenbank, SprecherId
from ..services import pin, uebersicht
from ..services.pin import PinAenderung, PinAntwort
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


def _pruefe_pin(
    db: Datenbank,
    sprecher: SprecherId,
    x_pin: Annotated[str | None, Header()] = None,
) -> None:
    """Wächter der drei lesenden Wege — nur scharf, wenn eine PIN gesetzt ist."""
    person = _hole(db, sprecher)
    if person.pin_hash is not None and not pin.stimmt(x_pin or "", person.pin_hash):
        raise HTTPException(status_code=401, detail="Falsche oder fehlende PIN.")


def _hole(db: Datenbank, sprecher: SprecherId) -> Sprecher:
    person = db.get(Sprecher, sprecher)
    assert person is not None  # `SprecherId` hat die Datenbank schon geöffnet.
    return person


@router.get("/pin", response_model=PinAntwort)
def pin_stand(db: Datenbank, sprecher: SprecherId) -> PinAntwort:
    """Ob eine PIN gesetzt ist — ungeschützt, denn davon hängt ab, ob gefragt wird."""
    return PinAntwort(gesetzt=_hole(db, sprecher).pin_hash is not None)


@router.patch("/pin", response_model=PinAntwort)
def pin_setzen(aenderung: PinAenderung, db: Datenbank, sprecher: SprecherId) -> PinAntwort:
    """Die eigene PIN setzen, ändern oder (mit `pin: null`) wieder entfernen."""
    person = _hole(db, sprecher)
    person.pin_hash = pin.pruefwert(aenderung.pin) if aenderung.pin is not None else None
    db.commit()
    return PinAntwort(gesetzt=person.pin_hash is not None)


@router.get("", response_model=KontoAntwort, dependencies=[Depends(_pruefe_pin)])
def konto(sprecher: SprecherId, db: Datenbank, ablage: Ablage) -> KontoAntwort:
    """Profil, Kennzahlen und Textquellen — die eigenen, wie die Aufsicht sie sieht."""
    person = _hole(db, sprecher)
    return KontoAntwort(
        sprecher=uebersicht.profil(db, person, ablage),
        quellen=uebersicht.quellen(db),
    )


@router.get("/sessions", response_model=SitzungenAntwort, dependencies=[Depends(_pruefe_pin)])
def sitzungen(db: Datenbank, ab: int = 0, anzahl: int = 10) -> SitzungenAntwort:
    """Die eigenen Sitzungen, jüngste zuerst, seitenweise."""
    return uebersicht.sitzungen_seite(db, ab, anzahl)


@router.get("/recordings", response_model=AufnahmenAntwort, dependencies=[Depends(_pruefe_pin)])
def aufnahmen(db: Datenbank, ablage: Ablage, ab: int = 0, anzahl: int = 10) -> AufnahmenAntwort:
    """Die eigenen Aufnahmen mit ihrem Text, neueste zuerst, seitenweise.

    Anhören und Verwerfen bleiben bei `api/recordings.py` — beides sind
    bereits sprecherbezogene Wege und brauchen keinen zweiten hier.
    """
    return uebersicht.aufnahmen_seite(db, ablage, ab, anzahl)
