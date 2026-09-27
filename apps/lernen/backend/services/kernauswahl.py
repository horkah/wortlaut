"""Der Kern: die Aufnahmen, die das freigegebene Modell am besten verstanden hat.

Wofür es ihn gibt, steht bei der Achse (`wortlaut/laeufe.py`, „Die Auswahl");
hier, wie er gewählt wird.

**Nach dem freigegebenen Modell** - mit dem dieser Mensch diktiert. Seine
Werte kommen von dort, wo die Modelltafel sie holt
(`messwerte.py`): bei einem trainierten Stand aus der Kreuzvalidierung seines
Laufs, für später dazugekommene Aufnahmen aus der Auswertung in „hören"; bei
einem freigegebenen Grundmodell allein aus „hören". Gezählt wird die WER des
Originals - die Aufnahme, wie sie gesprochen wurde, nicht ihre Abwandlung.

**Teile und Kopien erben den Wert ihres Originals.** Ein trainierter Stand
misst sie nicht - derselbe Ton wie eine gelernte Aufnahme
(`hoeren/services/auswertung.verwandte`); der Wert des Originals stammt aus
der Faltung, die es zurückhielt.

**Fehlende Werte misst der Trainer nach, vor der ersten Faltung.** Solche
Aufnahmen stehen als `offen` in der Kernauswahl, samt Modell und Tempo
(`training/bewerten.vervollstaendige_kern`); gewählt wird danach nach
derselben Regel (`laeufe.waehle_kern`). Der Trainer, weil diese App nicht in
den Korpus schreibt (Grundentscheidung 6) und ein Lauf anders als ein
Webprozess Neustarts übersteht.

**Wie viele, steht sofort fest:** `anzahl` (`laeufe.kern_anzahl`).
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
    # Fürs Nachmessen: bei einem Stand sein Lerntempo, bei einem Grundmodell
    # keins (`hoeren/services/auswertung.tempo_fuer`).
    tempo: float = tempo.VORGABE
    # Jede Aufnahme mit ihrer WER, die außerhalb des Kerns eingeschlossen.
    wer: dict[str, float] = field(default_factory=dict)
    # Die Aufnahmen, deren Wert vom Original stammt.
    geerbt: list[str] = field(default_factory=list)
    # Die Aufnahmen ohne Wert: Der Trainer misst sie, bevor er wählt.
    offen: list[str] = field(default_factory=list)
    # Jede Aufnahme mit ihrem Stamm, in Korpusreihenfolge - für die Faltungen
    # des Kerns (`laeufe.verteile_kern`).
    staemme: dict[str, str] = field(default_factory=dict)

    @property
    def anzahl(self) -> int:
        """Wie viele Aufnahmen der Kern haben wird - schon bevor er gewählt ist."""
        return laeufe.kern_anzahl(len(self.wer) + len(self.offen))

    def als_dict(self) -> dict[str, Any]:
        inhalt: dict[str, Any] = {
            "modell": self.modell,
            "anteil": self.anteil,
            "anzahl": self.anzahl,
            "tempo": self.tempo,
            "geerbt": self.geerbt,
            "wer": self.wer,
            "staemme": self.staemme,
            "offen": self.offen,
        }
        # Solange etwas offen ist, gibt es keinen `kern` (`laeufe.kern_aus`).
        return inhalt if self.offen else laeufe.mit_kern(inhalt)


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
    # Grundmodell oder Stand ohne Lauf: was „hören" unter dem Namen gemessen hat.
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

    # Fehlende Gewichte fielen sonst erst auf der Karte auf, nach der Schlange.
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
        staemme=staemme,
    )
