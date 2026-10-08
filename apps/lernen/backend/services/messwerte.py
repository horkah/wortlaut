"""Alle Modelle nebeneinander, gemessen an denselben Aufnahmen.

Gefragt ist eine Rangfolge - welches Modell *diesem* Menschen am besten
zuhört -, und die braucht einen gemeinsamen Boden.

**Der Boden sind alle Aufnahmen außer den Korrekturen**
(`gemessene_aufnahmen` in „hören"). Jede Zahl eines trainierten Standes stammt
aus der Faltung, die diese Aufnahme zurückhielt (`aufteilung.py`); die
Grundmodelle haben nichts gelernt.

**Hier wird nur zusammengetragen**, beides aus `wortlaut/metriken.py`:

* Für die Grundmodelle die Auswertung von „hören" - jede Aufnahme durch jedes
  Grundmodell (`apps/hoeren/backend/api/auswertung.py`).
* Für jeden trainierten Stand die `bewertung.jsonl` seines Laufs - dieselben
  Aufnahmen, dieselben Maße (`apps/lernen/training/bewerten.py`).

**Die Rechenzeit vergleicht sich nur im selben Rechenwerk**
(`wortlaut/rechenwerk.py`): Auf dem Prozessor braucht dasselbe Modell das
Zehn- bis Zwanzigfache.

**Verglichen wird nur, was alle gemessen haben.** Jedes Mittel läuft über die
Aufnahmen, die alle Modelle mit Messungen haben - sonst läge ein Unterschied
an der Auswahl. Ist die Schnittmenge leer, rechnet jedes Modell auf seinem,
und die Ansicht sagt es dazu.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import laeufe, metriken, streuung

from apps.hoeren.backend.db.models import Erkennung
from apps.hoeren.backend.services.auswertung import FALTUNG, gemessene_aufnahmen


# Die Maße einer Zeile, benannt wie in „hören".
MASSE = metriken.MESSFELDER


@dataclass
class Messreihe:
    """Was ein Modell erreicht hat, Aufnahme für Aufnahme."""

    werte: dict[str, dict[str, float]] = field(default_factory=dict)
    # Worauf gemessen wurde - `cuda/int8_float16`, `cpu/int8`, leer wenn
    # unbekannt. Eine Menge: Wich ein Lauf auf den Prozessor aus, ist seine
    # Rechenzeit eine Mischung, und das soll sichtbar sein.
    werke: set[str] = field(default_factory=set)
    # Welche Faltung eine Aufnahme gehört hat - nur bei einem trainierten
    # Stand, und nur bei Messungen aus seiner Kreuzvalidierung.
    faltungen: dict[str, int] = field(default_factory=dict)

    @property
    def werk(self) -> str:
        """Das eine Rechenwerk dieser Reihe - leer, wenn es nicht eines ist."""
        return next(iter(self.werke)) if len(self.werke) == 1 else ''

    def nur_aus(self, faltungen: set[int]) -> Messreihe:
        """Ohne die Messungen der Faltungen, die nicht in `faltungen` stehen.

        Messungen ohne Faltung - der ausgelieferte Stand auf später
        Aufgenommenem - bleiben.
        """
        behalten = {
            kennung: werte
            for kennung, werte in self.werte.items()
            if kennung not in self.faltungen or self.faltungen[kennung] in faltungen
        }
        return Messreihe(
            werte=behalten,
            werke=set(self.werke),
            faltungen={k: f for k, f in self.faltungen.items() if k in behalten},
        )

    def mittel(self, aufnahmen: set[str]) -> dict[str, float]:
        """Die Mittel je Maß - über genau diese Aufnahmen; leer ohne gemeinsame."""
        gemeinsam = sorted(aufnahmen & set(self.werte))
        return _mittelwerte([self.werte[kennung] for kennung in gemeinsam]) if gemeinsam else {}

    def intervalle(self, aufnahmen: set[str], blockart: str = streuung.AUS) -> dict[str, dict]:
        """Zu jedem Mittel aus `mittel` der Bereich, in dem es liegen dürfte.

        Zusätzlich - `mittel` bleibt unverändert; `AUS` (die Vorgabe) gibt
        nichts (`wortlaut/streuung.py`).
        """
        if blockart == streuung.AUS:
            return {}
        verfahren = streuung.Verfahren(blockart=blockart)
        gemeinsam = sorted(aufnahmen & set(self.werte))
        ergebnis: dict[str, dict] = {}
        for mass in MASSE:
            paare = [
                (kennung, self.werte[kennung][mass])
                for kennung in gemeinsam
                if self.werte[kennung].get(mass) is not None
            ]
            bereich = streuung.intervall(streuung.bilde(paare), verfahren)
            if bereich is not None:
                ergebnis[mass] = bereich.als_dict()
        return ergebnis

    def unterschied_zu(
        self, andere: Messreihe, aufnahmen: set[str], blockart: str = streuung.AUS
    ) -> dict[str, dict]:
        """Diese Reihe gegen eine andere - gepaart, auf denselben Aufnahmen.

        In der Differenz fällt heraus, was beide gleich trifft - etwa eine
        schwer verständliche Aufnahme; zwei getrennte Bereiche überlappten
        deshalb oft trotz belastbarem Unterschied. Diese Reihe minus `andere`;
        die Richtung steht in `metriken.HOCH_IST_GUT`.
        """
        if blockart == streuung.AUS:
            return {}
        verfahren = streuung.Verfahren(blockart=blockart)
        # Nur Aufnahmen, die beide gemessen haben - sonst wäre es kein Paar.
        gemeinsam = sorted(aufnahmen & set(self.werte) & set(andere.werte))
        ergebnis: dict[str, dict] = {}
        for mass in MASSE:
            drillinge = [
                (kennung, self.werte[kennung][mass], andere.werte[kennung][mass])
                for kennung in gemeinsam
                if self.werte[kennung].get(mass) is not None
                and andere.werte[kennung].get(mass) is not None
            ]
            gemessen = streuung.unterschied(streuung.bilde_paare(drillinge), verfahren)
            if gemessen is not None:
                ergebnis[mass] = gemessen.als_dict()
        return ergebnis

    def anzahl(self, aufnahmen: set[str]) -> int:
        """Wie viele dieser Aufnahmen gemessen sind."""
        return len(aufnahmen & set(self.werte))


def _mittelwerte(zeilen: list[dict[str, float]]) -> dict[str, float]:
    ergebnis: dict[str, float] = {}
    for mass in MASSE:
        vorhanden = [zeile[mass] for zeile in zeilen if zeile.get(mass) is not None]
        if vorhanden:
            ergebnis[mass] = round(sum(vorhanden) / len(vorhanden), 6)
    return ergebnis


def messaufnahmen(korpus: Session) -> set[str]:
    """Die Aufnahmen, an denen gemessen wird: alle gültigen außer den Korrekturen."""
    return {aufnahme.id for aufnahme, _vorlage in gemessene_aufnahmen(korpus)}


def grundmodelle(korpus: Session, namen: list[str], aufnahmen: set[str]) -> dict[str, Messreihe]:
    """Was die unveränderten Modelle in „hören" auf diesen Aufnahmen erreicht haben."""
    reihen = {name: Messreihe() for name in namen}
    if not aufnahmen or not namen:
        return reihen

    for zeile in korpus.scalars(
        select(Erkennung).where(
            Erkennung.modell.in_(namen), Erkennung.recording_id.in_(aufnahmen)
        )
    ):
        reihen[zeile.modell].werte[zeile.recording_id] = {
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
    for zeile in laeufe.bewertungszeilen(lauf.verzeichnis):
        kennung = str(zeile.get("recording_id", ""))
        if not kennung or (aufnahmen and kennung not in aufnahmen):
            continue
        reihe.werte[kennung] = {
            mass: float(zeile[mass]) for mass in MASSE if zeile.get(mass) is not None
        }
        reihe.werke.add(str(zeile.get("rechenwerk", "")))
        if zeile.get("faltung") is not None:
            reihe.faltungen[kennung] = int(zeile["faltung"])

    if korpus is not None and ref:
        for zeile in korpus.scalars(
            select(Erkennung).where(
                Erkennung.modell == ref, Erkennung.recording_id.in_(aufnahmen or {""})
            )
        ):
            reihe.werte[zeile.recording_id] = {
                mass: float(getattr(zeile, mass)) for mass in MASSE
            }
            reihe.werke.add(zeile.rechenwerk)
            # Hier gemessen hat der ausgelieferte Stand, keine Faltung.
            if zeile.herkunft != FALTUNG:
                reihe.faltungen.pop(zeile.recording_id, None)
    return reihe


def gemeinsame_aufnahmen(reihen: list[Messreihe]) -> set[str]:
    """Die Aufnahmen, die **jedes** messende Modell hat.

    Modelle ohne Messung bleiben außen vor, sonst wäre die Schnittmenge leer.
    """
    gemessen = [set(reihe.werte) for reihe in reihen if reihe.werte]
    if not gemessen:
        return set()
    return set.intersection(*gemessen)
