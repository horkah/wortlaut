"""Hat es etwas gebracht? - der trainierte Stand gegen die Baseline.

Die Baseline misst „hören" in seiner Auswertung: das Grundmodell des Laufs
an denselben Aufnahmen, mit demselben Maß (`apps/hoeren/.../auswertung.py`).
Neu gemessen wird nicht - eine zweite Messung wäre eine zweite Gelegenheit,
es anders zu machen.

Der trainierte Stand zählt jede Aufnahme aus der Faltung, die sie zurückhielt.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import laeufe

from apps.hoeren.backend.db.models import Erkennung

# Benannt wie in „hören".
MASSE = ("genauigkeit", "wer", "cer", "mer", "wil")

# Bei diesem Maß ist größer besser; bei allen übrigen kleiner.
HOCH_IST_GUT = {"genauigkeit"}


@dataclass(frozen=True)
class Gegenueber:
    """Ein Maß, einmal vorher und einmal nachher."""

    mass: str
    baseline: float | None
    trainiert: float | None
    anzahl: int

    @property
    def besser(self) -> bool | None:
        """Ob der trainierte Stand gewonnen hat. `None`, solange eines fehlt."""
        if self.baseline is None or self.trainiert is None:
            return None
        if self.mass in HOCH_IST_GUT:
            return self.trainiert > self.baseline
        return self.trainiert < self.baseline


def _mittel(werte: list[float]) -> float | None:
    return sum(werte) / len(werte) if werte else None


def baseline(korpus: Session, aufnahmen: set[str], basismodell: str) -> dict[str, Erkennung]:
    """Die gemessenen Zeilen aus „hören" zu diesen Aufnahmen.

    `openai/whisper-small` heißt in der Auswertung `small`.
    """
    kurz = basismodell.rsplit("/", 1)[-1].removeprefix("whisper-")
    return {
        zeile.recording_id: zeile
        for zeile in korpus.scalars(
            select(Erkennung).where(
                Erkennung.modell == kurz, Erkennung.recording_id.in_(aufnahmen or {""})
            )
        )
    }


def bewertung(lauf: laeufe.Lauf) -> dict[str, dict]:
    """Was das trainierte Modell erreicht hat, je Aufnahme."""
    return {
        str(zeile["recording_id"]): zeile
        for zeile in laeufe.bewertungszeilen(lauf.verzeichnis)
        if zeile.get("recording_id")
    }


def gegenueber(lauf: laeufe.Lauf, korpus: Session) -> list[Gegenueber]:
    """Baseline gegen trainierten Stand, je Maß.

    Nur, was beide gemessen haben - sonst läge ein Unterschied an der Auswahl.
    """
    nachher_zeilen = bewertung(lauf)
    if not nachher_zeilen:
        return []
    vorher_zeilen = baseline(korpus, set(nachher_zeilen), str(lauf.auftrag.get("basismodell", "")))
    gemeinsam = sorted(set(nachher_zeilen) & set(vorher_zeilen))
    if not gemeinsam:
        return []
    return [_gegenueber(mass, gemeinsam, vorher_zeilen, nachher_zeilen) for mass in MASSE]


def _gegenueber(
    mass: str, gemeinsam: list[str], vorher_zeilen: dict, nachher_zeilen: dict
) -> Gegenueber:
    """Ein Maß vorher und nachher."""
    vorher = [float(getattr(vorher_zeilen[k], mass)) for k in gemeinsam]
    nachher = [float(nachher_zeilen[k][mass]) for k in gemeinsam if mass in nachher_zeilen[k]]
    return Gegenueber(
        mass=mass,
        baseline=_mittel(vorher),
        trainiert=_mittel(nachher),
        anzahl=len(gemeinsam),
    )
