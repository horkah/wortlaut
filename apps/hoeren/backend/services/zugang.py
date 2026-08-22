"""Der Zugang zu einem Sprecher — zugleich seine Kennung.

Ein Zugang sieht so aus::

    spr_01J8ZQ…8K.7f2ac1…                 <sprecher_id>.<geheimnis>

Er trägt die Kennung sichtbar vor sich her, und genau das ist der Zweck: Der
Server spaltet am Punkt, öffnet **die** Datenbank dieses Sprechers und prüft
dort den Prüfwert des Geheimnisses. Die Kennung ist damit abgeleitet und nicht
behauptet, und der Nachschlag geht auf dieselbe Datei, die die Anfrage ohnehin
öffnet — kein Durchsuchen aller Sprecher.

Dass die Kennung offen dasteht, kostet nichts: Wer sie in einen fremden Zugang
schreibt, dessen Geheimnis passt dort nicht, und die Antwort ist 401.

Gespeichert wird nur der Prüfwert. Ein einfacher SHA-256 genügt dafür — anders
als ein Passwort ist das Geheimnis kein gemerktes Wort, sondern 160 Bit aus
`os.urandom`; ein Wörterbuchangriff hat daran nichts zu holen.
"""

from __future__ import annotations

import hashlib
import secrets

TRENNER = "."
PRAEFIX = "spr_"
GEHEIMNIS_BYTES = 20


def erzeuge(sprecher_id: str) -> tuple[str, str]:
    """Ein neuer Zugang: `(zugang, pruefwert)`.

    Der Zugang geht einmal an den Menschen, der Prüfwert in die Datenbank. Ein
    zweites Mal ist der Zugang nirgends zu haben — verloren heißt ersetzen.
    """
    geheimnis = secrets.token_urlsafe(GEHEIMNIS_BYTES)
    return f"{sprecher_id}{TRENNER}{geheimnis}", pruefwert(geheimnis)


def pruefwert(geheimnis: str) -> str:
    return hashlib.sha256(geheimnis.encode("utf-8")).hexdigest()


def zerlege(vorgelegt: str) -> tuple[str, str] | None:
    """`(sprecher_id, geheimnis)` — oder None, wenn das kein Sprecherzugang ist.

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
