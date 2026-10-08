"""Wie sicher ist eine gemessene Zahl? - Vertrauensbereiche über Messreihen.

`metriken.py` bewertet ein Paar aus Vorlage und erkanntem Text; diese Datei
sagt, wie weit der Mittelwert über viele solcher Paare trägt. Bei sechzig
Aufnahmen ist das 95-%-Intervall einer WER mehrere Prozentpunkte breit -
breiter als die meisten Unterschiede, um die es geht.

**Bootstrap statt Formel.** Die Einzelwerte sind weder normalverteilt noch
unabhängig noch gleich schwer (eine WER über drei Wörter springt in
Dritteln); der Bootstrap braucht nichts davon (Bisani/Ney, ICASSP 2004).

**Je Aufnahme ein Block.** Gezogen wird nach der Kennung der Aufnahme, die
der Aufrufer mitgibt.

**Fester Keim.** Die Ziehungen hängen allein an der Anzahl der Blöcke:
dieselbe Messreihe, derselbe Bereich, auf jeder Maschine. Gleich viele Blöcke
bekommen dieselben Ziehungen - die Voraussetzung für den gepaarten
`unterschied`.

Keine gemessene Zahl ändert sich: `Intervall.mittel` ist der gewöhnliche
Mittelwert, der Bereich steht daneben.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache

# ── Die Wahl ────────────────────────────────────────────────────────────────
#
# Was der Aufrufer einstellen darf; `AUS` ist überall die Vorgabe.
AUS = "aus"

# Je Aufnahme ziehen.
BLOCK_AUFNAHME = "aufnahme"

# ── Die Zahlen des Verfahrens ───────────────────────────────────────────────
#
# Konstanten, keine Konfiguration: Wer sie ändert, ändert jede damit gerechnete
# Zahl - und die `marke` (siehe `Verfahren`).
KEIM = 20260913

# Darunter wackeln die Perzentile sichtbar; der Fehler fällt mit der Wurzel,
# der Aufwand steigt linear.
ZIEHUNGEN = 2000

# Das übliche Niveau. 0,95 heißt: der Bereich zwischen dem 2,5- und dem
# 97,5-Perzentil der Ziehungen.
NIVEAU = 0.95

# Unter zwei Blöcken gibt es nichts zu ziehen.
MINDESTENS = 2

# Nachkommastellen der ausgegebenen Zahlen - dieselbe Rundung wie bei den
# Mittelwerten, die schon in `bewertung.jsonl` stehen.
STELLEN = 6


@dataclass(frozen=True)
class Verfahren:
    """Womit gerechnet wurde - gehört zu jedem Ergebnis dazu.

    Ohne seine Parameter ist ein Bereich nicht nachvollziehbar; die `marke`
    steht neben jedem gespeicherten Wert.
    """

    blockart: str = BLOCK_AUFNAHME
    ziehungen: int = ZIEHUNGEN
    niveau: float = NIVEAU
    keim: int = KEIM

    @property
    def marke(self) -> str:
        return f"bootstrap/{self.blockart}/{self.ziehungen}/{self.niveau}/{self.keim}"

    def als_dict(self) -> dict[str, object]:
        return {
            "art": "bootstrap",
            "blockart": self.blockart,
            "ziehungen": self.ziehungen,
            "niveau": self.niveau,
            "keim": self.keim,
            "marke": self.marke,
        }


@dataclass(frozen=True)
class Intervall:
    """Ein Mittelwert mit dem Bereich, in dem er liegen dürfte."""

    mittel: float
    unten: float
    oben: float
    # Die Streuung der Ziehungen - der Standardfehler des Mittelwerts.
    streuung: float
    bloecke: int
    einheiten: int
    verfahren: Verfahren

    @property
    def breite(self) -> float:
        return self.oben - self.unten

    def als_dict(self) -> dict[str, object]:
        return {
            "mittel": self.mittel,
            "unten": self.unten,
            "oben": self.oben,
            "streuung": self.streuung,
            "bloecke": self.bloecke,
            "einheiten": self.einheiten,
            "marke": self.verfahren.marke,
        }


@dataclass(frozen=True)
class Unterschied:
    """Zwei Messreihen an denselben Einheiten - gepaart verglichen.

    Eine schwere Aufnahme zieht beide Modelle herunter; in der Differenz fällt
    dieser gemeinsame Anteil heraus. Zwei getrennte Bereiche tragen ihn beide
    und überlappen oft, obwohl der Unterschied belastbar ist.
    """

    # `a` minus `b`. Ob das gut ist, hängt am Maß und entscheidet der Aufrufer:
    # bei der Genauigkeit ist mehr besser, bei jeder Fehlerrate weniger.
    differenz: float
    unten: float
    oben: float
    # Zweiseitiger Bootstrap-p-Wert zur Nullhypothese „kein Unterschied".
    p: float
    bloecke: int
    einheiten: int
    verfahren: Verfahren

    @property
    def belegt(self) -> bool:
        """Ob der Bereich die Null nicht enthält - nur dann ist etwas gezeigt."""
        return self.unten > 0.0 or self.oben < 0.0

    def als_dict(self) -> dict[str, object]:
        return {
            "differenz": self.differenz,
            "unten": self.unten,
            "oben": self.oben,
            "p": self.p,
            "belegt": self.belegt,
            "bloecke": self.bloecke,
            "einheiten": self.einheiten,
            "marke": self.verfahren.marke,
        }


# ── Die Ziehungen ───────────────────────────────────────────────────────────


@lru_cache(maxsize=64)
def zuege(anzahl: int, wie_oft: int = ZIEHUNGEN, keim: int = KEIM) -> tuple[tuple[int, ...], ...]:
    """`wie_oft` Ziehungen von `anzahl` Blöcken mit Zurücklegen - immer dieselben.

    Gemerkt, weil eine Tafel dieselbe Blockzahl dutzendfach braucht.
    """
    wuerfel = random.Random(f"{keim}:{anzahl}:{wie_oft}")
    stellen = range(anzahl)
    return tuple(tuple(wuerfel.choices(stellen, k=anzahl)) for _ in range(wie_oft))


def _perzentil(sortiert: Sequence[float], anteil: float) -> float:
    """Das `anteil`-Perzentil einer sortierten Reihe, linear dazwischen gerechnet."""
    if not sortiert:
        return 0.0
    if len(sortiert) == 1:
        return float(sortiert[0])
    stelle = anteil * (len(sortiert) - 1)
    unten = int(stelle)
    oben = min(unten + 1, len(sortiert) - 1)
    rest = stelle - unten
    return float(sortiert[unten]) * (1.0 - rest) + float(sortiert[oben]) * rest


def _streuung(werte: Sequence[float], mittel: float) -> float:
    if len(werte) < 2:
        return 0.0
    return (sum((wert - mittel) ** 2 for wert in werte) / (len(werte) - 1)) ** 0.5


# ── Blöcke bilden ───────────────────────────────────────────────────────────


def bilde(paare: Iterable[tuple[str, float]]) -> list[list[float]]:
    """Werte zu Blöcken bündeln - nach dem Schlüssel, den der Aufrufer mitgibt.

    Der Schlüssel ist die Kennung der Aufnahme. Sortiert nach Schlüssel, damit
    dieselben Ziehungen dieselben Werte treffen.
    """
    nach_schluessel: dict[str, list[float]] = {}
    for schluessel, wert in paare:
        nach_schluessel.setdefault(schluessel, []).append(wert)
    return [nach_schluessel[schluessel] for schluessel in sorted(nach_schluessel)]


def bilde_paare(drillinge: Iterable[tuple[str, float, float]]) -> list[list[tuple[float, float]]]:
    """Dasselbe für zwei Reihen an denselben Aufnahmen - je Aufnahme ein Paar."""
    nach_schluessel: dict[str, list[tuple[float, float]]] = {}
    for schluessel, links, rechts in drillinge:
        nach_schluessel.setdefault(schluessel, []).append((links, rechts))
    return [nach_schluessel[schluessel] for schluessel in sorted(nach_schluessel)]


# ── Die beiden Rechnungen ───────────────────────────────────────────────────


def _ziehe(
    bloecke: Sequence[Sequence[float]], art: Verfahren
) -> tuple[float, list[float], int] | None:
    """Mittel, sortierte Mittel aller Ziehungen und Zahl der Einheiten - `None` bei zu wenig.

    Der Mittelwert ist exakt der gewöhnliche; die Ziehungen schätzen nur, wie
    weit er streut.
    """
    summen = [sum(block) for block in bloecke]
    anzahlen = [len(block) for block in bloecke]
    einheiten = sum(anzahlen)
    if len(bloecke) < MINDESTENS or not einheiten:
        return None
    hole_summe = summen.__getitem__
    hole_anzahl = anzahlen.__getitem__
    gezogen = sorted(
        sum(map(hole_summe, zug)) / sum(map(hole_anzahl, zug))
        for zug in zuege(len(bloecke), art.ziehungen, art.keim)
    )
    return sum(summen) / einheiten, gezogen, einheiten


def _bereich(gezogen: Sequence[float], art: Verfahren) -> tuple[float, float]:
    """Die Perzentile des Niveaus - 2,5 und 97,5 bei 95 %."""
    rand = (1.0 - art.niveau) / 2.0
    return (
        round(_perzentil(gezogen, rand), STELLEN),
        round(_perzentil(gezogen, 1.0 - rand), STELLEN),
    )


def intervall(
    bloecke: Sequence[Sequence[float]], verfahren: Verfahren | None = None
) -> Intervall | None:
    """Der Vertrauensbereich des Mittelwerts über alle Werte aller Blöcke; `None` bei zu wenig."""
    art = verfahren or Verfahren()
    if (gezogen := _ziehe(bloecke, art)) is None:
        return None
    mittel, ziehungen, einheiten = gezogen
    unten, oben = _bereich(ziehungen, art)
    return Intervall(
        mittel=round(mittel, STELLEN),
        unten=unten,
        oben=oben,
        streuung=round(_streuung(ziehungen, sum(ziehungen) / len(ziehungen)), STELLEN),
        bloecke=len(bloecke),
        einheiten=einheiten,
        verfahren=art,
    )


def unterschied(
    bloecke: Sequence[Sequence[tuple[float, float]]], verfahren: Verfahren | None = None
) -> Unterschied | None:
    """Der gepaarte Vergleich zweier Reihen: Bereich und p-Wert der Differenz.

    Beide Reihen an derselben Ziehung. Der p-Wert ist der zweiseitige
    Bootstrap-Wert; die Eins in Zähler und Nenner verhindert ein p von genau
    null, wo nur „kleiner als 1/2000" gemessen ist.
    """
    art = verfahren or Verfahren()
    differenzen = [[links - rechts for links, rechts in block] for block in bloecke]
    if (gezogen := _ziehe(differenzen, art)) is None:
        return None
    mittel, ziehungen, einheiten = gezogen

    nicht_groesser = sum(1 for wert in ziehungen if wert <= 0.0)
    nicht_kleiner = len(ziehungen) - sum(1 for wert in ziehungen if wert < 0.0)
    p = 2.0 * (min(nicht_groesser, nicht_kleiner) + 1) / (len(ziehungen) + 1)

    unten, oben = _bereich(ziehungen, art)
    return Unterschied(
        differenz=round(mittel, STELLEN),
        unten=unten,
        oben=oben,
        p=round(min(p, 1.0), 4),
        bloecke=len(bloecke),
        einheiten=einheiten,
        verfahren=art,
    )
