"""Die PIN vor „Meine Daten" — vier Ziffern, ein anderes Bedrohungsmodell.

Nicht dieselbe Rechnung wie beim Zugang (`wortlaut.zugang`): Dort ist das
Geheimnis 160 zufällige Bit, hier vier Ziffern — zehntausend Möglichkeiten,
mit blankem SHA-256 in Sekunden durchprobiert, wäre der Prüfwert je zu sehen.
Das ist hier keine Lücke, sondern die Absicht: Die PIN ist eine zusätzliche
Hürde gegen den Klick aus Versehen (eine Zielperson, die kaum liest, siehe
Grundentscheidung 7), nicht das Schloss selbst — das bleibt der Zugang. Wer
den Zugang eines Sprechers vorlegt, hat also schon die eigentliche Kennung in
der Hand; die PIN schützt nur noch vor der eigenen, unbeabsichtigten Geste.

Trotzdem zeitkonstant verglichen, aus Gewohnheit und weil es nichts kostet —
nicht, weil es hier tragend wäre.
"""

from __future__ import annotations

import hashlib
import secrets

from pydantic import BaseModel, field_validator


def gueltig(pin: str) -> bool:
    return len(pin) == 4 and pin.isdigit()


def pruefwert(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def stimmt(pin: str, gespeichert: str | None) -> bool:
    """Zeitkonstanter Vergleich; None (keine PIN gesetzt) stimmt mit nichts."""
    if not gespeichert:
        return False
    return secrets.compare_digest(pruefwert(pin), gespeichert)


class PinAntwort(BaseModel):
    gesetzt: bool


class PinAenderung(BaseModel):
    """`pin: null` nimmt die PIN wieder weg."""

    pin: str | None = None

    @field_validator("pin")
    @classmethod
    def _vier_ziffern(cls, wert: str | None) -> str | None:
        if wert is not None and not gueltig(wert):
            raise ValueError("Die PIN muss aus genau vier Ziffern bestehen.")
        return wert
