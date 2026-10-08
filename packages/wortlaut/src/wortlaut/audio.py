"""Alles, was mit Klang zu tun hat: umwandeln, vermessen.

Browser nehmen mit `MediaRecorder` in Opus auf, das Training braucht 16 kHz
Mono-WAV. Die Umwandlung passiert genau hier, mit ffmpeg als einzigem externen
Werkzeug. Die Messungen laufen ohne numpy, allein mit der Standardbibliothek -
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
FENSTER = 320  # 20 ms bei 16 kHz - feinste sinnvolle Auflösung für Pegelverläufe


class AudioFehler(RuntimeError):
    """Umwandlung oder Vermessung ist fehlgeschlagen."""


@dataclass(frozen=True)
class Befund:
    """Messwerte einer Aufnahme. Bewertet werden sie erst in `services/quality.py`.

    Die Felder heißen wie die Spalten von `recordings` in „hören".
    """

    dauer_s: float
    pegel_dbfs: float  # mittlerer Pegel (RMS)
    spitze_dbfs: float
    clipping_anteil: float  # Anteil der Abtastwerte am Anschlag
    stille_vorn_s: float
    stille_hinten_s: float


# Luft vor und hinter der Stimme beim Zuschnitt - Stille kostet das Training
# nichts, ein verschluckter Anlaut das Wort.
RAND_S = 0.15


@dataclass(frozen=True)
class Verlauf:
    """Der Lautstärkeverlauf einer Aufnahme - ein Wert je 20-ms-Fenster.

    Dasselbe Raster, mit dem `untersuche` die Randstille misst - Kurve und
    vorgeschlagene Grenzen kommen aus denselben Zahlen. `werte` und `schwelle`
    sind linear auf den Vollausschlag bezogen (0 bis 1): Eine logarithmische
    Achse machte aus jeder Aufnahme dasselbe zappelnde Band.
    """

    fenster_s: float
    werte: tuple[float, ...]
    schwelle: float
    dauer_s: float


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


def _lies(wav: Path) -> tuple[array.array, int]:
    """Abtastwerte und Rate einer WAV-Datei - die eine Stelle, die sie öffnet."""
    with wave.open(str(wav), "rb") as datei:
        if datei.getsampwidth() != 2 or datei.getnchannels() != 1:
            raise AudioFehler("Erwartet wird mono mit 16 bit - bitte erst umwandeln.")
        abtastrate = datei.getframerate()
        werte = array.array("h")
        werte.frombytes(datei.readframes(datei.getnframes()))

    if not werte:
        raise AudioFehler("Die Aufnahme enthält keine Abtastwerte.")
    return werte, abtastrate


def _fensterpegel(werte: array.array) -> list[float]:
    """Der RMS je 20-ms-Fenster - das Raster, auf dem alles Weitere aufsetzt."""
    return [
        math.sqrt(sum(wert * wert for wert in werte[start : start + FENSTER]) / FENSTER)
        for start in range(0, len(werte) - FENSTER + 1, FENSTER)
    ]


def _schwelle(spitze: float) -> float:
    """Ab wann ein Fenster als Sprache zählt.

    Relativ zur Spitze: absolute Werte wären für leise Sprecher unbrauchbar.
    Nach unten begrenzt, damit Rauschen nicht als Sprache zählt.
    """
    return max(spitze * 10 ** (-35 / 20), VOLLAUSSCHLAG * 10 ** (-60 / 20))


def untersuche(wav: Path) -> Befund:
    """Misst Dauer, Pegel, Clipping und Randstille einer WAV-Datei."""
    werte, abtastrate = _lies(wav)

    spitze = max(max(werte), -min(werte))
    # „Am Anschlag" heißt hier: die obersten 0,1 % des Wertebereichs. Genau
    # 32767 zu prüfen wäre zu streng, weil die Umwandlung leicht rundet.
    am_anschlag = sum(1 for wert in werte if abs(wert) >= 32700)

    # Pegelverlauf in 20-ms-Fenstern; daraus RMS und die Randstille.
    fenster_rms = _fensterpegel(werte) or [float(spitze)]
    gesamt_rms = math.sqrt(sum(r * r for r in fenster_rms) / len(fenster_rms))

    schwelle = _schwelle(spitze)
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


def verlauf(wav: Path) -> Verlauf:
    """Der Lautstärkeverlauf einer Aufnahme, zum Zeichnen und zum Schneiden.

    Dieselbe Rechnung wie in `untersuche`, je Fenster herausgereicht
    (`packages/ui/Pegelverlauf.svelte`). Acht Sekunden ergeben vierhundert
    Werte - fein genug für eine Sprechpause, klein genug für JSON.
    """
    werte, abtastrate = _lies(wav)
    spitze = float(max(max(werte), -min(werte)))
    fenster_rms = _fensterpegel(werte) or [spitze]
    return Verlauf(
        fenster_s=FENSTER / abtastrate,
        werte=tuple(rms / VOLLAUSSCHLAG for rms in fenster_rms),
        schwelle=_schwelle(spitze) / VOLLAUSSCHLAG,
        dauer_s=len(werte) / abtastrate,
    )


def stimmgrenzen(kurve: Verlauf, rand_s: float = RAND_S) -> tuple[float, float]:
    """Wo die Stimme anfängt und aufhört - mit etwas Luft an beiden Enden.

    **Aus dem Pegel, nicht aus einem VAD.** Ein Raum, ein Mikrofon vor dem
    Mund, eine Äußerung - was laut wird, ist diese Person. Ein auf
    durchschnittlicher Sprache trainiertes Modell zu fragen, wo abweichende
    Sprache anfängt, träfe dieselbe Annahme, an der die Diktierfunktion des
    Telefons scheitert; und es brächte torch in den Webprozess.

    Die Grenzen sind ein Vorschlag, den ein Mensch verschiebt. Ohne Fenster
    über der Schwelle ist er die ganze Aufnahme.
    """
    laut = [nummer for nummer, wert in enumerate(kurve.werte) if wert >= kurve.schwelle]
    if not laut:
        return 0.0, kurve.dauer_s
    start = max(0.0, laut[0] * kurve.fenster_s - rand_s)
    ende = min(kurve.dauer_s, (laut[-1] + 1) * kurve.fenster_s + rand_s)
    return start, ende


def dauer(wav: Path) -> float:
    """Wie lang eine WAV-Datei ist, ohne sie zu lesen.

    Aus dem Kopf der Datei, anders als `untersuche`, das jeden Abtastwert
    liest.
    """
    with wave.open(str(wav), "rb") as datei:
        return datei.getnframes() / datei.getframerate()


def schneide_ausschnitt(
    quelle: Path, ziel: Path, start_s: float, ende_s: float, nach_aussen: bool = False
) -> tuple[float, float]:
    """Schreibt den Bereich [start_s, ende_s) einer WAV-Datei in eine neue Datei.

    Für die Abschnitte in „schreiben", für Zuschnitt und Teilung in „hören"
    (`services/zuschnitt.py`). Verlustfrei: Bei 16 kHz mono PCM ist ein
    Schnitt das Kopieren eines Byte-Bereichs, ohne Umkodieren und ohne
    Blenden. Grenzen außerhalb der Datei werden gestutzt - Whisper meldet
    gelegentlich ein Ende hinter dem letzten Abtastwert.

    `nach_aussen` rundet den Anfang ab- und das Ende aufwärts: Ein Rahmen zu
    viel sind 62 Mikrosekunden Stille, einer zu wenig ein angeschnittener
    Abtastwert. Zurück kommen die tatsächlich erreichten Grenzen.
    """
    with wave.open(str(quelle), "rb") as datei:
        rahmen_gesamt = datei.getnframes()
        rate = datei.getframerate()
        # Ohne `nach_aussen` schneidet beides ab.
        ab, auf = (math.floor, math.ceil) if nach_aussen else (int, int)
        von = max(0, min(rahmen_gesamt, ab(start_s * rate)))
        bis = max(von, min(rahmen_gesamt, auf(ende_s * rate)))
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

    return von / rate, bis / rate
