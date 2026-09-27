"""Text → sprechbare Einheiten von grob 3–12 Sekunden.

Die Aufnahme erfolgt äußerungsweise: eine Einheit, eine Aufnahme. Deshalb
entsteht hier die Einheit, an der später alles hängt - Audio-Text-Paare sind
dadurch von Haus aus ausgerichtet, ohne Forced Alignment.

Geschnitten wird in drei Stufen, jeweils nur so tief wie nötig:
Satzgrenze → Teilsatzgrenze → Wortgrenze. Zu kurze Nachbarn werden wieder
zusammengelegt, damit keine Ein-Wort-Fetzen übrig bleiben.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import sprachen

MIN_SEKUNDEN = 3.0
MAX_SEKUNDEN = 12.0

# Satzende: Zeichen, danach Leerraum.
_SATZENDE = re.compile(r"(?<=[.!?…])\s+")
_TEILSATZ = re.compile(r"(?<=[,;:])\s+|\s+(?=–|-)")
_LEERRAUM = re.compile(r"\s+")


@dataclass(frozen=True)
class Sprachmass:
    """Was am Schneiden von der Sprache abhängt: wie viele Zeichen eine
    Sekunde Vorlesen füllen, und welche Punkte kein Satzende sind.

    Beides steuert nur die Länge der Vorlagen; eine Näherung genügt.
    """

    zeichen_pro_sekunde: float
    abkuerzung: re.Pattern[str]


# Je Sprache ein Maß; fehlt eines, gilt das der Vorgabesprache.
MASSE: dict[str, Sprachmass] = {
    # Deutlich vorgelesenes Deutsch, nachgezählt an den Vorlagen dieses
    # Projekts.
    sprachen.DEUTSCH: Sprachmass(
        zeichen_pro_sekunde=13.0,
        abkuerzung=re.compile(
            r"(?:\b[A-Za-zÄÖÜäöü]|\bz|\bd|\bu|\bevtl|\bbzw|\bDr|\bNr|\bAbb)\.$"
        ),
    ),
    # Rund 150 Wörter je Minute bei gut sechs Zeichen je Wort samt Leerzeichen.
    sprachen.ENGLISCH: Sprachmass(
        zeichen_pro_sekunde=15.0,
        abkuerzung=re.compile(
            r"(?:\b[A-Za-z]|\bMr|\bMrs|\bMs|\bDr|\bSt|\bvs|\be\.g|\bi\.e|\betc|\bapprox)\.$"
        ),
    ),
}


def mass(sprache: str) -> Sprachmass:
    return MASSE.get(sprachen.normiere(sprache), MASSE[sprachen.VORGABE])


@dataclass(frozen=True)
class Einheit:
    """Eine Sprecheinheit mit der geschätzten Sprechdauer ihres Textes."""

    text: str
    dauer_geschaetzt_s: float


def dauer(text: str, sprache: str = sprachen.VORGABE) -> float:
    """Wie lange dieser Text gesprochen etwa dauert.

    Mit Vorgabesprache, anders als beim Erkenner: Die Schätzung steuert nur
    die Länge einer Vorlage.
    """
    return len(text) / mass(sprache).zeichen_pro_sekunde


def schneide(text: str, sprache: str = sprachen.VORGABE) -> list[Einheit]:
    """Zerlegt einen Fließtext in Einheiten passender Sprechdauer."""
    m = mass(sprache)
    einheiten: list[str] = []
    for absatz in text.split("\n\n"):
        absatz = _LEERRAUM.sub(" ", absatz).strip()
        if not absatz:
            continue
        for satz in _saetze(absatz, m):
            einheiten.extend(_teile_bis_passend(satz, m))
    return [
        Einheit(text=t, dauer_geschaetzt_s=len(t) / m.zeichen_pro_sekunde)
        for t in _lege_kurze_zusammen(einheiten, m)
    ]


def _saetze(absatz: str, m: Sprachmass) -> list[str]:
    """Trennt an Satzgrenzen und klebt an Abkürzungen wieder zusammen."""
    teile = _SATZENDE.split(absatz)
    saetze: list[str] = []
    for teil in teile:
        if saetze and m.abkuerzung.search(saetze[-1]):
            saetze[-1] = f"{saetze[-1]} {teil}"
        else:
            saetze.append(teil)
    return [s for s in saetze if s.strip()]


def _teile_bis_passend(satz: str, m: Sprachmass) -> list[str]:
    """Zu lange Sätze an Teilsatz-, notfalls an Wortgrenzen weiter zerlegen."""
    if len(satz) / m.zeichen_pro_sekunde <= MAX_SEKUNDEN:
        return [satz]

    stuecke = [s for s in _TEILSATZ.split(satz) if s and s.strip()]
    if len(stuecke) > 1:
        ergebnis: list[str] = []
        for stueck in stuecke:
            ergebnis.extend(_teile_bis_passend(stueck.strip(), m))
        return ergebnis

    return _teile_an_wortgrenzen(satz, m)


def _teile_an_wortgrenzen(satz: str, m: Sprachmass) -> list[str]:
    """Letzte Stufe: Wörter sammeln, bis die Höchstdauer erreicht ist."""
    ergebnis: list[str] = []
    aktuell: list[str] = []
    for wort in satz.split(" "):
        probe = " ".join([*aktuell, wort])
        if aktuell and len(probe) / m.zeichen_pro_sekunde > MAX_SEKUNDEN:
            ergebnis.append(" ".join(aktuell))
            aktuell = [wort]
        else:
            aktuell.append(wort)
    if aktuell:
        ergebnis.append(" ".join(aktuell))
    return ergebnis


def _lege_kurze_zusammen(einheiten: list[str], m: Sprachmass) -> list[str]:
    """Nachbarn verschmelzen, solange das Ergebnis nicht zu lang wird."""
    ergebnis: list[str] = []
    for einheit in einheiten:
        if ergebnis and len(ergebnis[-1]) / m.zeichen_pro_sekunde < MIN_SEKUNDEN:
            verbunden = f"{ergebnis[-1]} {einheit}"
            if len(verbunden) / m.zeichen_pro_sekunde <= MAX_SEKUNDEN:
                ergebnis[-1] = verbunden
                continue
        ergebnis.append(einheit)
    return ergebnis
