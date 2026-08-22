"""Gemeinsame Abhängigkeiten der Endpunkte: Zugang, Datenbank, Ablage.

Hier hängt die Bindung zwischen Aufrufer und Verzeichnis. Es gibt drei Arten
von Zugang, alle als `Authorization: Bearer …`:

* **Verwaltung** — `WORTLAUT_AUTH_TOKEN`. Legt Sprecherprofile an, gibt deren
  Zugänge aus und zieht sie zurück. Sie kommt an keine Aufnahme heran; wer für
  einen Sprecher aufnehmen will, benutzt dessen Zugang. Das ist der Preis
  dafür, dass es nur **einen** Weg zu den Daten gibt und der die Kennung
  ableitet. Ist der Token nicht gesetzt, ist die Verwaltung zu — auch in der
  Entwicklung.
* **Sprecherzugang** — `<sprecher_id>.<geheimnis>` (siehe `wortlaut.zugang`).
  Er ist zugleich die Kennung: Der Server spaltet ihn, öffnet die Datenbank
  dieses Sprechers und prüft dort den Prüfwert.
* **Aufsicht** — `WORTLAUT_ADMIN_TOKEN`. Der eine Zugang, der über allen
  Korpora steht: einsehen, umbenennen, sichern, löschen. Er wählt seinen
  Sprecher ausdrücklich in der Adresse, denn er hat keinen eigenen — deshalb
  liegen seine Wege unter `/api/admin/…` und nirgends sonst (siehe
  `api/admin.py`). Er darf alles, was die Verwaltung darf; umgekehrt nicht.

  „Leer" heißt auch hier **abgeschaltet**: Ein offenstehender Zugang, der
  löschen darf, wäre kein Entwicklungskomfort, sondern ein Unfall mit Ansage.

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

    Vor dem ersten Zugriff laufen die offenen Migrationen. Ohne das trägt ein
    Update das neue Schema nur in die Datenbanken, die danach entstehen: Beim
    Anlegen eines Profils migriert `api/speakers.py`, sonst nichts und nirgends.
    Wer eine Spalte hinzufügt, legt damit jeden bestehenden Korpus still — die
    Modelle in `db/models.py` fragen die Spalte ab, SQLite kennt sie nicht, und
    was scheitert, ist nicht bloß die neue Ansicht, sondern jedes `SELECT` auf
    `speakers`: die Liste der Aufsicht ebenso wie die Zugangsprüfung weiter
    unten, mit der sich jeder Sprecher anmeldet.

    `make migrate` bleibt daneben bestehen — es ist der Weg, das für alle
    Korpora auf einmal und vor dem ersten Aufruf zu tun. Es darf nur nicht der
    einzige sein: Der Container startet uvicorn, nicht ein Skript, an das sich
    beim Ausrollen jemand erinnern muss.

    Die Prüfung auf die Datei bleibt davor, und zwar zwingend:
    `wende_migrationen_an` legt eine fehlende Datenbank an. Ohne diese
    Reihenfolge würde ein Tippfehler in der Kennung einen leeren Korpus
    erzeugen, statt mit 404 zu antworten.
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


def _vorgelegt(authorization: str | None) -> str:
    return (authorization or "").removeprefix("Bearer ")


def _gleich(vorgelegt: str, erwartet: str) -> bool:
    """Zeitkonstanter Vergleich über die UTF-8-Bytes.

    Zeitkonstant, weil sonst die Antwortzeit den Anfang des Tokens verrät.
    Ausdrücklich in Bytes, weil `compare_digest` Zeichenketten mit
    Nicht-ASCII-Zeichen abweist — ein Umlaut im Token genügte sonst für einen
    500er statt eines sauberen 401.
    """
    return secrets.compare_digest(vorgelegt.encode("utf-8"), erwartet.encode("utf-8"))


def _ist_aufsicht(vorgelegt: str) -> bool:
    """Der Aufsichtstoken, falls einer gesetzt ist. Leer = abgeschaltet."""
    erwartet = einstellungen().admin_token
    return bool(erwartet) and _gleich(vorgelegt, erwartet)


def _pruefe_aufsicht(authorization: Annotated[str | None, Header()] = None) -> None:
    """Wächter der Wege unter `/api/admin/…`.

    Ohne gesetzten `WORTLAUT_ADMIN_TOKEN` kommt hier niemand durch — auch nicht
    in der Entwicklung. Diese Wege löschen Korpora; ein offener Zugang dazu
    wäre kein Komfort, sondern der Unfall.
    """
    if not einstellungen().admin_token:
        raise HTTPException(
            status_code=401,
            detail="Die Aufsicht ist abgeschaltet: WORTLAUT_ADMIN_TOKEN ist nicht gesetzt.",
        )
    if not _ist_aufsicht(_vorgelegt(authorization)):
        raise HTTPException(status_code=401, detail="Nicht angemeldet")


def _pruefe_verwaltung(authorization: Annotated[str | None, Header()] = None) -> None:
    """Bearer-Token gegen `WORTLAUT_AUTH_TOKEN`. Nicht gesetzt = abgeschaltet.

    Die Aufsicht kommt hier ebenfalls durch: Wer jeden Korpus löschen darf,
    hätte an einem zweiten Token für das Anlegen eines Profils nichts gewonnen.

    Ohne gesetzten Token kommt hier niemand durch — wie bei der Aufsicht und
    aus demselben Grund. Früher stand die Verwaltung dann offen, gedacht als
    Bequemlichkeit für die Entwicklung. Nur unterscheidet keine Installation
    zwischen „Entwicklung" und „Betrieb": Wer den Token beim Aufsetzen
    vergisst, hat eine Seite im Netz, auf der jeder Profile anlegt und
    ausgegebene Zugänge zurückzieht — und nichts daran sieht falsch aus, weil
    genau das die Oberfläche der Verwaltung ist. Ein vergessener Token darf
    nicht die großzügigste aller Einstellungen sein.
    """
    vorgelegt = _vorgelegt(authorization)
    if _ist_aufsicht(vorgelegt):
        return
    if not einstellungen().auth_token:
        raise HTTPException(
            status_code=401,
            detail="Die Verwaltung ist abgeschaltet: WORTLAUT_AUTH_TOKEN ist nicht gesetzt.",
        )
    # Ein Sprecherzugang ist hier kein schwächerer Verwalter, sondern etwas
    # anderes. Er scheiterte auch am Vergleich weiter unten, aber mit
    # „Nicht angemeldet" — und wer seinen persönlichen Link vorlegt, sucht dann
    # den Fehler beim Link statt an der Stelle, an der er steht.
    if zugangsdienst.zerlege(vorgelegt) is not None:
        raise HTTPException(
            status_code=401, detail="Das ist ein Sprecherzugang, kein Verwalterzugang."
        )

    if not _gleich(vorgelegt, einstellungen().auth_token):
        raise HTTPException(status_code=401, detail="Nicht angemeldet")


def _wer_ruft(authorization: Annotated[str | None, Header()] = None) -> Zugang:
    """Die Kennung aus dem Vorgelegten ableiten — die einzige Stelle, die das tut."""
    vorgelegt = _vorgelegt(authorization)
    # Die Aufsicht zuerst: Sonst fiele sie in die Verwaltung und die Oberfläche
    # bekäme nie zu sehen, dass sie mehr darf.
    if _ist_aufsicht(vorgelegt):
        return Zugang(art="aufsicht")

    teile = zugangsdienst.zerlege(vorgelegt)
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
Aufsicht = Depends(_pruefe_aufsicht)
