"""Die Aufteilung ansehen - wer lernt, wer steuert, wer prüft.

Ein einziger Weg, und er ist bewusst nur lesend: Die Zuteilung wird nicht
gewählt, sondern vergeben (siehe `services/aufteilung.py`). Ein Endpunkt, der
sie ändern könnte, wäre der Weg, auf dem eine Testaufnahme ins Training
rutscht - und damit der Weg, auf dem jede spätere Zahl ihren Wert verliert.

Zugeteilt wird beim Hinsehen: Diese Abfrage holt nach, was seit dem letzten
Mal aufgenommen wurde. Deshalb ist sie kein reines `GET` im strengen Sinne -
sie legt Zeilen an. Der Alternative, einen Knopf „jetzt zuteilen" danebenzu-
stellen, fehlt nichts als die Gewissheit, dass ihn jemand drückt.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from wortlaut import laeufe

from ..deps import Datenbank, Korpus, SprecherId
from ..services import aufteilung

router = APIRouter(prefix="/lernen/api/aufteilung", tags=["Aufteilung"])


class TeilAntwort(BaseModel):
    """Ein Teil der Aufteilung, wie die Oberfläche ihn beschriftet."""

    schluessel: str
    name: str
    erklaerung: str


TEILE = [
    TeilAntwort(
        schluessel=laeufe.TRAIN,
        name="Training",
        erklaerung="Daraus lernt das Modell.",
    ),
    TeilAntwort(
        schluessel=laeufe.VALIDIERUNG,
        name="Validierung",
        erklaerung="Steuert das Lernen, wird aber nicht gelernt - die zweite Kurve.",
    ),
    TeilAntwort(
        schluessel=laeufe.TEST,
        name="Test",
        erklaerung="Bleibt ungesehen, bis das Modell fertig ist. Daran wird gemessen.",
    ),
]


class ProbeAntwort(BaseModel):
    nummer: int
    aufnahme_id: str
    teil: str
    dauer_s: float
    erstellt: str
    text: str


class AufteilungAntwort(BaseModel):
    teile: list[TeilAntwort]
    # Das Muster, das die Zuteilung befolgt - die Oberfläche zeigt es, damit
    # niemand das Verhältnis aus den Zahlen zurückrechnen muss.
    muster: list[str]
    anzahl: dict[str, int]
    sekunden: dict[str, float]
    proben: list[ProbeAntwort]
    # Zuteilungen ohne Aufnahme: Die Aufnahme wurde gelöscht, der Platz bleibt
    # vergeben. Sichtbar, damit die Summe unten aufgeht.
    verwaist: int


@router.get("", response_model=AufteilungAntwort)
def uebersicht(db: Datenbank, korpus: Korpus, sprecher: SprecherId) -> AufteilungAntwort:
    proben = aufteilung.proben(db, korpus)
    return AufteilungAntwort(
        teile=TEILE,
        muster=list(laeufe.MUSTER),
        anzahl=aufteilung.zaehle(proben),
        sekunden={
            teil: round(sum(p.aufnahme.dauer_s for p in proben if p.teil == teil), 1)
            for teil in laeufe.TEILE
        },
        proben=[
            ProbeAntwort(
                nummer=probe.nummer,
                aufnahme_id=probe.aufnahme.id,
                teil=probe.teil,
                dauer_s=probe.aufnahme.dauer_s,
                erstellt=probe.aufnahme.erstellt,
                text=probe.vorlage.text,
            )
            for probe in proben
        ],
        verwaist=len(aufteilung.verwaist(db, korpus)),
    )
