"""Gemeinsame Abhängigkeiten der Endpunkte: Zugang und Korpus.

Dieselbe Aufgabe wie in `apps/hoeren/backend/deps.py` und `apps/schreiben/…`
und aus demselben Grund: Der Sprecher wird aus dem vorgelegten Zugang
**abgeleitet** und nirgends behauptet. Wer hier ein Modell trainiert,
trainiert sein eigenes; die Bindung zieht der Server, nicht der Aufrufer.

**Diese App hat keine eigene Datenbank mehr.** Sie hatte eine, und darin stand
genau eine Sache: die Aufteilung in Lernen und Prüfen. Mit dem Testdrittel ist
sie im September 2026 weggefallen - die Faltungen der Kreuzvalidierung folgen
der Reihenfolge des Korpus und stehen im Schnappschuss jedes Laufs
(`services/aufteilung.py`). Was bleibt, liegt in Verzeichnissen: die Läufe
unter `data/snapshots/`, die Modellstände in der Registry.

Der **Korpus** (`hoeren.sqlite`) wird hier nur gelesen. Er gehört „hören"
(Grundentscheidung 6); daraus kommen die Aufnahmen, ihre Vorlagen und die
Baseline. Dass er nur lesend vorkommt, ist keine Zusage auf Papier: Es gibt
in dieser App keinen Weg, der in ihn schreibt - und seit dem Wegfall der
eigenen Datenbank auch keinen, der überhaupt irgendwo schreibt.
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
    """Nach dem Löschen eines Sprechers - und zwischen zwei Tests.

    Nur noch ein Zwischenspeicher, seit diese App keine eigene Datenbank mehr
    hat: der lesende Zugriff auf den Korpus.
    """
    namen = [sprecher_id] if sprecher_id else list(_korpus_engines)
    for name in namen:
        engine = _korpus_engines.pop(name, None)
        if engine is not None:
            engine.dispose()


def _zugang(
    authorization: Annotated[str | None, Header()] = None,
) -> zugangsdienst.Sprecherzugang:
    """Der geprüfte Zugang - die einzige Stelle, die ihn hier auflöst.

    Nur der Sprecherzugang gilt. Verwaltung und Aufsicht kommen hier nicht
    durch, und das ist kein Versehen: Ein Modell gehört einem Menschen, und
    wer keines hat, hat hier nichts zu sehen. Wer über alle Korpora schauen
    will, tut das in „hören", wo die Aufsicht zu Hause ist.

    Geprüft wird über `wortlaut.zugang.pruefe` und nicht mehr von Hand. Hier
    stand einmal derselbe Ablauf noch einmal ausgeschrieben - zerlegen, die
    Korpusdatei suchen, das Sprechermodell von „hören" über eine eigene Sitzung
    laden, den Prüfwert vergleichen. Das war die dritte Fassung derselben
    sicherheitsrelevanten Regel, und sie brachte als einzige einen Import der
    ORM-Modelle einer fremden App mit. Der Weg der Bibliothek öffnet den Korpus
    ausdrücklich lesend (`mode=ro`) - er ist damit auch der richtigere: Diese
    App schreibt nicht in den Korpus (Grundentscheidung 6).

    Herausgereicht wird der ganze Zugang und nicht mehr nur die Kennung: Er
    trägt seit `wortlaut/zugang.py` auch die Sprache des Profils, und die
    braucht der Trainingsauftrag. Zweimal zu prüfen, um zwei Felder derselben
    Zeile zu bekommen, wäre zweimal dieselbe Arbeit.
    """
    vorgelegt = (authorization or "").removeprefix("Bearer ")
    # Zwei Lagen, zwei Sätze: Was gar kein Sprecherzugang ist - ein Verwalter-
    # oder Aufsichtstoken - soll nicht so klingen, als sei der persönliche Link
    # abgelaufen. Die Form entscheidet das, ohne irgendeine Datenbank zu
    # befragen.
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
    """Die Sprache des Profils, für den Trainingsauftrag.

    Sie kommt aus derselben Prüfung wie die Kennung und kostet keine zweite
    Abfrage (`wortlaut/zugang.py`). Der Auftrag trägt sie danach selbst, damit
    der Trainer sie nicht aus der Umgebung nehmen muss - und damit in
    `auftrag.json` steht, wofür trainiert wurde.
    """
    return wer.sprache


def _korpus(sprecher_id: Annotated[str, Depends(_sprecher_id)]) -> Iterator[Session]:
    with Session(korpus_engine(sprecher_id)) as sitzung:
        yield sitzung


SprecherId = Annotated[str, Depends(_sprecher_id)]
Sprache = Annotated[str, Depends(_sprache)]
Korpus = Annotated[Session, Depends(_korpus)]
