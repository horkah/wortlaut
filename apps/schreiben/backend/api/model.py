"""Welcher Modellstand für **diesen** Sprecher läuft.

Ein Modell gehört zu genau einem Menschen (Grundentscheidung 3), und wer hier
diktiert, diktiert auf seinem eigenen: `lernen` gibt je Sprecher einen Stand
frei, und der gilt für den, der ihn vorlegt. Deshalb hängt diese Auskunft am
Zugang und nicht mehr an der Konfiguration.

Die Oberfläche muss sie jederzeit zeigen können: Wer eine Fehlererkennung
beurteilt, beurteilt immer ein bestimmtes Modell.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import einstellungen
from ..deps import SprecherId, modellstand

router = APIRouter(prefix="/api/model", tags=["Modell"])


class ModellAntwort(BaseModel):
    sprecher_id: str
    ref: str  # leer = kein Stand aus „lernen", es läuft das Grundmodell
    basismodell: str
    methode: str | None  # full | lora, aus dem Manifest
    erstellt: str | None
    wer: float | None
    laufzeit: str  # local | remote
    # Eine Zeile für die Kopfzeile - hier gebaut, damit alle Ansichten
    # dieselbe Auskunft geben.
    beschriftung: str


@router.get("", response_model=ModellAntwort)
def modell(sprecher: SprecherId) -> ModellAntwort:
    konfiguration = einstellungen()
    stand = modellstand(konfiguration, sprecher)

    if stand is None:
        # Der Normalfall, solange „lernen" für diesen Sprecher nichts
        # freigegeben hat: unverändertes Whisper.
        return ModellAntwort(
            sprecher_id=sprecher,
            ref="",
            basismodell=konfiguration.asr_modell,
            methode=None,
            erstellt=None,
            wer=None,
            laufzeit=konfiguration.asr,
            beschriftung=f"whisper-{konfiguration.asr_modell} · unverändert",
        )

    ref, manifest = stand
    if not manifest:
        # Ein vorgegebener Stand, den es nicht gibt: Falsch gesetzte Umgebung
        # soll man sehen, nicht raten müssen.
        return ModellAntwort(
            sprecher_id=sprecher,
            ref=ref,
            basismodell="?",
            methode=None,
            erstellt=None,
            wer=None,
            laufzeit=konfiguration.asr,
            beschriftung=f"Modellstand {ref} nicht gefunden",
        )

    metriken = manifest.get("metriken") or {}
    wer = metriken.get("wer")
    erstellt = manifest.get("erstellt")
    return ModellAntwort(
        sprecher_id=sprecher,
        ref=ref,
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
