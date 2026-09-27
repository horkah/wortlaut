"""Hat es etwas gebracht? - der trainierte Stand gegen die Baseline.

Die Baseline misst „hören" in seiner Auswertung: das Grundmodell des Laufs
an denselben Aufnahmen, je Fassung, mit demselben Maß
(`apps/hoeren/.../auswertung.py`). Neu gemessen wird nicht - eine zweite
Messung wäre eine zweite Gelegenheit, es anders zu machen.

Der trainierte Stand zählt jede Aufnahme aus der Faltung, die sie zurückhielt.

**Je Fassung**, denn ein Stand, der auf dem Original gewinnt und beim Rauschen
verliert, hat den Sprecher gelernt, nicht die Aufnahmesituation.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import augmentierung, laeufe, streuung

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
    # Der gepaarte Vergleich, trainiert minus Baseline - `None` ohne Anforderung
    # (`blockart = aus`) oder bei zu wenigen gemeinsamen Aufnahmen.
    unterschied: dict | None = None
    # Die beiden Vertrauensbereiche einzeln, für die Anzeige daneben.
    bereich_baseline: dict | None = None
    bereich_trainiert: dict | None = None

    @property
    def besser(self) -> bool | None:
        """Ob der trainierte Stand gewonnen hat. `None`, solange eines fehlt.

        Wer vorn liegt - ob das mehr ist als Zufall, sagt `unterschied`.
        """
        if self.baseline is None or self.trainiert is None:
            return None
        if self.mass in HOCH_IST_GUT:
            return self.trainiert > self.baseline
        return self.trainiert < self.baseline


def _mittel(werte: list[float]) -> float | None:
    return sum(werte) / len(werte) if werte else None


def baseline(korpus: Session, aufnahmen: set[str], basismodell: str) -> dict[str, dict]:
    """Die gemessenen Zeilen aus „hören" zu diesen Aufnahmen, nach Fassung.

    `openai/whisper-small` heißt in der Auswertung `small`.
    """
    kurz = basismodell.rsplit("/", 1)[-1].removeprefix("whisper-")
    treffer: dict[str, dict] = {}
    for zeile in korpus.scalars(
        select(Erkennung).where(
            Erkennung.modell == kurz, Erkennung.recording_id.in_(aufnahmen or {""})
        )
    ):
        treffer.setdefault(zeile.variante, {})[zeile.recording_id] = zeile
    return treffer


def bewertung(lauf: laeufe.Lauf) -> dict[str, dict[str, dict]]:
    """Was das trainierte Modell erreicht hat, nach Fassung."""
    treffer: dict[str, dict[str, dict]] = {}
    for zeile in laeufe.lies_zeilen(lauf.verzeichnis / laeufe.BEWERTUNG):
        kennung = zeile.get("recording_id")
        if kennung:
            treffer.setdefault(zeile.get("variante", augmentierung.ORIGINAL), {})[kennung] = zeile
    return treffer


def _bereich(werte: list[tuple[str, float]], blockart: str) -> dict | None:
    ergebnis = streuung.intervall(
        streuung.bilde(werte, blockart), streuung.Verfahren(blockart=blockart)
    )
    return ergebnis.als_dict() if ergebnis is not None else None


def je_fassung(
    lauf: laeufe.Lauf, korpus: Session, blockart: str = streuung.AUS
) -> dict[str, list[Gegenueber]]:
    """Baseline gegen trainierten Stand, je Fassung und Maß.

    Nur, was beide gemessen haben - sonst läge ein Unterschied an der Auswahl.

    `blockart` schaltet Vertrauensbereiche dazu (Vorgabe `aus`). Innerhalb
    einer Fassung fallen die Blockarten zusammen; unterscheiden tun sie sich
    erst über alle Fassungen (`services/messwerte.py`).
    """
    gemessen = bewertung(lauf)
    if not gemessen:
        return {}

    alle_aufnahmen = {kennung for je_variante in gemessen.values() for kennung in je_variante}
    vorher = baseline(korpus, alle_aufnahmen, str(lauf.auftrag.get("basismodell", "")))

    ergebnis: dict[str, list[Gegenueber]] = {}
    for variante in augmentierung.VARIANTEN:
        nachher_zeilen = gemessen.get(variante, {})
        vorher_zeilen = vorher.get(variante, {})
        gemeinsam = sorted(set(nachher_zeilen) & set(vorher_zeilen))
        if not gemeinsam:
            continue
        ergebnis[variante] = [
            _gegenueber(mass, gemeinsam, vorher_zeilen, nachher_zeilen, blockart)
            for mass in MASSE
        ]
    return ergebnis


def _gegenueber(
    mass: str,
    gemeinsam: list[str],
    vorher_zeilen: dict,
    nachher_zeilen: dict,
    blockart: str,
) -> Gegenueber:
    """Ein Maß vorher und nachher - und, wenn gefragt, wie sicher der Abstand ist."""
    vorher = [(k, float(getattr(vorher_zeilen[k], mass))) for k in gemeinsam]
    nachher = [
        (k, float(nachher_zeilen[k][mass])) for k in gemeinsam if mass in nachher_zeilen[k]
    ]
    if blockart == streuung.AUS:
        return Gegenueber(
            mass=mass,
            baseline=_mittel([wert for _k, wert in vorher]),
            trainiert=_mittel([wert for _k, wert in nachher]),
            anzahl=len(gemeinsam),
        )

    # Gepaart wird nur über Aufnahmen, die auf **beiden** Seiten eine Zahl zu
    # diesem Maß haben. Eine fehlende Seite schweigend als null zu zählen wäre
    # der bequemste Weg zu einem Unterschied, den es nicht gibt.
    beide = {k for k, _wert in nachher}
    drillinge = [
        (k, float(nachher_zeilen[k][mass]), float(getattr(vorher_zeilen[k], mass)))
        for k in gemeinsam
        if k in beide
    ]
    gemessen = streuung.unterschied(
        streuung.bilde_paare(drillinge, blockart), streuung.Verfahren(blockart=blockart)
    )
    return Gegenueber(
        mass=mass,
        baseline=_mittel([wert for _k, wert in vorher]),
        trainiert=_mittel([wert for _k, wert in nachher]),
        anzahl=len(gemeinsam),
        unterschied=gemessen.als_dict() if gemessen is not None else None,
        bereich_baseline=_bereich(vorher, blockart),
        bereich_trainiert=_bereich(nachher, blockart),
    )
