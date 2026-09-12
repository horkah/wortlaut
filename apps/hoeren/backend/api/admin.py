"""Die Aufsicht: über alle Korpora sehen, sichern, umbenennen, löschen.

Alles hier hängt an `WORTLAUT_ADMIN_TOKEN` (siehe `deps.py`). Ohne gesetzten
Token ist dieser ganze Router zu - auch in der Entwicklung.

Der Unterschied zu jedem anderen Weg dieser App: Hier steht der Sprecher
**in der Adresse**. Er ist nicht abgeleitet, weil die Aufsicht keinen eigenen
hat; sie sieht über alle hinweg. Damit das nicht die stille Verwechslung
zurückholt, gegen die der Zugang als Kennung angetreten ist, liegen diese Wege
unter einem eigenen Präfix und nirgends sonst: Wer `/api/admin/…` liest, sieht
sofort, dass hier jemand von außen auf einen fremden Korpus schaut.

**Eine Grenze gibt es, und sie ist absichtlich hart:** Es gibt keinen Weg, der
mehr als einen Sprecher löscht. Sichern über alle geht, löschen nur einzeln,
und auch das nur mit der Kennung als Bestätigung im Aufruf. Ein Versehen soll
höchstens eine Person kosten, nie den ganzen Bestand.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from wortlaut import corpus, sicherung

from ..config import einstellungen
from ..db.models import Aufnahme, Sprecher
from ..deps import Ablage, Aufsicht, engine_fuer, vergiss_engine
from ..services import augmentierung, ausleitung, loeschung, pin, uebersicht
from ..services.pin import PinAenderung, PinAntwort
from ..services.uebersicht import (
    SEITE,
    AufnahmenAntwort,
    QuelleAntwort,
    SitzungenAntwort,
    UebersichtAntwort,
    Umbenennung,
)

router = APIRouter(prefix="/api/admin", tags=["Aufsicht"], dependencies=[Aufsicht])

Bestaetigung = Annotated[
    str,
    Query(
        description=(
            "Zur Bestätigung die Kennung des Sprechers wiederholen. "
            "Löschen ist nicht rückgängig zu machen."
        )
    ),
]


# ── Ansehen ─────────────────────────────────────────────────────────────────
#
# Die Modelle und das Auslesen selbst - Profil, Kennzahlen, Textquellen,
# Sitzungen, Aufnahmen - stehen in `services/uebersicht.py`: „hören" zeigt
# dieselben Daten noch an einer zweiten Stelle, dem Sprecher selbst
# (`api/konto.py`), und beide sollen dieselbe Zählung benutzen.


class EinsichtAntwort(BaseModel):
    sprecher: UebersichtAntwort
    quellen: list[QuelleAntwort]


@router.get("/speakers", response_model=list[UebersichtAntwort])
def uebersicht_aller(ablage: Ablage) -> list[UebersichtAntwort]:
    """Alle Sprecher mit dem Umfang ihrer Daten - die Startseite der Aufsicht."""
    antworten = []
    for sprecher_id in corpus.sprecher_ids(einstellungen().data_dir):
        with Session(engine_fuer(sprecher_id)) as sitzung:
            sprecher = sitzung.get(Sprecher, sprecher_id)
            if sprecher is not None:
                antworten.append(uebersicht.profil(sitzung, sprecher, ablage))
    return antworten


@router.get("/speakers/{sprecher_id}", response_model=EinsichtAntwort)
def einsicht(sprecher_id: str, ablage: Ablage) -> EinsichtAntwort:
    """Was in der Datenbank **eines** Sprechers steht: Profil und Quellen.

    Sitzungen und Aufnahmen stehen nicht darin, sondern hinter eigenen Wegen:
    Es können Hunderte oder Tausende sein, und sie sind das Einzige, was
    seitenweise geholt werden muss.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        return EinsichtAntwort(
            sprecher=uebersicht.profil(sitzung, sprecher, ablage),
            quellen=uebersicht.quellen(sitzung),
        )


@router.get("/speakers/{sprecher_id}/sessions", response_model=SitzungenAntwort)
def sitzungen(sprecher_id: str, ab: int = 0, anzahl: int = SEITE) -> SitzungenAntwort:
    """Die Sitzungen eines Sprechers, jüngste zuerst, seitenweise."""
    with Session(engine_fuer(sprecher_id)) as sitzung:
        _hole(sitzung, sprecher_id)
        return uebersicht.sitzungen_seite(sitzung, ab, anzahl)


@router.get("/speakers/{sprecher_id}/recordings", response_model=AufnahmenAntwort)
def aufnahmen(
    sprecher_id: str, ablage: Ablage, ab: int = 0, anzahl: int = SEITE
) -> AufnahmenAntwort:
    """Die Aufnahmen eines Sprechers, neueste zuerst, seitenweise."""
    with Session(engine_fuer(sprecher_id)) as sitzung:
        _hole(sitzung, sprecher_id)
        return uebersicht.aufnahmen_seite(sitzung, ablage, ab, anzahl)


@router.get("/speakers/{sprecher_id}/recordings/{aufnahme_id}/audio")
def abhoeren(sprecher_id: str, aufnahme_id: str, ablage: Ablage) -> FileResponse:
    """Hineinhören, bevor gelöscht wird - sonst löscht die Aufsicht blind."""
    with Session(engine_fuer(sprecher_id)) as sitzung:
        _hole(sitzung, sprecher_id)
        aufnahme = _hole_aufnahme(sitzung, aufnahme_id)
        pfad = ablage.pfad(aufnahme.blob)
    if not pfad.is_file():
        raise HTTPException(status_code=404, detail="Zu dieser Aufnahme liegt kein Audio mehr.")
    return FileResponse(pfad, media_type="audio/wav")


# ── Umbenennen ──────────────────────────────────────────────────────────────


@router.patch("/speakers/{sprecher_id}", response_model=UebersichtAntwort)
def benenne_um(sprecher_id: str, aenderung: Umbenennung, ablage: Ablage) -> UebersichtAntwort:
    """Nur der Name ändert sich.

    Die Kennung bleibt, was sie ist: Sie steckt in jedem ausgegebenen Zugang,
    in den Pfaden der Ablage und in der `.env` von „schreiben". Ein Name ist
    eine Beschriftung, eine Kennung ist eine Zusage.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        sprecher.name = aenderung.name
        sitzung.commit()
        return uebersicht.profil(sitzung, sprecher, ablage)


@router.patch("/speakers/{sprecher_id}/pin", response_model=PinAntwort)
def setze_pin(sprecher_id: str, aenderung: PinAenderung) -> PinAntwort:
    """Die PIN einer Person setzen, ändern oder (mit `pin: null`) wegnehmen.

    Anders als beim eigenen Weg (`api/konto.py`) unter keinem eigenen Vorbehalt:
    Die Aufsicht ist der Rückweg, wenn jemand seine PIN vergessen oder aus
    Versehen eine falsche eingetippt hat, und braucht dafür nicht die alte.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        sprecher.pin_hash = pin.pruefwert(aenderung.pin) if aenderung.pin is not None else None
        sitzung.commit()
        return PinAntwort(gesetzt=sprecher.pin_hash is not None)


# ── Sichern und ausleiten ───────────────────────────────────────────────────


@router.get("/speakers/{sprecher_id}/sicherung")
def sicherung_eines(sprecher_id: str) -> FileResponse:
    """Der vollständige Stand eines Sprechers als `.tgz` - zum Zurückspielen.

    Gepackt wird in `services/ausleitung.py`: Denselben Griff hat ein Sprecher
    für seine eigenen Daten (`api/konto.py`), und beide sollen dieselbe Datei
    bekommen.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        return ausleitung.sicherung_eines(_hole(sitzung, sprecher_id))


@router.get("/sicherung")
def sicherung_aller() -> FileResponse:
    """Der ganze Bestand als **eine** `.tgz` - alle Korpora, alle Diktate.

    Das ist die Sicherung, die man wegträgt: Ein Server weniger, und dieses
    eine Archiv stellt alles wieder her. Nicht darin ist, was sich neu rechnen
    lässt - Modellstände, abgewandelte Fassungen, Messwerte der Auswertung
    (`services/ausleitung.py`). Was unwiederbringlich ist, sind die Aufnahmen,
    und die sind vollzählig drin.
    """
    konfiguration = einstellungen()
    kennungen = corpus.sprecher_ids(konfiguration.data_dir)
    sprecher_liste = []
    verzeichnisse: list[str] = []
    for sprecher_id in kennungen:
        verzeichnisse.extend(loeschung.datenverzeichnisse(sprecher_id))
        with Session(engine_fuer(sprecher_id)) as sitzung:
            sprecher = sitzung.get(Sprecher, sprecher_id)
            if sprecher is not None:
                sprecher_liste.append(ausleitung.kurz(sprecher))

    beschreibung = {"umfang": "gesamt", "sprecher": sprecher_liste}
    return ausleitung.archiv(
        f"wortlaut-gesamt-{sicherung.zeitmarke()}.tgz",
        lambda ziel: sicherung.schreibe_archiv(
            konfiguration.data_dir,
            verzeichnisse,
            ziel,
            beschreibung=beschreibung,
            ohne=ausleitung.abgeleitet(kennungen),
        ),
        "application/gzip",
    )


@router.get("/speakers/{sprecher_id}/datensatz")
def datensatz(sprecher_id: str, ablage: Ablage) -> FileResponse:
    """Text-Audio-Paare als `.zip` - für Training und Ansehen von außen.

    Keine Sicherung, sondern ein Auszug in Ordnerform (siehe
    `services/export.py`).
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        return ausleitung.datensatz_eines(sitzung, sprecher, ablage)


# ── Löschen ─────────────────────────────────────────────────────────────────
#
# Drei Stufen, jede enger als die vorige: eine Aufnahme, alle Aufnahmen einer
# Person, die Person. Eine vierte Stufe „alle Personen" gibt es nicht und soll
# es nicht geben - sie wäre ein Knopf, der einmal im Leben gedrückt wird, und
# dann versehentlich.


@router.delete("/speakers/{sprecher_id}/recordings/{aufnahme_id}", status_code=204)
def loesche_aufnahme(sprecher_id: str, aufnahme_id: str, ablage: Ablage) -> None:
    """Eine Aufnahme wirklich löschen: Audio und Datensatz.

    Der Unterschied zum Verwerfen durch den Sprecher (`api/recordings.py`):
    Dort bleibt die Zeile als Spur stehen, damit die Warteschlange die Vorlage
    wieder anbietet. Hier räumt jemand auf - dann soll auch nichts stehen
    bleiben. Die Vorlage wird dadurch ebenfalls wieder offen.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        _hole(sitzung, sprecher_id)
        aufnahme = _hole_aufnahme(sitzung, aufnahme_id)
        ablage.loesche(aufnahme.blob)
        # Samt der abgewandelten Fassungen: Dieselbe Stimme, nur lauter oder
        # verrauscht, ist derselbe Gesundheitsdatensatz.
        augmentierung.loesche(ablage, aufnahme)
        sitzung.delete(aufnahme)
        sitzung.commit()


@router.delete("/speakers/{sprecher_id}/recordings", status_code=200)
def loesche_alle_aufnahmen(
    sprecher_id: str, bestaetigung: Bestaetigung, ablage: Ablage
) -> dict[str, int]:
    """Alle Aufnahmen eines Sprechers - Profil, Quellen und Vorlagen bleiben.

    Danach steht die Warteschlange wieder ganz am Anfang: Der Text ist noch da,
    gesprochen ist nichts mehr. Das ist der Fall „neu anfangen", nicht der Fall
    „Person löschen" - dafür gibt es den Weg darunter.
    """
    _pruefe_bestaetigung(sprecher_id, bestaetigung)
    with Session(engine_fuer(sprecher_id)) as sitzung:
        _hole(sitzung, sprecher_id)
        alle = sitzung.scalars(select(Aufnahme)).all()
        for aufnahme in alle:
            ablage.loesche(aufnahme.blob)
            augmentierung.loesche(ablage, aufnahme)
        sitzung.execute(delete(Aufnahme))
        sitzung.commit()
        return {"geloescht": len(alle)}


@router.delete("/speakers/{sprecher_id}", status_code=200)
def loesche_sprecher(sprecher_id: str, bestaetigung: Bestaetigung) -> dict[str, list[str]]:
    """Eine Person vollständig löschen - Korpus, Diktate, Modelle, Schnappschüsse.

    Dasselbe, was `scripts/purge_speaker.py` auf der Kommandozeile tut; beide
    fragen `services/loeschung.py`, damit es nicht zwei Vorstellungen davon
    gibt, was zu einer Person gehört.

    Es gibt hier bewusst keine Mehrzahl: Der Weg nimmt genau eine Kennung, und
    die muss zur Bestätigung ein zweites Mal dastehen. Wer zwei Personen
    löschen will, tut es zweimal - und denkt dabei zweimal nach.
    """
    _pruefe_bestaetigung(sprecher_id, bestaetigung)
    konfiguration = einstellungen()
    if not corpus.datenbank_pfad(konfiguration.data_dir, sprecher_id).is_file():
        raise HTTPException(status_code=404, detail="Unbekannter Sprecher")

    # Erst die Verbindung aus dem Zwischenspeicher nehmen: Eine offene Engine
    # auf eine gelöschte Datei legte die Datei beim nächsten Zugriff wieder an.
    vergiss_engine(sprecher_id)
    entfernt = loeschung.loesche(konfiguration.data_dir, sprecher_id)
    return {
        "geloescht": [str(pfad) for pfad in entfernt],
        "zu_pruefen": [str(pfad) for pfad in loeschung.ohne_marke(konfiguration.data_dir)],
    }


# ── Innereien ───────────────────────────────────────────────────────────────


def _hole(sitzung: Session, sprecher_id: str) -> Sprecher:
    sprecher = sitzung.get(Sprecher, sprecher_id)
    if sprecher is None:
        raise HTTPException(status_code=404, detail="Unbekannter Sprecher")
    return sprecher


def _hole_aufnahme(sitzung: Session, aufnahme_id: str) -> Aufnahme:
    aufnahme = sitzung.get(Aufnahme, aufnahme_id)
    if aufnahme is None:
        raise HTTPException(status_code=404, detail="Unbekannte Aufnahme")
    return aufnahme


def _pruefe_bestaetigung(sprecher_id: str, bestaetigung: str) -> None:
    """Die Kennung muss zweimal dastehen - einmal als Ziel, einmal als Absicht."""
    if bestaetigung != sprecher_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Zum Löschen muss `bestaetigung` die Kennung des Sprechers wiederholen "
                f"({sprecher_id})."
            ),
        )
