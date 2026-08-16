"""Transkription im eigenen Prozess über faster-whisper (CTranslate2).

Erwartet ein für faster-whisper exportiertes Modellverzeichnis, also den
`ct2/`-Ordner eines Modellstands aus der Registry.
"""

from __future__ import annotations

from pathlib import Path

from . import Abschnitt, Transkript


class LokalerTranskriptor:
    def __init__(
        self, modellverzeichnis: Path, *, geraet: str = "auto", rechenart: str = "int8"
    ) -> None:
        self.modellverzeichnis = modellverzeichnis
        self.geraet = geraet
        self.rechenart = rechenart
        self._modell = None  # erst beim ersten Aufruf laden

    def transkribiere(self, wav: Path, sprache: str = "de") -> Transkript:
        if self._modell is None:
            from faster_whisper import WhisperModel

            self._modell = WhisperModel(
                str(self.modellverzeichnis), device=self.geraet, compute_type=self.rechenart
            )

        rohabschnitte, _info = self._modell.transcribe(str(wav), language=sprache)
        abschnitte = [
            Abschnitt(start_s=a.start, ende_s=a.end, text=a.text.strip()) for a in rohabschnitte
        ]
        return Transkript(text=" ".join(a.text for a in abschnitte).strip(), abschnitte=abschnitte)
