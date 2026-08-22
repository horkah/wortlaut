"""Zugänge ausgeben, zurückziehen und auskunft geben, wer gerade ruft.

Drei Endpunkte, zwei Wächter:

* `GET /api/zugang` beantwortet die Frage, für wen dieser Browser gerade
  eingestellt ist. Er hat keinen eigenen Wächter, denn er ist die Antwort
  darauf — die Kennung kommt aus dem Vorgelegten.
* `POST` und `DELETE` unter einem Sprecher gehören der Verwaltung. Sie geben
  den Zugang aus bzw. ziehen ihn zurück.

Der Zugang wird genau einmal im Klartext zurückgegeben, beim Ausgeben.
Gespeichert ist nur sein Prüfwert; ein zweites Mal ist er nicht zu haben. Wer
ihn verliert, lässt einen neuen ausgeben — und der alte gilt damit nicht mehr.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.models import Sprecher, jetzt
from ..deps import Verwaltung, Wer, engine_fuer
from ..services import zugang as zugangsdienst

router = APIRouter(tags=["Zugang"])


class WerAntwort(BaseModel):
    """Wer ruft — die Grundlage dafür, dass die Oberfläche es anzeigen kann."""

    art: str  # sprecher | verwaltung
    sprecher_id: str | None = None
    name: str | None = None


class ZugangAntwort(BaseModel):
    sprecher_id: str
    # Der Zugang im Klartext — nur hier, nur dieses eine Mal.
    zugang: str
    erneuert: str


@router.get("/api/zugang", response_model=WerAntwort)
def wer_ruft(wer: Wer) -> WerAntwort:
    if wer.art != "sprecher":
        return WerAntwort(art=wer.art)
    with Session(engine_fuer(wer.sprecher_id)) as sitzung:
        sprecher = sitzung.get(Sprecher, wer.sprecher_id)
        name = sprecher.name if sprecher is not None else None
    return WerAntwort(art="sprecher", sprecher_id=wer.sprecher_id, name=name)


@router.post(
    "/api/speakers/{sprecher_id}/zugang",
    response_model=ZugangAntwort,
    status_code=201,
    dependencies=[Verwaltung],
)
def gib_aus(sprecher_id: str) -> ZugangAntwort:
    """Einen neuen Zugang ausgeben. Ein vorhandener gilt danach nicht mehr."""
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        neuer, hash_ = zugangsdienst.erzeuge(sprecher_id)
        sprecher.zugang_hash = hash_
        sprecher.zugang_erneuert = jetzt()
        sitzung.commit()
        return ZugangAntwort(
            sprecher_id=sprecher_id, zugang=neuer, erneuert=sprecher.zugang_erneuert
        )


@router.delete("/api/speakers/{sprecher_id}/zugang", status_code=204, dependencies=[Verwaltung])
def zieh_zurueck(sprecher_id: str) -> None:
    """Den Zugang zurückziehen, ohne Ersatz. Danach kommt niemand mehr herein.

    Für einen verlorenen Zugang genügt das Ausgeben eines neuen; das hier ist
    der Fall, in dem gar niemand mehr hineinsoll — bis ein neuer ausgegeben
    wird.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        sprecher.zugang_hash = None
        sprecher.zugang_erneuert = None
        sitzung.commit()


def _hole(sitzung: Session, sprecher_id: str) -> Sprecher:
    sprecher = sitzung.get(Sprecher, sprecher_id)
    if sprecher is None:
        raise HTTPException(status_code=404, detail="Unbekannter Sprecher")
    return sprecher
