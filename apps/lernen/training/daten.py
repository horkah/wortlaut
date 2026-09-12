"""Das Manifest als Datensatz - Audio hinein, Merkmale und Marken heraus.

Bewusst ohne torchaudio, librosa oder `datasets`: Eine WAV-Datei mit 16 kHz,
mono, 16 bit ist genau das, was der Merkmalsausleser von Whisper erwartet, und
sie zu lesen kann die Standardbibliothek. Jede dieser Bibliotheken brächte
eigene Abhängigkeiten und eigene Meinungen über Abtastraten mit; hier gibt es
darüber nichts zu meinen, weil „hören" schon beim Aufnehmen umwandelt
(`wortlaut/audio.py`).
"""

from __future__ import annotations

import array
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from wortlaut import laeufe

VOLLAUSSCHLAG = 32768.0


def lies_wav(pfad: Path) -> np.ndarray:
    """Eine WAV-Datei als float32 zwischen -1 und 1."""
    with wave.open(str(pfad), "rb") as datei:
        werte = array.array("h")
        werte.frombytes(datei.readframes(datei.getnframes()))
    return np.asarray(werte, dtype=np.float32) / VOLLAUSSCHLAG


@dataclass
class Probe:
    merkmale: np.ndarray
    marken: list[int]
    gewicht: float


class Proben(torch.utils.data.Dataset):
    """Die Zeilen eines Teils des Manifests, beim Zugriff in Merkmale verwandelt.

    Beim Zugriff und nicht im Voraus: Ein Log-Mel-Spektrogramm von Whisper ist
    immer 30 Sekunden lang, also 80×3000 Fließkommazahlen - knapp ein Megabyte
    je Probe. Bei vierhundert Aufnahmen mal vier Fassungen wären das anderthalb
    Gigabyte im Arbeitsspeicher, für Daten, die ohnehin nur einmal je Durchgang
    gebraucht werden. Das Lesen einer kurzen WAV-Datei kostet dagegen nichts,
    was neben einem Trainingsschritt auffiele.
    """

    def __init__(
        self, zeilen: list[dict[str, Any]], korpus: Path, ausleser, zerteiler
    ) -> None:
        self.zeilen = zeilen
        self.korpus = korpus
        self.ausleser = ausleser
        self.zerteiler = zerteiler

    def __len__(self) -> int:
        return len(self.zeilen)

    def __getitem__(self, stelle: int) -> Probe:
        zeile = self.zeilen[stelle]
        klang = lies_wav(self.korpus / str(zeile["audio"]))
        merkmale = self.ausleser(
            klang, sampling_rate=16_000, return_tensors="np"
        ).input_features[0]
        return Probe(
            merkmale=merkmale,
            marken=self.zerteiler(str(zeile["text"])).input_ids,
            gewicht=float(zeile.get("gewicht", 1.0)),
        )


@dataclass
class Stapler:
    """Fasst Proben zu einem Stapel zusammen und füllt die Marken auf.

    Die Merkmale brauchen kein Auffüllen - Whisper schneidet und füllt jede
    Aufnahme auf dieselben 30 Sekunden. Die Marken schon, und die Füllstellen
    bekommen -100: Das ist der Wert, den die Verlustfunktion von PyTorch
    überspringt. Ohne ihn lernte das Modell, nach dem Satz noch Füllzeichen
    vorherzusagen.
    """

    zerteiler: Any

    def __call__(self, proben: list[Probe]) -> dict[str, torch.Tensor]:
        marken = self.zerteiler.pad(
            [{"input_ids": probe.marken} for probe in proben], return_tensors="pt"
        )
        maskiert = marken["input_ids"].masked_fill(marken.attention_mask.ne(1), -100)

        # Whisper setzt die Anfangsmarke beim Erzeugen selbst davor. Steht sie
        # schon in den Marken, lernte das Modell sie zweimal.
        if (maskiert[:, 0] == self.zerteiler.bos_token_id).all().item():
            maskiert = maskiert[:, 1:]

        return {
            "input_features": torch.tensor(
                np.stack([probe.merkmale for probe in proben]), dtype=torch.float32
            ),
            "labels": maskiert,
            "gewichte": torch.tensor(
                [probe.gewicht for probe in proben], dtype=torch.float32
            ),
        }


def zeilen_fuer(verzeichnis: Path, teile: set[str]) -> list[dict[str, Any]]:
    """Die Manifestzeilen dieser Teile - die einzige Stelle, die `split` auswertet.

    Eine Stelle, weil hier die Zusage hängt, dass keine Testaufnahme ins
    Training gerät. Stünde die Bedingung an zwei Orten, könnte einer davon
    einmal falsch sein, und niemand sähe es am Ergebnis: Ein Modell, das seine
    Prüfung kennt, sieht schlicht gut aus.
    """
    return [
        zeile
        for zeile in laeufe.manifestzeilen(verzeichnis)
        if str(zeile.get("split", "")) in teile
    ]
