"""Was mit einer Aufnahme geschieht, bevor ein Modell sie hört - an einer Stelle.

Zwei Griffe gibt es: die Ränder abschneiden (`stille.py`) und schneller
abspielen (`tempo.py`). Beide hängen am Modellstand und nicht am Aufrufer, und
beide müssen **überall gleich** ausfallen - im Training, in der Auswertung von
„hören" und beim Diktieren in „schreiben".

**Warum sie hier zusammenkommen.** Nicht der Sparsamkeit wegen, sondern weil
ihre Reihenfolge eine Entscheidung ist. Erst schneiden, dann vorspulen ergibt
etwas anderes als umgekehrt: Die Stilleschwelle liegt relativ zur Spitze der
Aufnahme, und ein Phasenvokoder verändert die Hüllkurve. Der Unterschied ist
klein und genau deshalb gefährlich - vier Aufrufer, die ihn vier Mal selbst
entscheiden, entscheiden ihn irgendwann verschieden, und ein Modell bekäme beim
Diktieren etwas minimal anderes zu hören als beim Lernen. Niemand sähe je,
woran es lag.

Die Reihenfolge ist: **erst schneiden, dann vorspulen.** Geschnitten wird an
der Aufnahme, wie sie gesprochen wurde - an ihrem eigenen Pegel und ihrer
eigenen Spitze. Was danach kommt, ist eine Rechnung auf dem Ausschnitt und
ändert nichts mehr daran, wo er anfängt.
"""

from __future__ import annotations

from pathlib import Path

from . import audio, stille, tempo


def aus_manifest(manifest: dict | None) -> tuple[float, bool]:
    """Wie dieser Stand gehört werden will: `(faktor, schneiden)`.

    **Die eine Stelle, an der ein Manifest darüber befragt wird.** „hören"
    misst damit, „schreiben" diktiert damit, und beide bekommen dieselbe
    Antwort - auch für die Felder, die ein altes Manifest nicht hat: kein
    Vorspulen, kein Schneiden. Ein Grundmodell (`None`) wird gar nicht
    vorbereitet; die Auswertung ist die Baseline und misst den Ausgangszustand
    (`012_ohne_profiltempo.sql`).
    """
    if not manifest:
        return tempo.VORGABE, False
    return float(manifest.get("tempo", tempo.VORGABE)), stille.gilt(manifest.get("stille"))


def marke(faktor: float, schneiden: bool) -> str:
    """Wie ein vorbereiteter Ausschnitt heißt: `2x`, `1x-geschnitten`.

    Damit legt ein Aufrufer, der Ergebnisse aufhebt, sie je Zustand getrennt
    ab. Ohne das fände ein Lauf, der bei jeder Faltung neu über die
    Geschwindigkeit entscheidet, die Datei der Faltung davor vor - und lernte
    auf einem Faktor, der in keinem Protokoll steht (`training/finetune.py`).
    """
    return tempo.marke(faktor) + ("-geschnitten" if stille.gilt(schneiden) else "")


def noetig(faktor: float, schneiden: bool) -> bool:
    """Ob überhaupt eine zweite Datei entstehen kann.

    Für den Aufrufer, der eine Ablage bereitstellen muss, bevor er weiß, ob sie
    gebraucht wird. `True` heißt „womöglich" und nicht „bestimmt": Ob sich das
    Schneiden lohnt, steht erst nach dem Messen fest (`stille.grenzen`).
    """
    return tempo.vorspulen_noetig(faktor) or stille.gilt(schneiden)


def bereite_vor(
    quelle: Path, ablage: Path, *, faktor: float = tempo.VORGABE, schneiden: bool = False
) -> tuple[Path, float]:
    """Die Datei, die das Modell hören soll - und was vorn fehlt.

    Gibt `(quelle, 0.0)` zurück, wenn nichts zu tun war; dann entsteht keine
    Datei. Sonst liegt das Ergebnis unter `ablage`, und der Pfad dorthin kommt
    zurück.

    **Der zweite Wert ist der Versatz in Sekunden der Originalaufnahme.** Wer
    nur einen Text vergleicht - der Trainer, die Auswertung - braucht ihn
    nicht. Wer Zeitmarken zurückrechnet, braucht ihn unbedingt: „schreiben"
    schneidet das Diktat an den Grenzen, die Whisper meldet, und die zählen ab
    dem Anfang dessen, was Whisper gehört hat. Fehlt dort der Versatz, liegt
    jeder Abschnitt um die weggeschnittene Stille daneben - und zwar leise, denn
    der Text stimmt ja.

    `ablage` ist ein Verzeichnis und keine Datei: Zwischen den beiden Griffen
    kann ein Zwischenstand liegen, und wo der hingehört, entscheidet nicht der
    Aufrufer.

    **Und `ablage` gehört diesem Aufruf allein.** Die Namen darin sind fest -
    `geschnitten.wav`, `vorgespult.wav` -, denn ein Verzeichnis für eine
    Aufnahme braucht keine eindeutigen Namen. Wer dasselbe Verzeichnis für
    mehrere Aufnahmen hergibt und nebenläufig arbeitet, sieht seine Dateien
    einander unter den Händen wegnehmen (so geschehen im Trainer, der mit
    mehreren Fäden lädt - siehe `training/daten.py`).
    """
    ergebnis, versatz_s = quelle, 0.0
    if stille.gilt(schneiden):
        geschnitten = ablage / "geschnitten.wav"
        bereich = stille.grenzen(ergebnis)
        if bereich is not None:
            audio.schneide_ausschnitt(ergebnis, geschnitten, *bereich)
            ergebnis, versatz_s = geschnitten, bereich[0]
    if tempo.vorspulen_noetig(faktor):
        schnell = ablage / "vorgespult.wav"
        tempo.spule_vor(ergebnis, schnell, faktor)
        ergebnis = schnell
    return ergebnis, versatz_s
