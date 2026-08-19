"""Welcher Modellstand hier läuft — dauerhaft sichtbar in der Kopfzeile.

Ein Modellwechsel ist eine Konfigurationsänderung mit Neustart und kein
Laufzeitereignis. Genau deshalb muss die Oberfläche jederzeit zeigen können,
welcher Stand die Ausgabe erzeugt hat: Wer eine Fehlererkennung beurteilt,
beurteilt immer ein bestimmtes Modell.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from wortlaut import registry

from ..config import einstellungen

router = APIRouter(prefix="/api/model", tags=["Modell"])


class ModellAntwort(BaseModel):
    sprecher_id: str
    ref: str  # leer = kein Stand aus „lernen", es läuft das Grundmodell
    basismodell: str
    methode: str | None  # full | lora, aus dem Manifest
    erstellt: str | None
    wer: float | None
    laufzeit: str  # local | remote
    # Eine Zeile für die Kopfzeile — hier gebaut, damit alle Ansichten
    # dieselbe Auskunft geben.
    beschriftung: str


@router.get("", response_model=ModellAntwort)
def modell() -> ModellAntwort:
    konfiguration = einstellungen()

    if not konfiguration.modell_ref:
        # Der Normalfall, solange es „lernen" nicht gibt: unverändertes Whisper.
        return ModellAntwort(
            sprecher_id=konfiguration.sprecher_id,
            ref="",
            basismodell=konfiguration.asr_modell,
            methode=None,
            erstellt=None,
            wer=None,
            laufzeit=konfiguration.asr,
            beschriftung=f"whisper-{konfiguration.asr_modell} · unverändert",
        )

    sprecher_id, version = konfiguration.modell_ref.split("/", 1)
    try:
        manifest = registry.lies_stand(konfiguration.data_dir, sprecher_id, version)
    except (OSError, ValueError):
        # Falsch gesetzte Umgebung soll man sehen, nicht raten müssen.
        return ModellAntwort(
            sprecher_id=sprecher_id,
            ref=konfiguration.modell_ref,
            basismodell="?",
            methode=None,
            erstellt=None,
            wer=None,
            laufzeit=konfiguration.asr,
            beschriftung=f"Modellstand {konfiguration.modell_ref} nicht gefunden",
        )

    metriken = manifest.get("metriken") or {}
    wer = metriken.get("wer")
    erstellt = manifest.get("erstellt")
    return ModellAntwort(
        sprecher_id=sprecher_id,
        ref=konfiguration.modell_ref,
        basismodell=manifest.get("basismodell", "?"),
        methode=manifest.get("methode"),
        erstellt=erstellt,
        wer=wer,
        laufzeit=konfiguration.asr,
        beschriftung=" · ".join(
            teil
            for teil in (
                str(manifest.get("basismodell", "?")).split("/")[-1],
                f"Stand {str(erstellt)[:10]}" if erstellt else "",
                # Dezimalkomma: die Zeile steht in einer deutschen Oberfläche.
                f"WER {wer * 100:.1f} %".replace(".", ",") if isinstance(wer, int | float) else "",
            )
            if teil
        ),
    )
