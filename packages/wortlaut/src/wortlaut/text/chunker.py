"""Text → sprechbare Einheiten von grob 3–12 Sekunden.

Die Aufnahme erfolgt äußerungsweise: eine Einheit, eine Aufnahme. Deshalb
entsteht hier die Einheit, an der später alles hängt — Audio-Text-Paare sind
dadurch von Haus aus ausgerichtet, ohne Forced Alignment.

Geschnitten wird in drei Stufen, jeweils nur so tief wie nötig:
Satzgrenze → Teilsatzgrenze → Wortgrenze. Zu kurze Nachbarn werden wieder
zusammengelegt, damit keine Ein-Wort-Fetzen übrig bleiben.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Geschätzte Sprechgeschwindigkeit für deutliches Vorlesen auf Deutsch.
# Bewusst eine grobe Näherung: sie steuert nur die Länge der Vorlagen, nicht
# die Bewertung der Aufnahmen.
ZEICHEN_PRO_SEKUNDE = 13.0

MIN_SEKUNDEN = 3.0
MAX_SEKUNDEN = 12.0

# Satzende: Zeichen, danach Leerraum. Gängige Abkürzungen (z. B., Dr.) werden
# ausgenommen, weil ihr Punkt kein Satzende ist.
_SATZENDE = re.compile(r"(?<=[.!?…])\s+")
_ABKUERZUNG = re.compile(r"(?:\b[A-Za-zÄÖÜäöü]|\bz|\bd|\bu|\bevtl|\bbzw|\bDr|\bNr|\bAbb)\.$")
_TEILSATZ = re.compile(r"(?<=[,;:])\s+|\s+(?=–|—)")
_LEERRAUM = re.compile(r"\s+")


@dataclass(frozen=True)
class Einheit:
    """Eine Sprecheinheit mit der geschätzten Sprechdauer ihres Textes."""

    text: str
    dauer_geschaetzt_s: float


def dauer(text: str) -> float:
    return len(text) / ZEICHEN_PRO_SEKUNDE


def schneide(text: str) -> list[Einheit]:
    """Zerlegt einen Fließtext in Einheiten passender Sprechdauer."""
    einheiten: list[str] = []
    for absatz in text.split("\n\n"):
        absatz = _LEERRAUM.sub(" ", absatz).strip()
        if not absatz:
            continue
        for satz in _saetze(absatz):
            einheiten.extend(_teile_bis_passend(satz))
    return [Einheit(text=t, dauer_geschaetzt_s=dauer(t)) for t in _lege_kurze_zusammen(einheiten)]


def _saetze(absatz: str) -> list[str]:
    """Trennt an Satzgrenzen und klebt an Abkürzungen wieder zusammen."""
    teile = _SATZENDE.split(absatz)
    saetze: list[str] = []
    for teil in teile:
        if saetze and _ABKUERZUNG.search(saetze[-1]):
            saetze[-1] = f"{saetze[-1]} {teil}"
        else:
            saetze.append(teil)
    return [s for s in saetze if s.strip()]


def _teile_bis_passend(satz: str) -> list[str]:
    """Zu lange Sätze an Teilsatz-, notfalls an Wortgrenzen weiter zerlegen."""
    if dauer(satz) <= MAX_SEKUNDEN:
        return [satz]

    stuecke = [s for s in _TEILSATZ.split(satz) if s and s.strip()]
    if len(stuecke) > 1:
        ergebnis: list[str] = []
        for stueck in stuecke:
            ergebnis.extend(_teile_bis_passend(stueck.strip()))
        return ergebnis

    return _teile_an_wortgrenzen(satz)


def _teile_an_wortgrenzen(satz: str) -> list[str]:
    """Letzte Stufe: Wörter sammeln, bis die Höchstdauer erreicht ist."""
    ergebnis: list[str] = []
    aktuell: list[str] = []
    for wort in satz.split(" "):
        probe = " ".join([*aktuell, wort])
        if aktuell and dauer(probe) > MAX_SEKUNDEN:
            ergebnis.append(" ".join(aktuell))
            aktuell = [wort]
        else:
            aktuell.append(wort)
    if aktuell:
        ergebnis.append(" ".join(aktuell))
    return ergebnis


def _lege_kurze_zusammen(einheiten: list[str]) -> list[str]:
    """Nachbarn verschmelzen, solange das Ergebnis nicht zu lang wird."""
    ergebnis: list[str] = []
    for einheit in einheiten:
        if ergebnis and dauer(ergebnis[-1]) < MIN_SEKUNDEN:
            verbunden = f"{ergebnis[-1]} {einheit}"
            if dauer(verbunden) <= MAX_SEKUNDEN:
                ergebnis[-1] = verbunden
                continue
        ergebnis.append(einheit)
    return ergebnis
