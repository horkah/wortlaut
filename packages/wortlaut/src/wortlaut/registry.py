"""Die Modell-Registry - Dateien statt Tabelle.

    data/modelle/<sprecher_id>/<version>/
    ├── manifest.json
    ├── ct2/                        für faster-whisper exportiert
    └── checkpoint/                 Rohgewichte, optional

Ein Modellstand ist damit ein Verzeichnis, das man kopieren, sichern und per
`scp` verschieben kann. Geschrieben wird die Registry von „lernen", gelesen von
„schreiben", das ohne einen Stand mit dem unveränderten Whisper-Modell
arbeitet. Das Format ist die Nahtstelle zwischen beiden und gehört deshalb an
genau eine Stelle.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

MODELLE = "modelle"
MANIFEST = "manifest.json"


def stand_verzeichnis(datenverzeichnis: Path, sprecher_id: str, version: str) -> Path:
    return datenverzeichnis / MODELLE / sprecher_id / version


def lies_stand(datenverzeichnis: Path, sprecher_id: str, version: str) -> dict[str, Any]:
    pfad = stand_verzeichnis(datenverzeichnis, sprecher_id, version) / MANIFEST
    return json.loads(pfad.read_text(encoding="utf-8"))


def schreibe_stand(datenverzeichnis: Path, manifest: dict[str, Any]) -> Path:
    """Legt `manifest.json` an; `id` hat die Form `<sprecher_id>/<version>`."""
    sprecher_id, version = str(manifest["id"]).split("/", 1)
    verzeichnis = stand_verzeichnis(datenverzeichnis, sprecher_id, version)
    verzeichnis.mkdir(parents=True, exist_ok=True)
    pfad = verzeichnis / MANIFEST
    pfad.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return pfad


def alle_staende(datenverzeichnis: Path, sprecher_id: str) -> list[dict[str, Any]]:
    """Alle Modellstände eines Sprechers, älteste zuerst."""
    wurzel = datenverzeichnis / MODELLE / sprecher_id
    if not wurzel.is_dir():
        return []
    return [
        json.loads((eintrag / MANIFEST).read_text(encoding="utf-8"))
        for eintrag in sorted(wurzel.iterdir())
        if (eintrag / MANIFEST).is_file()
    ]


def loesche_stand(datenverzeichnis: Path, sprecher_id: str, version: str) -> bool:
    """Einen Modellstand vollständig entfernen; `False`, wenn es ihn nicht gab.

    Das ganze Verzeichnis, nicht nur sein Manifest: Ein Stand ohne Manifest
    wäre ein Gigabyte Gewichte, das niemand mehr zuordnen kann - und für jede
    Abfrage hier unsichtbar, weil sie über das Manifest geht.
    """
    verzeichnis = stand_verzeichnis(datenverzeichnis, sprecher_id, version)
    if not verzeichnis.is_dir():
        return False
    shutil.rmtree(verzeichnis)
    return True


def stand_zu_lauf(
    datenverzeichnis: Path, sprecher_id: str, job_id: str
) -> dict[str, Any] | None:
    """Der Stand, den dieser Lauf hervorgebracht hat - falls er es tat.

    Die Verbindung steht im Manifest (`job_id`) und nicht im Namen des
    Verzeichnisses: Der Name nennt Zeit, Methode und Datensatz, weil man ihn
    lesen können soll. Eine Kennung darin wäre für Menschen nutzlos und für
    diese Abfrage nicht sicherer.
    """
    for stand in alle_staende(datenverzeichnis, sprecher_id):
        if stand.get("job_id") == job_id:
            return stand
    return None


def aktiver_stand(datenverzeichnis: Path, sprecher_id: str) -> dict[str, Any] | None:
    """Der freigegebene Stand - höchstens einer je Sprecher."""
    freigegeben = [
        stand
        for stand in alle_staende(datenverzeichnis, sprecher_id)
        if stand.get("status") == "active"
    ]
    return freigegeben[-1] if freigegeben else None
