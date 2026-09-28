"""Transkription - zwei austauschbare Umsetzungen hinter einem Protokoll.

`local` lädt faster-whisper in den eigenen Prozess, auf der Karte, wenn eine
da ist (`rechenwerk.py`); `remote` spricht einen OpenAI-kompatiblen Endpunkt
an. Beide importieren ihre Abhängigkeiten erst beim Aufruf.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Abschnitt:
    """Ein vorlesbarer Ausschnitt mit seiner Lage in der Aufnahme."""

    start_s: float
    ende_s: float
    text: str


@dataclass(frozen=True)
class Transkript:
    text: str
    abschnitte: list[Abschnitt]
    # Die mittlere Wahrscheinlichkeit der erzeugten Marken, 0 bis 1 - wie
    # sicher das Modell war. `None`, wo die Umsetzung es nicht sagt.
    sicherheit: float | None = None


class Transkriptor(Protocol):
    """Was ein Erkenner können muss.

    `sprache` hat keine Vorgabe: Jeder Aufrufer sagt, für wen er hört - die
    Sprache des Profils (`wortlaut/sprachen.py`).
    """

    def transkribiere(self, wav: Path, sprache: str) -> Transkript: ...


__all__ = ["Abschnitt", "Transkript", "Transkriptor"]
