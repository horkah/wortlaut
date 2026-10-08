"""Der Zugang zu einem Sprecher - zugleich seine Kennung.

In der Bibliothek, weil alle drei Apps denselben Zugang auslegen.

Ein Zugang sieht so aus::

    spr_01J8ZQ…8K.7f2ac1…                 <sprecher_id>.<geheimnis>

Der Server spaltet am Punkt, öffnet die Datenbank dieses Sprechers und prüft
dort den Prüfwert des Geheimnisses: Die Kennung ist abgeleitet, nicht
behauptet, und nachgeschlagen wird in genau einer Datei. Wer die offene
Kennung in einen fremden Zugang schreibt, scheitert am Geheimnis.

Gespeichert wird nur ein SHA-256 - das Geheimnis ist kein gemerktes Wort,
sondern 160 Bit Zufall, gegen die kein Wörterbuch hilft.
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


def aus_kopf(authorization: str | None) -> str:
    """Das Vorgelegte aus `Authorization: Bearer …` - leer, wenn nichts kam."""
    return (authorization or "").removeprefix("Bearer ")


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

    Die Sprache kommt mit, weil die Prüfung die Zeile ohnehin liest - „lernen"
    braucht sie für den Auftrag, „schreiben" für das Diktat.
    """

    sprecher_id: str
    name: str
    sprache: str


def pruefe(datenverzeichnis: Path, vorgelegt: str) -> Sprecherzugang | None:
    """Den Sprecher zu einem vorgelegten Zugang - oder None, wenn er nicht gilt.

    Gelesen wird mit `mode=ro`: „lernen" und „schreiben" dürfen den Korpus nur
    lesen (Grundentscheidung 6). Ein unbekannter Sprecher, eine fehlende Datei
    und ein falsches Geheimnis sind dasselbe Ergebnis - sonst ließen sich
    Kennungen abklopfen.
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
    return Sprecherzugang(
        sprecher_id=sprecher_id,
        name=zeile[0] or "",
        sprache=zeile[2] or sprachen.VORGABE,
    )


def verlange_sprecher(datenverzeichnis: Path, authorization: str | None) -> Sprecherzugang:
    """Der Wächter von „lernen" und „schreiben": nur ein gültiger Sprecherzugang, sonst 401.

    Ein Verwalter- oder Aufsichtstoken soll nicht wie ein abgelaufener
    persönlicher Link klingen; die Form entscheidet das ohne Datenbank.
    """
    from fastapi import HTTPException

    vorgelegt = aus_kopf(authorization)
    if zerlege(vorgelegt) is None:
        raise HTTPException(
            status_code=401, detail="Für diesen Weg braucht es den Zugang eines Sprechers."
        )
    wer = pruefe(datenverzeichnis, vorgelegt)
    if wer is None:
        raise HTTPException(status_code=401, detail="Dieser Zugang gilt nicht mehr.")
    return wer
