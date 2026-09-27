"""Sprecherprofile: Name und Sprache. Sonst nichts.

Ein Profil anzulegen heißt, ein Korpusverzeichnis mit eigener Datenbank
anzulegen. Welches Grundmodell trainiert wird, steht im Auftrag des Laufs,
welches diktiert, in der Freigabe von „lernen".

Diese Wege gehören der Verwaltung. Ein neues Profil hat noch keinen Zugang
(`api/zugang.py`); `zugang_erneuert` sagt, ob einer besteht.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from wortlaut import corpus, db, ids, sprachen

from ..config import einstellungen
from ..db.models import Sprecher, jetzt
from ..deps import engine_fuer
from ..services.uebersicht import ProfilAntwort, profilfelder

router = APIRouter(prefix="/api/speakers", tags=["Sprecher"])


class NeuerSprecher(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sprache: str = sprachen.VORGABE

    @field_validator("sprache")
    @classmethod
    def _bekannte_sprache(cls, wert: str) -> str:
        """Abweisen, was dieses System nicht kann - und normiert ablegen.

        Ein Profil trägt seine Sprache ein Leben lang, und niemand prüft sie
        später nach.
        """
        try:
            return sprachen.pruefe(wert)
        except sprachen.UnbekannteSprache as fehler:
            raise ValueError(str(fehler)) from fehler


# Was ein Profil ist, steht in `services/uebersicht.py`; die Aufsicht zeigt
# dasselbe mit Kennzahlen.
SprecherAntwort = ProfilAntwort


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
        erstellt=jetzt(),
    )
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sitzung.add(sprecher)
        sitzung.commit()
        # In der Sitzung auslesen - danach ist die Instanz abgelöst.
        return _als_antwort(sprecher)


@router.get("", response_model=list[SprecherAntwort])
def liste() -> list[SprecherAntwort]:
    """Alle Profile - die Verzeichnisse unter `data/korpus/` sind die Liste."""
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
    return SprecherAntwort(**profilfelder(sprecher))
