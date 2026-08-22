"""Sprecherprofile: Name, Sprache, Basismodell. Sonst nichts.

Ein Profil anzulegen heißt, ein Korpusverzeichnis mit eigener Datenbank
anzulegen. Alle anderen Endpunkte setzen ein bestehendes Profil voraus.

Diese Wege gehören der Verwaltung (`WORTLAUT_AUTH_TOKEN`, siehe `deps.py`).
Ein frisch angelegtes Profil hat noch keinen Zugang und ist damit für
niemanden erreichbar — der Zugang wird gesondert ausgegeben (`api/zugang.py`).
`zugang_erneuert` sagt in der Liste, ob schon einer besteht.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from wortlaut import corpus, db, ids

from ..config import einstellungen
from ..db.models import Sprecher, jetzt
from ..deps import engine_fuer

router = APIRouter(prefix="/api/speakers", tags=["Sprecher"])


class NeuerSprecher(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sprache: str = "de"
    basismodell: str = "openai/whisper-large-v3"


class SprecherAntwort(BaseModel):
    id: str
    name: str
    sprache: str
    basismodell: str
    erstellt: str
    # Wann der geltende Zugang ausgegeben wurde; None heißt: keiner da. Der
    # Zugang selbst steht hier nie — er ist nur beim Ausgeben zu sehen.
    zugang_erneuert: str | None = None


@router.post("", response_model=SprecherAntwort, status_code=201)
def lege_an(eingabe: NeuerSprecher) -> SprecherAntwort:
    konfiguration = einstellungen()
    sprecher_id = ids.neue_id("spr")

    datenbank = corpus.datenbank_pfad(konfiguration.data_dir, sprecher_id)
    db.wende_migrationen_an(datenbank, konfiguration.migrationsverzeichnis)

    sprecher = Sprecher(
        id=sprecher_id,
        name=eingabe.name.strip(),
        sprache=eingabe.sprache,
        basismodell=eingabe.basismodell,
        erstellt=jetzt(),
    )
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sitzung.add(sprecher)
        sitzung.commit()
        # Innerhalb der Sitzung auslesen: danach ist die Instanz abgelöst und
        # kann ihre Felder nicht mehr nachladen.
        return _als_antwort(sprecher)


@router.get("", response_model=list[SprecherAntwort])
def liste() -> list[SprecherAntwort]:
    """Alle Profile — die Verzeichnisse unter `data/korpus/` sind die Liste."""
    antworten: list[SprecherAntwort] = []
    for sprecher_id in corpus.sprecher_ids(einstellungen().data_dir):
        with Session(engine_fuer(sprecher_id)) as sitzung:
            sprecher = sitzung.get(Sprecher, sprecher_id)
            if sprecher is not None:
                antworten.append(_als_antwort(sprecher))
    return antworten


@router.get("/{sprecher_id}", response_model=SprecherAntwort)
def einzeln(sprecher_id: str) -> SprecherAntwort:
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = sitzung.get(Sprecher, sprecher_id)
        if sprecher is None:
            raise HTTPException(status_code=404, detail="Unbekannter Sprecher")
        return _als_antwort(sprecher)


def _als_antwort(sprecher: Sprecher) -> SprecherAntwort:
    return SprecherAntwort(
        id=sprecher.id,
        name=sprecher.name,
        sprache=sprecher.sprache,
        basismodell=sprecher.basismodell,
        erstellt=sprecher.erstellt,
        zugang_erneuert=sprecher.zugang_erneuert,
    )
