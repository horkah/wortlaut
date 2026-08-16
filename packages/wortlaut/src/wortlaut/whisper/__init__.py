"""Transkription — zwei austauschbare Umsetzungen hinter einem Protokoll.

GPU-Arbeit läuft nie im Web-Prozess (Grundentscheidung 5): `local` lädt
faster-whisper in den eigenen Prozess, `remote` spricht einen
OpenAI-kompatiblen Endpunkt an. Genutzt wird das von der App „schreiben"; die
Schnittstelle steht hier, weil sie zum geteilten Vertrag gehört.

Beide Umsetzungen importieren ihre Abhängigkeiten erst beim Aufruf — „hören"
zieht dadurch weder Modelle noch HTTP-Clients mit.
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


class Transkriptor(Protocol):
    def transkribiere(self, wav: Path, sprache: str = "de") -> Transkript: ...


__all__ = ["Abschnitt", "Transkript", "Transkriptor"]
