"""Wie der Korpus in sechs Faltungen zerfällt - und warum das nirgends steht.

Jede Aufnahme kommt in die Faltung mit dem geringsten Zählerstand, bei
Gleichstand in die mit der niedrigsten Nummer - bei lauter einzelnen Aufnahmen
also 1, 2, 3, 4, 5, 6, 1, 2, … (`wortlaut.laeufe.verteile`). Je Faltung läuft ein Training, das auf den anderen fünf Sechsteln lernt und auf
diesem einen misst. Sechs Trainings später ist jede Aufnahme genau einmal von
einem Modell gehört worden, das sie nie gesehen hat - und das ist die Zahl, die
in der Modelltabelle steht.

**Eine Verwandtschaft ist eine Aufnahme.** Teile und Kopien aus „Editieren"
sind neue Aufnahmen, aber derselbe Ton (`zuschnitt.stamm`). Sie stehen direkt
unter ihrem Original, und einzeln verteilt landeten sie in anderen Faltungen -
dann lernte das Modell der einen Faltung den Ton, an dem es in der anderen
gemessen wird, und die Zahl stiege, ohne dass es besser hörte. Verteilt wird
deshalb je Stamm: Original, Teile und Kopien teilen sich eine Faltung, und
gezählt wird der Stamm mit all seinen Aufnahmen. Darum der Zählerstand statt
einer festen Runde: Reihum bekam die Faltung einer dreiteiligen Verwandtschaft
trotzdem ihren nächsten Platz, und die Faltungen liefen auseinander. Und darum
die größten Verwandtschaften zuerst: Geschnitten wird oft spät, und hinter
einer späten großen Verwandtschaft bliebe nichts mehr, das aufholen könnte.

**Warum hier nichts mehr gespeichert wird.** Bis September 2026 stand in einer
Tabelle, welche Aufnahme lernt, steuert und prüft; einmal vergeben und nie
wieder angefasst. Das musste so sein, solange es ein Testdrittel gab: Eine
Aufnahme, die einmal geprüft hatte, durfte nie trainieren, sonst maß der Test
das Auswendiggelernte. Rückte durch eine Löschung alles um einen Platz vor, war
genau das passiert.

Diese Gefahr gibt es nicht mehr. In fünf von sechs Faltungen trainiert jede
Aufnahme ohnehin; welche Faltung sie trägt, entscheidet nur, in welchem der
sechs Läufe sie gemessen wird. Die Faltung folgt deshalb schlicht der
Reihenfolge des Korpus, wird bei jedem Auftrag neu gerechnet und im
Schnappschuss festgehalten (`services/auftraege.py`). Eine Tabelle daneben wäre
eine zweite Wahrheit über dieselbe Sache.

**Was dabei verloren geht, und warum das in Ordnung ist.** Wer eine Aufnahme
löscht, verschiebt die Faltungen aller jüngeren. Zwei Läufe über verschiedene
Korpusstände messen damit auf verschiedenen Faltungen. Das ist kein Bruch: Jeder
Lauf misst über **alle** Aufnahmen, die er kennt, und trägt sein Manifest bei
sich. Verglichen werden Läufe, nicht Faltungen.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session
from wortlaut import laeufe

from apps.hoeren.backend.db.models import Aufnahme, Vorlage
from apps.hoeren.backend.services import zuschnitt
from apps.hoeren.backend.services.auswertung import gueltige_aufnahmen


@dataclass(frozen=True)
class Probe:
    """Eine Aufnahme mit ihrer Vorlage und ihrer Faltung."""

    aufnahme: Aufnahme
    vorlage: Vorlage
    faltung: int
    nummer: int


def proben(korpus: Session) -> list[Probe]:
    """Alle brauchbaren Aufnahmen mit ihrer Faltung, älteste zuerst.

    Die Reihenfolge ist die des Korpus und damit die des Aufnehmens. Sie ist
    zugleich die der Zuteilung unter gleich großen Stämmen: Die größten
    zuerst, kommt jeder in die Faltung mit den wenigsten Aufnahmen, und mit
    ihm alle seine Teile und Kopien (siehe oben). Nichts daran ist gespeichert, und nichts muss es sein.
    """
    reihe = gueltige_aufnahmen(korpus)
    groessen: dict[str, int] = {}
    for aufnahme, _ in reihe:
        stamm = zuschnitt.stamm(aufnahme)
        groessen[stamm] = groessen.get(stamm, 0) + 1
    faltungen = dict(zip(groessen, laeufe.verteile(groessen.values()), strict=True))
    return [
        Probe(
            aufnahme=aufnahme,
            vorlage=vorlage,
            faltung=faltungen[zuschnitt.stamm(aufnahme)],
            nummer=nummer,
        )
        for nummer, (aufnahme, vorlage) in enumerate(reihe)
    ]


def zaehle(proben_liste: list[Probe]) -> dict[int, int]:
    """Wie viele Aufnahmen auf jede Faltung entfallen - alle sechs, auch leere.

    Alle sechs, weil eine fehlende Faltung eine Auskunft ist: Unter sechs
    Aufnahmen bleiben Faltungen leer, und ein Lauf darüber hätte Sechstel, die
    nichts messen.
    """
    return {
        faltung: sum(1 for probe in proben_liste if probe.faltung == faltung)
        for faltung in range(laeufe.FALTUNGEN)
    }


def genug(proben_liste: list[Probe]) -> bool:
    """Ob sich damit kreuzvalidieren lässt: mindestens eine Aufnahme je Faltung.

    Weniger als sechs Aufnahmen ergeben leere Faltungen - ein Training, das auf
    nichts misst, und eine Zahl, die keine ist. Dann steht die Schaltfläche
    still und sagt, woran es liegt.
    """
    return all(anzahl > 0 for anzahl in zaehle(proben_liste).values())
