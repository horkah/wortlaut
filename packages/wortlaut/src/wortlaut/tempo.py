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

# Die Grenzen, innerhalb derer gesucht werden darf (siehe
# `apps/lernen/training/tempowahl.py`). Unter 1,0 wird gedehnt statt
# vorgespult - das kann helfen, wenn jemand sehr schnell spricht.
#
# Nach oben stand hier lange 3,0, und das war zu eng: An einem echten Korpus
# fiel die Fehlerkurve bis zur obersten Stützstelle und hörte dort auf, weil
# das Raster aufhörte. Ein Optimum am Rand ist keines - es ist die Aussage,
# dass man zu kurz gesucht hat. Bei 4,0 ist Schluss, weil von einer kurzen
# Silbe dann noch ein knappes Dutzend Spektrogrammrahmen übrig bleibt.
SPANNE = (0.75, 4.0)

# Was ein einzelner `atempo` verträgt. Darüber hinaus werden mehrere
# hintereinandergehängt; das ist die von ffmpeg vorgesehene Art und keine
# Krücke.
_JE_STUFE = (0.5, 2.0)


def filterkette(faktor: float) -> str:
    """Die ffmpeg-Filterkette für diesen Faktor.

    Ein `atempo` schafft höchstens das Doppelte, also wird der Faktor auf
    mehrere aufgeteilt: 3,0 wird zu zweimal ~1,732. Gleichmäßig aufgeteilt und
    nicht `2,0 · 1,5` - jede Stufe rechnet neu, und zwei gleich große Schritte
    verteilen den Fehler besser als ein großer und ein kleiner.
    """
    stufen = 1
    while faktor ** (1 / stufen) > _JE_STUFE[1] or faktor ** (1 / stufen) < _JE_STUFE[0]:
        stufen += 1
        if stufen > 8:  # pragma: no cover - bei dieser SPANNE unerreichbar
            raise AudioFehler(f"Faktor {faktor:g} lässt sich nicht zerlegen.")
    einzeln = faktor ** (1 / stufen)
    return ",".join([f"atempo={einzeln:.6f}"] * stufen)


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
    """Ob überhaupt etwas zu tun ist. Bei 1,0 ist es das nicht.

    Mit einer kleinen Toleranz, weil der Faktor aus einer Suche kommen kann
    und 0,9999999 kein Vorspulen ist, sondern eine Kommastelle.
    """
    return abs(faktor - VORGABE) > 1e-6


def in_spanne(faktor: float) -> float:
    """Der Faktor, auf die erlaubte Spanne gestutzt."""
    return min(max(float(faktor), SPANNE[0]), SPANNE[1])


def spule_vor(quelle: Path, ziel: Path, faktor: float) -> None:
    """Dieselbe Aufnahme schneller, bei gleicher Tonhöhe.

    Ausgeschrieben wird wieder 16 kHz, mono, PCM 16 bit - dasselbe Format wie
    überall (`audio.py`). Das ist nicht selbstverständlich: ffmpeg richtet sich
    sonst nach der Endung, und eine vorgespulte Datei in einem anderen Format
    wäre für den Trainer kein Audio mehr, sondern ein Fehler zur Unzeit.
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
