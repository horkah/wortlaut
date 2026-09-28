"""Wonach ausgewählt wird - die Steuergröße eines Laufs (`laeufe.STEUERUNGEN`).

Bester Zwischenstand, Abbruch bei `geduldig` und das α des Abschlusses hängen
an einer Zahl auf der zurückgehaltenen Faltung:

* `verlust` - der gewichtete Validierungsverlust, einmal je Durchgang. Billig,
  aber nicht das, woran der Stand gemessen wird: Unter Teacher Forcing
  bestraft er Marken, an denen die freie Dekodierung längst einen anderen
  Pfad nähme, und er sieht die Textangleichung nicht.
* `wer` - die WER nach freier Dekodierung, mehrmals je Durchgang. Dieselbe
  Rechnung wie die Messung der Faltung (`wortlaut/metriken.py`, Mittel über
  die Zeilen), nur gierig in torch statt mit Beam Search in CTranslate2.

Ohne torch, damit Plan und Rechnung sich prüfen lassen, ohne ein Modell zu
laden.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wortlaut import laeufe, metriken

# Wie oft je Durchgang bei `wer` geprüft wird, wenn das Rezept nichts sagt.
WER_PRUEFUNGEN = 3


@dataclass(frozen=True)
class Pruefplan:
    """Wann geprüft wird und worauf es ankommt."""

    # Der Name der Größe im Trainer: `loss` oder `wer` (`eval_loss`, `eval_wer`).
    mass: str
    # Prüfungen je Durchgang.
    je_durchgang: int
    # Schritte zwischen zwei Prüfungen; `None`: am Ende jedes Durchgangs.
    alle_schritte: int | None = None

    @property
    def dekodiert(self) -> bool:
        """Ob jede Prüfung frei dekodiert."""
        return self.mass == "wer"

    @property
    def metrik(self) -> str:
        """Der Schlüssel für `metric_for_best_model`."""
        return f"eval_{self.mass}"

    @property
    def name(self) -> str:
        """Für Protokoll und Bericht."""
        return "Validierungs-WER" if self.dekodiert else "Validierungsverlust"

    def geduld(self, rezept: dict[str, Any]) -> int:
        """Prüfungen ohne Gewinn bis Schluss - die Geduld des Rezepts zählt Durchgänge."""
        return int(rezept.get("geduld", 5)) * self.je_durchgang


def plane(
    steuerung: str, hat_pruefung: bool, schritte_je_durchgang: int, rezept: dict[str, Any]
) -> Pruefplan:
    """Der Prüfplan dieses Trainings.

    Ohne Validierung (Endmodell) gibt es nichts zu steuern; es gilt der
    Verlust, geprüft wird nie.
    """
    if steuerung not in laeufe.STEUERUNGEN:
        raise RuntimeError(
            f"Unbekannte Steuergröße: {steuerung}. Zur Wahl: {', '.join(laeufe.STEUERUNGEN)}."
        )
    if steuerung != laeufe.STEUERUNG_WER or not hat_pruefung:
        return Pruefplan(mass="loss", je_durchgang=1)
    gewuenscht = max(1, int(rezept.get("wer_pruefungen_je_durchgang", WER_PRUEFUNGEN)))
    # Nie öfter als je Schritt; ein winziger Korpus prüft dann eben je Schritt.
    je_durchgang = min(gewuenscht, max(1, schritte_je_durchgang))
    alle = max(1, -(-schritte_je_durchgang // je_durchgang))
    return Pruefplan(mass="wer", je_durchgang=je_durchgang, alle_schritte=alle)


def mittlere_wer(referenzen: list[str], hypothesen: list[str]) -> float:
    """Die WER je Zeile, gemittelt - wie die Messung einer Faltung (`bewerten._zusammengefasst`)."""
    if not referenzen:
        return 0.0
    return sum(
        metriken.bewerte(referenz, hypothese).wer
        for referenz, hypothese in zip(referenzen, hypothesen, strict=True)
    ) / len(referenzen)


def wer_rechner(zerteiler):
    """`compute_metrics` für den Trainer: erzeugte Marken und Sollmarken zu einer WER.

    Beide kommen mit -100 aufgefüllt (`Stapler`, Trainer); das wird vor dem
    Entziffern zur Füllmarke. Die Referenz ist der entzifferte Sollwert - der
    Text der Zeile, wie der Zerteiler ihn sieht.
    """
    import numpy as np

    def rechne(vorhersage) -> dict[str, float]:
        erzeugt = vorhersage.predictions
        if isinstance(erzeugt, tuple):
            erzeugt = erzeugt[0]
        fuellung = zerteiler.pad_token_id
        erzeugt = np.where(erzeugt == -100, fuellung, erzeugt)
        soll = np.where(vorhersage.label_ids == -100, fuellung, vorhersage.label_ids)
        hypothesen = zerteiler.batch_decode(erzeugt, skip_special_tokens=True)
        referenzen = zerteiler.batch_decode(soll, skip_special_tokens=True)
        return {"wer": round(mittlere_wer(referenzen, hypothesen), 6)}

    return rechne
