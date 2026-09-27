"""Die Aufsicht: über alle Korpora sehen, sichern, umbenennen, löschen.

Alles hängt an `WORTLAUT_ADMIN_TOKEN` (`deps.py`); ohne ihn ist der Router zu.
Als einzige Wege der App nennen diese ihren Sprecher in der Adresse - die
Aufsicht hat keinen eigenen - und liegen deshalb unter `/api/admin/…`.

Kein Weg löscht mehr als einen Sprecher; gelöscht wird nur mit der Kennung als
Bestätigung. Sichern über alle geht.
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
from ..services import augmentierung, ausleitung, loeschung, pin, uebersicht, zuschnitt
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
# Das Auslesen steht in `services/uebersicht.py`, geteilt mit `api/konto.py`.


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

    Sitzungen und Aufnahmen kommen seitenweise über eigene Wege.
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

    Die Kennung bleibt - sie steckt im Zugang und in den Pfaden.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        sprecher.name = aenderung.name
        sitzung.commit()
        return uebersicht.profil(sitzung, sprecher, ablage)


@router.patch("/speakers/{sprecher_id}/pin", response_model=PinAntwort)
def setze_pin(sprecher_id: str, aenderung: PinAenderung) -> PinAntwort:
    """Die PIN einer Person setzen, ändern oder (mit `pin: null`) wegnehmen.

    Der Rückweg für eine vergessene PIN; die alte braucht es nicht.
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

    Gepackt in `services/ausleitung.py`, wie für den Sprecher selbst.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        return ausleitung.sicherung_eines(_hole(sitzung, sprecher_id))


@router.get("/sicherung")
def sicherung_aller() -> FileResponse:
    """Der ganze Bestand als **eine** `.tgz` - alle Korpora, alle Diktate.

    Die Sicherung zum Wegtragen; was sich neu rechnen lässt, bleibt draußen
    (`services/ausleitung.py`).
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

    Keine Sicherung (`services/export.py`).
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        sprecher = _hole(sitzung, sprecher_id)
        return ausleitung.datensatz_eines(sitzung, sprecher, ablage)


# ── Löschen ─────────────────────────────────────────────────────────────────
#
# Drei Stufen: eine Aufnahme, alle Aufnahmen einer Person, die Person. Eine
# Stufe „alle Personen" gibt es nicht.


@router.delete("/speakers/{sprecher_id}/recordings/{aufnahme_id}", status_code=204)
def loesche_aufnahme(sprecher_id: str, aufnahme_id: str, ablage: Ablage) -> None:
    """Eine Aufnahme wirklich löschen: Audio und Datensatz.

    Anders als beim Verwerfen (`api/recordings.py`) bleibt keine Zeile als
    Spur. Die Vorlage wird wieder offen.
    """
    with Session(engine_fuer(sprecher_id)) as sitzung:
        _hole(sitzung, sprecher_id)
        aufnahme = _hole_aufnahme(sitzung, aufnahme_id)
        ablage.loesche(aufnahme.blob)
        # Fassungen und Zuschnitt sind dieselbe Stimme.
        augmentierung.loesche(ablage, aufnahme)
        zuschnitt.loesche(ablage, aufnahme)
        sitzung.delete(aufnahme)
        sitzung.commit()


@router.delete("/speakers/{sprecher_id}/recordings", status_code=200)
def loesche_alle_aufnahmen(
    sprecher_id: str, bestaetigung: Bestaetigung, ablage: Ablage
) -> dict[str, int]:
    """Alle Aufnahmen eines Sprechers - Profil, Quellen und Vorlagen bleiben.

    „Neu anfangen": Die Warteschlange steht wieder am Anfang.
    """
    _pruefe_bestaetigung(sprecher_id, bestaetigung)
    with Session(engine_fuer(sprecher_id)) as sitzung:
        _hole(sitzung, sprecher_id)
        alle = sitzung.scalars(select(Aufnahme)).all()
        for aufnahme in alle:
            ablage.loesche(aufnahme.blob)
            augmentierung.loesche(ablage, aufnahme)
            zuschnitt.loesche(ablage, aufnahme)
        sitzung.execute(delete(Aufnahme))
        sitzung.commit()
        return {"geloescht": len(alle)}


@router.delete("/speakers/{sprecher_id}", status_code=200)
def loesche_sprecher(sprecher_id: str, bestaetigung: Bestaetigung) -> dict[str, list[str]]:
    """Eine Person vollständig löschen - Korpus, Diktate, Modelle, Schnappschüsse.

    Derselbe Umfang wie `scripts/purge_speaker.py` (`services/loeschung.py`).
    Genau eine Kennung, zur Bestätigung zweimal.
    """
    _pruefe_bestaetigung(sprecher_id, bestaetigung)
    konfiguration = einstellungen()
    if not corpus.datenbank_pfad(konfiguration.data_dir, sprecher_id).is_file():
        raise HTTPException(status_code=404, detail="Unbekannter Sprecher")

    # Erst die Engine vergessen - sie legte die Datei sonst wieder an.
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
