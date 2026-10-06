"""Der Zuschnitt einer Aufnahme: die Datei auf das kürzen, was zählt.

Zwischen Knopfdruck und Stimme liegt Stille, die mittrainiert und mitgemessen
würde. Was geschnitten wird, entscheidet ein Mensch (`api/zuschnitt.py`); hier
steht, was mit der Datei geschieht.

**Ein Zuschnitt überschreibt die Aufnahme.** `recordings.blob` zeigt danach
auf die gekürzte Datei, und die Zeile beschreibt sie - Dauer, Pegel, Stille,
Hinweise. Eine zweite Fassung daneben gibt es nicht, also auch keine Frage,
welche gilt, und kein Zurück. Geschnitten wird verlustfrei: In 16 kHz mono PCM
ist ein Schnitt das Kopieren eines Byte-Bereichs, nach außen gerundet
(`audio.schneide_ausschnitt`, `nach_aussen=True`), ohne Blenden - geschnitten
wird in der Stille.
"""

from __future__ import annotations

import json
import tempfile
import wave
from pathlib import Path

from sqlalchemy import func
from wortlaut import audio as klang
from wortlaut import storage

from ..db.models import Aufnahme, Vorlage
from . import quality


def schneide(
    ablage: storage.Ablage, aufnahme: Aufnahme, vorlage: Vorlage, start_s: float, ende_s: float
) -> klang.Befund:
    """Die Aufnahme auf [start, ende) kürzen und die Zeile nachführen.

    Die Datei wird ersetzt; Dauer, Pegel, Stille und Hinweise kommen aus der
    neuen. Abwandlungen und Messwerte am alten Ton räumt der Aufrufer weg.
    """
    quelle = ablage.pfad(aufnahme.blob)
    if not quelle.is_file():
        raise klang.AudioFehler(f"Audio fehlt: {aufnahme.blob}")
    if not ende_s > start_s:
        raise klang.AudioFehler(
            f"Das Ende muss hinter dem Anfang liegen ({start_s:.2f} bis {ende_s:.2f} s)."
        )

    # Erst daneben schreiben, dann über das Original legen.
    with tempfile.TemporaryDirectory() as verzeichnis:
        entwurf = Path(verzeichnis) / "zuschnitt.wav"
        klang.schneide_ausschnitt(quelle, entwurf, start_s, ende_s, nach_aussen=True)
        befund = klang.untersuche(entwurf)
        ablage.lege_ab(aufnahme.blob, entwurf)

    aufnahme.dauer_s = befund.dauer_s
    aufnahme.pegel_dbfs = befund.pegel_dbfs
    aufnahme.spitze_dbfs = befund.spitze_dbfs
    aufnahme.clipping_anteil = befund.clipping_anteil
    aufnahme.stille_vorn_s = befund.stille_vorn_s
    aufnahme.stille_hinten_s = befund.stille_hinten_s
    aufnahme.hinweise = json.dumps(
        quality.pruefe(befund, vorlage.dauer_geschaetzt_s), ensure_ascii=False
    )
    return befund


def reihenfolge() -> tuple:
    """Wie Aufnahmen der Reihe nach stehen: nach Datum, und bei gleichem Datum
    das Original vor seinen Teilen (`017_teilen.sql`).

    Für `order_by(*zuschnitt.reihenfolge())`; absteigend stehen die Teile vor
    dem Original, aber beieinander.
    """
    return (Aufnahme.erstellt, func.coalesce(Aufnahme.sortierschluessel, Aufnahme.id))


def stamm(aufnahme: Aufnahme) -> str:
    """Die Aufnahme, aus der diese hervorging - bei einer gewöhnlichen sie selbst.

    Teile und Kopien aus „Editieren" sind derselbe Ton; wo es um unabhängige
    Prüfstücke geht - Faltungen, die Auswertung eines Standes -, zählt die
    Verwandtschaft als eine. Abzulesen am Sortierschlüssel: `rec_A.1.2`
    stammt aus `rec_A`, auch wenn `rec_A` gelöscht ist.
    """
    return (aufnahme.sortierschluessel or aufnahme.id).split(".", 1)[0]


def teile(
    ablage: storage.Ablage,
    aufnahme: Aufnahme,
    start_s: float,
    teilung_s: float,
    ende_s: float,
    ziel_vorn: str,
    ziel_hinten: str,
) -> tuple[klang.Befund, klang.Befund]:
    """Aus dem Original zwei Dateien schneiden: [start, teilung) und [teilung, ende).

    Außen wird nach außen gerundet, die Teilung sitzt auf genau einem Rahmen - aneinandergelegt ergeben die Teile Byte für Byte den
    Bereich des Originals.

    Gibt die Befunde beider Teile zurück; abgelegt ist danach beides.
    """
    quelle = ablage.pfad(aufnahme.blob)
    if not quelle.is_file():
        raise klang.AudioFehler(f"Audio fehlt: {aufnahme.blob}")
    if not start_s < teilung_s < ende_s:
        raise klang.AudioFehler(
            "Die Teilung muss zwischen Anfang und Ende liegen "
            f"({start_s:.2f} < {teilung_s:.2f} < {ende_s:.2f} s)."
        )
    with wave.open(str(quelle), "rb") as datei:
        rate = datei.getframerate()
    # Ein Viertelrahmen hinter der Grenze: `int` und `floor` landen beide auf
    # demselben Rahmen, keine Gleitkommazahl kippt einen auf den Nachbarn.
    innen = (round(teilung_s * rate) + 0.25) / rate

    with tempfile.TemporaryDirectory() as verzeichnis:
        vorn = Path(verzeichnis) / "vorn.wav"
        hinten = Path(verzeichnis) / "hinten.wav"
        klang.schneide_ausschnitt(quelle, vorn, start_s, innen)
        klang.schneide_ausschnitt(quelle, hinten, innen, ende_s, nach_aussen=True)
        befunde = (klang.untersuche(vorn), klang.untersuche(hinten))
        ablage.lege_ab(ziel_vorn, vorn)
        ablage.lege_ab(ziel_hinten, hinten)
    return befunde


def kopiere(
    ablage: storage.Ablage, aufnahme: Aufnahme, start_s: float, ende_s: float, ziel: str
) -> klang.Befund:
    """Einen Ausschnitt des Originals als eigene Datei ablegen - ein Teil allein.

    Für „Editieren", wenn die Teilung auf Anfang oder Ende liegt.
    """
    quelle = ablage.pfad(aufnahme.blob)
    if not quelle.is_file():
        raise klang.AudioFehler(f"Audio fehlt: {aufnahme.blob}")
    if not ende_s > start_s:
        raise klang.AudioFehler(
            f"Das Ende muss hinter dem Anfang liegen ({start_s:.2f} bis {ende_s:.2f} s)."
        )
    with tempfile.TemporaryDirectory() as verzeichnis:
        entwurf = Path(verzeichnis) / "kopie.wav"
        klang.schneide_ausschnitt(quelle, entwurf, start_s, ende_s, nach_aussen=True)
        befund = klang.untersuche(entwurf)
        ablage.lege_ab(ziel, entwurf)
    return befund
