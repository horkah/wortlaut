"""Transkription im eigenen Prozess über faster-whisper (CTranslate2).

Zwei Arten von Modellangaben, beide von faster-whisper selbst unterschieden:

* ein Verzeichnis - der `ct2/`-Ordner eines Modellstands aus der Registry,
  also das feingetunte Modell aus „lernen";
* ein Name wie `small` oder `medium` - das unveränderte Whisper-Modell, das
  faster-whisper beim ersten Aufruf herunterlädt. Damit ist „schreiben"
  benutzbar, bevor es „lernen" gibt.

Worauf gerechnet wird, entscheidet dieser Kasten nicht, sondern
`wortlaut/rechenwerk.py` - dieselbe Antwort für „schreiben", die Auswertung in
„hören" und den Trainer. Nur so sind ihre Rechenzeiten vergleichbar.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .. import rechenwerk
from . import Abschnitt, Transkript

_log = logging.getLogger(__name__)


class LokalerTranskriptor:
    """Ein Whisper-Modell, geladen beim ersten Aufruf.

    **Warum erst beim ersten Aufruf.** Ein Modell wiegt hunderte Megabyte bis
    Gigabyte. Ein Webdienst, der beim Start vier davon lädt, startet nicht in
    Sekunden - und wer nur die Oberfläche aufruft, braucht keines.

    **Warum der Rückfall auf den Prozessor.** Die Karte kann belegt sein: Ein
    Training will acht Gigabyte, das Sprachmodell für die Textquelle weitere
    sechs. Ein Diktat darf daran nicht scheitern - lieber langsam verstanden
    als gar nicht. Der Rückfall gilt dann für diesen Transkriptor und bleibt;
    ein Modell, das bei jeder Aufnahme zwischen Karte und Prozessor wechselte,
    wäre in seinen Rechenzeiten nicht mehr zu lesen.

    Was dabei **nicht** stillschweigend geschieht: ein ausdrücklich verlangtes
    Gerät zu übergehen. Wer `cuda` in die Konfiguration schreibt, bekommt den
    Fehler zu sehen - sonst sucht er die verlorene Rechenzeit an der falschen
    Stelle.
    """

    def __init__(
        self,
        modell: Path | str,
        *,
        geraet: str = rechenwerk.AUTO,
        rechenart: str = rechenwerk.AUTO,
    ) -> None:
        self.modell = modell
        self.wunsch = geraet
        self.geraet, self.rechenart = rechenwerk.waehle(geraet, rechenart)
        self._geladen = None  # das Modell selbst, erst beim ersten Aufruf geladen

    @property
    def marke(self) -> str:
        """Das Rechenwerk, auf dem dieser Transkriptor **wirklich** läuft.

        Erst nach dem ersten Aufruf verlässlich: Ob die Karte den Platz
        hergibt, zeigt sich beim Laden und nicht davor.
        """
        return rechenwerk.marke(self.geraet, self.rechenart)

    def _lade(self):
        from faster_whisper import WhisperModel

        try:
            return WhisperModel(
                str(self.modell), device=self.geraet, compute_type=self.rechenart
            )
        except Exception as ursache:  # noqa: BLE001 - jede Ursache heißt: nicht auf der Karte
            if self.geraet != rechenwerk.CUDA or self.wunsch == rechenwerk.CUDA:
                raise
            _log.warning(
                "Karte nicht nutzbar (%s) - %s läuft auf dem Prozessor.", ursache, self.modell
            )
            self.geraet, self.rechenart = rechenwerk.CPU, rechenwerk.RECHENART_CPU
            return WhisperModel(
                str(self.modell), device=self.geraet, compute_type=self.rechenart
            )

    def transkribiere(self, wav: Path, sprache: str = "de") -> Transkript:
        if self._geladen is None:
            self._geladen = self._lade()

        rohabschnitte, _info = self._geladen.transcribe(str(wav), language=sprache)
        abschnitte = [
            Abschnitt(start_s=a.start, ende_s=a.end, text=a.text.strip()) for a in rohabschnitte
        ]
        return Transkript(text=" ".join(a.text for a in abschnitte).strip(), abschnitte=abschnitte)
