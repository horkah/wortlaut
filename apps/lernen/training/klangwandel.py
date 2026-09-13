"""Abwandlung während des Trainings - breit, gewürfelt, und nirgends abgelegt.

Vorschlag **A** aus `docs/trainingsverfahren.md`: „Augmentierung dorthin, wo
sie wirkt." Bis September 2026 war die einzige Abwandlung dieses Projekts die
Amplitude, und die ist an Whisper nahezu wirkungslos - das Modell hört ein
Log-Mel-Spektrogramm, und eine gleichmäßige Verstärkung verschiebt darin kaum
mehr als einen Summanden. Genau deshalb sind `pegel` und `lauter` verworfen
(`wortlaut/augmentierung.py`). Was bleibt, muss das Spektrogramm **an jeder
Stelle** verändern, nicht bloß seine Höhe.

Vier Griffe tun das, und sie sind absichtlich in dieser Reihenfolge gestaffelt:

* **Masken** (SpecAugment) - waagerechte und senkrechte Balken ins fertige
  Spektrogramm. Das Modell lernt, aus dem Rest zu schließen, statt sich auf
  einzelne Frequenzbänder oder Augenblicke zu verlassen. Der Standardgriff der
  Spracherkennung seit 2019, und der einzige hier, der praktisch nichts kostet.
* **Raum** - Faltung mit einer abklingenden Impulsantwort. Das ist der Abstand
  zum Mikrofon, die Wand dahinter, das kleine Zimmer.
* **Rauschen** - Grundgeräusch bei gewürfeltem Abstand. Nicht dasselbe wie die
  gemessene Fassung `rauschen`: Dort ist der Abstand fest (20 dB), damit die
  Messung vergleichbar bleibt; hier ist er jedes Mal ein anderer, damit das
  Modell keinen bestimmten Abstand auswendig lernt.
* **Tempo** - schneller oder langsamer abgespielt, Tonhöhe und Dauer zugleich.

**Warum Tempo erst in der letzten Stufe.** Bei dysarthrischer Sprache ist das
Sprechtempo kein Zufall, sondern ein Merkmal des Sprechers - womöglich genau
das Merkmal, auf das dieses Modell sich einstellen soll. Es zu verwürfeln kann
helfen (mehr Fälle) oder schaden (das Kennzeichen verwischt). Das ist eine
Frage, keine Meinung, und sie gehört deshalb in eine eigene Stufe, die man
gegen die darunter messen kann.

**Was hier ausdrücklich nicht steht: die Lautstärke.** Sie wäre der billigste
Griff von allen und ist der einzige, von dem wir wissen, dass er nichts bringt.

**Warum nichts davon abgelegt wird.** Gemessen kostet eine abgewandelte
Fassung 33 ms; ein ganzer Korpus von 400 Aufnahmen wäre in 13 Sekunden
gerechnet. Platz zu sparen ist hier also kein Argument, und Zeit erst recht
nicht - ein Trainingsschritt dauert länger als die Abwandlung, die ihn füttert.
Entscheidend ist ein anderes: Abgelegt wäre je Aufnahme **eine** Fassung, immer
dieselbe, in jedem Durchgang. Gewürfelt ist es in jedem Durchgang eine andere,
und genau daran liegt die Wirkung. Eine Datei wäre hier nicht die Ersparnis,
sondern der Verlust.

**Was sauber bleibt: die Validierung.** Abgewandelt wird allein, woraus gelernt
wird. Die Validierung steuert den Lauf - sie sagt, welcher Durchgang der beste
war und welches α gewinnt (`abschluss.py`). Eine Validierung, die in jedem
Durchgang anders klingt, misst nicht mehr das Modell, sondern den Würfel.

Gerechnet wird mit numpy, anders als in `wortlaut/augmentierung.py`: Hier läuft
kein Webdienst, sondern ein Container mit torch darin, und die Faltung über die
Fourier-Transformation ist der Unterschied zwischen zwei Millisekunden und
einer halben Sekunde.
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

# Wie viele Abtastwerte auf einen Spektrogrammrahmen gehen. Fest bei Whisper,
# und hier nötig, um zu wissen, welcher Teil der 3000 Rahmen überhaupt Ton
# enthält - der Rest ist Auffüllung auf 30 Sekunden.
RAHMENSCHRITT = 160

# Die Vorgaben. Sie stehen im Rezept (`rezepte/*.yaml`) und hier nur als
# Rückfalllinie, damit ein Rezept ohne diesen Abschnitt trotzdem läuft.
VORGABEN: dict[str, Any] = {
    # SpecAugment: zwei Zeitbalken bis 12 % der gesprochenen Länge, zwei
    # Frequenzbalken bis 16 Mel-Bänder. Das ist die kleine Einstellung aus der
    # Literatur („SM"), und sie ist hier mit Absicht nicht die große: Bei
    # wenigen hundert kurzen Sätzen verdeckt zu viel Maske den Satz selbst.
    "zeitmasken": 2,
    "zeitmaske_anteil": 0.12,
    "frequenzmasken": 2,
    "frequenzmaske_baender": 16,
    # Raum: Nachhallzeiten, wie sie ein Wohnzimmer und ein gefliester Flur
    # haben. Darüber hinaus klingt es nach Kirche, und dort diktiert niemand.
    "raum_wahrscheinlichkeit": 0.5,
    "raum_nachhall_s": [0.05, 0.35],
    # Rauschen: von „kaum zu hören" bis „stört deutlich". Die gemessene
    # Fassung liegt mit 20 dB mitten darin.
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

    Lineare Neuabtastung und keine Tonhöhenkorrektur - das ist die „speed
    perturbation", die in der Spracherkennung seit Jahren genau so gemacht
    wird: billig, und sie erzeugt einen Sprecher, den es so nicht gibt, aber
    geben könnte. Eine echte Tempoänderung bei gleicher Tonhöhe bräuchte ein
    Phasen-Vocoder und damit eine Abhängigkeit, deren Nutzen hier nicht
    gemessen ist.
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
    Exponentialkurve, mit dem Direktschall als erstem Wert. Das ist die
    schlichteste Nachbildung eines Raums, die noch nach Raum klingt: Ein
    gemessener Raum wäre schöner, verlangte aber eine Sammlung von
    Impulsantworten im Abbild.

    Gefaltet wird über die Fourier-Transformation. Direkt gerechnet wären es
    bei vier Sekunden Ton und 0,3 s Nachhall dreihundert Millionen
    Multiplikationen - eine halbe Sekunde je Probe, und damit teurer als der
    Trainingsschritt, den sie füttert.
    """
    laenge = max(2, int(nachhall_s * RATE))
    huelle = np.exp(-6.9 * np.arange(laenge) / laenge)  # ~ -60 dB am Ende
    antwort = (wuerfel.standard_normal(laenge) * huelle).astype(np.float32)
    antwort[0] = 1.0

    n = int(2 ** np.ceil(np.log2(len(welle) + laenge)))
    gefaltet = np.fft.irfft(np.fft.rfft(welle, n) * np.fft.rfft(antwort, n), n)
    gefaltet = gefaltet[: len(welle)].astype(np.float32)

    # Auf den Ausschlag von vorher zurück: Der Raum soll den Klang ändern, nicht
    # die Lautstärke - die ist die eine Größe, von der wir wissen, dass sie
    # nichts bringt.
    hoch = float(np.max(np.abs(gefaltet)))
    vorher = float(np.max(np.abs(welle)))
    return gefaltet * (vorher / hoch) if hoch > 1e-9 else gefaltet


def rauschen(welle: np.ndarray, abstand_db: float, wuerfel: np.random.Generator) -> np.ndarray:
    """Weißes Rauschen im genannten Abstand zur Aufnahme selbst.

    Fester Abstand zur Aufnahme und nicht fester Pegel - dieselbe Überlegung
    wie bei der gemessenen Fassung (`wortlaut/augmentierung.py`): Ein absoluter
    Pegel träfe eine leise Aufnahme viel härter als eine laute.
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

    **Nur über den gesprochenen Teil.** Whisper füllt jede Aufnahme auf 30
    Sekunden auf, also auf 3000 Rahmen; bei einem Satz von vier Sekunden sind
    2600 davon Stille. Ein Zeitbalken an zufälliger Stelle träfe mit
    Neun-zu-eins-Wahrscheinlichkeit die Auffüllung und täte nichts. `rahmen`
    sagt deshalb, wie weit der Ton reicht.

    Dasselbe gilt für die Frequenzbalken: Sie enden ebenfalls beim letzten
    gesprochenen Rahmen, damit die Auffüllung genau das bleibt, was der
    Merkmalsausleser erzeugt hat.

    Maskiert wird auf den kleinsten Wert des Spektrogramms und nicht auf null:
    Das hier sind logarithmierte Werte, und null wäre darin nicht Stille,
    sondern ein recht lauter Ton.
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
        # Auch der Frequenzbalken endet beim letzten gesprochenen Rahmen. In
        # der Literatur läuft er über die ganze Zeitachse - dort ist die aber
        # so lang wie der Ton. Hier wären es 2600 Rahmen Auffüllung, die dann
        # als einzige Stelle im Spektrogramm maskierte Bänder trügen: ein
        # Merkmal, das mit der Sprache nichts zu tun hat und das das Modell
        # trotzdem lernen könnte.
        aus[start : start + hoehe, :rahmen] = leise

    return aus


# ── Der Wandler, wie ihn der Datensatz benutzt ──────────────────────────────


@dataclass
class Wandler:
    """Was eine Stufe an einer Probe tut - Welle zuerst, Spektrogramm danach.

    Ein Wandler je Ladefaden, jeder mit eigenem Würfel: Zwei Fäden, die sich
    einen Zufallsstrom teilen, hätten eine Reihenfolge, auf die sich niemand
    verlassen kann. Der Keim kommt von außen (`daten.py`) und hängt am Keim des
    Laufs - damit ist ein Lauf bei gleicher Einstellung wiederholbar, ohne dass
    eine einzelne Probe es wäre. Das ist die schwächere Zusage als auf der
    Messseite, und sie genügt hier: Gemessen wird am Ende auf unabgewandelten
    Testaufnahmen.
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
