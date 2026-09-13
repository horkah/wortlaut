"""Hat es etwas gebracht? - der trainierte Stand gegen die Grundlinie.

Die Frage dieser App ist nicht, wie gut ein Modell ist, sondern ob das
Training es besser gemacht hat. Dafür braucht es zwei Zahlen zu denselben
Aufnahmen, und die zweite liegt schon da: „hören" hat in seiner Auswertung
jede Aufnahme durch `base`, `small`, `medium` und `large-v3` geschickt und je
Fassung gemessen (`apps/hoeren/.../auswertung.py`). Die Zeilen zu `small` auf
den **Testaufnahmen** sind die Grundlinie - dasselbe Grundmodell, auf das hier
trainiert wird, an denselben Aufnahmen, mit demselben Maß.

**Warum nicht neu gemessen.** Weil eine zweite Messung derselben Sache eine
zweite Gelegenheit wäre, sie anders zu machen - ein anderes Gerät, eine andere
Quantisierung, eine andere Textangleichung. Gemessen wird einmal, und was
verglichen wird, stammt aus derselben Rechnung.

**Warum über alle Aufnahmen.** Auf allem anderen hat das trainierte Modell
gelernt. Eine Verbesserung dort ist keine Auskunft, sondern eine
Selbstverständlichkeit.

**Warum je Fassung.** Weil die interessantere Hälfte der Frage lautet, ob das
Modell den Sprecher verstanden hat oder seine Aufnahmesituation. Ein Stand,
der auf dem Original gewinnt und beim Rauschen verliert, hat etwas anderes
gelernt als einer, der überall gleichmäßig zulegt.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import augmentierung, laeufe, streuung

from apps.hoeren.backend.db.models import Erkennung

# Die Maße, die verglichen werden - dieselben Namen wie in „hören", damit
# niemand zwei Vokabulare im Kopf halten muss.
MASSE = ("genauigkeit", "wer", "cer", "mer", "wil")

# Bei diesem Maß ist größer besser; bei allen übrigen kleiner.
HOCH_IST_GUT = {"genauigkeit"}


@dataclass(frozen=True)
class Gegenueber:
    """Ein Maß, einmal vorher und einmal nachher."""

    mass: str
    grundlinie: float | None
    trainiert: float | None
    anzahl: int
    # Der gepaarte Vergleich der beiden - `None`, solange niemand ihn
    # angefordert hat (`blockart = aus`, die Vorgabe) oder zu wenige Aufnahmen
    # gemeinsam gemessen wurden. Die Differenz ist **trainiert minus
    # Grundlinie**: bei der Genauigkeit ist positiv gut, bei jeder Fehlerrate
    # negativ.
    unterschied: dict | None = None
    # Die beiden Vertrauensbereiche einzeln, für die Anzeige daneben.
    bereich_grundlinie: dict | None = None
    bereich_trainiert: dict | None = None

    @property
    def besser(self) -> bool | None:
        """Ob der trainierte Stand gewonnen hat. `None`, solange eines fehlt.

        Sagt, wer vorn liegt - **nicht**, ob das mehr ist als Zufall. Diese
        zweite Frage beantwortet `unterschied`, und zwar nur, wenn sie gestellt
        wurde. Beide nebeneinander stehen zu lassen ist Absicht: Die Pfeile in
        der Ansicht gab es vorher, sie sollen bleiben, was sie waren, und die
        schärfere Auskunft tritt daneben statt an ihre Stelle.
        """
        if self.grundlinie is None or self.trainiert is None:
            return None
        if self.mass in HOCH_IST_GUT:
            return self.trainiert > self.grundlinie
        return self.trainiert < self.grundlinie


def _mittel(werte: list[float]) -> float | None:
    return sum(werte) / len(werte) if werte else None


def grundlinie(korpus: Session, aufnahmen: set[str], basismodell: str) -> dict[str, dict]:
    """Die gemessenen Zeilen aus „hören" zu diesen Aufnahmen, nach Fassung.

    `basismodell` kommt als `openai/whisper-small` herein und heißt in der
    Auswertung schlicht `small` - die eine Stelle, an der die beiden
    Schreibweisen aufeinandertreffen.
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
    """Was das trainierte Modell auf den Testaufnahmen erreicht hat, nach Fassung."""
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
    """Grundlinie gegen trainierten Stand, je Fassung und Maß.

    Verglichen wird nur, was **beide** gemessen haben. Eine Aufnahme, die in
    der Auswertung von „hören" noch nicht gerechnet ist, fällt aus beiden
    Mittelwerten - sonst stünde ein Mittel über zwanzig gegen ein Mittel über
    achtzehn, und der Unterschied läge an der Auswahl statt am Modell.

    `blockart` schaltet die Vertrauensbereiche dazu; `aus` ist die Vorgabe und
    ergibt genau das, was diese Funktion immer schon ergeben hat. Innerhalb
    **einer** Fassung trägt jede Aufnahme ohnehin nur eine Messung bei - die
    beiden Blockarten fallen hier also zusammen. Der Unterschied zwischen
    ihnen zeigt sich erst dort, wo über alle Fassungen gemittelt wird
    (`services/messwerte.py`).
    """
    gemessen = bewertung(lauf)
    if not gemessen:
        return {}

    alle_aufnahmen = {kennung for je_variante in gemessen.values() for kennung in je_variante}
    vorher = grundlinie(korpus, alle_aufnahmen, str(lauf.auftrag.get("basismodell", "")))

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
            grundlinie=_mittel([wert for _k, wert in vorher]),
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
        grundlinie=_mittel([wert for _k, wert in vorher]),
        trainiert=_mittel([wert for _k, wert in nachher]),
        anzahl=len(gemeinsam),
        unterschied=gemessen.als_dict() if gemessen is not None else None,
        bereich_grundlinie=_bereich(vorher, blockart),
        bereich_trainiert=_bereich(nachher, blockart),
    )
