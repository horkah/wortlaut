"""Der Zuschnitt einer Aufnahme - und die eine Regel, welche Datei gilt.

Zwischen Knopfdruck und Stimme liegt Stille, die mittrainiert und mitgemessen
würde. Was geschnitten wird, entscheidet ein Mensch (`api/zuschnitt.py`); hier
steht, was mit den Dateien geschieht.

**Die Regel** (`arbeitsblob`): Gibt es einen Zuschnitt, gilt er, sonst das
Original. Jeder Weg, der Audio anfasst, fragt hier - Anhören, Abwandlungen,
Auswertung, Trainingsmanifest, Datensatz. Ein Schalter daneben ließe jemanden
auf einer Datei trainieren, die er in der Ansicht nicht hört.

**Das Original bleibt**, `recordings.blob` zeigt darauf, und ein Zuschnitt
lässt sich zurücknehmen. Geschnitten wird verlustfrei: In 16 kHz mono PCM ist
ein Schnitt das Kopieren eines Byte-Bereichs, nach außen gerundet
(`audio.schneide_ausschnitt`, `nach_aussen=True`), ohne Blenden - geschnitten
wird in der Stille.
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

from sqlalchemy import func
from wortlaut import audio as klang
from wortlaut import corpus, storage

from ..db.models import Aufnahme


def hat_zuschnitt(aufnahme: Aufnahme) -> bool:
    """Ob zu dieser Aufnahme ein Zuschnitt eingetragen ist."""
    return aufnahme.zuschnitt_start_s is not None and aufnahme.zuschnitt_ende_s is not None


def zuschnitt_blob(aufnahme: Aufnahme) -> str:
    """Wo der Zuschnitt dieser Aufnahme liegt - ob er schon da ist oder nicht."""
    return corpus.zuschnitt_relpfad(aufnahme.speaker_id, aufnahme.id)


def arbeitsblob(aufnahme: Aufnahme) -> str:
    """**Die Regel.** Die Datei, mit der überall gearbeitet wird.

    Aus der Zeile, nicht von der Platte. Fehlt die eingetragene Datei, ist
    das ein Fehler und kein stiller Rückfall auf das Original.
    """
    return zuschnitt_blob(aufnahme) if hat_zuschnitt(aufnahme) else aufnahme.blob


def arbeitsdauer(aufnahme: Aufnahme) -> float:
    """Wie lang die Arbeitsdatei ist - gerechnet, nicht gespeichert.

    `recordings.dauer_s` bleibt die Dauer des Originals.
    """
    if not hat_zuschnitt(aufnahme):
        return aufnahme.dauer_s
    return aufnahme.zuschnitt_ende_s - aufnahme.zuschnitt_start_s


def schneide(
    ablage: storage.Ablage, aufnahme: Aufnahme, start_s: float, ende_s: float
) -> tuple[float, float]:
    """Den Zuschnitt schreiben und die Grenzen in die Zeile eintragen.

    Ein zweiter Schnitt ersetzt den ersten. Geschnitten wird immer aus dem
    Original, sonst wanderte die Grenze nach innen. Eingetragen werden die
    tatsächlich erreichten Grenzen.
    """
    quelle = ablage.pfad(aufnahme.blob)
    if not quelle.is_file():
        raise klang.AudioFehler(f"Audio fehlt: {aufnahme.blob}")
    if not ende_s > start_s:
        raise klang.AudioFehler(
            f"Das Ende muss hinter dem Anfang liegen ({start_s:.2f} bis {ende_s:.2f} s)."
        )

    # Erst daneben schreiben, dann ablegen.
    with tempfile.TemporaryDirectory() as verzeichnis:
        entwurf = Path(verzeichnis) / "zuschnitt.wav"
        erreicht = klang.schneide_ausschnitt(quelle, entwurf, start_s, ende_s, nach_aussen=True)
        ablage.lege_ab(zuschnitt_blob(aufnahme), entwurf)

    aufnahme.zuschnitt_start_s, aufnahme.zuschnitt_ende_s = erreicht
    return erreicht


def nimm_zurueck(ablage: storage.Ablage, aufnahme: Aufnahme) -> bool:
    """Den Zuschnitt verwerfen; ab dann gilt wieder das Original.

    Gibt zurück, ob es etwas zurückzunehmen gab; die Datei geht mit.
    """
    if not hat_zuschnitt(aufnahme):
        return False
    ablage.loesche(zuschnitt_blob(aufnahme))
    aufnahme.zuschnitt_start_s = None
    aufnahme.zuschnitt_ende_s = None
    return True


def stelle_her(ablage: storage.Ablage, aufnahme: Aufnahme) -> bool:
    """Eine fehlende Zuschnittdatei aus dem Original und den Grenzen nachrechnen.

    Der Zuschnitt wird mitgesichert und ist gewöhnlich da; für ein halb
    kopiertes Verzeichnis ruft die Zuschnittansicht dies beim Auflisten. Das
    Ergebnis ist Byte für Byte dasselbe.
    """
    if not hat_zuschnitt(aufnahme) or ablage.pfad(zuschnitt_blob(aufnahme)).is_file():
        return False
    schneide(ablage, aufnahme, aufnahme.zuschnitt_start_s, aufnahme.zuschnitt_ende_s)
    return True


def loesche(ablage: storage.Ablage, aufnahme: Aufnahme) -> None:
    """Die zugeschnittene Fassung entfernen. Das Original bleibt unangetastet.

    Für die Löschwege, die das Original selbst anfassen.
    """
    ablage.loesche(zuschnitt_blob(aufnahme))


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

    Aus dem Original, dessen Kurve die Ansicht zeigt; ein vorhandener Zuschnitt
    spielt keine Rolle. Außen wird nach außen gerundet, die Teilung sitzt auf
    genau einem Rahmen - aneinandergelegt ergeben die Teile Byte für Byte den
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
