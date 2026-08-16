"""Gemeinsame Testbausteine für beide Testverzeichnisse.

Hier steht nur, was sowohl die Bibliothek als auch die App braucht: eine
Möglichkeit, sprachähnliche WAV-Dateien zu erzeugen. Ohne sie ließe sich weder
die Messung noch der Aufnahme-Endpunkt ohne echtes Mikrofon prüfen.
"""

from __future__ import annotations

import array
import math
import wave
from collections.abc import Callable
from pathlib import Path

import pytest

WavSchreiber = Callable[..., Path]


@pytest.fixture
def wav_schreiben() -> WavSchreiber:
    """Erzeugt eine WAV-Datei mit einstellbarem Pegel, Rand und Format."""

    def schreibe(
        ziel: Path,
        *,
        sekunden: float = 4.0,
        amplitude: int = 6000,
        abtastrate: int = 16_000,
        kanaele: int = 1,
        stille_vorn_s: float = 0.3,
    ) -> Path:
        werte = array.array("h")
        for nummer in range(int(abtastrate * sekunden)):
            zeit = nummer / abtastrate
            # Amplitudenmodulation macht daraus etwas, das im Pegelverlauf
            # eher nach Sprache aussieht als ein reiner Dauerton.
            huellkurve = (
                0.0 if zeit < stille_vorn_s else 0.6 + 0.4 * math.sin(2 * math.pi * 3 * zeit)
            )
            wert = int(amplitude * huellkurve * math.sin(2 * math.pi * 180 * zeit))
            werte.extend([wert] * kanaele)

        ziel.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(ziel), "wb") as datei:
            datei.setnchannels(kanaele)
            datei.setsampwidth(2)
            datei.setframerate(abtastrate)
            datei.writeframes(werte.tobytes())
        return ziel

    return schreibe
