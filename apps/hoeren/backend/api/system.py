"""Worauf wortlaut läuft - die Auskunft hinter dem Menüpunkt „System".

In „hören", weil jede App ihre übergreifenden Fragen an die Wurzel der Domain
stellt (`packages/ui/wer.ts`). Gerechnet wird in `wortlaut/systemlage.py`.

Jeder gültige Zugang genügt - die Maschine gehört nicht ins offene Netz, ist
aber keine Auskunft über einen Menschen. Die Oberfläche fragt einmal je
Sekunde; eine Abfrage kostet einen Aufruf von `nvidia-smi` im Arbeitsfaden.
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
