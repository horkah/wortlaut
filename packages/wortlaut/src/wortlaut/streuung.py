"""Wie sicher ist eine gemessene Zahl? - Vertrauensbereiche über Messreihen.

`metriken.py` beantwortet die Frage „wie gut war dieses eine Paar aus Vorlage
und erkanntem Text". Diese Datei beantwortet die zweite, die immer danach
kommt und die das Projekt bisher nicht gestellt hat: **Wie weit trägt der
Mittelwert über sechzig solcher Paare?**

Ohne eine Antwort darauf ist jeder Vergleich zweier Modelle eine Rangfolge von
Rauschen. Bei sechzig Testaufnahmen ist das 95-%-Intervall einer Wortfehlerrate
mehrere Prozentpunkte breit - breiter als fast jeder Unterschied, um den es in
dieser App geht. Eine Tabelle, die 0,142 neben 0,138 stellt und die bessere
Zahl hervorhebt, behauptet dann etwas, das sie nicht gemessen hat.

**Warum Bootstrap und keine Formel.** Für den Mittelwert einer Fehlerrate gibt
es keine brauchbare geschlossene Form: Die Einzelwerte sind weder
normalverteilt noch unabhängig noch gleich schwer (eine WER über drei Wörter
springt in Dritteln). Der Bootstrap braucht davon nichts - er zieht aus den
vorhandenen Messungen neue Stichproben und liest die Streuung an ihnen ab
(Bisani/Ney, ICASSP 2004).

**Warum blockweise.** Vier Fassungen derselben Aufnahme (Original,
wie gesprochen und mit Rauschen) sind mehrere Messungen an *einem* Gegenstand.
Wer sie einzeln zieht, tut so, als lägen vier unabhängige Auskünfte vor, und
bekommt ein Intervall heraus, das deutlich zu schmal ist. Gezogen wird deshalb
je Aufnahme, mit allen ihren Fassungen zusammen - der blockweise Bootstrap
(Liu u. a., Interspeech 2020). Die naive Ziehung je Einheit bleibt als
`BLOCK_EINHEIT` wählbar: Sie ist das, was die meiste Literatur rechnet, und
ohne sie wären die Zahlen dieses Projekts mit ihr nicht vergleichbar.

**Warum ein Keim und keine Zufallszahl.** Ein Vertrauensbereich, der bei jedem
Aufruf ein wenig anders ausfällt, ist eine schlechte Auskunft: Zwei Blicke auf
dieselbe Tabelle ergäben zwei Zahlen, und niemand wüsste, ob sich das Modell
oder der Würfel geändert hat. Der Keim steht fest, die Ziehungen hängen allein
an der **Anzahl** der Blöcke - dieselbe Messreihe ergibt auf jeder Maschine
und zu jeder Zeit denselben Bereich. Dass zwei Modelle mit gleich vielen
Blöcken dieselben Ziehungen bekommen, ist dabei kein Mangel, sondern die
Voraussetzung für `unterschied`: Nur wer beide Modelle an denselben gezogenen
Aufnahmen misst, vergleicht gepaart.

**Was diese Datei nicht tut.** Sie ändert keine gemessene Zahl. Jeder
Mittelwert, den die App vorher zeigte, kommt hier unverändert wieder heraus
(`Intervall.mittel`); das Intervall steht daneben, nicht an seiner Stelle.
Alles hier ist eine zusätzliche Auskunft und keine andere.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache

# ── Die Wahl ────────────────────────────────────────────────────────────────
#
# Was der Aufrufer einstellen darf. `AUS` ist die Vorgabe überall dort, wo
# vorher nichts stand: Diese Datei ist eine Erweiterung, und eine Erweiterung
# schaltet sich nicht selbst ein.
AUS = "aus"

# Je Aufnahme ziehen, mit allen ihren Fassungen. Die richtige Wahl, wenn die
# Messreihe mehrere Fassungen derselben Aufnahme enthält.
BLOCK_AUFNAHME = "aufnahme"

# Je Messeinheit ziehen - die naive Ziehung. Zu schmal, sobald Fassungen
# derselben Aufnahme in der Reihe stehen; wählbar, weil sie das in der
# Literatur übliche Verfahren ist.
BLOCK_EINHEIT = "einheit"

BLOCKARTEN = (AUS, BLOCK_AUFNAHME, BLOCK_EINHEIT)

# ── Die Zahlen des Verfahrens ───────────────────────────────────────────────
#
# Sie stehen hier als Konstanten und nicht in der Konfiguration: Wer sie
# ändert, ändert jede Zahl, die je damit gerechnet wurde, und dann sind alte
# und neue Bereiche nicht mehr dieselbe Größe. Geändert werden darf das - aber
# sichtbar, in einem Commit, und mit einer neuen `marke` (siehe `Verfahren`).
KEIM = 20260913

# Zweitausend Ziehungen. Darunter wackeln die Perzentile selbst sichtbar,
# darüber wird es langsam, ohne genauer zu werden: Der Fehler des Bootstraps
# fällt mit der Wurzel, der Aufwand steigt linear.
ZIEHUNGEN = 2000

# Das übliche Niveau. 0,95 heißt: der Bereich zwischen dem 2,5- und dem
# 97,5-Perzentil der Ziehungen.
NIVEAU = 0.95

# Unter zwei Blöcken gibt es nichts zu ziehen - ein „Vertrauensbereich" über
# eine einzige Aufnahme wäre eine Zahl ohne Inhalt.
MINDESTENS = 2

# Nachkommastellen der ausgegebenen Zahlen - dieselbe Rundung wie bei den
# Mittelwerten, die schon in `bewertung.jsonl` stehen.
STELLEN = 6


@dataclass(frozen=True)
class Verfahren:
    """Womit gerechnet wurde - gehört zu jedem Ergebnis dazu.

    Ein Vertrauensbereich ohne seine Parameter ist nicht nachvollziehbar: 2,5 %
    bis 97,5 % über zweitausend blockweise Ziehungen ist etwas anderes als 5 %
    bis 95 % über zweihundert. Die `marke` fasst das in eine Zeichenkette, die
    sich neben jeden gespeicherten Wert legen lässt.
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

    **Warum gepaart und nicht zwei Bereiche nebeneinander.** Beide Modelle
    haben dieselben Aufnahmen gehört. Eine schwer verständliche Aufnahme zieht
    beide herunter, eine leichte hebt beide - dieser gemeinsame Anteil fällt
    in der Differenz heraus. Zwei getrennte Bereiche tragen ihn dagegen beide
    mit und überlappen sich deshalb oft, obwohl der Unterschied belastbar ist.
    Der gepaarte Vergleich ist die schärfere und die ehrlichere Auskunft.
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

    Gemerkt, weil dieselbe Blockzahl in einer Tabelle dutzendfach vorkommt: Ein
    Dutzend Modelle mal die Fassungen mal vier Maße greifen alle auf dieselben
    Ziehungen zu. Sie einmal zu würfeln spart nicht nur Zeit - es ist zugleich
    das, was `unterschied` gepaart macht.
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


def bilde(paare: Iterable[tuple[str, float]], blockart: str = BLOCK_AUFNAHME) -> list[list[float]]:
    """Werte zu Blöcken bündeln - nach dem Schlüssel, den der Aufrufer mitgibt.

    Der Schlüssel ist die Kennung der Aufnahme; bei `BLOCK_EINHEIT` bekommt
    jeder Wert seinen eigenen Block. Sortiert wird nach dem Schlüssel, damit
    die Reihenfolge der Blöcke nicht davon abhängt, in welcher Reihenfolge
    jemand die Zeilen gelesen hat - sonst wären die Ziehungen zwar dieselben,
    träfen aber andere Werte.
    """
    if blockart == BLOCK_EINHEIT:
        return [[wert] for _schluessel, wert in sorted(paare, key=lambda eintrag: eintrag[0])]
    nach_schluessel: dict[str, list[float]] = {}
    for schluessel, wert in paare:
        nach_schluessel.setdefault(schluessel, []).append(wert)
    return [nach_schluessel[schluessel] for schluessel in sorted(nach_schluessel)]


def bilde_paare(
    drillinge: Iterable[tuple[str, float, float]], blockart: str = BLOCK_AUFNAHME
) -> list[list[tuple[float, float]]]:
    """Dasselbe für zwei Reihen an denselben Einheiten - je Einheit ein Paar."""
    if blockart == BLOCK_EINHEIT:
        return [
            [(links, rechts)]
            for _schluessel, links, rechts in sorted(drillinge, key=lambda eintrag: eintrag[0])
        ]
    nach_schluessel: dict[str, list[tuple[float, float]]] = {}
    for schluessel, links, rechts in drillinge:
        nach_schluessel.setdefault(schluessel, []).append((links, rechts))
    return [nach_schluessel[schluessel] for schluessel in sorted(nach_schluessel)]


# ── Die beiden Rechnungen ───────────────────────────────────────────────────


def intervall(
    bloecke: Sequence[Sequence[float]], verfahren: Verfahren | None = None
) -> Intervall | None:
    """Der Vertrauensbereich des Mittelwerts über alle Werte aller Blöcke.

    `None`, wenn zu wenige Blöcke da sind - lieber keine Auskunft als eine, die
    aussieht wie eine. Der Mittelwert selbst ist **exakt** der, den auch die
    schlichte Mittelung liefert: Der Bootstrap schätzt nur seine Streuung, er
    ersetzt ihn nicht.
    """
    art = verfahren or Verfahren()
    summen = [sum(block) for block in bloecke]
    anzahlen = [len(block) for block in bloecke]
    einheiten = sum(anzahlen)
    if len(bloecke) < MINDESTENS or not einheiten:
        return None

    mittel = sum(summen) / einheiten
    hole_summe = summen.__getitem__
    hole_anzahl = anzahlen.__getitem__
    gezogen = sorted(
        sum(map(hole_summe, zug)) / sum(map(hole_anzahl, zug))
        for zug in zuege(len(bloecke), art.ziehungen, art.keim)
    )

    rand = (1.0 - art.niveau) / 2.0
    return Intervall(
        mittel=round(mittel, STELLEN),
        unten=round(_perzentil(gezogen, rand), STELLEN),
        oben=round(_perzentil(gezogen, 1.0 - rand), STELLEN),
        streuung=round(_streuung(gezogen, sum(gezogen) / len(gezogen)), STELLEN),
        bloecke=len(bloecke),
        einheiten=einheiten,
        verfahren=art,
    )


def unterschied(
    bloecke: Sequence[Sequence[tuple[float, float]]], verfahren: Verfahren | None = None
) -> Unterschied | None:
    """Der gepaarte Vergleich zweier Reihen: Bereich und p-Wert der Differenz.

    Gezogen wird **einmal**, und beide Reihen werden an derselben Ziehung
    gemessen - daher gepaart. Der p-Wert ist der übliche zweiseitige
    Bootstrap-Wert: der Anteil der Ziehungen, der auf der anderen Seite der
    Null liegt, verdoppelt. Die Eins im Zähler und im Nenner ist keine
    Kosmetik: Ohne sie käme bei zweitausend Ziehungen ein p von genau null
    heraus, und das behauptete Gewissheit, wo nur „kleiner als 1/2000" gemessen
    wurde.
    """
    art = verfahren or Verfahren()
    differenzen = [[links - rechts for links, rechts in block] for block in bloecke]
    summen = [sum(block) for block in differenzen]
    anzahlen = [len(block) for block in differenzen]
    einheiten = sum(anzahlen)
    if len(bloecke) < MINDESTENS or not einheiten:
        return None

    mittel = sum(summen) / einheiten
    hole_summe = summen.__getitem__
    hole_anzahl = anzahlen.__getitem__
    gezogen = sorted(
        sum(map(hole_summe, zug)) / sum(map(hole_anzahl, zug))
        for zug in zuege(len(bloecke), art.ziehungen, art.keim)
    )

    nicht_groesser = sum(1 for wert in gezogen if wert <= 0.0)
    nicht_kleiner = len(gezogen) - sum(1 for wert in gezogen if wert < 0.0)
    p = 2.0 * (min(nicht_groesser, nicht_kleiner) + 1) / (len(gezogen) + 1)

    rand = (1.0 - art.niveau) / 2.0
    return Unterschied(
        differenz=round(mittel, STELLEN),
        unten=round(_perzentil(gezogen, rand), STELLEN),
        oben=round(_perzentil(gezogen, 1.0 - rand), STELLEN),
        p=round(min(p, 1.0), 4),
        bloecke=len(bloecke),
        einheiten=einheiten,
        verfahren=art,
    )
