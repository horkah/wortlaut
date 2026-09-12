"""Wie die Erkennung für **diesen** Sprecher läuft - Modell und Aufbereitung.

Ein Modell gehört zu genau einem Menschen (Grundentscheidung 3), und wer hier
diktiert, diktiert auf seinem eigenen. Diese Auskunft hängt deshalb am Zugang
und nicht an der Konfiguration.

**Warum hier inzwischen gewählt werden darf.** Früher stand das Modell in der
Umgebung und ein Wechsel war ein Neustart - richtig, solange es je Sprecher
höchstens einen trainierten Stand gab. „lernen" liefert vier (zwei Methoden mal
zwei Datensätze), und daneben stehen die unveränderten Grundmodelle, gegen die
in „hören" schon gemessen wurde. Welcher davon dieser Person am besten zuhört,
beantwortet keine Kennzahl allein; das beantwortet sich beim Diktieren, und
dafür muss man wechseln können.

Aufgegeben wird dabei nichts: Die Kopfzeile nennt weiterhin dauerhaft, was
gerade arbeitet - jetzt samt Methode und Datensatz, denn vier Stände vom selben
Tag wären sonst nicht auseinanderzuhalten. Wer eine Ausgabe beurteilt,
beurteilt immer ein bestimmtes Modell.

Die zweite Stellschraube daneben ist das **Aussteuern** vor dem Erkennen
(Vorgabe: an). Warum es hilft und warum nur die gehörte Fassung davon
betroffen ist, steht in `services/erkennung.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import einstellungen
from ..deps import Datenbank, SprecherId, modellstand
from ..services import erkennung

router = APIRouter(prefix="/api/model", tags=["Modell"])


class WahlAntwort(BaseModel):
    """Ein wählbares Modell - Grundmodell oder trainierter Stand."""

    ref: str
    name: str
    art: str  # grundmodell | trainiert
    beschriftung: str
    methode: str | None
    daten: str | None
    erstellt: str | None
    wer: float | None
    # Der Stand, den „lernen" freigegeben hat - die Vorgabe, wenn nichts
    # gewählt ist.
    freigegeben: bool


class ModellAntwort(BaseModel):
    sprecher_id: str
    # Was gerade geladen ist - immer gefüllt, und immer einer der `ref`-Werte
    # aus `auswahl`. Früher war das Feld leer, sobald kein Stand aus „lernen"
    # lief; seit sich das Modell auswählen lässt, muss die Oberfläche den
    # aktiven Eintrag in ihrer Liste wiederfinden können, und ein Feld, das
    # dafür manchmal leer ist, wäre ein Sonderfall in jeder Ansicht.
    ref: str
    basismodell: str
    methode: str | None  # full | lora, aus dem Manifest
    daten: str | None  # original | augmentiert, aus dem Manifest
    erstellt: str | None
    wer: float | None
    laufzeit: str  # local | remote
    # Ob der Sprecher ausdrücklich gewählt hat - sonst gilt die Vorgabe.
    gewaehlt: bool
    # Ob das Diktat vor dem Erkennen ausgesteuert wird.
    aussteuern: bool
    # Eine Zeile für die Kopfzeile - hier gebaut, damit alle Ansichten
    # dieselbe Auskunft geben.
    beschriftung: str
    auswahl: list[WahlAntwort]


class Auswahl(BaseModel):
    """Was geändert werden soll. Was fehlt, bleibt, wie es war.

    Beide Felder sind eigens `None`-fähig und nicht bloß vorbelegt: Ein leeres
    `ref` heißt „zurück zur Vorgabe", und das ist etwas anderes als „das Modell
    nicht anfassen". Ohne die Unterscheidung setzte ein Umlegen des Schalters
    nebenbei die Modellwahl zurück.
    """

    ref: str | None = None
    aussteuern: bool | None = None


def _auswahl(sprecher: str) -> list[WahlAntwort]:
    return [
        WahlAntwort(
            ref=wahl.ref,
            name=wahl.name,
            art=wahl.art,
            beschriftung=wahl.beschriftung,
            methode=wahl.methode,
            daten=wahl.daten,
            erstellt=wahl.erstellt,
            wer=wahl.wer,
            freigegeben=wahl.freigegeben,
        )
        for wahl in erkennung.auswahl(einstellungen(), sprecher)
    ]


def _antwort(sprecher: str, wahl: str, ausgesteuert: bool) -> ModellAntwort:
    konfiguration = einstellungen()
    stand = modellstand(konfiguration, sprecher, wahl)
    auswahl = _auswahl(sprecher)

    if stand is None:
        # Ein Grundmodell: entweder ausdrücklich gewählt oder die Vorgabe,
        # solange „lernen" für diesen Sprecher nichts freigegeben hat.
        name = wahl or konfiguration.asr_modell
        return ModellAntwort(
            sprecher_id=sprecher,
            ref=name,
            basismodell=name,
            methode=None,
            daten=None,
            erstellt=None,
            wer=None,
            laufzeit=konfiguration.asr,
            gewaehlt=bool(wahl),
            aussteuern=ausgesteuert,
            beschriftung=f"whisper-{name} · unverändert",
            auswahl=auswahl,
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
            gewaehlt=bool(wahl),
            aussteuern=ausgesteuert,
            beschriftung=f"Modellstand {ref} nicht gefunden",
            auswahl=auswahl,
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
        gewaehlt=bool(wahl),
        aussteuern=ausgesteuert,
        beschriftung=" · ".join(
            teil
            for teil in (
                str(manifest.get("basismodell", "?")).split("/")[-1],
                methode,
                daten,
                f"Stand {str(erstellt)[:10]}" if erstellt else "",
                # Dezimalkomma: die Zeile steht in einer deutschen Oberfläche.
                f"WER {wer * 100:.1f} %".replace(".", ",") if isinstance(wer, int | float) else "",
            )
            if teil
        ),
        auswahl=auswahl,
    )


@router.get("", response_model=ModellAntwort)
def modell(sprecher: SprecherId, db: Datenbank) -> ModellAntwort:
    return _antwort(
        sprecher,
        erkennung.gewaehlt(db, einstellungen(), sprecher),
        erkennung.aussteuern(db),
    )


@router.put("", response_model=ModellAntwort)
def waehle(auswahl: Auswahl, sprecher: SprecherId, db: Datenbank) -> ModellAntwort:
    """Modell oder Aufbereitung ändern. Was nicht genannt wird, bleibt stehen.

    Beim Modell wird gegen die Liste geprüft und nicht gegen das Dateisystem:
    Wählbar ist, was diese App anbietet. Ein beliebiger Pfad im Feld wäre sonst
    ein Weg, fremde Verzeichnisse laden zu lassen - und der Stand eines anderen
    Sprechers ist fremde Stimme.
    """
    if auswahl.ref and auswahl.ref not in {
        wahl.ref for wahl in erkennung.auswahl(einstellungen(), sprecher)
    }:
        raise HTTPException(status_code=404, detail="Dieses Modell steht hier nicht zur Wahl.")

    if auswahl.ref is not None:
        erkennung.waehle(db, auswahl.ref)
    if auswahl.aussteuern is not None:
        erkennung.setze_aussteuern(db, auswahl.aussteuern)

    return _antwort(
        sprecher,
        erkennung.gewaehlt(db, einstellungen(), sprecher),
        erkennung.aussteuern(db),
    )
