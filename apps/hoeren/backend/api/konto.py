"""Ein Sprecher sieht sich selbst an - dieselben Daten, die die Aufsicht sieht.

Anders als in `api/admin.py` steht kein Sprecher in der Adresse: Die Kennung
kommt aus dem Zugang (`deps.py`), geöffnet wird nur die eigene Datenbank.

Ein Sprecher darf über seine Daten alles bis auf die zwei großen Löschstufen,
die bei der Aufsicht bleiben: ansehen, umbenennen, Sicherung und Datensatz
mitnehmen (über `services/ausleitung.py`, wie die Aufsicht). Anhören und
Verwerfen einer Aufnahme stehen in `api/recordings.py`.

Mit gesetzter PIN (`services/pin.py`) verlangt jeder Weg hier `X-Pin` - außer
`GET .../pin`, sonst ließe sich nicht fragen, ob gefragt werden muss, und
`PATCH .../pin`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..db.models import Sprecher
from ..deps import Ablage, Datenbank, SprecherId
from ..services import ausleitung, pin, uebersicht
from ..services.pin import PinAenderung, PinAntwort
from ..services.uebersicht import (
    AufnahmenAntwort,
    QuelleAntwort,
    UebersichtAntwort,
    Umbenennung,
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
    """Wächter dieser Ansicht - nur scharf, wenn eine PIN gesetzt ist."""
    person = _hole(db, sprecher)
    if person.pin_hash is not None and not pin.stimmt(x_pin or "", person.pin_hash):
        raise HTTPException(status_code=401, detail="Falsche oder fehlende PIN.")


def _hole(db: Datenbank, sprecher: SprecherId) -> Sprecher:
    person = db.get(Sprecher, sprecher)
    assert person is not None  # `SprecherId` hat die Datenbank schon geöffnet.
    return person


@router.get("/pin", response_model=PinAntwort)
def pin_stand(db: Datenbank, sprecher: SprecherId) -> PinAntwort:
    """Ob eine PIN gesetzt ist - ungeschützt, denn davon hängt ab, ob gefragt wird."""
    return PinAntwort(gesetzt=_hole(db, sprecher).pin_hash is not None)


@router.get("/pin/pruefung", status_code=204, dependencies=[Depends(_pruefe_pin)])
def pin_pruefung() -> None:
    """Stimmt die vorgelegte PIN? Für „Darstellung" und „Zugangsdaten", die
    nichts abzurufen haben (`packages/ui/pin.svelte.ts`). Die Arbeit tut
    `_pruefe_pin`; 204 heißt ja."""


@router.patch("/pin", response_model=PinAntwort)
def pin_setzen(aenderung: PinAenderung, db: Datenbank, sprecher: SprecherId) -> PinAntwort:
    """Die eigene PIN setzen, ändern oder (mit `pin: null`) wieder entfernen."""
    person = _hole(db, sprecher)
    person.pin_hash = pin.pruefwert(aenderung.pin) if aenderung.pin is not None else None
    db.commit()
    return PinAntwort(gesetzt=person.pin_hash is not None)


@router.get("", response_model=KontoAntwort, dependencies=[Depends(_pruefe_pin)])
def konto(sprecher: SprecherId, db: Datenbank, ablage: Ablage) -> KontoAntwort:
    """Profil, Kennzahlen und Textquellen - die eigenen, wie die Aufsicht sie sieht.

    „Sitzungen" zählt nur die mit Aufnahmen; wer die Seite nur geöffnet hat,
    hat keine Sitzung erlebt. Die Aufsicht zählt alle.
    """
    person = _hole(db, sprecher)
    return KontoAntwort(
        sprecher=uebersicht.profil(db, person, ablage, nur_sitzungen_mit_aufnahmen=True),
        quellen=uebersicht.quellen(db),
    )


@router.get(
    "/aufnahmezeiten", response_model=list[str], dependencies=[Depends(_pruefe_pin)]
)
def aufnahmezeiten(db: Datenbank) -> list[str]:
    """Wann jede eigene gültige Aufnahme entstand - Stoff für den Kalender in
    „Meine Daten", der sie nach Tagen in der Zeitzone des Betrachters zählt."""
    return uebersicht.aufnahmezeiten(db)


@router.get("/recordings", response_model=AufnahmenAntwort, dependencies=[Depends(_pruefe_pin)])
def aufnahmen(db: Datenbank, ablage: Ablage, ab: int = 0, anzahl: int = 10) -> AufnahmenAntwort:
    """Die eigenen Aufnahmen mit ihrem Text, neueste zuerst, seitenweise.

    Anhören und Verwerfen: `api/recordings.py`.
    """
    return uebersicht.aufnahmen_seite(db, ablage, ab, anzahl)


@router.patch("", response_model=UebersichtAntwort, dependencies=[Depends(_pruefe_pin)])
def umbenennen(
    aenderung: Umbenennung, db: Datenbank, sprecher: SprecherId, ablage: Ablage
) -> UebersichtAntwort:
    """Den eigenen Namen ändern - dieselbe Beschriftung, die die Aufsicht ändert.

    Die Kennung bleibt - sie steckt im Zugang und in den Pfaden.
    """
    person = _hole(db, sprecher)
    person.name = aenderung.name
    db.commit()
    return uebersicht.profil(db, person, ablage, nur_sitzungen_mit_aufnahmen=True)


@router.get("/sicherung", dependencies=[Depends(_pruefe_pin)])
def sicherung(db: Datenbank, sprecher: SprecherId) -> FileResponse:
    """Der eigene Stand als `.tgz` - dieselbe Datei, die die Aufsicht zieht."""
    return ausleitung.sicherung_eines(_hole(db, sprecher))


@router.get("/datensatz", dependencies=[Depends(_pruefe_pin)])
def datensatz(db: Datenbank, sprecher: SprecherId, ablage: Ablage) -> FileResponse:
    """Die eigenen Text-Audio-Paare als `.zip` - zum Mitnehmen, nicht zum Sichern."""
    return ausleitung.datensatz_eines(db, _hole(db, sprecher), ablage)
