"""Die PIN vor „Meine Daten" - vier Ziffern, ein anderes Bedrohungsmodell.

Vier Ziffern mit blankem SHA-256 wären in Sekunden durchprobiert, läge der
Prüfwert je offen. Das ist Absicht: Die PIN ist eine Hürde gegen den Klick aus
Versehen (Grundentscheidung 7), das Schloss bleibt der Zugang. Zeitkonstant
verglichen wird trotzdem, weil es nichts kostet.
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
