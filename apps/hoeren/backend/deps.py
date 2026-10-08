"""Gemeinsame Abhängigkeiten der Endpunkte: Zugang, Datenbank, Ablage.

Hier hängt die Bindung zwischen Aufrufer und Verzeichnis. Drei Arten von
Zugang, alle als `Authorization: Bearer …`:

* **Verwaltung** (`WORTLAUT_AUTH_TOKEN`) - Profile und Zugänge, keine Aufnahme.
  Es gibt nur einen Weg zu den Daten, und der leitet die Kennung ab.
* **Sprecherzugang** (`<sprecher_id>.<geheimnis>`, `wortlaut.zugang`) - zugleich
  die Kennung.
* **Aufsicht** (`WORTLAUT_ADMIN_TOKEN`) - über allen Korpora; nennt ihren
  Sprecher in der Adresse und hat ihre Wege deshalb unter `/api/admin/…`.
  Darf alles, was die Verwaltung darf.

Leer heißt bei beiden Token abgeschaltet. `?sprecher=` ist nur eine
Behauptung, die stimmen muss; weicht sie ab, kommt 403 statt eines stillen
Schreibens ins falsche Verzeichnis.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from wortlaut import corpus, db, schluessel, sprachen, storage
from wortlaut import zugang as zugangsdienst

from .config import einstellungen
from .db.models import Sprecher

# Engines sind teuer im Aufbau und beliebig oft wiederverwendbar.
_engines: dict[str, Engine] = {}


@dataclass(frozen=True)
class Zugang:
    """Wer ruft. `sprecher_id` ist leer, außer ein Sprecher ruft selbst."""

    art: str  # sprecher | verwaltung | aufsicht
    sprecher_id: str = ""


def engine_fuer(sprecher_id: str) -> Engine:
    """Engine für die Datenbank eines Sprechers; legt nichts an, aber holt sie ein.

    Vor dem ersten Zugriff laufen die offenen Migrationen - ein Update braucht
    so keinen Handgriff, und eine neue Spalte legt keinen bestehenden Korpus
    still. Die Datei wird vorher geprüft: `wende_migrationen_an` legte eine
    fehlende an, und ein Tippfehler in der Kennung ergäbe einen leeren Korpus
    statt 404.
    """
    if sprecher_id not in _engines:
        konfiguration = einstellungen()
        pfad = corpus.datenbank_pfad(konfiguration.data_dir, sprecher_id)
        if not pfad.is_file():
            raise HTTPException(status_code=404, detail=f"Unbekannter Sprecher: {sprecher_id}")
        db.wende_migrationen_an(pfad, konfiguration.migrationsverzeichnis)
        _engines[sprecher_id] = db.verbinde(pfad)
    return _engines[sprecher_id]


def vergiss_engine(sprecher_id: str) -> None:
    """Nach dem Löschen eines Sprechers: Verbindung aus dem Zwischenspeicher nehmen."""
    engine = _engines.pop(sprecher_id, None)
    if engine is not None:
        engine.dispose()


def _ist_aufsicht(vorgelegt: str) -> bool:
    """Der Aufsichtstoken, falls einer gesetzt ist. Leer = abgeschaltet."""
    erwartet = einstellungen().admin_token
    return bool(erwartet) and schluessel.gleich(vorgelegt, erwartet)


def _pruefe_aufsicht(authorization: Annotated[str | None, Header()] = None) -> None:
    """Wächter der Wege unter `/api/admin/…`.

    Ohne gesetzten `WORTLAUT_ADMIN_TOKEN` kommt niemand durch.
    """
    if not einstellungen().admin_token:
        raise HTTPException(
            status_code=401,
            detail="Die Aufsicht ist abgeschaltet: WORTLAUT_ADMIN_TOKEN ist nicht gesetzt.",
        )
    if not _ist_aufsicht(zugangsdienst.aus_kopf(authorization)):
        raise HTTPException(status_code=401, detail="Nicht angemeldet")


def _pruefe_verwaltung(authorization: Annotated[str | None, Header()] = None) -> None:
    """Bearer-Token gegen `WORTLAUT_AUTH_TOKEN`. Nicht gesetzt = abgeschaltet.

    Die Aufsicht kommt ebenfalls durch. Ohne gesetzten Token niemand: Keine
    Installation weiß, ob sie Entwicklung ist, und ein vergessener Token darf
    nicht die großzügigste Einstellung sein.
    """
    vorgelegt = zugangsdienst.aus_kopf(authorization)
    if _ist_aufsicht(vorgelegt):
        return
    if not einstellungen().auth_token:
        raise HTTPException(
            status_code=401,
            detail="Die Verwaltung ist abgeschaltet: WORTLAUT_AUTH_TOKEN ist nicht gesetzt.",
        )
    # Eine eigene Meldung, damit niemand den Fehler beim persönlichen Link sucht.
    if zugangsdienst.zerlege(vorgelegt) is not None:
        raise HTTPException(
            status_code=401, detail="Das ist ein Sprecherzugang, kein Verwalterzugang."
        )

    if not schluessel.gleich(vorgelegt, einstellungen().auth_token):
        raise HTTPException(status_code=401, detail="Nicht angemeldet")


def _wer_ruft(authorization: Annotated[str | None, Header()] = None) -> Zugang:
    """Die Kennung aus dem Vorgelegten ableiten - die einzige Stelle, die das tut."""
    vorgelegt = zugangsdienst.aus_kopf(authorization)
    # Die Aufsicht zuerst, sonst fiele sie in die Verwaltung.
    if _ist_aufsicht(vorgelegt):
        return Zugang(art="aufsicht")

    teile = zugangsdienst.zerlege(vorgelegt)
    if teile is None:
        _pruefe_verwaltung(authorization)
        return Zugang(art="verwaltung")

    sprecher_id, geheimnis = teile
    # Ein Zugang zu einem gelöschten Sprecher gilt schlicht nicht mehr.
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
    """Der Sprecher dieser Anfrage - aus dem Zugang, nie aus dem Parameter."""
    if zugang.art != "sprecher":
        raise HTTPException(
            status_code=401, detail="Für diesen Weg braucht es den Zugang eines Sprechers."
        )
    if sprecher is not None and sprecher != zugang.sprecher_id:
        # Die Behauptung im Parameter weicht ab - laut statt still.
        raise HTTPException(
            status_code=403,
            detail=f"Dieser Zugang gehört zu {zugang.sprecher_id}, die Anfrage nennt {sprecher}.",
        )
    return zugang.sprecher_id


def _sprecher_sitzung(sprecher_id: Annotated[str, Depends(_sprecher_id)]) -> Iterator[Session]:
    with Session(engine_fuer(sprecher_id)) as sitzung:
        yield sitzung


def _ablage() -> storage.Ablage:
    return storage.LokaleAblage(einstellungen().data_dir)


def _sprache(
    sprecher_id: Annotated[str, Depends(_sprecher_id)],
    sitzung: Annotated[Session, Depends(_sprecher_sitzung)],
) -> str:
    """Die Sprache dieses Profils - aus der Sitzung, die ohnehin offen ist.

    Für alles, was für diesen Menschen gelesen oder gesprochen wird.
    """
    sprecher = sitzung.get(Sprecher, sprecher_id)
    return sprecher.sprache if sprecher is not None else sprachen.VORGABE


# Kurzschreibweisen für die Signaturen der Endpunkte.
SprecherId = Annotated[str, Depends(_sprecher_id)]
Sprache = Annotated[str, Depends(_sprache)]
Datenbank = Annotated[Session, Depends(_sprecher_sitzung)]
Ablage = Annotated[storage.Ablage, Depends(_ablage)]
Wer = Annotated[Zugang, Depends(_wer_ruft)]
Verwaltung = Depends(_pruefe_verwaltung)
Aufsicht = Depends(_pruefe_aufsicht)
