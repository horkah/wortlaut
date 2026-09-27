"""Dieselbe Aufnahme, unter veränderten Bedingungen gehört - die gemessenen Fassungen.

Eine Aufnahme ist ein einzelner Fall: diese Stimme, dieses Mikrofon, dieser
Raum. Ob ein Modell den Sprecher versteht oder nur diese Aufnahmesituation
verträgt, zeigt erst eine Abwandlung:

* **`rauschen`** - hörbares Grundrauschen in festem Abstand zur Lautstärke der
  Aufnahme: der Lüfter, die Straße, das billige Mikrofon. Rauschen ändert das
  Spektrogramm an jeder Stelle; eine bloße Verstärkung dagegen verschiebt im
  normierten Log-Mel-Spektrogramm kaum mehr als einen Summanden.

**Fester Abstand statt festem Pegel**, damit die Störung für eine leise und
eine laute Aufnahme gleich schwer wiegt. **Gewürfelt und wiederholbar**: Der
Keim ist die Kennung der Aufnahme, dieselbe Aufnahme ergibt auf jeder Maschine
dasselbe Rauschen.

Dies sind die Fassungen, in denen **gemessen** wird - wenige und fest, damit
Modelle vergleichbar bleiben. Womit **trainiert** wird, steht in
`apps/lernen/training/klangwandel.py`: breit, zufällig, je Durchgang anders.

Gerechnet wird mit der Standardbibliothek, ohne numpy im Webprozess.
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

# Die unabgewandelte Aufnahme - keine Abwandlung, sie liegt schon da.
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

    Normalverteilt, damit es nach Grundgeräusch klingt und nicht nach einem
    Defekt.
    """
    streuung = _rms(werte) * 10 ** (-RAUSCHABSTAND_DB / 20)
    if streuung < 1.0:
        # Darunter bliebe nach dem Runden bei einer fast stillen Aufnahme nichts.
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

# Die Reihenfolge, in der überall gezählt und angezeigt wird.
VARIANTEN = (ORIGINAL, *(abwandlung.name for abwandlung in ABWANDLUNGEN))

_NACH_NAME = {abwandlung.name: abwandlung for abwandlung in ABWANDLUNGEN}


def abwandlung(name: str) -> Abwandlung:
    """Die Abwandlung zu ihrem Namen. `original` ist keine - das ist ein Fehler."""
    if name not in _NACH_NAME:
        raise AudioFehler(f"Keine Abwandlung mit dem Namen {name!r}.")
    return _NACH_NAME[name]


def wandle_ab(quelle: Path, ziel: Path, name: str, keim: str) -> None:
    """Liest eine WAV-Datei, wandelt sie ab und schreibt das Ergebnis.

    Länge, Abtastrate und Format bleiben; abgewandelt werden nur die
    Abtastwerte.
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
