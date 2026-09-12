"""Alle Modelle nebeneinander, gemessen an denselben Testaufnahmen.

Die Frage dieser Ansicht ist nicht „wie gut ist ein Modell", sondern „welches
von diesen hört *diesem* Menschen am besten zu". Das ist eine Frage nach einer
Rangfolge, und eine Rangfolge braucht einen gemeinsamen Boden.

**Der gemeinsame Boden sind die Testaufnahmen.** Ein Drittel des Korpus ist von
der ersten Aufnahme an zum Prüfen bestimmt und wird nie wieder umsortiert
(siehe `aufteilung.py`). Kein trainiertes Modell hat sie je gesehen; die
unveränderten Grundmodelle sowieso nicht. Nur an ihnen darf verglichen werden -
auf allem anderen hätte die eine Seite gelernt und die andere nicht.

**Gemessen wurde bereits, hier wird nur zusammengetragen.** Zwei Rechnungen
liegen längst vor, und beide stammen aus `wortlaut/metriken.py`:

* Für die Grundmodelle die Auswertung von „hören" - jede Aufnahme durch `base`,
  `small`, `medium`, `large-v3`, in allen vier Fassungen
  (`apps/hoeren/backend/api/auswertung.py`).
* Für jeden trainierten Stand die `bewertung.jsonl` seines Laufs - dieselben
  Testaufnahmen, dieselben vier Fassungen, dieselben Maße
  (`apps/lernen/training/bewerten.py`).

Ein drittes Mal zu messen wäre eine dritte Gelegenheit, es anders zu machen -
anderes Gerät, andere Quantisierung, andere Textangleichung.

**Die Rechenzeit ist nur innerhalb desselben Rechenwerks eine Auskunft.** Sie
hängt an der Maschine, nicht am Modell: Dasselbe whisper-small braucht auf
einem Prozessor das Zehn- bis Zwanzigfache dessen, was es auf einer Karte
braucht. Jede Messung trägt deshalb mit, worauf sie entstand
(`wortlaut/rechenwerk.py`), und die Ansicht vergleicht die Spalte nur, wenn
alle dasselbe nennen.

**Verglichen wird nur, was alle gemessen haben.** Die Einheit ist nicht die
Aufnahme, sondern das Paar aus Aufnahme und Fassung. Aus allen Modellen, die
überhaupt etwas gemessen haben, wird die Schnittmenge dieser Paare gebildet,
und jedes Mittel läuft über genau sie. Sonst stünde ein Mittel über zwanzig
gegen eines über achtzehn, und der Unterschied läge an der Auswahl statt am
Modell.

Bleibt die Schnittmenge leer - etwa weil die Auswertung in „hören" noch nie
gelaufen ist -, rechnet jedes Modell auf dem, was es hat, und die Ansicht sagt
dazu, dass die Zahlen nicht auf demselben Boden stehen. Eine leere Tabelle
wäre die schlechtere Auskunft: Sie verschwiege, dass etwas gemessen wurde.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import augmentierung, laeufe

from apps.hoeren.backend.db.models import Erkennung

from . import aufteilung

# Die Maße, die eine Zeile der Tabelle trägt - dieselben Namen wie in „hören",
# damit niemand zwei Vokabulare im Kopf halten muss.
MASSE = ("genauigkeit", "wer", "cer", "mer", "wil", "rechenzeit_s")

# Bei diesem Maß ist größer besser; bei allen übrigen kleiner.
HOCH_IST_GUT = {"genauigkeit"}

# Der Schlüssel der Zusammenfassung über alle Fassungen. Kein Name, den eine
# Fassung je trägt - sonst verdeckte die Summe eine ihrer Zeilen.
ALLE = "alle"

# Eine Messeinheit: diese Aufnahme in dieser Fassung.
Einheit = tuple[str, str]


@dataclass
class Messreihe:
    """Was ein Modell auf den Testaufnahmen erreicht hat, Einheit für Einheit."""

    werte: dict[Einheit, dict[str, float]] = field(default_factory=dict)
    # Worauf gemessen wurde - `cuda/int8_float16`, `cpu/int8`, leer für Zeilen
    # von vor `008_rechenwerk.sql`. Eine Menge und kein einzelner Wert: Ein
    # Lauf, der auf halber Strecke von der Karte auf den Prozessor ausgewichen
    # ist, hat zwei, und dann ist seine Rechenzeit kein Mittel, sondern eine
    # Mischung. Sichtbar zu machen ist das besser, als es zu glätten.
    werke: set[str] = field(default_factory=set)

    @property
    def werk(self) -> str:
        """Das eine Rechenwerk dieser Reihe - leer, wenn es nicht eines ist."""
        return next(iter(self.werke)) if len(self.werke) == 1 else ''

    def mittel(self, einheiten: set[Einheit]) -> dict[str, dict[str, float]]:
        """Die Mittel je Fassung und über alles - über genau diese Einheiten.

        Fassungen ohne eine einzige gemeinsame Einheit fehlen im Ergebnis. Eine
        Null dafür einzusetzen behauptete eine Messung, die nicht stattfand.
        """
        gemeinsam = sorted(einheiten & set(self.werte))
        if not gemeinsam:
            return {}

        nach_fassung: dict[str, list[dict[str, float]]] = {ALLE: []}
        for schluessel in gemeinsam:
            _aufnahme, fassung = schluessel
            nach_fassung.setdefault(fassung, []).append(self.werte[schluessel])
            nach_fassung[ALLE].append(self.werte[schluessel])

        return {
            fassung: _mittelwerte(zeilen)
            for fassung, zeilen in nach_fassung.items()
            if zeilen
        }

    def einheiten_je_fassung(self, einheiten: set[Einheit]) -> dict[str, int]:
        gezaehlt: dict[str, int] = {ALLE: 0}
        for _aufnahme, fassung in sorted(einheiten & set(self.werte)):
            gezaehlt[fassung] = gezaehlt.get(fassung, 0) + 1
            gezaehlt[ALLE] += 1
        return gezaehlt


def _mittelwerte(zeilen: list[dict[str, float]]) -> dict[str, float]:
    ergebnis: dict[str, float] = {}
    for mass in MASSE:
        vorhanden = [zeile[mass] for zeile in zeilen if zeile.get(mass) is not None]
        if vorhanden:
            ergebnis[mass] = round(sum(vorhanden) / len(vorhanden), 6)
    return ergebnis


def testaufnahmen(db: Session, korpus: Session) -> set[str]:
    """Die Aufnahmen, an denen gemessen werden darf - der Testteil der Aufteilung."""
    return {
        probe.aufnahme.id
        for probe in aufteilung.proben(db, korpus)
        if probe.teil == laeufe.TEST
    }


def grundmodelle(korpus: Session, namen: list[str], aufnahmen: set[str]) -> dict[str, Messreihe]:
    """Was die unveränderten Modelle in „hören" auf diesen Aufnahmen erreicht haben."""
    reihen = {name: Messreihe() for name in namen}
    if not aufnahmen or not namen:
        return reihen

    for zeile in korpus.scalars(
        select(Erkennung).where(
            Erkennung.modell.in_(namen),
            Erkennung.recording_id.in_(aufnahmen),
            Erkennung.variante.in_(augmentierung.VARIANTEN),
        )
    ):
        reihen[zeile.modell].werte[(zeile.recording_id, zeile.variante)] = {
            mass: float(getattr(zeile, mass)) for mass in MASSE
        }
        reihen[zeile.modell].werke.add(zeile.rechenwerk)
    return reihen


def stand(lauf: laeufe.Lauf, aufnahmen: set[str]) -> Messreihe:
    """Was ein trainierter Stand auf denselben Aufnahmen erreicht hat.

    Aus der `bewertung.jsonl` seines Laufs. Aufnahmen, die dort stehen,
    inzwischen aber nicht mehr im Testteil liegen - gelöscht etwa -, fallen
    heraus: Der gemeinsame Boden ist der Korpus von heute.
    """
    reihe = Messreihe()
    for zeile in laeufe.lies_zeilen(lauf.verzeichnis / laeufe.BEWERTUNG):
        kennung = str(zeile.get("recording_id", ""))
        if not kennung or (aufnahmen and kennung not in aufnahmen):
            continue
        fassung = str(zeile.get("variante") or augmentierung.ORIGINAL)
        reihe.werte[(kennung, fassung)] = {
            mass: float(zeile[mass]) for mass in MASSE if zeile.get(mass) is not None
        }
        reihe.werke.add(str(zeile.get("rechenwerk", "")))
    return reihe


def gemeinsame_einheiten(reihen: list[Messreihe]) -> set[Einheit]:
    """Die Paare aus Aufnahme und Fassung, die **jedes** messende Modell hat.

    Modelle ohne eine einzige Messung bleiben dabei außen vor. Sie schrumpfen
    die Schnittmenge sonst auf nichts, und zwar ausgerechnet dann, wenn ein
    Grundmodell in der Liste steht, das in „hören" nie gerechnet wurde.
    """
    gemessen = [set(reihe.werte) for reihe in reihen if reihe.werte]
    if not gemessen:
        return set()
    return set.intersection(*gemessen)
