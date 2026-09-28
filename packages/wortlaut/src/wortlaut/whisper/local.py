"""Transkription im eigenen Prozess über faster-whisper (CTranslate2).

Zwei Arten von Modellangaben, beide von faster-whisper selbst unterschieden:

* ein Verzeichnis - der `ct2/`-Ordner eines Modellstands aus der Registry,
  also das feingetunte Modell aus „lernen";
* ein Name wie `small` oder `medium` - das unveränderte Modell, das
  faster-whisper beim ersten Aufruf herunterlädt.

Worauf gerechnet wird, entscheidet `wortlaut/rechenwerk.py`.

Liegt im Verzeichnis eines Standes ein `startprompt.txt`, beginnt jede
Erkennung damit (`initial_prompt`) - das Vokabular, das der Stand beim
Training mitbekommen hat (`apps/lernen/training/kontext.py`).
"""

from __future__ import annotations

import gc
import logging
import math
from pathlib import Path

from .. import rechenwerk
from . import Abschnitt, Transkript

_log = logging.getLogger(__name__)

# Der Startprompt eines Standes, neben seinen Gewichten.
STARTPROMPT = "startprompt.txt"


def startprompt(modell: Path | str) -> str | None:
    """Der Startprompt, der bei diesem Modell liegt - `None` bei einem Namen oder ohne Datei."""
    datei = Path(modell) / STARTPROMPT
    try:
        text = datei.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


class LokalerTranskriptor:
    """Ein Whisper-Modell, geladen beim ersten Aufruf - ein Webdienst soll in
    Sekunden starten.

    Ist die Karte belegt, weicht er auf den Prozessor aus und bleibt dort;
    ein Wechsel je Aufnahme machte die Rechenzeiten unlesbar. Ein ausdrücklich
    verlangtes `cuda` wird nie übergangen - dann kommt der Fehler.
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
        # Mit dem Modell gelesen, damit ein neu geschriebener Stand ihn mitbringt.
        self.startprompt: str | None = None

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

    def entlade(self) -> None:
        """Das Modell jetzt von der Karte nehmen.

        CTranslate2 gibt seinen Speicher frei, sobald niemand mehr auf das
        Modell zeigt - dieser Aufruf legt den Zeitpunkt fest. Gebraucht vom
        Trainer, der nach dem Messen wieder die ganze Karte will, und von der
        Auswertung nach jedem Lauf. Ein späteres `transkribiere` lädt neu.
        """
        if self._geladen is None:
            return
        self._geladen = None
        gc.collect()

    def lade(self) -> None:
        """Das Modell jetzt auf die Karte holen, statt beim ersten Satz - wer
        sich eine Karte teilt, kann dann auf Platz warten (`training/bewerten.py`)."""
        if self._geladen is None:
            self._geladen = self._lade()
            self.startprompt = startprompt(self.modell)

    def transkribiere(self, wav: Path, sprache: str) -> Transkript:
        self.lade()

        rohabschnitte, _info = self._geladen.transcribe(
            str(wav), language=sprache, initial_prompt=self.startprompt
        )
        rohabschnitte = list(rohabschnitte)
        abschnitte = [
            Abschnitt(start_s=a.start, ende_s=a.end, text=a.text.strip()) for a in rohabschnitte
        ]
        return Transkript(
            text=" ".join(a.text for a in abschnitte).strip(),
            abschnitte=abschnitte,
            sicherheit=_sicherheit(rohabschnitte),
        )


def _sicherheit(rohabschnitte: list) -> float | None:
    """Die mittlere Markenwahrscheinlichkeit über alle Abschnitte, nach Marken gewichtet.

    faster-whisper nennt je Abschnitt den Mittelwert der Log-Wahrscheinlichkeiten
    (`avg_logprob`); zurück in eine Wahrscheinlichkeit erst nach dem Mitteln.
    """
    marken = sum(len(a.tokens) for a in rohabschnitte)
    if not marken:
        return None
    return math.exp(sum(a.avg_logprob * len(a.tokens) for a in rohabschnitte) / marken)
