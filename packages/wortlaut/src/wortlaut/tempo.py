"""Alles schneller abspielen - vor jeder Erkennung, bei gleicher Tonhöhe.

**Wofür.** Dysarthrische Sprache ist oft stark verlangsamt: gedehnte Vokale,
lange Pausen mitten im Wort. Whisper ist auf Sprache trainiert, die das nicht
tut - eine gedehnte Silbe belegt in seinem Spektrogramm den Platz von dreien,
und was es dort sucht, liegt weiter auseinander, als es je gesehen hat. Ob
Vorspulen das näher an Bekanntes rückt oder bloß Information wegwirft, ist
keine Meinungsfrage, sondern eine Messung.

Dieses Modul ist die Rechnung dazu, und zwar die einzige im Projekt: Wer
vorspult - die Auswertung in „hören", der Trainer, das Diktat in „schreiben" -
fragt hier. Zwei Rechnungen, die sich um ein Promille unterschieden, wären der
unauffälligste denkbare Fehler: Ein Modell, das auf vorgespulter Sprache
gelernt hat, bekäme beim Diktieren etwas minimal anderes zu hören, und niemand
sähe je, woran es lag.

**Warum die Tonhöhe bleibt.** Schneller abspielen im naiven Sinn - jeden
zweiten Abtastwert nehmen - hebt die Stimme mit an. Dann sind zwei Dinge
zugleich anders, und die Messung sagt nicht mehr, welches gewirkt hat.
Gerechnet wird deshalb mit `atempo` von ffmpeg, einem Phasenvokoder: Dauer
ändert sich, Tonhöhe nicht.

(Das naive Verfahren gibt es in diesem Projekt auch, im Trainer als
Würfelgriff - dort ist die mitwandernde Tonhöhe erwünscht, weil sie einen
Sprecher erfindet, den es geben könnte: `apps/lernen/training/klangwandel.py`.
Hier wäre sie ein Störfaktor.)

**Warum ffmpeg und nicht numpy.** Einen Phasenvokoder selbst zu schreiben wäre
viel Mathematik für ein Werkzeug, das ohnehin im Abbild liegt - ohne ffmpeg
käme nicht eine einzige Aufnahme herein (`audio.py`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .audio import ABTASTRATE, AudioFehler

# Was zur Wahl steht. Keine freie Zahl: Jeder Wert verdreifacht im
# schlimmsten Fall die Messzeilen eines Sprechers (siehe unten), und ein
# Schieberegler lüde dazu ein, sieben Zwischenwerte auszuprobieren, von denen
# keiner je wieder zusammenpasst.
FAKTOREN = (1.0, 2.0, 3.0)
VORGABE = 1.0

# `atempo` kann je Durchgang höchstens verdoppeln; für das Dreifache werden
# zwei hintereinandergehängt. Das ist keine Krücke, sondern die von ffmpeg
# vorgesehene Art.
_FILTER = {2.0: "atempo=2.0", 3.0: "atempo=1.5,atempo=2.0"}


def pruefe(faktor: float) -> float:
    """Der bestellte Faktor, oder ein Fehler - sofort statt nach Stunden."""
    if faktor not in FAKTOREN:
        raise AudioFehler(
            f"Kein Tempofaktor: {faktor}. Zur Wahl stehen: "
            + ", ".join(f"{f:g}" for f in FAKTOREN)
        )
    return faktor


def marke(faktor: float) -> str:
    """Wie ein Faktor neben einer Messung steht: `1x`, `2x`, `3x`.

    Eine Zeichenkette und keine Kommazahl, aus demselben Grund wie beim
    Rechenwerk (`rechenwerk.marke`): Sie wird nur verglichen und nie gerechnet,
    und ein Fließkommawert als Schlüssel ist eine Einladung, dass `2.0` und
    `2.0000001` einmal verschiedene Messreihen werden.
    """
    return f"{faktor:g}x"


def vorspulen_noetig(faktor: float) -> bool:
    """Ob überhaupt etwas zu tun ist. Bei 1,0 ist es das nicht."""
    return faktor in _FILTER


def spule_vor(quelle: Path, ziel: Path, faktor: float) -> None:
    """Dieselbe Aufnahme schneller, bei gleicher Tonhöhe.

    Ausgeschrieben wird wieder 16 kHz, mono, PCM 16 bit - dasselbe Format wie
    überall (`audio.py`). Das ist nicht selbstverständlich: ffmpeg richtet sich
    sonst nach der Endung, und eine vorgespulte Datei in einem anderen Format
    wäre für den Trainer kein Audio mehr, sondern ein Fehler zur Unzeit.
    """
    if not vorspulen_noetig(faktor):
        raise AudioFehler(f"Bei Faktor {faktor:g} ist nichts vorzuspulen.")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    # Schalter und Wert gehören paarweise in eine Zeile:
    # fmt: off
    befehl = [
        "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
        "-i", str(quelle),
        "-filter:a", _FILTER[faktor],
        "-ac", "1",
        "-ar", str(ABTASTRATE),
        "-sample_fmt", "s16",
        str(ziel),
    ]
    # fmt: on
    ergebnis = subprocess.run(befehl, capture_output=True, text=True, check=False)
    if ergebnis.returncode != 0:
        raise AudioFehler(f"ffmpeg ist gescheitert: {ergebnis.stderr.strip()[:500]}")
