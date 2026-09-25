"""Worauf wortlaut läuft - die Auskunft hinter dem Menüpunkt „System".

Sie steht in „hören", weil jede App ihre übergreifenden Fragen hierher stellt
(`packages/ui/wer.ts`): Hier liegt die Wurzel der Domain, also ist der Weg aus
jeder App derselbe. Gerechnet wird in `wortlaut/systemlage.py`.

**Mit Wächter, aber jedem.** Wie viel Speicher die Karte hat, ist keine
Auskunft über einen Menschen - aber eine über die Maschine, und die gehört
nicht ins offene Netz. Jeder gültige Zugang genügt: Sprecher, Verwaltung und
Aufsicht sehen dasselbe.

**Keine Rechnung, die sich lohnt, zwischenzuspeichern.** Die Oberfläche fragt
einmal je Sekunde, solange die Ansicht offen ist, und hört nach fünf Minuten
von selbst auf. Eine Abfrage kostet einen Aufruf von `nvidia-smi` - rund
fünfzig Millisekunden in einem Arbeitsfaden, nicht in der Ereignisschleife.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from wortlaut import systemlage

from ..config import einstellungen
from ..deps import Wer

router = APIRouter(tags=["System"])


def _orte() -> list[tuple[str, Path]]:
    """Wo wortlaut schreibt - je Platte eine Zeile, doppelte fallen weg."""
    daten = einstellungen().data_dir
    orte = [("Daten", daten), ("Training", daten / "snapshots")]
    # Die Grundmodelle, sofern ein Cache gesetzt ist (im Abbild: `HF_HOME`).
    if cache := os.environ.get("HF_HOME"):
        orte.append(("Modellcache", Path(cache)))
    return orte


@router.get("/api/system", response_model=systemlage.Systemlage)
def system(_wer: Wer) -> systemlage.Systemlage:
    return systemlage.lage(_orte())
