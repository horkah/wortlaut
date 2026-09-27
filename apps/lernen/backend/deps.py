"""Gemeinsame Abhängigkeiten der Endpunkte: Zugang und Korpus.

Der Sprecher wird aus dem Zugang abgeleitet, wie in den anderen Apps. Eine
eigene Datenbank hat „lernen" nicht: Läufe und Stände sind Verzeichnisse.

Der Korpus (`hoeren.sqlite`) gehört „hören" (Grundentscheidung 6) und wird
hier nur gelesen - es gibt keinen Weg, der in ihn schreibt.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from wortlaut import corpus, db
from wortlaut import zugang as zugangsdienst

from .config import einstellungen

_korpus_engines: dict[str, Engine] = {}


def korpus_engine(sprecher_id: str) -> Engine:
    """Der Korpus dieses Sprechers - lesend.

    Ohne Migrationen und ohne Anlegen: Eine fehlende Datei ist ein 404, kein
    leerer Korpus aus einem Tippfehler.
    """
    if sprecher_id not in _korpus_engines:
        pfad = corpus.datenbank_pfad(einstellungen().data_dir, sprecher_id)
        if not pfad.is_file():
            raise HTTPException(status_code=404, detail=f"Unbekannter Sprecher: {sprecher_id}")
        _korpus_engines[sprecher_id] = db.verbinde(pfad)
    return _korpus_engines[sprecher_id]


def vergiss_engines(sprecher_id: str = "") -> None:
    """Nach dem Löschen eines Sprechers - und zwischen zwei Tests."""
    namen = [sprecher_id] if sprecher_id else list(_korpus_engines)
    for name in namen:
        engine = _korpus_engines.pop(name, None)
        if engine is not None:
            engine.dispose()


def _zugang(
    authorization: Annotated[str | None, Header()] = None,
) -> zugangsdienst.Sprecherzugang:
    """Der geprüfte Zugang, samt Sprache des Profils.

    Nur der Sprecherzugang gilt: Ein Modell gehört einem Menschen. Verwaltung
    und Aufsicht schauen in „hören". `wortlaut.zugang.pruefe` öffnet den Korpus
    lesend (`mode=ro`).
    """
    vorgelegt = (authorization or "").removeprefix("Bearer ")
    # Ein Verwalter- oder Aufsichtstoken soll nicht wie ein abgelaufener
    # persönlicher Link klingen; die Form entscheidet das ohne Datenbank.
    if zugangsdienst.zerlege(vorgelegt) is None:
        raise HTTPException(
            status_code=401, detail="Für diesen Weg braucht es den Zugang eines Sprechers."
        )

    wer = zugangsdienst.pruefe(einstellungen().data_dir, vorgelegt)
    if wer is None:
        raise HTTPException(status_code=401, detail="Dieser Zugang gilt nicht mehr.")
    return wer


def _sprecher_id(wer: Annotated[zugangsdienst.Sprecherzugang, Depends(_zugang)]) -> str:
    return wer.sprecher_id


def _sprache(wer: Annotated[zugangsdienst.Sprecherzugang, Depends(_zugang)]) -> str:
    """Für den Trainingsauftrag: `auftrag.json` hält fest, wofür trainiert wurde."""
    return wer.sprache


def _korpus(sprecher_id: Annotated[str, Depends(_sprecher_id)]) -> Iterator[Session]:
    with Session(korpus_engine(sprecher_id)) as sitzung:
        yield sitzung


SprecherId = Annotated[str, Depends(_sprecher_id)]
Sprache = Annotated[str, Depends(_sprache)]
Korpus = Annotated[Session, Depends(_korpus)]
