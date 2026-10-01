"""Die nächste Sprecheinheit ausliefern - samt Sitzungsverwaltung.

Eine Sitzung ist ein Zeitstempelpaar, keine Position: Die ergibt sich aus den
Aufnahmen (`services/prompt_queue.py`), jede Sitzung ist also unterbrechbar.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from wortlaut import ids, sprachen, web

from ..config import einstellungen
from ..db.models import Sitzung, Vorlage, jetzt
from ..deps import Ablage, Datenbank, Sprache, SprecherId
from ..services import prompt_queue, vorlesen

router = APIRouter(tags=["Vorlagen"])


class SitzungAntwort(BaseModel):
    id: str
    begonnen: str


class EinheitAntwort(BaseModel):
    id: str
    text: str
    dauer_geschaetzt_s: float


class NaechsteAntwort(BaseModel):
    """Eine Einheit groß, davor und dahinter je eine blass."""

    vorher: EinheitAntwort | None
    aktuell: EinheitAntwort | None  # None heißt: nichts mehr offen
    nachher: EinheitAntwort | None
    erledigt: int
    gesamt: int


@router.post("/api/sessions", response_model=SitzungAntwort, status_code=201)
def beginne_sitzung(sprecher: SprecherId, db: Datenbank) -> SitzungAntwort:
    sitzung = Sitzung(
        id=ids.neue_id("ses"), speaker_id=sprecher, begonnen=jetzt(), zuletzt_aktiv=jetzt()
    )
    db.add(sitzung)
    db.commit()
    return SitzungAntwort(id=sitzung.id, begonnen=sitzung.begonnen)


@router.get("/api/prompts/next", response_model=NaechsteAntwort)
def naechste_einheit(
    sprecher: SprecherId, db: Datenbank, session: str | None = None, zufall: bool = False
) -> NaechsteAntwort:
    if session is not None:
        sitzung = db.get(Sitzung, session)
        if sitzung is None or sitzung.speaker_id != sprecher:
            raise HTTPException(status_code=404, detail="Unbekannte Sitzung")
        sitzung.zuletzt_aktiv = jetzt()
        db.commit()

    # Die Sitzung ist der Startwert des Mischens - sie überdauert ein Neuladen,
    # aber nicht den Tag. Ohne Sitzung tut es der Sprecher.
    ausschnitt = prompt_queue.naechste(
        db, sprecher, zufall=zufall, streuung=session or sprecher
    )
    return NaechsteAntwort(
        vorher=_als_antwort(ausschnitt.vorher),
        aktuell=_als_antwort(ausschnitt.aktuell),
        nachher=_als_antwort(ausschnitt.nachher),
        erledigt=ausschnitt.erledigt,
        gesamt=ausschnitt.gesamt,
    )


def _als_antwort(vorlage: Vorlage | None) -> EinheitAntwort | None:
    if vorlage is None:
        return None
    return EinheitAntwort(
        id=vorlage.id, text=vorlage.text, dauer_geschaetzt_s=vorlage.dauer_geschaetzt_s
    )


class StimmeAntwort(BaseModel):
    """Eine Stimme, die dieser Server sprechen kann."""

    schluessel: str
    name: str
    erklaerung: str
    sprache: str


@router.get("/api/vorlesen/stimmen", response_model=list[StimmeAntwort])
def verfuegbare_stimmen(sprecher: SprecherId) -> list[StimmeAntwort]:
    """Welche Stimmen der Server anbietet - leer heißt, der Browser liest vor
    (`packages/ui/Audio.svelte`)."""
    konfiguration = einstellungen()
    return [
        StimmeAntwort(
            schluessel=stimme.schluessel,
            name=stimme.name,
            erklaerung=stimme.erklaerung,
            sprache=stimme.sprache,
        )
        for stimme in vorlesen.stimmen(konfiguration.stimmen_dir, konfiguration.vorlesen_motor)
    ]


# Der feste Satz, an dem man Stimmen vergleicht, je Sprache - auf dem Server,
# sonst ließe die Hörprobe beliebigen Text sprechen. Alltäglich und kurz; in
# jeder Sprache dieselbe Szene.
PROBESAETZE = {
    sprachen.DEUTSCH: "Am Montag gehe ich zum Markt und kaufe frisches Brot.",
    sprachen.ENGLISCH: "On Monday I go to the market and buy fresh bread.",
}


def probesatz(sprache: str) -> str:
    return PROBESAETZE.get(sprachen.normiere(sprache), PROBESAETZE[sprachen.VORGABE])

# Vorlesungen immer nachfragen lassen (`wortlaut/web.py`): Die Adresse nennt
# Vorlage und Stimme, nicht, wann gerechnet wurde - eine neu gesprochene Datei
# hat dieselbe Adresse, und ohne `Cache-Control` spielte der Browser die alte.
NICHT_OHNE_NACHFRAGE = {"Cache-Control": web.IMMER_NACHFRAGEN}


@router.get("/api/vorlesen/probe")
def hoerprobe(
    stimme: str, sprecher: SprecherId, sprache: Sprache, ablage: Ablage
) -> FileResponse:
    """Einen festen Satz in dieser Stimme - zum Vergleichen, bevor man wählt.

    Abgelegt wie eine Vorlesung unter der Kennung `probe`, im Korpus des
    Sprechers.
    """
    konfiguration = einstellungen()
    if not vorlesen.bietet(konfiguration.stimmen_dir, konfiguration.vorlesen_motor, stimme):
        raise HTTPException(status_code=404, detail="Diese Stimme steht hier nicht zur Wahl.")

    blob = vorlesen.stelle_probe_her(
        ablage, sprecher, probesatz(sprache), stimme, konfiguration.stimmen_dir,
        konfiguration.vorlesen_motor,
    )
    if blob is None:
        raise HTTPException(status_code=404, detail="Diese Stimme spricht gerade nicht.")
    return FileResponse(
        ablage.pfad(blob), media_type="audio/wav", headers=NICHT_OHNE_NACHFRAGE
    )


@router.get("/api/prompts/{vorlage_id}/vorlesung")
def hoere_vorlage(
    vorlage_id: str, stimme: str, sprecher: SprecherId, db: Datenbank, ablage: Ablage
) -> FileResponse:
    """Diese Vorlage in dieser Stimme - gerechnet, falls sie noch nicht vorliegt.

    Anders als beim Abhören einer Aufnahme wird hier gerechnet: Niemand sonst
    fragt nach diesem Satz, und Piper braucht einen Bruchteil einer Sekunde.
    404 heißt: nimm die Browserstimme.
    """
    vorlage = db.get(Vorlage, vorlage_id)
    if vorlage is None or vorlage.speaker_id != sprecher:
        raise HTTPException(status_code=404, detail="Unbekannte Vorlage")

    konfiguration = einstellungen()
    if not vorlesen.bietet(konfiguration.stimmen_dir, konfiguration.vorlesen_motor, stimme):
        raise HTTPException(status_code=404, detail="Diese Stimme steht hier nicht zur Wahl.")

    blob = vorlesen.stelle_her(
        ablage, vorlage, stimme, konfiguration.stimmen_dir, konfiguration.vorlesen_motor
    )
    if blob is None:
        raise HTTPException(status_code=404, detail="Dieser Satz lässt sich nicht vorlesen.")
    return FileResponse(
        ablage.pfad(blob), media_type="audio/wav", headers=NICHT_OHNE_NACHFRAGE
    )
