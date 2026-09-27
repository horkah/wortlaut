"""Alle Modelle nebeneinander, gemessen an denselben Aufnahmen.

Gefragt ist eine Rangfolge - welches Modell *diesem* Menschen am besten
zuhört -, und die braucht einen gemeinsamen Boden.

**Der Boden sind alle Aufnahmen.** Jede Zahl eines trainierten Standes stammt
aus der Faltung, die diese Aufnahme zurückhielt (`aufteilung.py`); die
Grundmodelle haben nichts gelernt.

**Hier wird nur zusammengetragen**, beides aus `wortlaut/metriken.py`:

* Für die Grundmodelle die Auswertung von „hören" - jede Aufnahme durch `base`,
  `small`, `medium` und `large-v3`, in allen Fassungen
  (`apps/hoeren/backend/api/auswertung.py`).
* Für jeden trainierten Stand die `bewertung.jsonl` seines Laufs - dieselben
  Aufnahmen, dieselben Fassungen, dieselben Maße
  (`apps/lernen/training/bewerten.py`).

**Die Rechenzeit vergleicht sich nur im selben Rechenwerk**
(`wortlaut/rechenwerk.py`): Auf dem Prozessor braucht dasselbe Modell das
Zehn- bis Zwanzigfache.

**Verglichen wird nur, was alle gemessen haben.** Die Einheit ist das Paar aus
Aufnahme und Fassung; jedes Mittel läuft über die Schnittmenge aller Modelle
mit Messungen - sonst läge ein Unterschied an der Auswahl. Ist sie leer,
rechnet jedes Modell auf seinem, und die Ansicht sagt es dazu.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import augmentierung, laeufe, streuung

from apps.hoeren.backend.db.models import Erkennung
from apps.hoeren.backend.services.auswertung import gueltige_aufnahmen


# Die Maße einer Zeile, benannt wie in „hören".
MASSE = ("genauigkeit", "wer", "cer", "mer", "wil", "rechenzeit_s")

# Bei diesem Maß ist größer besser; bei allen übrigen kleiner.
HOCH_IST_GUT = {"genauigkeit"}

# Die Zusammenfassung über alle Fassungen - kein Fassungsname.
ALLE = "alle"

# Eine Messeinheit: diese Aufnahme in dieser Fassung.
Einheit = tuple[str, str]


@dataclass
class Messreihe:
    """Was ein Modell erreicht hat, Einheit für Einheit."""

    werte: dict[Einheit, dict[str, float]] = field(default_factory=dict)
    # Worauf gemessen wurde - `cuda/int8_float16`, `cpu/int8`, leer wenn
    # unbekannt. Eine Menge: Wich ein Lauf auf den Prozessor aus, ist seine
    # Rechenzeit eine Mischung, und das soll sichtbar sein.
    werke: set[str] = field(default_factory=set)

    @property
    def werk(self) -> str:
        """Das eine Rechenwerk dieser Reihe - leer, wenn es nicht eines ist."""
        return next(iter(self.werke)) if len(self.werke) == 1 else ''

    def mittel(self, einheiten: set[Einheit]) -> dict[str, dict[str, float]]:
        """Die Mittel je Fassung und über alles - über genau diese Einheiten.

        Fassungen ohne gemeinsame Einheit fehlen, statt eine Null zu behaupten.
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

        Zusätzlich - `mittel` bleibt unverändert; `AUS` (die Vorgabe) gibt
        nichts. Gezogen wird je Aufnahme: Ihre Fassungen sind Messungen an
        einem Gegenstand (`wortlaut/streuung.py`).
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

        In der Differenz fällt heraus, was beide gleich trifft - etwa eine
        schwer verständliche Aufnahme; zwei getrennte Bereiche überlappten
        deshalb oft trotz belastbarem Unterschied. Diese Reihe minus `andere`;
        die Richtung steht in `HOCH_IST_GUT`.
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
    """Die Aufnahmen, an denen gemessen wird: alle gültigen."""
    return {aufnahme.id for aufnahme, _vorlage in gueltige_aufnahmen(korpus)}


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


def stand(
    lauf: laeufe.Lauf,
    aufnahmen: set[str],
    korpus: Session | None = None,
    ref: str = "",
) -> Messreihe:
    """Was ein trainierter Stand auf denselben Aufnahmen erreicht hat.

    Aus zwei Quellen: `bewertung.jsonl` für jede Aufnahme des Trainings,
    gemessen von der Faltung, die sie zurückhielt - soweit sie noch im Korpus
    liegt. Was später dazukam, hat der ausgelieferte Stand in der Auswertung
    von „hören" gehört (`014_erkennungen_aus_faltungen.sql`). Die zweite liegt
    über der ersten; wo beide dieselbe Aufnahme nennen, steht dasselbe.
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

    Modelle ohne Messung bleiben außen vor, sonst wäre die Schnittmenge leer.
    """
    gemessen = [set(reihe.werte) for reihe in reihen if reihe.werte]
    if not gemessen:
        return set()
    return set.intersection(*gemessen)
