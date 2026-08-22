"""Gemeinsame Abhängigkeiten der Endpunkte: Authentifizierung, Datenbank, Ablage.

Jede Anfrage nennt ihren Sprecher als Abfrageparameter `sprecher` — auch die
mit Formular- oder JSON-Rumpf. Grund ist das Korpus-Layout: je Sprecher eine
Datenbank (siehe `wortlaut/corpus.py`). Ohne den Sprecher wüsste der Server
nicht, welche Datei er öffnen soll.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from wortlaut import corpus, db, storage

from .config import einstellungen

# Engines sind teuer im Aufbau und beliebig oft wiederverwendbar.
_engines: dict[str, Engine] = {}


def engine_fuer(sprecher_id: str) -> Engine:
    """Engine für die Datenbank eines Sprechers; legt nichts an."""
    if sprecher_id not in _engines:
        pfad = corpus.datenbank_pfad(einstellungen().data_dir, sprecher_id)
        if not pfad.is_file():
            raise HTTPException(status_code=404, detail=f"Unbekannter Sprecher: {sprecher_id}")
        _engines[sprecher_id] = db.verbinde(pfad)
    return _engines[sprecher_id]


def vergiss_engine(sprecher_id: str) -> None:
    """Nach dem Löschen eines Sprechers: Verbindung aus dem Zwischenspeicher nehmen."""
    engine = _engines.pop(sprecher_id, None)
    if engine is not None:
        engine.dispose()


def _sprecher_sitzung(sprecher: str) -> Iterator[Session]:
    with Session(engine_fuer(sprecher)) as sitzung:
        yield sitzung


def _pruefe_token(authorization: Annotated[str | None, Header()] = None) -> None:
    """Bearer-Token gegen `WORTLAUT_AUTH_TOKEN`. Leerer Wert = offen (Entwicklung)."""
    erwartet = einstellungen().auth_token
    if not erwartet:
        return
    vorgelegt = (authorization or "").removeprefix("Bearer ")
    # Zeitkonstanter Vergleich über die UTF-8-Bytes: sonst verrät die
    # Antwortzeit den Anfang des Tokens. Verglichen wird ausdrücklich in Bytes,
    # weil `compare_digest` Zeichenketten mit Nicht-ASCII-Zeichen abweist — ein
    # Umlaut im Token genügt sonst für einen 500er statt eines sauberen 401.
    if not secrets.compare_digest(vorgelegt.encode("utf-8"), erwartet.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Nicht angemeldet")


def _ablage() -> storage.Ablage:
    return storage.oeffne_ablage(einstellungen().storage, einstellungen().data_dir)


# Kurzschreibweisen für die Signaturen der Endpunkte.
Datenbank = Annotated[Session, Depends(_sprecher_sitzung)]
Ablage = Annotated[storage.Ablage, Depends(_ablage)]
Authentifiziert = Depends(_pruefe_token)
