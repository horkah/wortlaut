"""Wer lernt, wer steuert, wer prüft - und warum das nie wieder umsortiert wird.

Zwei Drittel der Aufnahmen trainieren das Modell, ein Drittel prüft es. Die
Zahl allein wäre leicht: jede dritte Aufnahme in den Test. Schwierig ist die
zweite Hälfte der Zusage - dass die Zuteilung **hält**.

**Warum sie gespeichert wird und nicht gerechnet.** Die naheliegende Lösung
wäre, beim Trainieren durchzuzählen: Aufnahme 1, 2 lernen, Aufnahme 3 prüft,
und so weiter. Das ist bis zur ersten gelöschten Aufnahme richtig. Danach rückt
alles dahinter um einen Platz vor - und Aufnahmen, die bisher geprüft haben,
landen im Training eines Modells, das anschließend an ihnen gemessen wird. Die
Zahl, die dabei herauskommt, sieht gut aus und bedeutet nichts.

Deshalb steht die Zuteilung in einer Tabelle, einmal je Aufnahme, und wird nie
wieder angefasst. Verschwindet eine Aufnahme, verschwindet ihre Zeile mit - die
übrigen behalten ihren Platz. Das Verhältnis weicht dadurch leicht von 2:1 ab;
das ist der richtige Preis. Ein sauberes Verhältnis wäre hier nur zu haben,
indem man die Trennung zwischen Lernen und Prüfen aufweicht, und dann misst
niemand mehr etwas.

**Warum ein Muster und kein Zufall.** Eine zufällige Auswahl bräuchte einen
gespeicherten Keim, um nachvollziehbar zu sein - also ebenfalls eine
gespeicherte Zuteilung, nur schwerer zu lesen. Das Muster steht in
`wortlaut/laeufe.py` und ist an der Nummer abzulesen, die neben jeder Zeile
steht.

**Wann zugeteilt wird.** Beim Hinsehen. Jede Abfrage dieser Ansicht und jeder
Auftrag holt zuerst nach, was noch keine Zeile hat - in der Reihenfolge des
Korpus, also nach Alter. Ein eigener Knopf dafür wäre einer, den jemand
vergisst, und ein Modell, das ohne die neuen Aufnahmen trainiert, sagt nicht,
dass sie fehlten.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from wortlaut import laeufe

from apps.hoeren.backend.db.models import Aufnahme, Vorlage
from apps.hoeren.backend.services.auswertung import gueltige_aufnahmen

from ..db.models import Zuteilung


@dataclass(frozen=True)
class Probe:
    """Eine Aufnahme mit ihrer Vorlage und ihrem Platz in der Aufteilung."""

    aufnahme: Aufnahme
    vorlage: Vorlage
    teil: str
    nummer: int


def _zugeteilt(db: Session) -> dict[str, Zuteilung]:
    return {zeile.recording_id: zeile for zeile in db.scalars(select(Zuteilung))}


def _naechste_nummer(db: Session) -> int:
    """Eine mehr als die höchste vergebene - nie eine wiederverwendete.

    Wiederzuverwenden, was eine gelöschte Aufnahme freigemacht hat, wäre genau
    das Umsortieren, das diese Tabelle verhindern soll: Die nächste Aufnahme
    bekäme den Platz einer alten und damit womöglich deren Teil.
    """
    hoechste = db.scalar(select(func.max(Zuteilung.nummer)))
    return 0 if hoechste is None else hoechste + 1


def teile_zu(db: Session, korpus: Session) -> int:
    """Allen noch unzugeteilten Aufnahmen ihren Teil geben; gibt deren Anzahl zurück.

    In der Reihenfolge des Korpus - älteste zuerst -, damit die Zuteilung nicht
    davon abhängt, wann jemand diese Seite geöffnet hat.
    """
    bekannt = set(_zugeteilt(db))
    nummer = _naechste_nummer(db)
    neu = 0

    for aufnahme, _vorlage in gueltige_aufnahmen(korpus):
        if aufnahme.id in bekannt:
            continue
        db.add(
            Zuteilung(
                recording_id=aufnahme.id,
                teil=laeufe.teil_fuer(nummer),
                nummer=nummer,
                zugeteilt=laeufe.jetzt(),
            )
        )
        nummer += 1
        neu += 1

    if neu:
        db.commit()
    return neu


def proben(db: Session, korpus: Session) -> list[Probe]:
    """Alle brauchbaren Aufnahmen mit ihrem Teil, älteste zuerst.

    Teilt vorher zu, was noch keinen Platz hat. Aufnahmen ohne Zeile kann es
    danach nicht mehr geben; sollte doch eine durchrutschen - etwa weil sie
    zwischen zwei Abfragen entstanden ist -, bleibt sie draußen, statt
    stillschweigend im Training zu landen.
    """
    teile_zu(db, korpus)
    zuteilung = _zugeteilt(db)
    return [
        Probe(
            aufnahme=aufnahme,
            vorlage=vorlage,
            teil=zuteilung[aufnahme.id].teil,
            nummer=zuteilung[aufnahme.id].nummer,
        )
        for aufnahme, vorlage in gueltige_aufnahmen(korpus)
        if aufnahme.id in zuteilung
    ]


def zaehle(proben_liste: list[Probe]) -> dict[str, int]:
    """Wie viele Aufnahmen auf jeden Teil entfallen - in fester Reihenfolge."""
    return {
        teil: sum(1 for probe in proben_liste if probe.teil == teil) for teil in laeufe.TEILE
    }


def verwaist(db: Session, korpus: Session) -> list[str]:
    """Zuteilungen zu Aufnahmen, die es nicht mehr gibt.

    Sie bleiben stehen, und das ist Absicht: Ihre Nummer ist vergeben, und
    genau daran hängt, dass die übrigen ihren Teil behalten. Gezeigt werden sie
    trotzdem - eine Aufteilung, die von hundert Zeilen spricht, während achtzig
    Aufnahmen da sind, soll das sagen und nicht verschweigen.
    """
    vorhanden = {aufnahme.id for aufnahme, _ in gueltige_aufnahmen(korpus)}
    return sorted(kennung for kennung in _zugeteilt(db) if kennung not in vorhanden)
