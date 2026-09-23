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
    """Messwerte einer Aufnahme. Bewertet werden sie erst in `services/quality.py`."""

    dauer_s: float
    pegel_dbfs: float  # mittlerer Pegel (RMS)
    spitze_dbfs: float
    clipping_anteil: float  # Anteil der Abtastwerte am Anschlag
    stille_vorn_s: float
    stille_hinten_s: float


# Wie viel Luft ein Zuschnitt vor und hinter der Stimme lässt. Lieber ein
# Zehntel zu viel als eine abgeschnittene Silbe: Ein paar Hundertstel Stille
# kosten das Training nichts, ein verschluckter Anlaut kostet es das Wort.
RAND_S = 0.15


@dataclass(frozen=True)
class Verlauf:
    """Der Lautstärkeverlauf einer Aufnahme - ein Wert je 20-ms-Fenster.

    Dasselbe Raster, mit dem `untersuche` die Randstille misst, nur
    herausgereicht statt zusammengefasst: Die Zuschnittansicht zeichnet
    daraus ihre Kurve, und die Stimmgrenzen fallen aus denselben Zahlen ab
    (`stimmgrenzen`). Zwei Raster für dieselbe Aufnahme hießen, dass die
    gezeichnete Kurve und die eingezeichnete Grenze aus verschiedenen
    Rechnungen kämen - und dann liegt die Linie neben dem Ausschlag.

    `werte` und `schwelle` sind auf den Vollausschlag bezogen (0 bis 1) und
    nicht in dBFS: Eine Kurve wird gezeichnet, nicht gelesen, und eine
    logarithmische Achse macht aus jeder Aufnahme dasselbe zappelnde Band.
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

    Dieselbe Rechnung wie in `untersuche`, nur nicht zu vier Zahlen
    zusammengefasst: Die Zuschnittansicht braucht die Fenster selbst, um daraus
    eine Kurve zu zeichnen (`packages/ui/Pegelverlauf.svelte`).

    Eine Aufnahme von acht Sekunden ergibt vierhundert Werte. Das ist wenig
    genug, um es als JSON zu schicken, und fein genug, um eine Sprechpause zu
    sehen - gröber wäre eine Kurve, in der eine Silbe verschwindet, feiner
    wären mehr Punkte, als ein Bild breit ist.
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

    **Warum aus dem Pegel und nicht aus einem Sprachmodell.** Ein VAD wie
    Silero erkennt Sprache und nicht bloß Lautstärke, und bei einer
    Tonaufnahme mit Hintergrundgeräuschen wäre das der bessere Weg. Hier ist
    die Lage eine andere: Aufgenommen wird äußerungsweise, in einem Raum, mit
    einem Mikrofon vor dem Mund - was zwischen Anfang und Ende laut wird, ist
    diese eine Person. Dafür einen halben Gigabyte Torch in den Web-Prozess zu
    holen, wäre der Preis für eine Unterscheidung, die hier nicht ansteht.

    Dazu kommt ein zweiter Grund, und der wiegt schwerer: wortlaut ist für
    Menschen gebaut, deren Aussprache von der Norm abweicht (siehe README). Ein
    Modell, das auf durchschnittlicher Sprache gelernt hat, zu fragen, wo hier
    Sprache anfängt, hieße dieselbe Annahme noch einmal zu treffen, an der die
    Diktierfunktion des Telefons bereits scheitert. Ein Pegel ist ein Pegel.

    **Was daraus folgt.** Die Grenzen sind ein Vorschlag, kein Befund - die
    Ansicht zeigt sie als zwei Linien, die sich mit Finger oder Maus
    verschieben lassen. Findet sich kein Fenster über der Schwelle, ist der
    Vorschlag die ganze Aufnahme: Lieber nichts vorschlagen als etwas
    wegschneiden.
    """
    laut = [nummer for nummer, wert in enumerate(kurve.werte) if wert >= kurve.schwelle]
    if not laut:
        return 0.0, kurve.dauer_s
    start = max(0.0, laut[0] * kurve.fenster_s - rand_s)
    ende = min(kurve.dauer_s, (laut[-1] + 1) * kurve.fenster_s + rand_s)
    return start, ende


def dauer(wav: Path) -> float:
    """Wie lang eine WAV-Datei ist, ohne sie zu lesen.

    `untersuche` weiß das auch, liest dafür aber jeden Abtastwert und rechnet
    Pegel, Clipping und Randstille mit. Wer nur wissen will, wie weit die
    Aufnahme reicht - etwa um eine Zeitmarke daran zu messen -, bekommt es hier
    aus dem Kopf der Datei.
    """
    with wave.open(str(wav), "rb") as datei:
        return datei.getnframes() / datei.getframerate()


def schneide_ausschnitt(
    quelle: Path, ziel: Path, start_s: float, ende_s: float, nach_aussen: bool = False
) -> tuple[float, float]:
    """Schreibt den Bereich [start_s, ende_s) einer WAV-Datei in eine neue Datei.

    Gebraucht von „schreiben": Whisper liefert Abschnittsgrenzen, und jeder
    Abschnitt braucht sein eigenes Audio - er kann einzeln neu eingesprochen
    werden und geht einzeln als Korrekturpaar an „hören". Und von „hören", wenn
    jemand die Stille an den Rändern einer Aufnahme wegschneidet
    (`services/zuschnitt.py`).

    Reine Standardbibliothek und ohne Umkodieren: ein Schnitt an
    Rahmengrenzen ist das Kopieren eines Byte-Bereichs. Grenzen außerhalb der
    Datei werden auf sie zurechtgestutzt, statt zu scheitern - Whisper meldet
    gelegentlich ein Ende hinter dem letzten Abtastwert.

    **Verlustfrei heißt hier wirklich verlustfrei.** Bei 16 kHz mono PCM ist
    ein Rahmen zwei Byte, und zwei Byte sind zugleich der kleinste Block, an
    dem sich schneiden lässt. Was hier herauskommt, ist Abtastwert für
    Abtastwert dasselbe wie im Original - kein Umkodieren, keine Ein- und
    Ausblendung, kein Generationsverlust. Mit einem komprimierten Format wäre
    das anders; deshalb liegt der Korpus in PCM (siehe `wandle_in_wav`).

    `nach_aussen` rundet den Anfang ab- und das Ende aufwärts auf den nächsten
    Rahmen, statt beide abzuschneiden. Beim Zuschneiden ist das die richtige
    Richtung: Ein Rahmen zu viel sind 62 Mikrosekunden Stille, ein Rahmen zu
    wenig ist ein angeschnittener Abtastwert. Zurück kommen die Grenzen, die
    dabei wirklich erreicht wurden - wer sie aufbewahrt, bewahrt auf, was in
    der Datei steht, und nicht, was jemand gewünscht hat.
    """
    with wave.open(str(quelle), "rb") as datei:
        rahmen_gesamt = datei.getnframes()
        rate = datei.getframerate()
        # Ohne `nach_aussen` schneidet beides ab - das Verhalten, auf das sich
        # „schreiben" seit jeher verlässt.
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
