"""Wie der Korpus in sechs Faltungen zerfällt - gerechnet, nicht gespeichert.

Je Faltung lernt ein Training auf den anderen fünf Sechsteln und misst an
diesem; danach ist jede Aufnahme einmal von einem Modell gehört, das sie nicht
kannte - die Zahl der Modelltafel.

**Eine Verwandtschaft ist eine Aufnahme.** Teile und Kopien aus „Editieren"
sind derselbe Ton (`zuschnitt.stamm`); in verschiedenen Faltungen lernte ein
Modell, woran es gemessen wird. Verteilt wird je Stamm nach Zählerstand, die
größten zuerst (`wortlaut.laeufe.verteile`), damit die einzelnen Aufnahmen
ausgleichen.

**Gerechnet bei jedem Auftrag und im Schnappschuss festgehalten**
(`services/auftraege.py`). In fünf von sechs Faltungen lernt jede Aufnahme
ohnehin; welche sie trägt, entscheidet nur, wo sie gemessen wird. Eine
Löschung verschiebt die Faltungen - verglichen werden Läufe, nicht Faltungen.
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

    Die Reihenfolge des Korpus entscheidet unter gleich großen Stämmen.
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

    Eine leere Faltung ist eine Auskunft.
    """
    return {
        faltung: sum(1 for probe in proben_liste if probe.faltung == faltung)
        for faltung in range(laeufe.FALTUNGEN)
    }


def genug(proben_liste: list[Probe]) -> bool:
    """Ob sich damit kreuzvalidieren lässt: mindestens eine Aufnahme je Faltung.

    Sonst misst ein Training an nichts; die Oberfläche sagt dann, woran es liegt.
    """
    return all(anzahl > 0 for anzahl in zaehle(proben_liste).values())
