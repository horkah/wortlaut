"""Die fertigen Modellstände eines Sprechers - und welcher freigegeben ist.

Ein Modellstand ist ein Verzeichnis (`wortlaut/registry.py`), kein
Datenbankeintrag: etwas, das man kopieren, sichern und per `scp` verschieben
kann. Diese Wege lesen daraus und setzen genau ein Feld - `status`.

**Warum Freigeben ein eigener Schritt ist.** Ein fertig gerechnetes Modell ist
noch keines, das jemand benutzen soll. Zwischen „das Training ist
durchgelaufen" und „damit diktiere ich" liegt der Blick auf die Zahlen, und den
nimmt einem nichts ab. Freigeben ist deshalb ein Knopf und keine Folge des
Fertigwerdens.

**Warum trotzdem mehrere nebeneinander stehen bleiben.** Vier Läufe ergeben
vier Stände (zwei Methoden mal zwei Datensätze), und die Frage, welcher der
beste ist, beantwortet man nicht, indem man drei wegwirft. Freigegeben ist
höchstens einer - das ist der, den „schreiben" von sich aus nimmt. Die übrigen
lassen sich dort ausdrücklich auswählen (siehe `apps/schreiben/backend/api/model.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from wortlaut import registry

from ..config import einstellungen
from ..deps import SprecherId

router = APIRouter(prefix="/lernen/api/modelle", tags=["Modelle"])


class StandAntwort(BaseModel):
    id: str
    version: str
    basismodell: str
    methode: str
    daten: str
    erstellt: str
    status: str
    wer: float | None
    genauigkeit: float | None
    test_einheiten: int | None
    job_id: str | None
    # Eine Zeile, wie sie in einer Liste steht - hier gebaut, damit „lernen"
    # und „schreiben" denselben Namen für denselben Stand zeigen.
    beschriftung: str


class ListeAntwort(BaseModel):
    staende: list[StandAntwort]


def _als_antwort(manifest: dict) -> StandAntwort:
    metriken = manifest.get("metriken") or {}
    kennung = str(manifest.get("id", "/"))
    version = kennung.split("/", 1)[-1]
    return StandAntwort(
        id=kennung,
        version=version,
        basismodell=str(manifest.get("basismodell", "?")),
        methode=str(manifest.get("methode", "?")),
        daten=str(manifest.get("daten", "?")),
        erstellt=str(manifest.get("erstellt", "")),
        status=str(manifest.get("status", "fertig")),
        wer=metriken.get("wer"),
        genauigkeit=metriken.get("genauigkeit"),
        test_einheiten=metriken.get("test_einheiten"),
        job_id=manifest.get("job_id"),
        beschriftung=beschriftung(manifest),
    )


def beschriftung(manifest: dict) -> str:
    """Wie ein Stand heißt, wenn er in einer Zeile stehen muss.

    Basismodell, Methode, Datensatz und Datum - vier Angaben, weil vier Stände
    nebeneinander liegen, die sich in genau diesen Punkten unterscheiden. Ein
    Datum allein sagte nicht, welcher von den vieren gemeint ist.
    """
    methode = {"full": "voll", "lora": "LoRA"}.get(str(manifest.get("methode")), "?")
    daten = {"original": "Originale", "augmentiert": "mit Abwandlungen"}.get(
        str(manifest.get("daten")), "?"
    )
    grund = str(manifest.get("basismodell", "?")).rsplit("/", 1)[-1]
    datum = str(manifest.get("erstellt", ""))[:10]
    return f"{grund} · {methode} · {daten} · {datum}"


@router.get("", response_model=ListeAntwort)
def liste(sprecher: SprecherId) -> ListeAntwort:
    return ListeAntwort(
        staende=[
            _als_antwort(manifest)
            for manifest in registry.alle_staende(einstellungen().data_dir, sprecher)
        ]
    )


@router.post("/{version}/freigabe", response_model=ListeAntwort)
def gib_frei(version: str, sprecher: SprecherId) -> ListeAntwort:
    """Diesen Stand freigeben - und damit jeden anderen zurückziehen.

    Höchstens einer je Sprecher: `registry.aktiver_stand` nimmt sonst den
    jüngsten und ließe offen, welcher gemeint war. Geschrieben wird in beide
    Manifeste, denn das Manifest ist die Wahrheit über den Stand - eine Liste
    daneben wäre eine zweite.
    """
    datenverzeichnis = einstellungen().data_dir
    staende = registry.alle_staende(datenverzeichnis, sprecher)
    if not any(str(stand.get("id", "")).endswith(f"/{version}") for stand in staende):
        raise HTTPException(status_code=404, detail="Unbekannter Modellstand.")

    for stand in staende:
        soll = str(stand.get("id", "")).endswith(f"/{version}")
        stand["status"] = "active" if soll else "zurueckgezogen"
        registry.schreibe_stand(datenverzeichnis, stand)

    return liste(sprecher)
