"""Die nächste Sprecheinheit ausliefern - samt Sitzungsverwaltung.

Eine Sitzung ist nicht mehr als ein Zeitstempelpaar: Sie hält fest, dass
aufgenommen wird, aber nicht wo. Die Position ergibt sich aus den vorhandenen
Aufnahmen (siehe `services/prompt_queue.py`), deshalb ist jede Sitzung
jederzeit unterbrechbar und an derselben Stelle fortsetzbar.
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

    # Die Sitzung ist der Startwert des Mischens: Sie überdauert ein Neuladen,
    # aber nicht den Tag, und hält die gestreute Reihenfolge damit genau so
    # lange fest, wie am Stück aufgenommen wird. Ohne Sitzung tut es der
    # Sprecher - irgendetwas Festes muss es sein.
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
    """Welche Stimmen der Server anbietet - oft keine, und das ist kein Fehler.

    Eine leere Liste ist der Normalfall einer frischen Installation: Dann liest
    der Browser vor wie bisher. Die Oberfläche stellt beides nebeneinander zur
    Wahl und sagt dazu, was der Unterschied ist (`packages/ui/Einstellungen.svelte`).

    Hinter dem Zugang und nicht offen: Die Liste verrät zwar nichts über einen
    Menschen, aber sie gehört zu einer App, die als Ganzes hinter dem Zugang
    liegt - eine Ausnahme davon wäre eine Regel mehr, die jemand prüfen muss.
    """
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


# Der Satz, an dem man eine Stimme vergleicht. Er steht **hier** und nicht im
# Browser: Sonst wäre dies ein Weg, beliebigen Text sprechen zu lassen - und
# damit Rechenzeit zu binden, ohne dass je eine Vorlage im Spiel wäre.
# Der feste Satz, an dem man Stimmen vergleicht - je Sprache einer.
#
# Er soll alltäglich klingen, geläufige Laute enthalten und kurz genug sein,
# dass man ihn zweimal hintereinander anhört, ohne die Geduld zu verlieren.
# Der englische ist bewusst dieselbe Szene: Wer beide hört, vergleicht Stimmen
# und nicht Texte.
PROBESAETZE = {
    sprachen.DEUTSCH: "Am Montag gehe ich zum Markt und kaufe frisches Brot.",
    sprachen.ENGLISCH: "On Monday I go to the market and buy fresh bread.",
}


def probesatz(sprache: str) -> str:
    return PROBESAETZE.get(sprachen.normiere(sprache), PROBESAETZE[sprachen.VORGABE])

# Was der Browser mit einer vorgelesenen Datei tun darf.
#
# Dieselbe Regel wie für die `index.html` und aus demselben Grund - `web.py`
# schreibt ihn aus: `FileResponse` schickt `ETag` und `Last-Modified`, aber
# kein `Cache-Control`, und ohne das **rät** der Browser, wie lange die Datei
# frisch bleibt. In dieser Zeit fragt er gar nicht erst nach.
#
# Hier trifft das besonders hart, weil die Adresse nicht sagt, wann gerechnet
# wurde: Sie nennt Vorlage und Stimme. Wird eine Stimme neu gesprochen - weil
# ein Modell dazukam oder ein Fehler behoben wurde -, bleibt die Adresse
# dieselbe und der Inhalt ist ein anderer. Safari auf dem iPhone hat so
# tagelang eine alte Aufnahme weitergespielt, über das Neuladen der Seite
# hinweg; der Server war längst berichtigt, und die Anfrage kam nicht an.
NICHT_OHNE_NACHFRAGE = {"Cache-Control": web.IMMER_NACHFRAGEN}


@router.get("/api/vorlesen/probe")
def hoerprobe(
    stimme: str, sprecher: SprecherId, sprache: Sprache, ablage: Ablage
) -> FileResponse:
    """Einen festen Satz in dieser Stimme - zum Vergleichen, bevor man wählt.

    Abgelegt wird das Ergebnis wie eine Vorlesung, nur unter der Kennung
    `probe`: Es ist derselbe Satz für jeden, es ändert sich nie, und beim
    zweiten Hinhören wird nichts mehr gerechnet. Dass es im Korpus des
    Sprechers liegt, ist kein Zufall - dann geht es mit ihm, wenn er geht.
    """
    konfiguration = einstellungen()
    bekannt = {
        eintrag.schluessel
        for eintrag in vorlesen.stimmen(konfiguration.stimmen_dir, konfiguration.vorlesen_motor)
    }
    if stimme not in bekannt:
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

    **Hier darf gerechnet werden, anders als beim Abhören einer Aufnahme.** Dort
    ist eine fehlende Datei ein Zeichen, dass ein Lauf sie noch nicht angelegt
    hat, und ein Abspieler ist kein Anlass, Rechenzeit zu binden. Hier ist der
    Abspieler der einzige Anlass, den es gibt: Niemand sonst fragt je nach
    diesem Satz. Piper braucht dafür den Bruchteil einer Sekunde, und beim
    zweiten Mal liegt die Datei da.

    **404 heißt: nimm die Browserstimme.** Keine Stimme abgelegt, Piper nicht
    installiert, ein Satz ohne Text - der Aufrufer unterscheidet das nicht und
    soll es nicht müssen. Vorlesen ist eine Hilfe und keine Bedingung; wer einen
    Satz nachsprechen will, soll ihn hören und keine Fehlermeldung lesen.
    """
    vorlage = db.get(Vorlage, vorlage_id)
    if vorlage is None or vorlage.speaker_id != sprecher:
        raise HTTPException(status_code=404, detail="Unbekannte Vorlage")

    konfiguration = einstellungen()
    bekannt = {
        eintrag.schluessel
        for eintrag in vorlesen.stimmen(konfiguration.stimmen_dir, konfiguration.vorlesen_motor)
    }
    if stimme not in bekannt:
        raise HTTPException(status_code=404, detail="Diese Stimme steht hier nicht zur Wahl.")

    blob = vorlesen.stelle_her(
        ablage, vorlage, stimme, konfiguration.stimmen_dir, konfiguration.vorlesen_motor
    )
    if blob is None:
        raise HTTPException(status_code=404, detail="Dieser Satz lässt sich nicht vorlesen.")
    return FileResponse(
        ablage.pfad(blob), media_type="audio/wav", headers=NICHT_OHNE_NACHFRAGE
    )
