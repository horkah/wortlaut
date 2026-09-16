"""Sprecherprofile: Name und Sprache. Sonst nichts.

Ein Profil anzulegen heißt, ein Korpusverzeichnis mit eigener Datenbank
anzulegen. Alle anderen Endpunkte setzen ein bestehendes Profil voraus.

**Ein Basismodell stand hier einmal daneben.** Es hat nie etwas entschieden:
Welches Grundmodell trainiert wird, steht in der Bestellung des Laufs, und
welches diktiert, entscheidet die Freigabe in „lernen". Das Feld wurde
gelesen, um angezeigt zu werden, und sonst nirgends - die Auswahl beim Anlegen
versprach etwas, das sie nicht hielt (`013_ohne_profilbasismodell.sql`).

Diese Wege gehören der Verwaltung (`WORTLAUT_AUTH_TOKEN`, siehe `deps.py`).
Ein frisch angelegtes Profil hat noch keinen Zugang und ist damit für
niemanden erreichbar - der Zugang wird gesondert ausgegeben (`api/zugang.py`).
`zugang_erneuert` sagt in der Liste, ob schon einer besteht.
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
    # Die Vorgabe steht in `wortlaut/sprachen.py` und nicht hier. Solange es
    # eine Sprache gibt, kommt dasselbe heraus; der Unterschied zeigt sich bei
    # der zweiten, und dann an genau einer Stelle.
    sprache: str = sprachen.VORGABE

    @field_validator("sprache")
    @classmethod
    def _bekannte_sprache(cls, wert: str) -> str:
        """Abweisen, was dieses System nicht kann - und normiert ablegen.

        Ein Profil trägt seine Sprache ein Leben lang: Sie entscheidet über
        die Vorlagen, das Feintuning und die Bewertung, und keiner der drei
        Wege prüft sie noch einmal nach. Was hier durchkommt, ist damit
        gesetzt - deshalb wird es hier geprüft und nicht später.
        """
        try:
            return sprachen.pruefe(wert)
        except sprachen.UnbekannteSprache as fehler:
            raise ValueError(str(fehler)) from fehler


# Was ein Profil ist, steht an einer Stelle und nicht an zweien: in
# `services/uebersicht.py`. Diese Datei liefert es nackt aus, die Aufsicht mit
# Kennzahlen daneben - und ein neues Feld erreicht beide, ohne dass jemand
# daran denken müsste (siehe den Kopf von `ProfilAntwort`).
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
        # Innerhalb der Sitzung auslesen: danach ist die Instanz abgelöst und
        # kann ihre Felder nicht mehr nachladen.
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
