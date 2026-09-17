"""Alle Modelle nebeneinander, gemessen an denselben Testaufnahmen.

Die Frage dieser Ansicht ist nicht „wie gut ist ein Modell", sondern „welches
von diesen hört *diesem* Menschen am besten zu". Das ist eine Frage nach einer
Rangfolge, und eine Rangfolge braucht einen gemeinsamen Boden.

**Der gemeinsame Boden sind alle Aufnahmen.** Seit September 2026 wird
kreuzvalidiert (siehe `aufteilung.py`): Jede Zahl eines trainierten Standes
stammt aus der Faltung, die genau diese Aufnahme zurückgehalten hat - kein
Modell hat je gehört, woran es gemessen wird. Die unveränderten Grundmodelle
haben ohnehin nie etwas gelernt. Beide Seiten stehen damit auf demselben,
größeren Boden: dem ganzen Korpus statt einem Drittel davon.

**Gemessen wurde bereits, hier wird nur zusammengetragen.** Zwei Rechnungen
liegen längst vor, und beide stammen aus `wortlaut/metriken.py`:

* Für die Grundmodelle die Auswertung von „hören" - jede Aufnahme durch `base`,
  `small`, `medium` und `large-v3`, in allen Fassungen
  (`apps/hoeren/backend/api/auswertung.py`).
* Für jeden trainierten Stand die `bewertung.jsonl` seines Laufs - dieselben
  Aufnahmen, dieselben Fassungen, dieselben Maße
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
from wortlaut import augmentierung, laeufe, streuung

from apps.hoeren.backend.db.models import Erkennung
from apps.hoeren.backend.services.auswertung import gueltige_aufnahmen


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

    def _je_fassung(self, einheiten: set[Einheit]) -> dict[str, list[Einheit]]:
        """Die gemeinsamen Einheiten nach Fassung, plus die Sammelreihe `alle`."""
        gemeinsam = sorted(einheiten & set(self.werte))
        nach_fassung: dict[str, list[Einheit]] = {ALLE: []}
        for schluessel in gemeinsam:
            _aufnahme, fassung = schluessel
            nach_fassung.setdefault(fassung, []).append(schluessel)
            nach_fassung[ALLE].append(schluessel)
        return {fassung: liste for fassung, liste in nach_fassung.items() if liste}

    def intervalle(
        self, einheiten: set[Einheit], blockart: str = streuung.AUS
    ) -> dict[str, dict[str, dict]]:
        """Zu jedem Mittel aus `mittel` der Bereich, in dem es liegen dürfte.

        Eine **zusätzliche** Auskunft: Die Zahlen aus `mittel` ändern sich
        dadurch nicht um eine Stelle - `Intervall.mittel` ist derselbe Wert,
        aus derselben Rechnung. `AUS` gibt nichts zurück, und das ist die
        Vorgabe: Wer nichts anfordert, bekommt die Tabelle von gestern.

        Gezogen wird je **Aufnahme** und nicht je Einheit, sobald mehrere
        Fassungen in der Reihe stehen: Vier Fassungen derselben Aufnahme sind
        mehrere Messungen an einem Gegenstand (siehe `wortlaut/streuung.py`).
        """
        if blockart == streuung.AUS:
            return {}
        verfahren = streuung.Verfahren(blockart=blockart)
        ergebnis: dict[str, dict[str, dict]] = {}
        for fassung, schluessel_liste in self._je_fassung(einheiten).items():
            je_mass: dict[str, dict] = {}
            for mass in MASSE:
                paare = [
                    (aufnahme, self.werte[schluessel][mass])
                    for schluessel in schluessel_liste
                    for aufnahme, _fassung in (schluessel,)
                    if self.werte[schluessel].get(mass) is not None
                ]
                bereich = streuung.intervall(streuung.bilde(paare, blockart), verfahren)
                if bereich is not None:
                    je_mass[mass] = bereich.als_dict()
            if je_mass:
                ergebnis[fassung] = je_mass
        return ergebnis

    def unterschied_zu(
        self, andere: Messreihe, einheiten: set[Einheit], blockart: str = streuung.AUS
    ) -> dict[str, dict[str, dict]]:
        """Diese Reihe gegen eine andere - gepaart, auf denselben Einheiten.

        Gepaart und nicht als zwei Bereiche nebeneinander: Beide Modelle haben
        dieselben Aufnahmen gehört, und der gemeinsame Anteil - die eine
        schwer verständliche Aufnahme, die beide herunterzieht - fällt in der
        Differenz heraus. Zwei getrennte Bereiche tragen ihn beide mit und
        überlappen sich deshalb oft, obwohl der Unterschied belastbar ist.

        Die Differenz ist **diese** Reihe minus `andere`. Ob das gut ist, hängt
        am Maß und steht in `HOCH_IST_GUT`.
        """
        if blockart == streuung.AUS:
            return {}
        verfahren = streuung.Verfahren(blockart=blockart)
        # Nur Einheiten, die beide gemessen haben - sonst wäre es kein Paar.
        gemeinsam = einheiten & set(self.werte) & set(andere.werte)
        ergebnis: dict[str, dict[str, dict]] = {}
        for fassung, schluessel_liste in self._je_fassung(gemeinsam).items():
            je_mass: dict[str, dict] = {}
            for mass in MASSE:
                drillinge = [
                    (aufnahme, self.werte[schluessel][mass], andere.werte[schluessel][mass])
                    for schluessel in schluessel_liste
                    for aufnahme, _fassung in (schluessel,)
                    if self.werte[schluessel].get(mass) is not None
                    and andere.werte[schluessel].get(mass) is not None
                ]
                gemessen = streuung.unterschied(
                    streuung.bilde_paare(drillinge, blockart), verfahren
                )
                if gemessen is not None:
                    je_mass[mass] = gemessen.als_dict()
            if je_mass:
                ergebnis[fassung] = je_mass
        return ergebnis

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


def messaufnahmen(korpus: Session) -> set[str]:
    """Die Aufnahmen, an denen gemessen wird - seit September 2026 alle.

    Vorher war es der Testteil der Aufteilung: ein Drittel, das kein Modell je
    gesehen hatte. Seit die Läufe kreuzvalidieren, ist jede Aufnahme genau
    einmal von einem Modell gehört worden, das sie nicht kannte
    (`training/bewerten.py`) - und die Grundmodelle aus „hören" haben ohnehin
    nie etwas gelernt. Beide Seiten stehen damit auf demselben, größeren Boden.
    """
    return {aufnahme.id for aufnahme, _vorlage in gueltige_aufnahmen(korpus)}


def grundmodelle(korpus: Session, namen: list[str], aufnahmen: set[str]) -> dict[str, Messreihe]:
    """Was die unveränderten Modelle in „hören" auf diesen Aufnahmen erreicht haben.

"""
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


def stand(
    lauf: laeufe.Lauf,
    aufnahmen: set[str],
    korpus: Session | None = None,
    ref: str = "",
) -> Messreihe:
    """Was ein trainierter Stand auf denselben Aufnahmen erreicht hat.

    **Aus zwei Quellen, und das ist Absicht.**

    Die `bewertung.jsonl` seines Laufs deckt jede Aufnahme ab, die es beim
    Training gab: Jede wurde von der Faltung gemessen, die sie zurückgehalten
    hatte. Aufnahmen, die dort stehen, inzwischen aber nicht mehr im Korpus
    liegen - gelöscht etwa -, fallen heraus; der gemeinsame Boden ist der
    Korpus von heute.

    Was seither dazukam, kennt diese Datei nicht. Dafür steht in „hören"
    inzwischen, was der **ausgelieferte** Stand desselben Laufs auf den
    neueren Aufnahmen erreicht - gerechnet in der Auswertung, wie ein
    Grundmodell und aus demselben Grund: Er hat sie nie gehört
    (`014_erkennungen_aus_faltungen.sql`).

    Die zweite Quelle wird über die erste gelegt und nicht umgekehrt. Beide
    reden nur dort über dieselbe Aufnahme, wo die Auswertung eine
    Faltungsmessung übernommen hat - und dann steht in beiden dasselbe.
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

    if korpus is not None and ref:
        for zeile in korpus.scalars(
            select(Erkennung).where(
                Erkennung.modell == ref,
                Erkennung.recording_id.in_(aufnahmen or {""}),
                Erkennung.variante.in_(augmentierung.VARIANTEN),
            )
        ):
            reihe.werte[(zeile.recording_id, zeile.variante)] = {
                mass: float(getattr(zeile, mass)) for mass in MASSE
            }
            reihe.werke.add(zeile.rechenwerk)
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
