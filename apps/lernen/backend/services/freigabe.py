"""Welches Modell gilt - freigeben aus der Oberfläche und mit `make release`.

Die Entscheidung hat einen Ort (Grundentscheidung 8): diese Datei. Der Knopf
unter „Modelle" und die Kommandozeile (`scripts/freigeben.py`) rufen dieselbe
Prüfung und schreiben über dieselbe Stelle in die Registry
(`wortlaut/registry.gib_frei`). „schreiben" liest die Freigabe bei jedem
Diktat neu - ein Neustart ist nicht nötig.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wortlaut import laeufe, registry

from apps.lernen.backend.config import einstellungen


class NichtFreigebbar(Exception):
    """Ein Modell, das hier nicht zur Wahl steht - oder ein Lauf ohne Stand."""


def grundmodellnamen() -> list[str]:
    """Die Grundmodelle, die auch freigegeben werden können - `small`, `medium`, …

    Die aus der Auswertung von „hören" und immer das, worauf trainiert wird:
    Es ist die Baseline.
    """
    konfiguration = einstellungen()
    namen = [teil.strip() for teil in konfiguration.auswertung_modelle.split(",") if teil.strip()]
    kurz = laeufe.kurzname(konfiguration.lernen_basismodell)
    if kurz not in namen:
        namen.append(kurz)
    return namen


def gib_frei(datenverzeichnis: Path, sprecher_id: str, ref: str) -> str:
    """Dieses Modell freigeben - und damit jedes andere zurückziehen.

    Geprüft gegen die eigene Liste, nicht das Dateisystem - sonst ließe ein
    Pfad fremde Stände laden. Leer nimmt die Freigabe zurück.
    """
    erlaubt = {
        *grundmodellnamen(),
        *(str(manifest.get("id", "")) for manifest in registry.alle_staende(datenverzeichnis, sprecher_id)),
    }
    if ref and ref not in erlaubt:
        raise NichtFreigebbar("Dieses Modell steht hier nicht zur Wahl.")
    return registry.gib_frei(datenverzeichnis, sprecher_id, ref)


def stand_aus_lauf(datenverzeichnis: Path, job_id: str) -> dict[str, Any]:
    """Der Stand, der aus diesem Lauf hervorging - für `make release JOB=…`."""
    lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
    if lauf is None:
        raise NichtFreigebbar(f"Kein Lauf {job_id} unter {laeufe.wurzel(datenverzeichnis)}.")
    for manifest in registry.alle_staende(datenverzeichnis, lauf.sprecher_id):
        if manifest.get("job_id") == job_id:
            return manifest
    raise NichtFreigebbar(
        f"Lauf {job_id} hat keinen Stand - Zustand: {lauf.zustand.get('status', 'wartet')}."
    )
