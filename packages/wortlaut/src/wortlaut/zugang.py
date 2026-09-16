"""Der Zugang zu einem Sprecher - zugleich seine Kennung.

Diese Datei liegt in der Bibliothek und nicht in einer App, weil zwei Apps
denselben Zugang lesen: „hören" gibt ihn aus und prüft ihn am eigenen Korpus,
„schreiben" legt seine Diktate unter demselben Sprecher ab und muss dieselbe
Kennung aus demselben Token ableiten. Zwei Auslegungen desselben Formats wären
zwei Gelegenheiten, sie auseinanderlaufen zu lassen.

Ein Zugang sieht so aus::

    spr_01J8ZQ…8K.7f2ac1…                 <sprecher_id>.<geheimnis>

Er trägt die Kennung sichtbar vor sich her, und genau das ist der Zweck: Der
Server spaltet am Punkt, öffnet **die** Datenbank dieses Sprechers und prüft
dort den Prüfwert des Geheimnisses. Die Kennung ist damit abgeleitet und nicht
behauptet, und der Nachschlag geht auf dieselbe Datei, die die Anfrage ohnehin
öffnet - kein Durchsuchen aller Sprecher.

Dass die Kennung offen dasteht, kostet nichts: Wer sie in einen fremden Zugang
schreibt, dessen Geheimnis passt dort nicht, und die Antwort ist 401.

Gespeichert wird nur der Prüfwert. Ein einfacher SHA-256 genügt dafür - anders
als ein Passwort ist das Geheimnis kein gemerktes Wort, sondern 160 Bit aus
`os.urandom`; ein Wörterbuchangriff hat daran nichts zu holen.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from . import corpus, sprachen

TRENNER = "."
PRAEFIX = "spr_"
GEHEIMNIS_BYTES = 20


def erzeuge(sprecher_id: str) -> tuple[str, str]:
    """Ein neuer Zugang: `(zugang, pruefwert)`.

    Der Zugang geht einmal an den Menschen, der Prüfwert in die Datenbank. Ein
    zweites Mal ist der Zugang nirgends zu haben - verloren heißt ersetzen.
    """
    geheimnis = secrets.token_urlsafe(GEHEIMNIS_BYTES)
    return f"{sprecher_id}{TRENNER}{geheimnis}", pruefwert(geheimnis)


def pruefwert(geheimnis: str) -> str:
    return hashlib.sha256(geheimnis.encode("utf-8")).hexdigest()


def zerlege(vorgelegt: str) -> tuple[str, str] | None:
    """`(sprecher_id, geheimnis)` - oder None, wenn das kein Sprecherzugang ist.

    Die Form entscheidet, nicht der Inhalt: Nur so lässt sich ein
    Sprecherzugang von einem Verwaltertoken unterscheiden, ohne beide gegen
    jede Datenbank zu halten.
    """
    sprecher_id, _, geheimnis = vorgelegt.partition(TRENNER)
    if not geheimnis or not sprecher_id.startswith(PRAEFIX):
        return None
    return sprecher_id, geheimnis


def stimmt(geheimnis: str, gespeichert: str | None) -> bool:
    """Zeitkonstanter Vergleich; None (zurückgezogen) stimmt mit nichts."""
    if not gespeichert:
        return False
    return secrets.compare_digest(pruefwert(geheimnis), gespeichert)


@dataclass(frozen=True)
class Sprecherzugang:
    """Wer ein vorgelegter Zugang ist: Kennung, Name und Sprache aus dem Korpus.

    **Warum die Sprache hier mitkommt.** Sie steht am Profil und gilt für
    alles, was daran hängt (`wortlaut/sprachen.py`). Wer sie braucht - „lernen"
    für den Trainingsauftrag, „schreiben" für das Diktat -, hat den Korpus des
    Sprechers ohnehin gerade offen: Diese Prüfung liest die Zeile bereits. Sie
    ein zweites Mal zu holen wäre eine zweite Abfrage für eine Auskunft, die
    schon auf dem Tisch liegt - und eine zweite Stelle, an der jemand den
    Rückfall auf Deutsch hinschreiben könnte.
    """

    sprecher_id: str
    name: str
    sprache: str


def pruefe(datenverzeichnis: Path, vorgelegt: str) -> Sprecherzugang | None:
    """Den Sprecher zu einem vorgelegten Zugang - oder None, wenn er nicht gilt.

    Der Nachschlag geht lesend in die Korpusdatenbank des Sprechers, dessen
    Kennung der Zugang vor sich herträgt: eine Datei, kein Durchsuchen. Das ist
    derselbe Weg, den „hören" in seiner `deps.py` geht - dort mit der ohnehin
    offenen Sitzung, hier ohne, weil „schreiben" den Korpus nur lesen darf und
    keinen Schreiber darauf öffnen soll (Grundentscheidung 6). `mode=ro` hält
    das fest: Diese Verbindung kann nicht schreiben, auch nicht aus Versehen.

    Ein unbekannter Sprecher, eine fehlende Datei und ein falsches Geheimnis
    sind bewusst dasselbe Ergebnis. Wer hier ein „gibt es nicht" von einem
    „stimmt nicht" unterscheiden könnte, könnte Kennungen abklopfen.
    """
    teile = zerlege(vorgelegt)
    if teile is None:
        return None
    sprecher_id, geheimnis = teile

    pfad = corpus.datenbank_pfad(datenverzeichnis, sprecher_id)
    if not pfad.is_file():
        return None
    try:
        with sqlite3.connect(f"file:{pfad}?mode=ro", uri=True) as verbindung:
            zeile = verbindung.execute(
                "SELECT name, zugang_hash, sprache FROM speakers WHERE id = ?",
                (sprecher_id,),
            ).fetchone()
    except sqlite3.Error:
        # Eine Datenbank, die es noch nicht gibt oder gerade angelegt wird, ist
        # kein Fehler dieser Anfrage - sie ist ein Zugang, der nicht gilt.
        return None

    if zeile is None or not stimmt(geheimnis, zeile[1]):
        return None
    # Die Spalte ist `NOT NULL DEFAULT 'de'` (001_init.sql), also steht dort
    # immer etwas - der Rückfall gilt einer Datenbank, die älter ist als diese
    # Zeile, und nicht dem Normalfall.
    return Sprecherzugang(
        sprecher_id=sprecher_id,
        name=zeile[0] or "",
        sprache=zeile[2] or sprachen.VORGABE,
    )
