"""Das Manifest als Datensatz - Audio hinein, Merkmale und Marken heraus.

Ohne torchaudio, librosa oder `datasets`: „hören" legt 16 kHz, mono, 16 bit
ab (`wortlaut/audio.py`), genau was Whispers Merkmalsausleser erwartet - das
liest die Standardbibliothek.
"""

from __future__ import annotations

import array
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from wortlaut import tempo

from .klangwandel import RAHMENSCHRITT, Wandler

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

    Nicht im Voraus: Ein Spektrogramm (80×3000) wiegt knapp ein Megabyte, und
    eine kurze WAV-Datei zu lesen fällt neben einem Trainingsschritt nicht auf.
    """

    def __init__(
        self,
        zeilen: list[dict[str, Any]],
        korpus: Path,
        ausleser,
        zerteiler,
        wandler: Wandler | None = None,
        faktor: float = tempo.VORGABE,
        zwischenlager: Path | None = None,
        fenster: int | None = None,
    ) -> None:
        self.zeilen = zeilen
        # Merkmalsrahmen je Probe; `None`: Whispers 30 Sekunden (`fenster.py`).
        self.fenster = fenster
        self.korpus = korpus
        self.faktor = faktor
        self.zwischenlager = zwischenlager
        self.ausleser = ausleser
        self.zerteiler = zerteiler
        # Ohne Wandler bleibt jede Probe, wie sie ist - so auch immer die
        # Validierung (`klangwandel.py`).
        self.wandler = wandler or Wandler()

    def __len__(self) -> int:
        return len(self.zeilen)

    def _pfad(self, relpfad: str) -> Path:
        """Die Datei, aus der diese Probe gelesen wird - vorgespult, falls verlangt.

        Einmal gerechnet und im Lauf abgelegt: Vorspulen kostet 80 ms, die
        Merkmale 9 ms, und das Ergebnis ist jedes Mal dasselbe - anders als die
        gewürfelte Abwandlung (`klangwandel.py`).
        """
        quelle = self.korpus / relpfad
        if not tempo.vorspulen_noetig(self.faktor) or self.zwischenlager is None:
            return quelle

        # Ein Pfad aus dem Korpus hinaus (`../../diktate/…`, Selbsttraining)
        # bleibt im Zwischenlager darin.
        ziel = self.zwischenlager / relpfad.replace("../", "")
        if not ziel.is_file():
            tempo.spule_vor(quelle, ziel, self.faktor)
        return ziel

    def __getitem__(self, stelle: int) -> Probe:
        zeile = self.zeilen[stelle]
        klang = lies_wav(self._pfad(str(zeile["audio"])))

        # Raum und Tempo wirken auf die Welle, Masken aufs Spektrogramm.
        klang = self.wandler.welle(klang)
        merkmale = self.ausleser(
            klang, sampling_rate=16_000, return_tensors="np"
        ).input_features[0]
        # Wie weit der Ton reicht - sonst träfe ein Zeitbalken meist die Stille.
        rahmen = min(merkmale.shape[1], len(klang) // RAHMENSCHRITT)
        merkmale = self.wandler.merkmale(merkmale, rahmen)
        if self.fenster is not None:
            merkmale = merkmale[:, : self.fenster]

        return Probe(
            merkmale=merkmale,
            marken=self.zerteiler(str(zeile["text"])).input_ids,
            gewicht=float(zeile.get("gewicht", 1.0)),
        )


@dataclass
class Stapler:
    """Fasst Proben zu einem Stapel zusammen und füllt die Marken auf.

    Die Merkmale sind schon gleich lang - 30 Sekunden oder das Fenster. Die Füllstellen der Marken
    bekommen -100, den Wert, den PyTorchs Verlust überspringt.
    """

    zerteiler: Any

    def __call__(self, proben: list[Probe]) -> dict[str, torch.Tensor]:
        marken = self.zerteiler.pad(
            [{"input_ids": probe.marken} for probe in proben], return_tensors="pt"
        )
        maskiert = marken["input_ids"].masked_fill(marken.attention_mask.ne(1), -100)

        # Die Anfangsmarke setzt Whisper beim Erzeugen selbst.
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
