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
from wortlaut import laeufe, tempo
from wortlaut.augmentierung import ORIGINAL

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

    Beim Zugriff und nicht im Voraus: Ein Log-Mel-Spektrogramm von Whisper ist
    immer 30 Sekunden lang, also 80×3000 Fließkommazahlen - knapp ein Megabyte
    je Probe. Bei vierhundert Aufnahmen mal ihren Fassungen wären das über ein
    Gigabyte im Arbeitsspeicher, für Daten, die ohnehin nur einmal je Durchgang
    gebraucht werden. Das Lesen einer kurzen WAV-Datei kostet dagegen nichts,
    was neben einem Trainingsschritt auffiele.
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
    ) -> None:
        self.zeilen = zeilen
        self.korpus = korpus
        self.faktor = faktor
        self.zwischenlager = zwischenlager
        self.ausleser = ausleser
        self.zerteiler = zerteiler
        # Ohne Wandler bleibt jede Probe, was sie war - das ist die Vorgabe und
        # zugleich das, was die Validierung immer bekommt (siehe
        # `klangwandel.py`: Eine Validierung, die in jedem Durchgang anders
        # klingt, misst den Würfel und nicht das Modell).
        self.wandler = wandler or Wandler()

    def __len__(self) -> int:
        return len(self.zeilen)

    def _pfad(self, relpfad: str) -> Path:
        """Die Datei, aus der diese Probe gelesen wird - vorgespult, falls verlangt.

        **Einmal gerechnet und nicht je Durchgang.** Vorspulen kostet gemessen
        80 ms - das ist neben einer Erkennung nichts, aber neben einem
        Trainingsschritt alles: Die Merkmalsextraktion braucht 9 ms, und bei
        sechzig Durchgängen über zweihundert Proben wären es anderthalb
        Stunden allein fürs Vorspulen. Die vorgespulte Fassung ist zudem jedes
        Mal dieselbe - anders als die gewürfelte Abwandlung nebenan, die genau
        deshalb **nicht** abgelegt wird (`klangwandel.py`).

        Abgelegt wird im Lauf und nicht im Korpus: Diese Dateien gehören zu
        diesem Lauf, gehen mit ihm und haben im Korpus nichts zu suchen.
        """
        quelle = self.korpus / relpfad
        if not tempo.vorspulen_noetig(self.faktor) or self.zwischenlager is None:
            return quelle

        ziel = self.zwischenlager / relpfad
        if not ziel.is_file():
            tempo.spule_vor(quelle, ziel, self.faktor)
        return ziel

    def __getitem__(self, stelle: int) -> Probe:
        zeile = self.zeilen[stelle]
        klang = lies_wav(self._pfad(str(zeile["audio"])))

        # Erst die Welle, dann das Spektrogramm - in dieser Reihenfolge, weil
        # Raum und Tempo nur an der Welle zu haben sind und die Masken nur am
        # fertigen Spektrogramm. Dazwischen liegt der Merkmalsausleser, und der
        # ist unverändert derselbe.
        klang = self.wandler.welle(klang)
        merkmale = self.ausleser(
            klang, sampling_rate=16_000, return_tensors="np"
        ).input_features[0]
        # Wie weit der Ton in den 3000 aufgefüllten Rahmen reicht. Ohne diese
        # Zahl träfe ein Zeitbalken meist die Stille dahinter.
        rahmen = min(merkmale.shape[1], len(klang) // RAHMENSCHRITT)
        merkmale = self.wandler.merkmale(merkmale, rahmen)

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


def zeilen_fuer_faltung(
    verzeichnis: Path, faltung: int | None, daten: str, korpus: Path | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Was in dieser Faltung gelernt und was daran gemessen wird.

    Gibt zwei Listen zurück: die Lernzeilen und die Messzeilen. Eine Stelle für
    beides, weil hier die eine Zusage der Kreuzvalidierung hängt - **kein
    Modell hört die Aufnahmen, an denen es gemessen wird**. Stünde die
    Bedingung an zwei Orten, könnte einer davon einmal falsch sein, und niemand
    sähe es am Ergebnis: Ein Modell, das seine Prüfung kennt, sieht schlicht
    gut aus.

    `faltung = None` heißt: das Endmodell. Es lernt auf allem und wird an
    nichts gemessen - die Zahlen des Laufs stammen aus den sechs Faltungen
    davor (siehe `finetune.py`).

    **Gemessen wird immer auf allen Fassungen**, gelernt je nach `daten`. Das
    ist kein Versehen, sondern der Punkt: Die zu vergleichenden Modelle
    unterscheiden sich in ihren Trainingsdaten und in nichts sonst - schon gar
    nicht in dem, woran sie gemessen werden.
    """
    lern: list[dict[str, Any]] = []
    mess: list[dict[str, Any]] = []
    for zeile in laeufe.manifestzeilen(verzeichnis):
        # **Was nicht mehr dasteht, wird nicht gelernt.** Ein Manifest ist der
        # Schnappschuss eines Korpus zu einer Stunde; wer danach eine Aufnahme
        # verwirft, löscht ihr Audio (`apps/hoeren/backend/api/recordings.py`).
        # Für einen frischen Lauf ändert das nichts - sein Manifest ist eben
        # geschrieben worden. Für einen, der ein altes Manifest noch einmal
        # aufnimmt (`nachziehen.py`), ist es der Unterschied zwischen laufen
        # und an einer fehlenden Datei scheitern.
        if korpus is not None and not (korpus / str(zeile["audio"])).is_file():
            continue
        eigene = faltung is not None and int(zeile.get("faltung", -1)) == faltung
        if eigene:
            mess.append(zeile)
            continue
        if daten == laeufe.MIT_VARIANTEN or str(zeile.get("variante")) == ORIGINAL:
            lern.append(zeile)
    return lern, mess
