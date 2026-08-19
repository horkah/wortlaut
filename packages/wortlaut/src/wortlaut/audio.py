"""Alles, was mit Klang zu tun hat: umwandeln, vermessen.

Browser nehmen mit `MediaRecorder` in Opus auf, das Training braucht 16 kHz
Mono-WAV. Die Umwandlung passiert genau hier, mit ffmpeg als einzigem externen
Werkzeug. Die Messungen laufen ohne numpy, allein mit der Standardbibliothek —
bei Ausschnitten von wenigen Sekunden ist das schnell genug und spart eine
schwere Abhängigkeit im Web-Prozess.
"""

from __future__ import annotations

import array
import math
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

ABTASTRATE = 16_000
VOLLAUSSCHLAG = 32768.0  # Betrag eines 16-Bit-Abtastwerts bei Vollaussteuerung
FENSTER = 320  # 20 ms bei 16 kHz — feinste sinnvolle Auflösung für Pegelverläufe


class AudioFehler(RuntimeError):
    """Umwandlung oder Vermessung ist fehlgeschlagen."""


@dataclass(frozen=True)
class Befund:
    """Messwerte einer Aufnahme. Bewertet werden sie erst in `services/quality.py`."""

    dauer_s: float
    pegel_dbfs: float  # mittlerer Pegel (RMS)
    spitze_dbfs: float
    clipping_anteil: float  # Anteil der Abtastwerte am Anschlag
    stille_vorn_s: float
    stille_hinten_s: float


def wandle_in_wav(quelle: Path, ziel: Path) -> None:
    """Beliebiges Eingangsformat → 16 kHz, mono, PCM 16 bit.

    ffmpeg erkennt das Eingangsformat selbst; der Browser darf also liefern,
    was er mag.
    """
    ziel.parent.mkdir(parents=True, exist_ok=True)
    # Schalter und Wert gehören paarweise in eine Zeile:
    # fmt: off
    befehl = [
        "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
        "-i", str(quelle),
        "-ac", "1",                 # mono
        "-ar", str(ABTASTRATE),     # 16 kHz
        "-sample_fmt", "s16",       # PCM 16 bit
        str(ziel),
    ]
    # fmt: on
    ergebnis = subprocess.run(
        befehl,
        capture_output=True,
        text=True,
        check=False,  # der Rückgabewert wird unten selbst geprüft
    )
    if ergebnis.returncode != 0:
        raise AudioFehler(f"ffmpeg ist gescheitert: {ergebnis.stderr.strip()[:500]}")


def untersuche(wav: Path) -> Befund:
    """Misst Dauer, Pegel, Clipping und Randstille einer WAV-Datei."""
    with wave.open(str(wav), "rb") as datei:
        if datei.getsampwidth() != 2 or datei.getnchannels() != 1:
            raise AudioFehler("Erwartet wird mono mit 16 bit — bitte erst umwandeln.")
        abtastrate = datei.getframerate()
        werte = array.array("h")
        werte.frombytes(datei.readframes(datei.getnframes()))

    if not werte:
        raise AudioFehler("Die Aufnahme enthält keine Abtastwerte.")

    spitze = max(max(werte), -min(werte))
    # „Am Anschlag" heißt hier: die obersten 0,1 % des Wertebereichs. Genau
    # 32767 zu prüfen wäre zu streng, weil die Umwandlung leicht rundet.
    am_anschlag = sum(1 for wert in werte if abs(wert) >= 32700)

    # Pegelverlauf in 20-ms-Fenstern; daraus RMS und die Randstille.
    fenster_rms = [
        math.sqrt(sum(wert * wert for wert in werte[start : start + FENSTER]) / FENSTER)
        for start in range(0, len(werte) - FENSTER + 1, FENSTER)
    ] or [float(spitze)]
    gesamt_rms = math.sqrt(sum(r * r for r in fenster_rms) / len(fenster_rms))

    # Schwelle relativ zur Spitze: absolute Werte wären für leise Sprecher
    # unbrauchbar. Nach unten begrenzt, damit Rauschen nicht als Sprache zählt.
    schwelle = max(spitze * 10 ** (-35 / 20), VOLLAUSSCHLAG * 10 ** (-60 / 20))
    fenster_dauer = FENSTER / abtastrate

    def stille_am_anfang(werte_folge: list[float]) -> float:
        anzahl = 0
        for rms in werte_folge:
            if rms >= schwelle:
                break
            anzahl += 1
        return anzahl * fenster_dauer

    return Befund(
        dauer_s=len(werte) / abtastrate,
        pegel_dbfs=_dbfs(gesamt_rms),
        spitze_dbfs=_dbfs(spitze),
        clipping_anteil=am_anschlag / len(werte),
        stille_vorn_s=stille_am_anfang(fenster_rms),
        stille_hinten_s=stille_am_anfang(fenster_rms[::-1]),
    )


def _dbfs(betrag: float) -> float:
    """Linearer Betrag → dBFS. Stille ergibt −120 statt minus unendlich."""
    return 20 * math.log10(max(betrag, 1e-6) / VOLLAUSSCHLAG)


def schneide_ausschnitt(quelle: Path, ziel: Path, start_s: float, ende_s: float) -> None:
    """Schreibt den Bereich [start_s, ende_s) einer WAV-Datei in eine neue Datei.

    Gebraucht von „schreiben": Whisper liefert Abschnittsgrenzen, und jeder
    Abschnitt braucht sein eigenes Audio — er kann einzeln neu eingesprochen
    werden und geht einzeln als Korrekturpaar an „hören".

    Reine Standardbibliothek und ohne Umkodieren: ein Schnitt an
    Rahmengrenzen ist das Kopieren eines Byte-Bereichs. Grenzen außerhalb der
    Datei werden auf sie zurechtgestutzt, statt zu scheitern — Whisper meldet
    gelegentlich ein Ende hinter dem letzten Abtastwert.
    """
    with wave.open(str(quelle), "rb") as datei:
        rahmen_gesamt = datei.getnframes()
        rate = datei.getframerate()
        von = max(0, min(rahmen_gesamt, int(start_s * rate)))
        bis = max(von, min(rahmen_gesamt, int(ende_s * rate)))
        datei.setpos(von)
        rohdaten = datei.readframes(bis - von)
        parameter = datei.getparams()

    if not rohdaten:
        raise AudioFehler(f"Leerer Ausschnitt {start_s:.2f}–{ende_s:.2f} s.")

    ziel.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ziel), "wb") as neu:
        # Kanäle, Breite und Rate der Quelle übernehmen; nur die Länge ändert sich.
        neu.setnchannels(parameter.nchannels)
        neu.setsampwidth(parameter.sampwidth)
        neu.setframerate(parameter.framerate)
        neu.writeframes(rohdaten)
