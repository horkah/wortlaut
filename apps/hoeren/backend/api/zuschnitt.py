"""Die Wege der Ansicht „Editieren": eine Aufnahme zuschneiden oder teilen.

Diese Wege zeigen den Lautstärkeverlauf einer Aufnahme, schlagen die Grenzen
der Stimme vor und schreiben, was ein Mensch daraus macht; was mit den Dateien
geschieht, steht in `services/zuschnitt.py`.

**Der Schlüssel** (`WORTLAUT_EDITOR_KEY`, `X-Editor-Key`) steht vor allen Wegen,
auch den lesenden: Zuschneiden und Teilen ersetzen Aufnahmen, und das trägt
der Sprecherzugang auf einem Telefon nicht; schon die Ansicht ist die Werkbank.

**Beim Schreiben**, je Aufnahme: die Datei überschrieben, die Zeile aus der
neuen Datei nachgeführt, die Messwerte weg - auch
übernommene Faltungen, wie beim Verwerfen (`api/recordings.py`). Der nächste
Auswertungslauf rechnet neu.

**Beim Teilen** entstehen neue Aufnahmen, und das Original geht: Zeile,
Datei, Messwerte und seine Vorlage (`teilen`).

Den Ausschnitt spielt der Browser aus der geladenen Datei ab
(`packages/ui/ausschnitt.ts`); vorläufige Dateien auf dem Server gibt es
nicht.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from wortlaut import audio as klang
from wortlaut import corpus, ids, schluessel
from wortlaut.text import chunker

from ..config import einstellungen
from ..db.models import GUELTIG, Aufnahme, Erkennung, jetzt, Vorlage
from ..deps import Ablage, Datenbank, Sprache, SprecherId
from ..services import quality, zuschnitt
from ..services.prompt_queue import naechste_position

router = APIRouter(prefix="/api/zuschnitt", tags=["Zuschnitt"])


def _pruefe_schluessel(
    vorgelegt: Annotated[str | None, Header(alias=schluessel.BEARBEITUNG.kopf)] = None,
) -> None:
    """Wächter aller Wege dieser Datei (`wortlaut.schluessel`)."""
    schluessel.BEARBEITUNG.verlange(einstellungen().editor_key, vorgelegt)


Schluessel = Depends(_pruefe_schluessel)


class ZuschnittAntwort(BaseModel):
    """Eine Aufnahme, wie „Editieren" sie braucht."""

    id: str
    text: str
    erstellt: str
    dauer_s: float
    # Der Lautstärkeverlauf, ein Wert je Fenster, bezogen auf Vollausschlag.
    verlauf: list[float]
    fenster_s: float
    # Ab wann ein Fenster als Stimme zählt - als blasse Linie gezeichnet.
    schwelle: float
    # Der Vorschlag nach dem Pegel (`audio.stimmgrenzen`).
    vorschlag_start_s: float
    vorschlag_ende_s: float


class Grenze(BaseModel):
    """Wohin eine einzelne Aufnahme geschnitten werden soll."""

    id: str
    start_s: float
    ende_s: float


class Auftrag(BaseModel):
    grenzen: list[Grenze]


class Teilung(BaseModel):
    """Wo eine Aufnahme geteilt wird - im Ton und im Text."""

    id: str
    start_s: float
    teilung_s: float
    ende_s: float
    # Die Texte der Teile, womöglich berichtigt; leer nur bei einem Teil ohne Länge.
    text_vorn: str = ""
    text_hinten: str = ""


class Teile(BaseModel):
    """Die Kennungen der beiden neuen Aufnahmen, vorderer Teil zuerst."""

    ids: list[str]


class Ergebnis(BaseModel):
    geschrieben: int
    # Was nicht ging, je Aufnahme ein Satz; die übrigen gelten.
    fehler: dict[str, str]


def _zeile(ablage: Ablage, aufnahme: Aufnahme, vorlage: Vorlage) -> ZuschnittAntwort | None:
    """Eine Aufnahme mit Kurve und Vorschlag; `None`, wenn es nichts zu zeigen gibt."""
    pfad = ablage.pfad(aufnahme.blob)
    if not pfad.is_file():
        return None
    try:
        kurve = klang.verlauf(pfad)
    except klang.AudioFehler:
        return None
    vorschlag = klang.stimmgrenzen(kurve)
    return ZuschnittAntwort(
        id=aufnahme.id,
        text=vorlage.text,
        erstellt=aufnahme.erstellt,
        dauer_s=kurve.dauer_s,
        verlauf=[round(wert, 5) for wert in kurve.werte],
        fenster_s=kurve.fenster_s,
        schwelle=round(kurve.schwelle, 5),
        vorschlag_start_s=round(vorschlag[0], 3),
        vorschlag_ende_s=round(vorschlag[1], 3),
    )


def _eigene(db: Datenbank, sprecher: str, aufnahme_id: str) -> Aufnahme:
    """Eine brauchbare Aufnahme dieses Sprechers - oder 404."""
    aufnahme = db.get(Aufnahme, aufnahme_id)
    if aufnahme is None or aufnahme.speaker_id != sprecher or aufnahme.status != GUELTIG:
        raise HTTPException(status_code=404, detail="Unbekannte Aufnahme")
    return aufnahme


@router.get(
    "/aufnahmen/{aufnahme_id}", response_model=ZuschnittAntwort, dependencies=[Schluessel]
)
def eine(sprecher: SprecherId, aufnahme_id: str, db: Datenbank, ablage: Ablage) -> ZuschnittAntwort:
    """Eine Aufnahme mit Kurve und Vorschlag."""
    aufnahme = _eigene(db, sprecher, aufnahme_id)
    vorlage = db.get(Vorlage, aufnahme.prompt_id)
    zeile = _zeile(ablage, aufnahme, vorlage) if vorlage is not None else None
    if zeile is None:
        raise HTTPException(status_code=404, detail="Zu dieser Aufnahme liegt kein Audio mehr.")
    return zeile


@router.get("/aufnahmen/{aufnahme_id}/original", dependencies=[Schluessel])
def original(
    sprecher: SprecherId, aufnahme_id: str, db: Datenbank, ablage: Ablage
) -> FileResponse:
    """Die Datei der Aufnahme - zum Abspielen in der Ansicht, ganz oder im Ausschnitt."""
    aufnahme = _eigene(db, sprecher, aufnahme_id)
    pfad = ablage.pfad(aufnahme.blob)
    if not pfad.is_file():
        raise HTTPException(status_code=404, detail="Zu dieser Aufnahme liegt kein Audio mehr.")
    return FileResponse(pfad, media_type="audio/wav")


@router.post("/schreiben", response_model=Ergebnis, dependencies=[Schluessel])
def schreiben(auftrag: Auftrag, sprecher: SprecherId, db: Datenbank, ablage: Ablage) -> Ergebnis:
    """Aufnahmen auf ihre Grenzen kürzen - die Originale werden überschrieben.

    Was außerhalb der Grenzen lag, ist danach weg; ein zweiter Schnitt kann
    nur noch weiter nach innen.

    **Jede Aufnahme für sich.** Eine, die scheitert, nimmt die anderen nicht
    mit; sie steht in `fehler` und ist unverändert geblieben. Ein Auftrag über
    zwanzig Aufnahmen, der an der siebten ganz abbräche, hinterließe sechs
    geschriebene und dreizehn offene, ohne dass jemand sähe, welche welche
    sind - dieselbe Arbeit zweimal, beim zweiten Mal im Blindflug.
    """
    geschrieben = 0
    fehler: dict[str, str] = {}

    for grenze in auftrag.grenzen:
        aufnahme = db.get(Aufnahme, grenze.id)
        if aufnahme is None or aufnahme.speaker_id != sprecher or aufnahme.status != GUELTIG:
            fehler[grenze.id] = "Unbekannte Aufnahme."
            continue
        vorlage = db.get(Vorlage, aufnahme.prompt_id)
        if vorlage is None:
            fehler[grenze.id] = "Zu dieser Aufnahme fehlt die Vorlage."
            continue
        try:
            zuschnitt.schneide(ablage, aufnahme, vorlage, grenze.start_s, grenze.ende_s)
        except klang.AudioFehler as ursache:
            db.rollback()
            fehler[grenze.id] = str(ursache)
            continue

        # Die Messwerte am alten Ton weg, sonst gälten sie als erledigt.
        db.execute(delete(Erkennung).where(Erkennung.recording_id == aufnahme.id))
        db.commit()
        geschrieben += 1

    return Ergebnis(geschrieben=geschrieben, fehler=fehler)


def _woerter(text: str) -> list[str]:
    return text.split()


def _stuecke(teilung: Teilung) -> list[tuple[int, str]]:
    """Welche Teile entstehen: `(nummer, text)`, 1 für vorn, 2 für hinten.

    Liegt die Teilung auf Anfang oder Ende, entsteht nur der andere Teil -
    eine Kopie mit eigenem Text. Der Text darf von der Vorlage abweichen, denn
    gemessen wird gegen ihn; geändert wird nur die Vorlage der neuen Aufnahme.
    """
    if not teilung.start_s <= teilung.teilung_s <= teilung.ende_s:
        raise HTTPException(
            status_code=400, detail="Die Teilung muss zwischen Anfang und Ende liegen."
        )
    leer_vorn = teilung.teilung_s <= teilung.start_s
    leer_hinten = teilung.teilung_s >= teilung.ende_s
    if leer_vorn and leer_hinten:
        raise HTTPException(status_code=400, detail="Der Ausschnitt hat keine Länge.")
    stuecke = [
        (nummer, " ".join(_woerter(text)))
        for nummer, text, leer in (
            (1, teilung.text_vorn, leer_vorn),
            (2, teilung.text_hinten, leer_hinten),
        )
        if not leer
    ]
    if any(not text for _, text in stuecke):
        raise HTTPException(status_code=400, detail="Jeder Teil, der entsteht, braucht Text.")
    return stuecke


def _naechste_nummer(db: Datenbank, stamm: str) -> int:
    """Die erste freie Nummer unter einem Original - ein zweites Teilen hängt hinten an.

    Sonst trügen die Teile eines zweiten Durchgangs dieselben Schlüssel wie
    die des ersten, und wer von beiden oben steht, entschiede der Zufall.
    """
    vorhanden = db.scalars(
        select(Aufnahme.sortierschluessel).where(Aufnahme.sortierschluessel.like(f"{stamm}.%"))
    ).all()
    nummern = [
        int(rest)
        for schluessel in vorhanden
        if schluessel and (rest := schluessel[len(stamm) + 1 :]).isdigit()
    ]
    return max(nummern, default=0) + 1


@router.post("/teilen", response_model=Teile, dependencies=[Schluessel])
def teilen(
    teilung: Teilung, sprecher: SprecherId, sprache: Sprache, db: Datenbank, ablage: Ablage
) -> Teile:
    """Eine Aufnahme durch zwei neue ersetzen - Ton und Text. Oder durch eine.

    Für eine Aufnahme mit zwei Äußerungen. Jeder Teil bekommt eigene Datei
    und eigene Vorlage in derselben Quelle, damit er zählt wie das Original,
    dazu dessen Datum und einen Sortierschlüssel darunter. Pegel und Hinweise
    kommen aus den neuen Dateien; gemessen wird beim nächsten Auswertungslauf.

    Das Original geht danach ganz (`_entferne`): Seine Teile stehen an seiner
    Stelle, und sein Satz käme sonst wieder in die Warteschlange.
    """
    original = _eigene(db, sprecher, teilung.id)
    vorlage = db.get(Vorlage, original.prompt_id)
    if vorlage is None:
        raise HTTPException(status_code=404, detail="Zu dieser Aufnahme fehlt die Vorlage.")
    stuecke = _stuecke(teilung)

    kennungen = [ids.neue_id("rec") for _ in stuecke]
    ziele = [corpus.audio_relpfad(sprecher, kennung) for kennung in kennungen]
    try:
        if len(stuecke) == 2:
            befunde = zuschnitt.teile(
                ablage, original, teilung.start_s, teilung.teilung_s, teilung.ende_s, *ziele
            )
        else:
            befunde = (
                zuschnitt.kopiere(ablage, original, teilung.start_s, teilung.ende_s, ziele[0]),
            )
    except klang.AudioFehler as fehler:
        for ziel in ziele:
            ablage.loesche(ziel)
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler

    stamm = original.sortierschluessel or original.id
    erste = _naechste_nummer(db, stamm)
    position = naechste_position(db, sprecher)
    for nummer, (kennung, ziel, befund, (_, text)) in enumerate(
        zip(kennungen, ziele, befunde, stuecke, strict=True), start=erste
    ):
        neue_vorlage = Vorlage(
            id=ids.neue_id("prm"),
            source_id=vorlage.source_id,
            speaker_id=sprecher,
            position=position + nummer - erste,
            text=text,
            dauer_geschaetzt_s=chunker.dauer(text, sprache),
            erstellt=jetzt(),
        )
        db.add(neue_vorlage)
        db.flush()
        teil = Aufnahme(
            id=kennung,
            prompt_id=neue_vorlage.id,
            speaker_id=sprecher,
            session_id=original.session_id,
            blob=ziel,
            **asdict(befund),
            modus=original.modus,
            status=GUELTIG,
            hinweise=json.dumps(
                quality.pruefe(befund, neue_vorlage.dauer_geschaetzt_s), ensure_ascii=False
            ),
            externe_id=None,
            # Ein Teil einer Korrektur ist so oft gesprochen wie sie.
            anlaeufe=original.anlaeufe,
            sortierschluessel=f"{stamm}.{nummer}",
            erstellt=original.erstellt,
        )
        db.add(teil)
    db.flush()
    blob = _entferne(db, original)
    db.commit()
    # Die Datei erst, wenn die Zeilen sicher stehen - sonst fehlte sie einer
    # Zeile, die ein gescheitertes Commit stehen ließe.
    ablage.loesche(blob)

    return Teile(ids=kennungen)


def _entferne(db: Datenbank, aufnahme: Aufnahme) -> str:
    """Eine Aufnahme aus dem Bestand nehmen, samt Messwerten und - wenn sonst
    keine gültige Aufnahme an ihr hängt - ihrer Vorlage.

    Verworfene Zeilen derselben Vorlage gehen mit: Sie hielten die Vorlage
    fest, und die stünde dann wieder in der Warteschlange. Gibt den Pfad der
    Datei zurück; die löscht der Aufrufer nach dem Commit.
    """
    vorlage_id, blob = aufnahme.prompt_id, aufnahme.blob
    db.execute(delete(Erkennung).where(Erkennung.recording_id == aufnahme.id))
    db.delete(aufnahme)
    db.flush()
    an_der_vorlage = db.scalars(select(Aufnahme).where(Aufnahme.prompt_id == vorlage_id)).all()
    if not any(andere.status == GUELTIG for andere in an_der_vorlage):
        for andere in an_der_vorlage:
            db.execute(delete(Erkennung).where(Erkennung.recording_id == andere.id))
            db.delete(andere)
        if (vorlage := db.get(Vorlage, vorlage_id)) is not None:
            db.delete(vorlage)
    return blob
