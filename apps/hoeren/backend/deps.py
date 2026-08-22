"""Gemeinsame Abhängigkeiten der Endpunkte: Zugang, Datenbank, Ablage.

Hier hängt die Bindung zwischen Aufrufer und Verzeichnis. Es gibt zwei Arten
von Zugang, beide als `Authorization: Bearer …`:

* **Verwaltung** — `WORTLAUT_AUTH_TOKEN`. Legt Sprecherprofile an, gibt deren
  Zugänge aus und zieht sie zurück. Sie kommt an keine Aufnahme heran; wer für
  einen Sprecher aufnehmen will, benutzt dessen Zugang. Das ist der Preis
  dafür, dass es nur **einen** Weg zu den Daten gibt und der die Kennung
  ableitet.
* **Sprecherzugang** — `<sprecher_id>.<geheimnis>` (siehe `services/zugang.py`).
  Er ist zugleich die Kennung: Der Server spaltet ihn, öffnet die Datenbank
  dieses Sprechers und prüft dort den Prüfwert.

`?sprecher=` gibt es weiterhin, aber nur noch als Behauptung, die stimmen muss.
Weicht sie von der abgeleiteten Kennung ab — alter Reiter, falsches Lesezeichen,
falsch konfiguriertes „schreiben" —, ist die Antwort 403. Ein Fehlgriff wird so
laut, statt still ins falsche Verzeichnis zu schreiben.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from wortlaut import corpus, db, storage

from .config import einstellungen
from .db.models import Sprecher
from .services import zugang as zugangsdienst

# Engines sind teuer im Aufbau und beliebig oft wiederverwendbar.
_engines: dict[str, Engine] = {}


@dataclass(frozen=True)
class Zugang:
    """Wer ruft. `sprecher_id` ist leer, solange die Verwaltung ruft."""

    art: str  # sprecher | verwaltung
    sprecher_id: str = ""


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


def _vorgelegt(authorization: str | None) -> str:
    return (authorization or "").removeprefix("Bearer ")


def _pruefe_verwaltung(authorization: Annotated[str | None, Header()] = None) -> None:
    """Bearer-Token gegen `WORTLAUT_AUTH_TOKEN`. Leerer Wert = offen (Entwicklung)."""
    vorgelegt = _vorgelegt(authorization)
    # Ein Sprecherzugang ist hier kein schwächerer Verwalter, sondern etwas
    # anderes. Ohne diese Zeile käme er auf einem Server ohne gesetzten Token
    # durch und dürfte Profile anlegen — genau die stille Verwechslung, gegen
    # die dieser Umbau angetreten ist.
    if zugangsdienst.zerlege(vorgelegt) is not None:
        raise HTTPException(
            status_code=401, detail="Das ist ein Sprecherzugang, kein Verwalterzugang."
        )

    erwartet = einstellungen().auth_token
    if not erwartet:
        return
    # Zeitkonstanter Vergleich über die UTF-8-Bytes: sonst verrät die
    # Antwortzeit den Anfang des Tokens. Verglichen wird ausdrücklich in Bytes,
    # weil `compare_digest` Zeichenketten mit Nicht-ASCII-Zeichen abweist — ein
    # Umlaut im Token genügt sonst für einen 500er statt eines sauberen 401.
    if not secrets.compare_digest(vorgelegt.encode("utf-8"), erwartet.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Nicht angemeldet")


def _wer_ruft(authorization: Annotated[str | None, Header()] = None) -> Zugang:
    """Die Kennung aus dem Vorgelegten ableiten — die einzige Stelle, die das tut."""
    teile = zugangsdienst.zerlege(_vorgelegt(authorization))
    if teile is None:
        _pruefe_verwaltung(authorization)
        return Zugang(art="verwaltung")

    sprecher_id, geheimnis = teile
    # Ein Zugang zu einem gelöschten Sprecher ist kein „nicht gefunden", sondern
    # ein Zugang, der nicht mehr gilt: Die Kennung stammt aus dem Zugang selbst,
    # niemand hat sie erraten.
    pfad = corpus.datenbank_pfad(einstellungen().data_dir, sprecher_id)
    if pfad.is_file():
        with Session(engine_fuer(sprecher_id)) as sitzung:
            sprecher = sitzung.get(Sprecher, sprecher_id)
            if sprecher is not None and zugangsdienst.stimmt(geheimnis, sprecher.zugang_hash):
                return Zugang(art="sprecher", sprecher_id=sprecher_id)
    raise HTTPException(status_code=401, detail="Dieser Zugang gilt nicht mehr.")


def _sprecher_id(
    zugang: Annotated[Zugang, Depends(_wer_ruft)], sprecher: str | None = None
) -> str:
    """Der Sprecher dieser Anfrage — aus dem Zugang, nie aus dem Parameter."""
    if zugang.art != "sprecher":
        raise HTTPException(
            status_code=401, detail="Für diesen Weg braucht es den Zugang eines Sprechers."
        )
    if sprecher is not None and sprecher != zugang.sprecher_id:
        # Die Behauptung im Parameter weicht von der abgeleiteten Kennung ab.
        # Laut werden statt still ins falsche Verzeichnis schreiben.
        raise HTTPException(
            status_code=403,
            detail=f"Dieser Zugang gehört zu {zugang.sprecher_id}, die Anfrage nennt {sprecher}.",
        )
    return zugang.sprecher_id


def _sprecher_sitzung(sprecher_id: Annotated[str, Depends(_sprecher_id)]) -> Iterator[Session]:
    with Session(engine_fuer(sprecher_id)) as sitzung:
        yield sitzung


def _ablage() -> storage.Ablage:
    return storage.oeffne_ablage(einstellungen().storage, einstellungen().data_dir)


# Kurzschreibweisen für die Signaturen der Endpunkte.
SprecherId = Annotated[str, Depends(_sprecher_id)]
Datenbank = Annotated[Session, Depends(_sprecher_sitzung)]
Ablage = Annotated[storage.Ablage, Depends(_ablage)]
Wer = Annotated[Zugang, Depends(_wer_ruft)]
Verwaltung = Depends(_pruefe_verwaltung)
