"""Dieselbe Aufnahme, unter veränderten Bedingungen gehört.

Eine Aufnahme im Korpus ist ein einzelner Fall: diese Stimme, dieses Mikrofon,
dieser Abstand, dieser Raum. Was die Auswertung daraus lernt, gilt streng
genommen nur für genau diesen Fall. Ob ein Modell den Sprecher *versteht* oder
bloß diese eine Aufnahmesituation gut verträgt, lässt sich daran nicht
ablesen - und das ist die Frage, auf die es ankommt, denn die nächste Aufnahme
entsteht mit anderem Pegel und anderem Grundgeräusch.

Deshalb bekommt jede Aufnahme eine Abwandlung, und zwar eine bewusst schlichte:

* **`rauschen`** - ein kleines, hörbares Grundrauschen darüber, in festem
  Abstand zur Lautstärke der Aufnahme selbst. Das ist der Lüfter, die Straße,
  das billige Mikrofon.

**Warum nur noch eine.** Hier standen bis September 2026 zwei weitere:
`pegel` (lauter gerechnet bis knapp unter den Anschlag) und `lauter` (alles
mal 1,15). Beide sind gemessen worden, und beide sind an Whisper nahezu
wirkungslos: Das Modell hört kein Wellenfeld, sondern ein Log-Mel-Spektrogramm,
und eine gleichmäßige Verstärkung verschiebt darin im Wesentlichen einen
Summanden. Was zwei Drittel der Rechenzeit einer Auswertung kostete, trennte
keine zwei Modelle voneinander - und eine Fassung, die nichts unterscheidet,
ist keine Messung, sondern eine Spalte. Sie sind samt ihren Dateien und
Datenbankzeilen verworfen (`009_ohne_pegelvarianten.sql`).

Was blieb, ist die eine, die wirklich etwas anderes verlangt: Rauschen ändert
das Spektrogramm an jeder Stelle und nicht nur seine Höhe.

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

**Wovon das hier zu unterscheiden ist.** Dies sind die Fassungen, in denen
**gemessen** wird - dieselben für jedes Modell, seit Monaten vergleichbar, und
deshalb absichtlich wenige. Womit **trainiert** wird, ist eine andere Frage und
steht woanders (`apps/lernen/training/klangwandel.py`): Dort darf die
Abwandlung breit, zufällig und je Durchgang verschieden sein, denn dort soll
sie nichts vergleichbar machen, sondern ein Modell härter.

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

from .audio import AudioFehler

# Die unabgewandelte Aufnahme. Sie ist keine Abwandlung und wird nirgends
# erzeugt - sie liegt schon da. Der Name steht hier, damit er an einer Stelle
# steht und nicht als Zeichenkette in jeder Abfrage.
ORIGINAL = "original"

# Die Grenzen eines 16-Bit-Abtastwerts. Was darüber hinausginge, wird
# abgeschnitten: Ein Überlauf klänge nicht laut, sondern kaputt.
KLEINSTER = -32768
GROESSTER = 32767

# Wie weit das Rauschen unter der Aufnahme selbst liegt. 20 dB sind deutlich
# zu hören und lassen die Sprache trotzdem vorn: Es soll stören, nicht
# zudecken.
RAUSCHABSTAND_DB = 20.0


def _begrenzt(wert: float) -> int:
    """Auf den Wertebereich zurechtstutzen und runden."""
    return max(KLEINSTER, min(GROESSTER, round(wert)))


def _rms(werte: array.array) -> float:
    return math.sqrt(sum(wert * wert for wert in werte) / len(werte))


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
