"""Wer hier zuhört.

Ein Modell gehört zu genau einem Menschen (Grundentscheidung 3), und wer hier
diktiert, diktiert auf seinem eigenen. Diese Auskunft hängt deshalb am Zugang
und nicht an der Konfiguration.

**Gewählt wird hier nichts.** Welches Modell gilt, entscheidet die
Modellübersicht in „lernen" - der eine Ort, an dem die eigenen Stände und die
unveränderten Grundmodelle nebeneinander stehen, an denselben Testaufnahmen
gemessen (`apps/lernen/backend/api/modelle.py`). Dieser Weg liest die Freigabe
und sagt, was daraus geladen wurde; wer sie ändern will, klickt in dieser App
auf die Modellzeile und landet dort.

Aufgegeben wird dabei nichts: Die Zeile unter dem Aufnahmeknopf nennt
weiterhin dauerhaft, was gerade arbeitet - samt Methode und Datensatz, denn
vier Stände vom selben Tag wären sonst nicht auseinanderzuhalten. Wer eine
Ausgabe beurteilt, beurteilt immer ein bestimmtes Modell.

**Dieser Weg liest nur.** Hier stand bis September 2026 eine zweite
Stellschraube: das Aussteuern vor dem Erkennen. Sie ist weg - Whisper hört ein
Log-Mel-Spektrogramm, und eine gleichmäßige Verstärkung verschiebt darin kaum
mehr als einen Summanden. Dieselbe Rechnung war in „hören" schon als Abwandlung
`pegel` verworfen worden, weil sie zwischen zwei Modellen nichts trennte; hier
hat sie noch eine Weile als Hörhilfe gestanden, ohne dass je jemand einen
Gewinn daran messen konnte.

Mit ihr ist der letzte Schreibweg dieser App gefallen und die Tabelle dahinter
(`004_ohne_aussteuern.sql`). „schreiben" hat damit keine Einstellung mehr, die
es selbst hält.
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
    # Was geladen ist: eine Standkennung `<sprecher_id>/<version>` oder ein
    # Grundmodellname. Immer gefüllt - die Oberfläche soll nie raten müssen,
    # ob „leer" ein Grundmodell oder eine fehlende Auskunft bedeutet.
    ref: str
    basismodell: str
    methode: str | None  # full | lora, aus dem Manifest
    daten: str | None  # original | augmentiert, aus dem Manifest
    erstellt: str | None
    # Was der Lauf dieses Standes selbst gemessen hat - über seine eigenen
    # Testeinheiten. Nicht dasselbe wie die Zahl in der Modellübersicht von
    # „lernen": Die rechnet über die Einheiten, die alle Modelle gemeinsam
    # haben. Deshalb steht dieser Wert in keiner Beschriftung; er ist die
    # Auskunft des Manifests und nicht der Vergleich.
    wer: float | None
    laufzeit: str  # local | remote
    # Ob ein trainierter Stand läuft oder ein unverändertes Grundmodell.
    trainiert: bool
    # Der kurze Code dieses Standes (`K7M2Q`) - dieselbe Kennung wie in
    # „lernen" (`registry.kurzkennung`). `null` bei einem Grundmodell und bei
    # einem Stand, den es nicht mehr gibt.
    kennung: str | None = None
    # Eine Zeile für die Kopfzeile - hier gebaut, damit alle Ansichten
    # dieselbe Auskunft geben.
    beschriftung: str


def _antwort(sprecher: str) -> ModellAntwort:
    konfiguration = einstellungen()
    stand = modellstand(konfiguration, sprecher)

    if stand is None:
        # Ein Grundmodell: entweder freigegeben oder das, womit eine
        # Installation anfängt, solange nichts freigegeben ist.
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
        # Ein Stand, den es nicht gibt - gelöscht oder falsch gesetzt. Falsch
        # gesetzte Umgebung soll man sehen, nicht raten müssen.
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
        # **Keine Kennzahl in dieser Zeile.** Hier stand einmal die Wortfehlerrate
        # aus dem Manifest, und sie war eine Falle: Das ist das Mittel über die
        # Testeinheiten *dieses* Laufs, während die Modellübersicht in „lernen"
        # über die Einheiten mittelt, die **alle** Modelle gemessen haben. Zwei
        # Zahlen zum selben Modell, beide richtig, und wer sie nebeneinander
        # sah, musste an einen Fehler glauben. Die Zahlen stehen jetzt an genau
        # einer Stelle - in der Tabelle, auf gemeinsamem Boden. Diese Zeile
        # sagt, **welches** Modell arbeitet, und nicht, wie gut.
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
