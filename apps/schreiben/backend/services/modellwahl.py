"""Welches Modell dieser Sprecher benutzt - und welche zur Wahl stehen.

Drei Herkünfte laufen hier zusammen, und die Reihenfolge ist die Rangfolge:

1. **Was der Sprecher gewählt hat** (`modellwahl`, siehe `002_modellwahl.sql`).
   Er hat sie ausdrücklich getroffen; sie gilt.
2. **`WORTLAUT_MODELL_REF`**, falls gesetzt - der eine Stand, der für alle
   gilt. Gedacht zum Erproben, nicht für den Betrieb; er sticht die Wahl
   deshalb **nicht**, sondern steht nur an ihrer Stelle, wenn keine getroffen
   wurde. Wäre es andersherum, sähe ein Sprecher eine Auswahl, die nichts tut.
3. **Der freigegebene Stand aus „lernen"** - die Vorgabe für jemanden, der nie
   etwas ausgewählt hat, und der Sinn des Freigebens.

Darunter liegt das unveränderte Grundmodell: Ohne alles davon fängt eine
Installation mit `whisper-small` an.

**Warum überhaupt gewählt werden darf.** Eine Person bekommt inzwischen vier
trainierte Stände (zwei Methoden mal zwei Datensätze) und daneben die
unveränderten Grundmodelle. Welcher davon ihr am besten zuhört, beantwortet
keine Kennzahl allein - das beantwortet sich beim Diktieren. Was dabei nicht
aufgegeben wird: Zu jeder Ausgabe steht fest, welches Modell sie erzeugt hat.
Die Kopfzeile nennt es dauerhaft, samt Methode und Datensatz.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session
from wortlaut import registry

from ..config import Einstellungen
from ..db.models import Modellwahl, jetzt

# Ein Stand aus der Registry heißt `<sprecher_id>/<version>`; ein Whisper-Name
# enthält keinen Schrägstrich. Daran allein sind beide zu unterscheiden - und
# das ist der Grund, warum beide im selben Feld stehen dürfen.
TRENNER = "/"


@dataclass(frozen=True)
class Wahl:
    """Ein wählbares Modell, wie die Oberfläche es anbietet."""

    ref: str
    name: str
    art: str  # grundmodell | trainiert
    beschriftung: str
    methode: str | None = None
    daten: str | None = None
    erstellt: str | None = None
    wer: float | None = None
    freigegeben: bool = False


def ist_stand(ref: str) -> bool:
    return TRENNER in ref


def gewaehlt(db: Session) -> str:
    """Was der Sprecher gewählt hat; leer heißt: nichts, es gilt die Vorgabe."""
    zeile = db.get(Modellwahl, 1)
    return zeile.ref if zeile is not None else ""


def waehle(db: Session, ref: str) -> None:
    """Die Wahl setzen. Leer setzt sie zurück auf die Vorgabe."""
    zeile = db.get(Modellwahl, 1)
    if not ref:
        if zeile is not None:
            db.delete(zeile)
            db.commit()
        return
    if zeile is None:
        db.add(Modellwahl(id=1, ref=ref, gewaehlt=jetzt()))
    else:
        zeile.ref, zeile.gewaehlt = ref, jetzt()
    db.commit()


def grundmodelle(konfiguration: Einstellungen) -> list[str]:
    namen = [teil.strip() for teil in konfiguration.auswertung_modelle.split(",") if teil.strip()]
    # Das konfigurierte Grundmodell steht immer zur Wahl, auch wenn es nicht in
    # der Messreihe steht - sonst fehlte ausgerechnet das, was ohne jede Wahl
    # läuft.
    if konfiguration.asr_modell not in namen:
        namen.append(konfiguration.asr_modell)
    return namen


def _stand_wahl(manifest: dict) -> Wahl:
    metriken = manifest.get("metriken") or {}
    methode = {"full": "voll", "lora": "LoRA"}.get(str(manifest.get("methode")), "?")
    daten = {"original": "Originale", "augmentiert": "mit Abwandlungen"}.get(
        str(manifest.get("daten")), "?"
    )
    erstellt = str(manifest.get("erstellt", ""))
    grund = str(manifest.get("basismodell", "?")).rsplit("/", 1)[-1]
    return Wahl(
        ref=str(manifest.get("id", "")),
        name=str(manifest.get("id", "")).split(TRENNER, 1)[-1],
        art="trainiert",
        beschriftung=f"{grund} · {methode} · {daten} · {erstellt[:10]}",
        methode=manifest.get("methode"),
        daten=manifest.get("daten"),
        erstellt=erstellt,
        wer=metriken.get("wer"),
        freigegeben=manifest.get("status") == "active",
    )


def auswahl(konfiguration: Einstellungen, sprecher_id: str) -> list[Wahl]:
    """Alles, was dieser Sprecher laden kann - Grundmodelle zuerst.

    Grundmodelle zuerst, weil sie die Grundlinie sind: Wer vergleichen will,
    vergleicht gegen sie. Die trainierten Stände darunter, jüngster zuletzt -
    dieselbe Reihenfolge wie in „lernen", damit dieselbe Liste nicht zweimal
    verschieden aussieht.
    """
    staende = [
        _stand_wahl(manifest)
        for manifest in registry.alle_staende(konfiguration.data_dir, sprecher_id)
    ]
    return [
        *(
            Wahl(
                ref=name,
                name=name,
                art="grundmodell",
                beschriftung=f"whisper-{name} · unverändert",
            )
            for name in grundmodelle(konfiguration)
        ),
        *staende,
    ]
