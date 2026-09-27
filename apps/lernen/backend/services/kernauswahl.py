"""Der Kern: die Aufnahmen, die das freigegebene Modell am besten verstanden hat.

Wofür es ihn gibt und warum nur auf ihm gelernt, aber auf allem gemessen wird,
steht bei der Achse selbst (`wortlaut/laeufe.py`, „Die Auswahl"). Hier steht,
wie er gewählt wird.

**Nach dem freigegebenen Modell.** Das ist das Modell, mit dem dieser Mensch
diktiert - und damit das beste Urteil darüber, welche Aufnahmen verständlich
sind. Seine Werte kommen von dort, wo die Modelltafel sie auch holt
(`messwerte.py`): bei einem trainierten Stand aus der Kreuzvalidierung seines
Laufs, für später dazugekommene Aufnahmen aus der Auswertung in „hören"; bei
einem freigegebenen Grundmodell allein aus „hören". Gezählt wird die WER des
Originals - die Aufnahme, wie sie gesprochen wurde, nicht ihre Abwandlung.

**Teile und Kopien erben den Wert ihres Originals.** Ein trainierter Stand
misst sie nicht: Es ist derselbe Ton wie eine Aufnahme, die er gelernt hat
(`hoeren/services/auswertung.verwandte`). Sein Wert für das Original stammt aus
der Faltung, die es zurückgehalten hatte, und gilt damit auch für sie.

**Ohne Wert kein Kern.** Hat das Modell eine Aufnahme weder gehört noch einen
Wert für ihr Original, lässt sich nicht sagen, ob sie hineingehört - sie
wegzulassen verwürfe womöglich die besten, sie hineinzunehmen machte den Kern
zu etwas anderem als dem, was er verspricht. Der Auftrag wird dann abgewiesen,
mit dem Weg dorthin: die Auswertung in „hören" laufen lassen, die das
freigegebene Modell auf allem misst, was ihm fehlt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from wortlaut import augmentierung, laeufe, registry

from apps.hoeren.backend.services import zuschnitt
from apps.lernen.backend.services import messwerte
from apps.lernen.backend.services.aufteilung import Probe


class KeinKern(ValueError):
    """Der Kern lässt sich nicht wählen - und die Meldung sagt, warum."""


@dataclass(frozen=True)
class Kernauswahl:
    """Was gewählt wurde und wonach - so, wie es in `kernauswahl.json` steht."""

    # Nach wessen Werten: die Kennung aus der Freigabe (`spr_…/<version>` oder
    # ein Grundmodellname wie `small`).
    modell: str
    anteil: float
    # Jede Aufnahme mit ihrer WER, die außerhalb des Kerns eingeschlossen.
    wer: dict[str, float] = field(default_factory=dict)
    # Die Aufnahmen, deren Wert vom Original stammt.
    geerbt: list[str] = field(default_factory=list)
    kern: list[str] = field(default_factory=list)

    @property
    def schwelle(self) -> float:
        """Die WER der schlechtesten Aufnahme, die noch zum Kern gehört."""
        return max((self.wer[kennung] for kennung in self.kern), default=0.0)

    def als_dict(self) -> dict[str, Any]:
        return {
            "modell": self.modell,
            "anteil": self.anteil,
            "schwelle": self.schwelle,
            "kern": self.kern,
            "geerbt": self.geerbt,
            "wer": self.wer,
        }


def _werte(
    datenverzeichnis: Path, korpus: Session, ref: str, aufnahmen: set[str]
) -> messwerte.Messreihe:
    """Was das Modell `ref` auf diesen Aufnahmen erreicht hat."""
    if registry.ist_stand(ref):
        sprecher_id, version = ref.split(registry.TRENNER, 1)
        try:
            manifest = registry.lies_stand(datenverzeichnis, sprecher_id, version)
        except (OSError, ValueError):
            manifest = {}
        job_id = str(manifest.get("job_id") or "")
        lauf = laeufe.lies_lauf(datenverzeichnis, job_id) if job_id else None
        if lauf is not None:
            return messwerte.stand(lauf, aufnahmen, korpus, ref)
    # Ein Grundmodell - oder ein Stand, dessen Lauf nicht mehr dasteht: Dann
    # bleibt, was „hören" unter seinem Namen gemessen hat.
    return messwerte.grundmodelle(korpus, [ref], aufnahmen)[ref]


def waehle(
    datenverzeichnis: Path, korpus: Session, sprecher_id: str, proben: list[Probe]
) -> Kernauswahl:
    """Den Kern für einen Auftrag über diese Proben wählen."""
    ref = registry.freigegeben(datenverzeichnis, sprecher_id)
    if not ref:
        raise KeinKern(
            "Für die Kernauswahl muss ein Modell freigegeben sein - nach dessen "
            "Werten wird gewählt."
        )

    staemme = {probe.aufnahme.id: zuschnitt.stamm(probe.aufnahme) for probe in proben}
    reihe = _werte(datenverzeichnis, korpus, ref, set(staemme) | set(staemme.values()))

    def wer_von(kennung: str) -> float | None:
        wert = reihe.werte.get((kennung, augmentierung.ORIGINAL), {}).get("wer")
        return None if wert is None else float(wert)

    wer: dict[str, float] = {}
    geerbt: list[str] = []
    ohne: list[str] = []
    for kennung, stamm in staemme.items():
        eigen = wer_von(kennung)
        if eigen is None and stamm != kennung:
            eigen = wer_von(stamm)
            if eigen is not None:
                geerbt.append(kennung)
        if eigen is None:
            ohne.append(kennung)
        else:
            wer[kennung] = eigen

    if ohne:
        raise KeinKern(
            f"{len(ohne)} von {len(staemme)} Aufnahmen hat "
            f"{registry.beschriftung(ref)} noch nicht gehört - erst die Auswertung "
            "in „hören“ laufen lassen, dann lässt sich der Kern wählen."
        )

    # Aufgerundet: Bei zehn Aufnahmen sind es sieben, bei neun ebenfalls sieben
    # und nicht sechs - lieber eine Aufnahme mehr gelernt als eine weniger.
    # Bei gleicher WER entscheidet die Kennung, damit derselbe Korpus immer
    # denselben Kern ergibt.
    anzahl = math.ceil(len(wer) * laeufe.KERN_ANTEIL)
    kern = sorted(wer, key=lambda kennung: (wer[kennung], kennung))[:anzahl]
    return Kernauswahl(
        modell=ref, anteil=laeufe.KERN_ANTEIL, wer=wer, geerbt=sorted(geerbt), kern=kern
    )
