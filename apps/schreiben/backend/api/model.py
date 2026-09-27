"""Wer hier zuhört.

Ein Modell gehört einem Menschen (Grundentscheidung 3); die Auskunft hängt am
Zugang. Nur lesend: Welches Modell gilt, entscheidet die Modelltafel in
„lernen" (`apps/lernen/backend/api/modelle.py`), erreichbar über die
Modellzeile. Die Zeile unter dem Aufnahmeknopf nennt dauerhaft, was arbeitet -
samt Methode und Datensatz, denn eine Ausgabe beurteilt man immer an einem
bestimmten Modell.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from wortlaut import registry

from ..config import einstellungen
from ..deps import SprecherId, aktive_ref, modellstand

router = APIRouter(prefix="/api/model", tags=["Modell"])


class ModellAntwort(BaseModel):
    sprecher_id: str
    # Standkennung `<sprecher_id>/<version>` oder Grundmodellname, immer gefüllt.
    ref: str
    basismodell: str
    methode: str | None  # full | lora, aus dem Manifest
    daten: str | None  # original | augmentiert, aus dem Manifest
    erstellt: str | None
    # Die WER aus dem Manifest, über die eigenen Einheiten des Laufs - nicht die
    # Zahl der Modelltafel (gemeinsamer Boden), darum in keiner Beschriftung.
    wer: float | None
    laufzeit: str  # local | remote
    # Ob ein trainierter Stand läuft oder ein unverändertes Grundmodell.
    trainiert: bool
    # Der kurze Code (`registry.kurzkennung`); `null` bei Grundmodell oder fehlendem Stand.
    kennung: str | None = None
    # Für die Kopfzeile, hier gebaut für alle Ansichten.
    beschriftung: str


def _antwort(sprecher: str) -> ModellAntwort:
    konfiguration = einstellungen()
    stand = modellstand(konfiguration, sprecher)

    if stand is None:
        # Freigegebenes Grundmodell oder die Vorgabe der Installation.
        name = aktive_ref(konfiguration, sprecher) or konfiguration.asr_modell
        return ModellAntwort(
            sprecher_id=sprecher,
            ref=name,
            basismodell=name,
            methode=None,
            daten=None,
            erstellt=None,
            wer=None,
            laufzeit=konfiguration.asr,
            trainiert=False,
            beschriftung=f"whisper-{name} · unverändert",
        )

    ref, manifest = stand
    if not manifest:
        # Gelöscht oder falsch gesetzt - sichtbar statt geraten.
        return ModellAntwort(
            sprecher_id=sprecher,
            ref=ref,
            basismodell="?",
            methode=None,
            daten=None,
            erstellt=None,
            wer=None,
            laufzeit=konfiguration.asr,
            trainiert=True,
            beschriftung=f"Modellstand {ref} nicht gefunden",
        )

    metriken = manifest.get("metriken") or {}
    wer = metriken.get("wer")
    erstellt = manifest.get("erstellt")
    methode = {"full": "voll", "lora": "LoRA"}.get(str(manifest.get("methode")), "")
    daten = {"original": "Originale", "augmentiert": "mit Abwandlungen"}.get(
        str(manifest.get("daten")), ""
    )
    return ModellAntwort(
        sprecher_id=sprecher,
        ref=ref,
        basismodell=str(manifest.get("basismodell", "?")),
        methode=manifest.get("methode"),
        daten=manifest.get("daten"),
        erstellt=erstellt,
        wer=wer,
        laufzeit=konfiguration.asr,
        trainiert=True,
        kennung=registry.kurzkennung(ref.split("/", 1)[-1]),
        # Welches Modell, nicht wie gut - Zahlen stehen nur in der Modelltafel.
        beschriftung=" · ".join(
            teil
            for teil in (
                str(manifest.get("basismodell", "?")).split("/")[-1],
                methode,
                daten,
                f"Stand {str(erstellt)[:10]}" if erstellt else "",
            )
            if teil
        ),
    )


@router.get("", response_model=ModellAntwort)
def modell(sprecher: SprecherId) -> ModellAntwort:
    return _antwort(sprecher)
