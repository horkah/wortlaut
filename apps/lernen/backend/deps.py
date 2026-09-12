"""Gemeinsame Abhängigkeiten der Endpunkte: Zugang, Datenbank, Korpus.

Dieselbe Aufgabe wie in `apps/hoeren/backend/deps.py` und `apps/schreiben/…`
und aus demselben Grund: Der Sprecher wird aus dem vorgelegten Zugang
**abgeleitet** und nirgends behauptet. Wer hier ein Modell trainiert,
trainiert sein eigenes; die Bindung zieht der Server, nicht der Aufrufer.

Zwei Datenbanken kommen hier zusammen, und die Richtung ist die ganze Ordnung
dieser App:

* **Der Korpus** (`hoeren.sqlite`) wird **nur gelesen**. Er gehört „hören"
  (Grundentscheidung 6). Daraus kommen die Aufnahmen, ihre Vorlagen und die
  Grundlinie - was die unveränderten Modelle in der Auswertung erreicht haben.
* **Die eigene Datenbank** (`lernen.sqlite`) wird geschrieben. Darin steht
  genau eine Sache: die Aufteilung in Lernen und Prüfen.

Dass der Korpus hier nur lesend vorkommt, ist keine Zusage auf Papier: Es gibt
in dieser App keinen Weg, der in ihn schreibt.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from wortlaut import corpus, db
from wortlaut import zugang as zugangsdienst

from apps.hoeren.backend.db.models import Sprecher

from .config import einstellungen

_engines: dict[str, Engine] = {}
_korpus_engines: dict[str, Engine] = {}


def engine_fuer(sprecher_id: str) -> Engine:
    """Die Lerndatenbank eines Sprechers; legt sie beim ersten Zugriff an.

    Anlegen ist hier unbedenklich - es ist die eigene Ablage dieser App. Der
    Korpus daneben wird ausdrücklich nicht angelegt (siehe `korpus_engine`).
    """
    if sprecher_id not in _engines:
        konfiguration = einstellungen()
        pfad = konfiguration.datenbank(sprecher_id)
        db.wende_migrationen_an(pfad, konfiguration.migrationsverzeichnis)
        _engines[sprecher_id] = db.verbinde(pfad)
    return _engines[sprecher_id]


def korpus_engine(sprecher_id: str) -> Engine:
    """Der Korpus dieses Sprechers - lesend.

    Ohne Migrationen und ohne Anlegen: Beides ist Sache von „hören". Fehlt die
    Datei, ist der Sprecher hier unbekannt, und das ist ein 404 und kein
    frisch angelegter, leerer Korpus. Genau diese Reihenfolge verhindert, dass
    ein Tippfehler in einer Kennung einen Korpus erzeugt.
    """
    if sprecher_id not in _korpus_engines:
        pfad = corpus.datenbank_pfad(einstellungen().data_dir, sprecher_id)
        if not pfad.is_file():
            raise HTTPException(status_code=404, detail=f"Unbekannter Sprecher: {sprecher_id}")
        _korpus_engines[sprecher_id] = db.verbinde(pfad)
    return _korpus_engines[sprecher_id]


def vergiss_engines(sprecher_id: str = "") -> None:
    """Nach dem Löschen eines Sprechers - und zwischen zwei Tests."""
    for zwischenspeicher in (_engines, _korpus_engines):
        namen = [sprecher_id] if sprecher_id else list(zwischenspeicher)
        for name in namen:
            engine = zwischenspeicher.pop(name, None)
            if engine is not None:
                engine.dispose()


def _sprecher_id(authorization: Annotated[str | None, Header()] = None) -> str:
    """Die Kennung aus dem vorgelegten Zugang - die einzige Stelle, die das tut.

    Nur der Sprecherzugang gilt. Verwaltung und Aufsicht kommen hier nicht
    durch, und das ist kein Versehen: Ein Modell gehört einem Menschen, und
    wer keines hat, hat hier nichts zu sehen. Wer über alle Korpora schauen
    will, tut das in „hören", wo die Aufsicht zu Hause ist.
    """
    vorgelegt = (authorization or "").removeprefix("Bearer ")
    teile = zugangsdienst.zerlege(vorgelegt)
    if teile is None:
        raise HTTPException(
            status_code=401, detail="Für diesen Weg braucht es den Zugang eines Sprechers."
        )

    sprecher_id, geheimnis = teile
    pfad = corpus.datenbank_pfad(einstellungen().data_dir, sprecher_id)
    if pfad.is_file():
        with Session(korpus_engine(sprecher_id)) as sitzung:
            person = sitzung.get(Sprecher, sprecher_id)
            if person is not None and zugangsdienst.stimmt(geheimnis, person.zugang_hash):
                return sprecher_id
    raise HTTPException(status_code=401, detail="Dieser Zugang gilt nicht mehr.")


def _sitzung(sprecher_id: Annotated[str, Depends(_sprecher_id)]) -> Iterator[Session]:
    with Session(engine_fuer(sprecher_id)) as sitzung:
        yield sitzung


def _korpus(sprecher_id: Annotated[str, Depends(_sprecher_id)]) -> Iterator[Session]:
    with Session(korpus_engine(sprecher_id)) as sitzung:
        yield sitzung


SprecherId = Annotated[str, Depends(_sprecher_id)]
Datenbank = Annotated[Session, Depends(_sitzung)]
Korpus = Annotated[Session, Depends(_korpus)]
