"""Zugänge ausgeben, zurückziehen und auskunft geben, wer gerade ruft.

* `GET /api/zugang` sagt, für wen dieser Browser eingestellt ist - Sprecher,
  Verwaltung oder Aufsicht - und was die mitgeschickten Schlüssel gerade
  öffnen (`wortlaut.schluessel`); die Antwort kommt aus dem Vorgelegten.
* `POST` und `DELETE` unter einem Sprecher gehören der Verwaltung.

Im Klartext gibt es den Zugang genau einmal, beim Ausgeben; gespeichert ist
nur der Prüfwert. Ein neuer macht den alten ungültig.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from wortlaut import schluessel
from wortlaut import zugang as zugangsdienst

from ..config import einstellungen
from ..db.models import Sprecher, jetzt
from ..deps import Verwaltung, Wer, engine_fuer

router = APIRouter(tags=["Zugang"])


class WerAntwort(BaseModel):
    """Wer ruft - die Grundlage dafür, dass die Oberfläche es anzeigen kann."""

    art: str  # sprecher | verwaltung | aufsicht
    sprecher_id: str | None = None
    name: str | None = None
    # Die Sprache des Profils, für das Vorlesen (`packages/ui/speak.ts`); leer
    # für Verwaltung und Aufsicht.
    sprache: str | None = None
    # Je Recht der Stand des Schlüssels: `aus`, `fehlt`, `falsch` oder `gilt`.
    # Dieselbe Rechnung wie in den Wächtern - die Oberfläche zeigt danach,
    # was geht, und blendet aus, was nicht geht.
    trainieren: str = schluessel.AUS
    bearbeiten: str = schluessel.AUS


class ZugangAntwort(BaseModel):
    sprecher_id: str
    # Der Zugang im Klartext - nur hier, nur dieses eine Mal.
    zugang: str
    erneuert: str


@router.get("/api/zugang", response_model=WerAntwort)
def wer_ruft(
    wer: Wer,
    trainerschluessel: Annotated[str | None, Header(alias=schluessel.TRAINER.kopf)] = None,
    bearbeitungsschluessel: Annotated[
        str | None, Header(alias=schluessel.BEARBEITUNG.kopf)
    ] = None,
) -> WerAntwort:
    konfiguration = einstellungen()
    rechte = {
        "trainieren": schluessel.TRAINER.stand(konfiguration.trainer_key, trainerschluessel),
        "bearbeiten": schluessel.BEARBEITUNG.stand(
            konfiguration.editor_key, bearbeitungsschluessel
        ),
    }
    if wer.art != "sprecher":
        return WerAntwort(art=wer.art, **rechte)
    with Session(engine_fuer(wer.sprecher_id)) as sitzung:
        sprecher = sitzung.get(Sprecher, wer.sprecher_id)
        name = sprecher.name if sprecher is not None else None
        sprache = sprecher.sprache if sprecher is not None else None
    return WerAntwort(
        art="sprecher", sprecher_id=wer.sprecher_id, name=name, sprache=sprache, **rechte
    )


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

    Für einen verlorenen Zugang genügt ein neuer; das hier sperrt, bis einer
    ausgegeben wird.
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
