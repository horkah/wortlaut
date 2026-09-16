"""Transkription - zwei austauschbare Umsetzungen hinter einem Protokoll.

GPU-Arbeit läuft nie im Web-Prozess (Grundentscheidung 5): `local` lädt
faster-whisper in den eigenen Prozess, `remote` spricht einen
OpenAI-kompatiblen Endpunkt an. Genutzt wird das von der App „schreiben"; die
Schnittstelle steht hier, weil sie zum geteilten Vertrag gehört.

Beide Umsetzungen importieren ihre Abhängigkeiten erst beim Aufruf - „hören"
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
    """Was ein Erkenner können muss - eine Frage, und sie nennt die Sprache.

    `sprache` hat bewusst **keine** Vorgabe. Hier stand einmal `= "de"`, und
    das war die bequemste der achtzehn Stellen, an denen Deutsch im Quelltext
    festsaß: Ein Aufrufer, der die Sprache nicht kennt, bekam stillschweigend
    die richtige Antwort - solange alle Deutsch sprechen. Ohne Vorgabe muss
    jeder Aufrufer sagen, für wen er hört, und ein Aufrufer, der es nicht
    weiß, fällt beim Übersetzen auf und nicht erst im Ergebnis
    (`wortlaut/sprachen.py`).
    """

    def transkribiere(self, wav: Path, sprache: str) -> Transkript: ...


__all__ = ["Abschnitt", "Transkript", "Transkriptor"]
