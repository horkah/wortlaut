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

**Fehlt ein Wert, wird er nachgemessen - vor dem Training.** Hat das Modell
eine Aufnahme weder gehört noch einen Wert für ihr Original, lässt sich nicht
sagen, ob sie hineingehört - sie wegzulassen verwürfe womöglich die besten,
sie hineinzunehmen machte den Kern zu etwas anderem als dem, was er
verspricht. Bis September 2026 wurde der Auftrag dann abgewiesen, mit dem
Hinweis auf die Auswertung in „hören". Seitdem steht die Aufnahme als `offen`
in der Kernauswahl, samt dem Modell und seinem Tempo, und der Trainer lässt
sie von genau diesem Modell hören, bevor die erste Faltung beginnt
(`training/bewerten.vervollstaendige_kern`). Erst danach wird gewählt, nach
derselben Regel (`laeufe.waehle_kern`).

Warum der Trainer und nicht die Auswertung in „hören": Diese App schreibt
nicht in den Korpus (Grundentscheidung 6), und der Trainer hat die Karte, auf
der er die Aufnahmen ohnehin gleich hört. Ein Auftrag, der auf eine Auswertung
im Webdienst wartete, hinge außerdem an dessen Prozess und überlebte keinen
Neustart; ein Lauf überlebt ihn, lässt sich anhalten und neu starten.

**Wie viele, steht trotzdem sofort fest.** `anzahl` ist der Anteil an allen
Aufnahmen des Auftrags, aufgerundet (`laeufe.kern_anzahl`) - die Übersicht
zeigt ihn vom ersten Augenblick an und nicht erst, wenn gewählt ist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from wortlaut import augmentierung, laeufe, registry, tempo

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
    # Mit welchem Faktor vorgespult wird, bevor das Modell zuhört - bei einem
    # Stand der, auf dem er gelernt hat, bei einem Grundmodell keiner
    # (`hoeren/services/auswertung.tempo_fuer`). Gebraucht, wenn nachgemessen
    # wird.
    tempo: float = tempo.VORGABE
    # Jede Aufnahme mit ihrer WER, die außerhalb des Kerns eingeschlossen.
    wer: dict[str, float] = field(default_factory=dict)
    # Die Aufnahmen, deren Wert vom Original stammt.
    geerbt: list[str] = field(default_factory=list)
    # Die Aufnahmen ohne Wert: Der Trainer misst sie, bevor er wählt.
    offen: list[str] = field(default_factory=list)

    @property
    def anzahl(self) -> int:
        """Wie viele Aufnahmen der Kern haben wird - schon bevor er gewählt ist."""
        return laeufe.kern_anzahl(len(self.wer) + len(self.offen))

    @property
    def kern(self) -> list[str] | None:
        """Der Kern - `None`, solange noch Werte fehlen."""
        return None if self.offen else laeufe.waehle_kern(self.wer)

    def als_dict(self) -> dict[str, Any]:
        inhalt: dict[str, Any] = {
            "modell": self.modell,
            "anteil": self.anteil,
            "anzahl": self.anzahl,
            "tempo": self.tempo,
            "geerbt": self.geerbt,
            "wer": self.wer,
        }
        # Die beiden Schlüssel schließen sich aus: Solange etwas offen ist,
        # gibt es keinen Kern, und ein Trainer, der `kern` liest, soll dann
        # keinen finden (`laeufe.kern_aus`).
        kern = self.kern
        if kern is None:
            inhalt["offen"] = self.offen
        else:
            inhalt["kern"] = kern
            inhalt["schwelle"] = schwelle(self.wer, kern)
        return inhalt


def schwelle(wer: dict[str, float], kern: list[str]) -> float:
    """Die WER der schlechtesten Aufnahme, die noch zum Kern gehört."""
    return max((wer[kennung] for kennung in kern), default=0.0)


def _tempo(datenverzeichnis: Path, ref: str) -> float:
    """Der Faktor, mit dem dieses Modell hört - wie in der Auswertung von „hören"."""
    if not registry.ist_stand(ref):
        return tempo.VORGABE
    sprecher_id, version = ref.split(registry.TRENNER, 1)
    try:
        manifest = registry.lies_stand(datenverzeichnis, sprecher_id, version)
    except (OSError, ValueError):
        return tempo.VORGABE
    return float(manifest.get("tempo", tempo.VORGABE))


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
    """Die Werte für den Kern eines Auftrags über diese Proben - und ihn, wenn keiner fehlt."""
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
    offen: list[str] = []
    for kennung, stamm in staemme.items():
        eigen = wer_von(kennung)
        if eigen is None and stamm != kennung:
            eigen = wer_von(stamm)
            if eigen is not None:
                geerbt.append(kennung)
        if eigen is None:
            offen.append(kennung)
        else:
            wer[kennung] = eigen

    # Nachmessen kann der Trainer nur, was er laden kann. Ein Stand, dessen
    # Gewichte nicht mehr dastehen, fiele sonst erst auf der Karte auf - nach
    # dem Warten in der Schlange und mit einer Meldung über faster-whisper.
    if offen and registry.ist_stand(ref) and not registry.ct2_verzeichnis(
        datenverzeichnis, ref
    ).is_dir():
        raise KeinKern(
            f"{len(offen)} von {len(staemme)} Aufnahmen hat {registry.beschriftung(ref)} "
            "noch nicht gehört, und seine Gewichte liegen nicht mehr da - nachmessen "
            "lässt sich so nichts."
        )

    return Kernauswahl(
        modell=ref,
        anteil=laeufe.KERN_ANTEIL,
        tempo=_tempo(datenverzeichnis, ref),
        wer=wer,
        geerbt=sorted(geerbt),
        offen=sorted(offen),
    )
