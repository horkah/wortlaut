"""Abwandlung während des Trainings - breit, gewürfelt, und nirgends abgelegt.

Whisper hört ein Log-Mel-Spektrogramm; eine gleichmäßige Verstärkung
verschiebt darin kaum mehr als einen Summanden. Wirksam ist nur, was das
Spektrogramm an jeder Stelle verändert. Vier Griffe, gestaffelt:

* **Masken** (SpecAugment) - Balken ins fertige Spektrogramm; das Modell lernt,
  aus dem Rest zu schließen. Kostet praktisch nichts.
* **Raum** - Faltung mit einer abklingenden Impulsantwort: Abstand, Wand, Zimmer.
* **Rauschen** - bei gewürfeltem Abstand, anders als die gemessene Fassung
  `rauschen` mit festen 20 dB.
* **Tempo** - schneller oder langsamer, Tonhöhe und Dauer zugleich. Zuletzt,
  weil das Tempo dysarthrischer Sprache ein Merkmal des Sprechers ist; ob es
  zu verwürfeln hilft, misst die eigene Stufe.

**Nichts wird abgelegt:** Eine Abwandlung kostet 33 ms, weniger als der
Trainingsschritt, und gewürfelt ist sie in jedem Durchgang eine andere -
darin liegt die Wirkung.

**Die Validierung bleibt unverändert:** Sie wählt Durchgang und α
(`abschluss.py`) und soll das Modell messen, nicht den Würfel.

Mit numpy statt wie `wortlaut/augmentierung.py`: Die Faltung über die
Fourier-Transformation braucht zwei Millisekunden statt einer halben Sekunde.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

# Die Stufen, aufeinander aufbauend. Jede enthält die darüber.
KEINE = "keine"
MASKEN = "masken"
UMGEBUNG = "umgebung"
VOLL = "voll"
STUFEN = (KEINE, MASKEN, UMGEBUNG, VOLL)

# Die Abtastrate des ganzen Projekts (`wortlaut/audio.py`).
RATE = 16_000

# Abtastwerte je Spektrogrammrahmen - sagt, welche der 3000 Rahmen Ton tragen.
RAHMENSCHRITT = 160

# Rückfall, falls einem Rezept (`rezepte/*.yaml`) der Abschnitt fehlt.
VORGABEN: dict[str, Any] = {
    # SpecAugment, die kleine Einstellung („SM") - die große verdeckt kurze Sätze.
    "zeitmasken": 2,
    "zeitmaske_anteil": 0.12,
    "frequenzmasken": 2,
    "frequenzmaske_baender": 16,
    # Raum: Wohnzimmer bis gefliester Flur.
    "raum_wahrscheinlichkeit": 0.5,
    "raum_nachhall_s": [0.05, 0.35],
    # Rauschen: von „kaum zu hören" bis „stört deutlich".
    "rausch_wahrscheinlichkeit": 0.5,
    "rausch_abstand_db": [10.0, 35.0],
    # Tempo: die klassische Dreiteilung 0,9 / 1,0 / 1,1, hier stufenlos.
    "tempo_wahrscheinlichkeit": 0.5,
    "tempo_faktor": [0.9, 1.1],
}


def stufe_aus(rezept: dict[str, Any], vorgabe: str = KEINE) -> str:
    """Die im Rezept genannte Stufe - für den Fall, dass ein Rezept eine setzt."""
    return str((rezept.get("augmentierung") or {}).get("stufe", vorgabe))


def einstellungen_aus(rezept: dict[str, Any]) -> dict[str, Any]:
    """Die Zahlen des Rezepts über die Vorgaben gelegt."""
    return {**VORGABEN, **(rezept.get("augmentierung") or {})}


def pruefe(stufe: str) -> str:
    """Die bestellte Stufe, oder ein Fehler - sofort, nicht nach zwei Stunden."""
    if stufe not in STUFEN:
        raise RuntimeError(
            f"Unbekannte Augmentierung: {stufe}. Zur Wahl stehen: {', '.join(STUFEN)}."
        )
    return stufe


# ── Die einzelnen Griffe ────────────────────────────────────────────────────


def tempo(welle: np.ndarray, faktor: float) -> np.ndarray:
    """Schneller oder langsamer, Dauer und Tonhöhe zugleich.

    Lineare Neuabtastung ohne Tonhöhenkorrektur - die übliche „speed
    perturbation". Gleiche Tonhöhe bräuchte einen Phasen-Vocoder.
    """
    if abs(faktor - 1.0) < 1e-3:
        return welle
    neue_laenge = max(1, round(len(welle) / faktor))
    return np.interp(
        np.linspace(0.0, len(welle) - 1.0, neue_laenge),
        np.arange(len(welle), dtype=np.float64),
        welle,
    ).astype(np.float32)


def raum(welle: np.ndarray, nachhall_s: float, wuerfel: np.random.Generator) -> np.ndarray:
    """Faltung mit einer abklingenden Impulsantwort - Abstand, Wand, Zimmer.

    Die Impulsantwort ist gewürfeltes Rauschen unter einer fallenden
    Exponentialkurve, mit dem Direktschall vorn - die schlichteste Nachbildung,
    die noch nach Raum klingt. Gefaltet über die Fourier-Transformation.
    """
    laenge = max(2, int(nachhall_s * RATE))
    huelle = np.exp(-6.9 * np.arange(laenge) / laenge)  # ~ -60 dB am Ende
    antwort = (wuerfel.standard_normal(laenge) * huelle).astype(np.float32)
    antwort[0] = 1.0

    n = int(2 ** np.ceil(np.log2(len(welle) + laenge)))
    gefaltet = np.fft.irfft(np.fft.rfft(welle, n) * np.fft.rfft(antwort, n), n)
    gefaltet = gefaltet[: len(welle)].astype(np.float32)

    # Zurück auf den ursprünglichen Ausschlag: Klang ändern, nicht Lautstärke.
    hoch = float(np.max(np.abs(gefaltet)))
    vorher = float(np.max(np.abs(welle)))
    return gefaltet * (vorher / hoch) if hoch > 1e-9 else gefaltet


def rauschen(welle: np.ndarray, abstand_db: float, wuerfel: np.random.Generator) -> np.ndarray:
    """Weißes Rauschen im genannten Abstand zur Aufnahme selbst.

    Relativ, wie in `wortlaut/augmentierung.py`: Ein fester Pegel träfe leise
    Aufnahmen härter.
    """
    leistung = float(np.sqrt(np.mean(welle.astype(np.float64) ** 2)))
    if leistung < 1e-9:
        return welle
    streuung = leistung * 10 ** (-abstand_db / 20)
    stoerung = wuerfel.standard_normal(len(welle)).astype(np.float32) * streuung
    return (welle + stoerung).astype(np.float32)


def masken(
    merkmale: np.ndarray,
    rahmen: int,
    einstellungen: dict[str, Any],
    wuerfel: np.random.Generator,
) -> np.ndarray:
    """SpecAugment: Zeit- und Frequenzbalken ins Spektrogramm.

    Nur über den gesprochenen Teil (`rahmen`): Bei vier Sekunden Satz sind 2600
    der 3000 Rahmen Auffüllung. Auch die Frequenzbalken enden dort.

    Maskiert wird auf den kleinsten Wert - in logarithmierten Werten wäre null
    ein lauter Ton.
    """
    aus = merkmale.copy()
    if rahmen <= 1:
        return aus
    leise = float(aus.min())

    breite = max(1, int(rahmen * float(einstellungen["zeitmaske_anteil"])))
    for _ in range(int(einstellungen["zeitmasken"])):
        laenge = int(wuerfel.integers(0, breite + 1))
        if laenge == 0:
            continue
        start = int(wuerfel.integers(0, max(1, rahmen - laenge)))
        aus[:, start : start + laenge] = leise

    baender = min(int(einstellungen["frequenzmaske_baender"]), aus.shape[0] - 1)
    for _ in range(int(einstellungen["frequenzmasken"])):
        hoehe = int(wuerfel.integers(0, baender + 1))
        if hoehe == 0:
            continue
        start = int(wuerfel.integers(0, max(1, aus.shape[0] - hoehe)))
        # Sonst trüge die Auffüllung maskierte Bänder - ein lernbares Merkmal
        # ohne Bezug zur Sprache.
        aus[start : start + hoehe, :rahmen] = leise

    return aus


# ── Der Wandler, wie ihn der Datensatz benutzt ──────────────────────────────


@dataclass
class Wandler:
    """Was eine Stufe an einer Probe tut - Welle zuerst, Spektrogramm danach.

    Ein Wandler je Ladefaden, jeder mit eigenem Würfel. Der Keim hängt am
    Keim des Laufs (`daten.py`): wiederholbar als Lauf, nicht je Probe - das
    genügt, gemessen wird unabgewandelt.
    """

    stufe: str = KEINE
    einstellungen: dict[str, Any] = None  # type: ignore[assignment]
    keim: int = 0
    _wuerfel: np.random.Generator = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.einstellungen is None:
            self.einstellungen = dict(VORGABEN)
        self._wuerfel = np.random.default_rng(self.keim)

    @property
    def taetig(self) -> bool:
        return self.stufe != KEINE

    def welle(self, klang: np.ndarray) -> np.ndarray:
        """Raum, Rauschen, Tempo - je nach Stufe und je nach Würfel."""
        if self.stufe in (KEINE, MASKEN):
            return klang
        e = self.einstellungen
        aus = klang

        if self._trifft(e["raum_wahrscheinlichkeit"]):
            aus = raum(aus, self._zwischen(e["raum_nachhall_s"]), self._wuerfel)
        if self._trifft(e["rausch_wahrscheinlichkeit"]):
            aus = rauschen(aus, self._zwischen(e["rausch_abstand_db"]), self._wuerfel)
        if self.stufe == VOLL and self._trifft(e["tempo_wahrscheinlichkeit"]):
            aus = tempo(aus, self._zwischen(e["tempo_faktor"]))
        return aus

    def merkmale(self, werte: np.ndarray, rahmen: int) -> np.ndarray:
        """Die Balken ins fertige Spektrogramm - in jeder Stufe außer `keine`."""
        if self.stufe == KEINE:
            return werte
        return masken(werte, rahmen, self.einstellungen, self._wuerfel)

    def _trifft(self, wahrscheinlichkeit: float) -> bool:
        return bool(self._wuerfel.random() < float(wahrscheinlichkeit))

    def _zwischen(self, grenzen: Any) -> float:
        unten, oben = float(grenzen[0]), float(grenzen[1])
        return float(self._wuerfel.uniform(unten, oben))
