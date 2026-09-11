"""Dieselbe Aufnahme, unter veränderten Bedingungen gehört.

Eine Aufnahme im Korpus ist ein einzelner Fall: diese Stimme, dieses Mikrofon,
dieser Abstand, dieser Raum. Was die Auswertung daraus lernt, gilt streng
genommen nur für genau diesen Fall. Ob ein Modell den Sprecher *versteht* oder
bloß diese eine Aufnahmesituation gut verträgt, lässt sich daran nicht
ablesen - und das ist die Frage, auf die es ankommt, denn die nächste Aufnahme
entsteht mit anderem Pegel und anderem Grundgeräusch.

Deshalb bekommt jede Aufnahme drei Abwandlungen, und zwar bewusst schlichte:

* **`pegel`** - lauter gerechnet, bis die Spitze knapp unter den Anschlag
  stößt. Der Wertebereich wird ausgeschöpft, ohne ihn zu verlassen. Das ist
  die Frage „liegt es nur daran, dass es zu leise war?".
* **`lauter`** - alles mal 1,15, für jede Aufnahme derselbe Faktor. Nicht
  dasselbe wie `pegel`: Hier ändert sich der Abstand zwischen leisen und
  lauten Aufnahmen **nicht**, und wer schon nah am Anschlag lag, stößt jetzt
  daran. Genau das ist der Fall, den jemand herstellt, der am Regler dreht.
* **`rauschen`** - ein kleines, hörbares Grundrauschen darüber, in festem
  Abstand zur Lautstärke der Aufnahme selbst. Das ist der Lüfter, die Straße,
  das billige Mikrofon.

**Warum fester Abstand und nicht fester Pegel.** Ein absoluter Rauschpegel
träfe eine leise Aufnahme viel härter als eine laute - die Abwandlung wäre für
jede Aufnahme eine andere, und der Vergleich zwischen zwei Aufnahmen sagte
dann mehr über deren Aussteuerung als über das Modell. Mit einem festen
Rauschabstand ist die Störung überall gleich schwer zu überhören.

**Warum gewürfelt und trotzdem wiederholbar.** Rauschen ist Zufall, aber eine
Messung, die sich nicht wiederholen lässt, ist keine. Der Würfel bekommt
deshalb die Kennung der Aufnahme als Keim: Dieselbe Aufnahme ergibt bei jedem
Lauf, auf jeder Maschine, dasselbe Rauschen. Eine gelöschte und neu gerechnete
Datei ist Byte für Byte dieselbe wie vorher.

Gerechnet wird ohne numpy, allein mit der Standardbibliothek - wie in
`audio.py` und aus demselben Grund: Bei Ausschnitten von wenigen Sekunden ist
das schnell genug und spart eine schwere Abhängigkeit im Web-Prozess.
"""

from __future__ import annotations

import array
import math
import random
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .audio import VOLLAUSSCHLAG, AudioFehler

# Die unabgewandelte Aufnahme. Sie ist keine Abwandlung und wird nirgends
# erzeugt - sie liegt schon da. Der Name steht hier, damit er an einer Stelle
# steht und nicht als Zeichenkette in jeder Abfrage.
ORIGINAL = "original"

# Die Grenzen eines 16-Bit-Abtastwerts. Was darüber hinausginge, wird
# abgeschnitten: Ein Überlauf klänge nicht laut, sondern kaputt.
KLEINSTER = -32768
GROESSTER = 32767

# Wohin `pegel` die Spitze legt. Knapp unter den Anschlag und nicht genau
# darauf: Beim Runden einzelner Abtastwerte bliebe sonst ein Rest, der als
# Übersteuerung gezählt würde (siehe `audio.untersuche`).
ZIEL_SPITZE_DBFS = -1.0

# Der eine Faktor von `lauter`, für jede Aufnahme derselbe: 15 % mehr.
LAUTER_FAKTOR = 1.15

# Wie weit das Rauschen unter der Aufnahme selbst liegt. 20 dB sind deutlich
# zu hören und lassen die Sprache trotzdem vorn: Es soll stören, nicht
# zudecken.
RAUSCHABSTAND_DB = 20.0


def _begrenzt(wert: float) -> int:
    """Auf den Wertebereich zurechtstutzen und runden."""
    return max(KLEINSTER, min(GROESSTER, round(wert)))


def _verstaerkt(werte: array.array, faktor: float) -> array.array:
    return array.array("h", (_begrenzt(wert * faktor) for wert in werte))


def _spitze(werte: array.array) -> int:
    return max(max(werte), -min(werte))


def _rms(werte: array.array) -> float:
    return math.sqrt(sum(wert * wert for wert in werte) / len(werte))


def pegel_ausschoepfen(werte: array.array, keim: str) -> array.array:
    """Lauter, bis die Spitze bei `ZIEL_SPITZE_DBFS` steht.

    Das schlichteste Verfahren, den Wertebereich auszunutzen: ein einziger
    Faktor über die ganze Aufnahme, bestimmt aus ihrem lautesten Punkt.
    Absichtlich keine Kompression und keine fensterweise Anpassung - die
    machten aus einer lauten und einer leisen Stelle dieselbe Lautstärke und
    änderten damit, *wie* gesprochen wurde. Hier ändert sich nur, wie weit der
    Regler aufgedreht war.

    Eine Aufnahme, die schon am Anschlag stand, wird dabei leiser. Das ist
    richtig so: „den Bereich optimal ausnutzen" heißt auch, ihn nicht zu
    verlassen.
    """
    spitze = _spitze(werte)
    if spitze == 0:
        # Stille bleibt Stille. Ein Faktor darauf wäre eine Division durch null.
        return array.array("h", werte)
    return _verstaerkt(werte, VOLLAUSSCHLAG * 10 ** (ZIEL_SPITZE_DBFS / 20) / spitze)


def gleichmaessig_lauter(werte: array.array, keim: str) -> array.array:
    """Alles mal `LAUTER_FAKTOR` - für jede Aufnahme derselbe Faktor.

    Dass eine ohnehin laute Aufnahme dabei an den Anschlag stößt, ist nicht
    der Fehler dieser Abwandlung, sondern ihr Gegenstand: Genau das passiert,
    wenn jemand pauschal lauter dreht. Abgeschnitten wird hart - eine weiche
    Begrenzung wäre eine zweite, unausgesprochene Bearbeitung.
    """
    return _verstaerkt(werte, LAUTER_FAKTOR)


def mit_rauschen(werte: array.array, keim: str) -> array.array:
    """Weißes Rauschen darüber, `RAUSCHABSTAND_DB` unter der Aufnahme.

    Normalverteilt und nicht gleichverteilt: So klingt es nach Grundgeräusch
    und nicht nach einem Defekt. Der Keim macht das Ergebnis wiederholbar
    (siehe Kopfkommentar).
    """
    streuung = _rms(werte) * 10 ** (-RAUSCHABSTAND_DB / 20)
    if streuung < 1.0:
        # Unter einem Abtastwert Streuung bliebe nach dem Runden fast nichts
        # übrig - bei einer (fast) stillen Aufnahme käme eine Abwandlung
        # heraus, die keine ist. Dann lieber das kleinste hörbare Rauschen.
        streuung = 1.0
    wuerfel = random.Random(keim)
    return array.array("h", (_begrenzt(wert + wuerfel.gauss(0.0, streuung)) for wert in werte))


@dataclass(frozen=True)
class Abwandlung:
    """Eine Art, dieselbe Aufnahme anders klingen zu lassen."""

    name: str
    titel: str
    erklaerung: str
    rechne: Callable[[array.array, str], array.array]


ABWANDLUNGEN = (
    Abwandlung(
        name="pegel",
        titel="Ausgesteuert",
        erklaerung="Lauter gerechnet, bis die Spitze knapp unter dem Anschlag steht.",
        rechne=pegel_ausschoepfen,
    ),
    Abwandlung(
        name="lauter",
        titel="15 % lauter",
        erklaerung="Alles mal 1,15 - für jede Aufnahme derselbe Faktor.",
        rechne=gleichmaessig_lauter,
    ),
    Abwandlung(
        name="rauschen",
        titel="Mit Rauschen",
        erklaerung="Ein hörbares Grundrauschen, 20 dB unter der Aufnahme.",
        rechne=mit_rauschen,
    ),
)

# Die Reihenfolge, in der überall gezählt und angezeigt wird: das Original
# zuerst, dann die Abwandlungen. Eine Stelle, damit Lauf, Auskunft und Ansicht
# nicht drei verschiedene Reihenfolgen haben.
VARIANTEN = (ORIGINAL, *(abwandlung.name for abwandlung in ABWANDLUNGEN))

_NACH_NAME = {abwandlung.name: abwandlung for abwandlung in ABWANDLUNGEN}


def abwandlung(name: str) -> Abwandlung:
    """Die Abwandlung zu ihrem Namen. `original` ist keine - das ist ein Fehler."""
    if name not in _NACH_NAME:
        raise AudioFehler(f"Keine Abwandlung mit dem Namen {name!r}.")
    return _NACH_NAME[name]


def wandle_ab(quelle: Path, ziel: Path, name: str, keim: str) -> None:
    """Liest eine WAV-Datei, wandelt sie ab und schreibt das Ergebnis.

    Länge, Abtastrate und Format bleiben, was sie waren - abgewandelt werden
    die Abtastwerte, nicht die Datei. Nur so ist die Abwandlung zur Aufnahme
    Punkt für Punkt dieselbe Stelle.
    """
    with wave.open(str(quelle), "rb") as datei:
        if datei.getsampwidth() != 2 or datei.getnchannels() != 1:
            raise AudioFehler("Erwartet wird mono mit 16 bit - bitte erst umwandeln.")
        parameter = datei.getparams()
        werte = array.array("h")
        werte.frombytes(datei.readframes(datei.getnframes()))

    if not werte:
        raise AudioFehler(f"{quelle.name} enthält keine Abtastwerte.")

    abgewandelt = abwandlung(name).rechne(werte, keim)

    ziel.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ziel), "wb") as neu:
        neu.setnchannels(parameter.nchannels)
        neu.setsampwidth(parameter.sampwidth)
        neu.setframerate(parameter.framerate)
        neu.writeframes(abgewandelt.tobytes())
