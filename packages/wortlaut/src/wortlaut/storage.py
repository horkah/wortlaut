"""Blob-Ablage: lokal oder S3-kompatibel.

Alle Pfade sind relativ zur Wurzel der Ablage (`korpus/spr_…/audio/rec_….wav`),
damit der Fachcode nichts über das Dateisystem des Servers wissen muss.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol


class Ablage(Protocol):
    """Was der Rest des Systems von einer Ablage erwartet."""

    def lege_ab(self, relpfad: str, quelle: Path) -> None:
        """Verschiebt `quelle` (typischerweise eine temporäre Datei) an `relpfad`."""

    def pfad(self, relpfad: str) -> Path:
        """Lokaler Pfad zum Lesen. Nur bei lokaler Ablage ohne Kopieren möglich."""

    def loesche(self, relpfad: str) -> None:
        """Entfernt den Blob. Fehlt er bereits, ist das kein Fehler."""


class LokaleAblage:
    """Dateien unter `WORTLAUT_DATA_DIR`. Sicherung heißt: Verzeichnis kopieren."""

    def __init__(self, wurzel: Path) -> None:
        self.wurzel = wurzel

    def lege_ab(self, relpfad: str, quelle: Path) -> None:
        ziel = self.pfad(relpfad)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        # `move` statt `copy`: die Quelle ist immer eine temporäre Datei, und
        # ein Verschieben innerhalb desselben Dateisystems ist atomar.
        shutil.move(str(quelle), ziel)

    def pfad(self, relpfad: str) -> Path:
        return self.wurzel / relpfad

    def loesche(self, relpfad: str) -> None:
        self.pfad(relpfad).unlink(missing_ok=True)


def oeffne_ablage(art: str, wurzel: Path) -> Ablage:
    """Fabrik für `WORTLAUT_STORAGE`."""
    if art == "local":
        return LokaleAblage(wurzel)
    if art == "s3":
        # Bewusst noch nicht gebaut: solange ein Server genügt, ist die lokale
        # Ablage die einfachere und für Gesundheitsdaten die engere Lösung.
        # Eine S3-Umsetzung müsste nur das Protokoll `Ablage` erfüllen.
        raise NotImplementedError("S3-Ablage ist noch nicht umgesetzt (siehe storage.py)")
    raise ValueError(f"Unbekannte Ablageart: {art!r}")
