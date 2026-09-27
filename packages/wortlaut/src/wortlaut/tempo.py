"""Alles schneller abspielen - vor jeder Erkennung, bei gleicher Tonhöhe.

**Wofür.** Dysarthrische Sprache ist oft stark verlangsamt: gedehnte Vokale,
lange Pausen mitten im Wort. Whisper ist auf Sprache trainiert, die das nicht
tut - eine gedehnte Silbe belegt in seinem Spektrogramm den Platz von dreien,
und was es dort sucht, liegt weiter auseinander, als es je gesehen hat. Ob
Vorspulen das näher an Bekanntes rückt oder bloß Information wegwirft, ist
keine Meinungsfrage, sondern eine Messung.

Die einzige Rechnung dafür im Projekt: Auswertung, Trainer und Diktat fragen
hier. Ein Modell, das auf vorgespulter Sprache gelernt hat, muss beim Diktieren
genau dasselbe hören.

**Die Tonhöhe bleibt.** Gerechnet wird mit `atempo` von ffmpeg, einem
Phasenvokoder: Die Dauer ändert sich, die Stimme nicht - sonst wären zwei Dinge
zugleich anders. (Die Tempo-Augmentierung im Trainer verschiebt die Tonhöhe
absichtlich mit, `apps/lernen/training/klangwandel.py`.) ffmpeg liegt ohnehin
im Abbild (`audio.py`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .audio import ABTASTRATE, AudioFehler

VORGABE = 1.0

# Wo gesucht werden darf (`apps/lernen/training/tempowahl.py`). Unter 1,0 wird
# gedehnt. Bei 4,0 bleibt von einer kurzen Silbe noch ein knappes Dutzend
# Spektrogrammrahmen.
SPANNE = (0.75, 4.0)

# Was ein einzelner `atempo` verträgt; darüber werden mehrere verkettet.
_JE_STUFE = (0.5, 2.0)


def filterkette(faktor: float) -> str:
    """Die ffmpeg-Filterkette für diesen Faktor.

    Gleichmäßig auf Stufen verteilt - 3,0 wird zweimal ~1,732, nicht 2,0 · 1,5;
    gleich große Schritte verteilen den Fehler besser.
    """
    stufen = 1
    while faktor ** (1 / stufen) > _JE_STUFE[1] or faktor ** (1 / stufen) < _JE_STUFE[0]:
        stufen += 1
        if stufen > 8:  # pragma: no cover - bei dieser SPANNE unerreichbar
            raise AudioFehler(f"Faktor {faktor:g} lässt sich nicht zerlegen.")
    einzeln = faktor ** (1 / stufen)
    return ",".join([f"atempo={einzeln:.6f}"] * stufen)


def marke(faktor: float) -> str:
    """Wie ein Faktor in Namen steht: `1x`, `2.25x`."""
    return f"{faktor:g}x"


def vorspulen_noetig(faktor: float) -> bool:
    """Ob überhaupt etwas zu tun ist - mit Toleranz, weil der Faktor aus einer
    Rechnung kommen kann."""
    return abs(faktor - VORGABE) > 1e-6


def in_spanne(faktor: float) -> float:
    """Der Faktor, auf die erlaubte Spanne gestutzt."""
    return min(max(float(faktor), SPANNE[0]), SPANNE[1])


def spule_vor(quelle: Path, ziel: Path, faktor: float) -> None:
    """Dieselbe Aufnahme schneller, bei gleicher Tonhöhe.

    Ausgeschrieben ausdrücklich als 16 kHz mono PCM 16 bit wie überall
    (`audio.py`); ffmpeg richtete sich sonst nach der Endung.
    """
    if not vorspulen_noetig(faktor):
        raise AudioFehler(f"Bei Faktor {faktor:g} ist nichts vorzuspulen.")
    if not SPANNE[0] <= faktor <= SPANNE[1]:
        raise AudioFehler(
            f"Faktor {faktor:g} liegt außerhalb von {SPANNE[0]:g} bis {SPANNE[1]:g}."
        )
    ziel.parent.mkdir(parents=True, exist_ok=True)
    # Schalter und Wert gehören paarweise in eine Zeile:
    # fmt: off
    befehl = [
        "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
        "-i", str(quelle),
        "-filter:a", filterkette(faktor),
        "-ac", "1",
        "-ar", str(ABTASTRATE),
        "-sample_fmt", "s16",
        str(ziel),
    ]
    # fmt: on
    ergebnis = subprocess.run(befehl, capture_output=True, text=True, check=False)
    if ergebnis.returncode != 0:
        raise AudioFehler(f"ffmpeg ist gescheitert: {ergebnis.stderr.strip()[:500]}")
