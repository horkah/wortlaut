"""Transkription im eigenen Prozess über faster-whisper (CTranslate2).

Zwei Arten von Modellangaben, beide von faster-whisper selbst unterschieden:

* ein Verzeichnis — der `ct2/`-Ordner eines Modellstands aus der Registry,
  also das feingetunte Modell aus „lernen";
* ein Name wie `tiny` oder `small` — das unveränderte Whisper-Modell, das
  faster-whisper beim ersten Aufruf herunterlädt. Damit ist „schreiben"
  benutzbar, bevor es „lernen" gibt.
"""

from __future__ import annotations

from pathlib import Path

from . import Abschnitt, Transkript


class LokalerTranskriptor:
    def __init__(
        self, modell: Path | str, *, geraet: str = "auto", rechenart: str = "int8"
    ) -> None:
        self.modell = modell
        self.geraet = geraet
        self.rechenart = rechenart
        self._geladen = None  # das Modell selbst, erst beim ersten Aufruf geladen

    def transkribiere(self, wav: Path, sprache: str = "de") -> Transkript:
        if self._geladen is None:
            from faster_whisper import WhisperModel

            self._geladen = WhisperModel(
                str(self.modell), device=self.geraet, compute_type=self.rechenart
            )

        rohabschnitte, _info = self._geladen.transcribe(str(wav), language=sprache)
        abschnitte = [
            Abschnitt(start_s=a.start, ende_s=a.end, text=a.text.strip()) for a in rohabschnitte
        ]
        return Transkript(text=" ".join(a.text for a in abschnitte).strip(), abschnitte=abschnitte)
