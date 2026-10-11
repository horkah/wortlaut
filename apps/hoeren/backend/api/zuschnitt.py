"""Die Wege der Ansicht „Editieren": eine Aufnahme kürzen, teilen, ihren Text berichtigen.

Diese Wege zeigen den Lautstärkeverlauf einer Aufnahme, schlagen die Grenzen
der Stimme vor und schreiben, was ein Mensch daraus macht; was mit den Dateien
geschieht, steht in `services/zuschnitt.py`.

**Der Schlüssel** (`WORTLAUT_EDITOR_KEY`, `X-Editor-Key`) steht vor allen Wegen,
auch den lesenden: Kürzen und Teilen ersetzen Aufnahmen, und das trägt der
Sprecherzugang auf einem Telefon nicht; schon die Ansicht ist die Werkbank.

**Gespeichert wird in einem Schritt** (`speichern`): Bis dahin hat nichts im
Editor eine Folge. Der Text steht danach an der Aufnahme (`recordings.text`),
die Vorlage bleibt unberührt; eine Korrektur aus „schreiben" gilt danach als
geprüft (`recordings.validiert`).

* **Ohne Teilung** bleibt es eine Aufnahme: die Datei auf Anfang und Ende
  gekürzt und überschrieben. Ändern sich Ton oder Text, gehen ihre
  Messwerte - auch übernommene Faltungen, wie beim Verwerfen
  (`api/recordings.py`). Der nächste Auswertungslauf rechnet neu.
* **Mit Teilung** entstehen zwei neue Aufnahmen an derselben Vorlage, und das
  Original geht: Zeile, Datei, Messwerte. Die Teile tragen die Kennungen
  aller Vorfahren und liegen in der Faltung des Originals.

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
from ..db.models import GUELTIG, Aufnahme, Erkennung, Textquelle, Vorlage, jetzt
from ..deps import Ablage, Datenbank, Sprache, SprecherId
from ..services import quality, uebersicht, zuschnitt

router = APIRouter(prefix="/api/zuschnitt", tags=["Zuschnitt"])

# Woher eine Aufnahme ihren Text hat, wenn er aus dem Sprechen kommt und nicht
# aus einer Vorlage (`api/intake.py`).
KORREKTUR = "korrektur"

# Was beim Vergleich von Grenzen als „dieselbe Stelle" gilt - weniger als ein
# Rahmen der Kurve.
GENAUIGKEIT_S = 1e-3


def _pruefe_schluessel(
    vorgelegt: Annotated[str | None, Header(alias=schluessel.BEARBEITUNG.kopf)] = None,
) -> None:
    """Wächter aller Wege dieser Datei (`wortlaut.schluessel`)."""
    schluessel.BEARBEITUNG.verlange(einstellungen().editor_key, vorgelegt)


Schluessel = Depends(_pruefe_schluessel)


class ZuschnittAntwort(BaseModel):
    """Eine Aufnahme, wie „Editieren" sie braucht."""

    id: str
    # Was gesagt wurde (`Aufnahme.text_zu`) - Vorbelegung des Textfelds.
    text: str
    erstellt: str
    # Wann zuletzt gespeichert; leer heißt nie.
    geaendert: str | None
    dauer_s: float
    # Der Stand der Datei; hängt an der Adresse des Audios, damit der Browser
    # nach einem Schnitt nicht die alte Fassung aus seinem Speicher nimmt.
    version: str
    # Ob der Text aus dem Sprechen kommt - dann prüft ihn das Speichern.
    korrektur: bool
    validiert: bool
    # Der Lautstärkeverlauf, ein Wert je Fenster, bezogen auf Vollausschlag.
    verlauf: list[float]
    fenster_s: float
    # Ab wann ein Fenster als Stimme zählt - als blasse Linie gezeichnet.
    schwelle: float
    # Der Vorschlag nach dem Pegel (`audio.stimmgrenzen`) - für „Auto".
    vorschlag_start_s: float
    vorschlag_ende_s: float
    # Wie gut das Modell von „schreiben" sie gehört hat - wie in „Meine Daten"
    # (`services/uebersicht.py`); leer, solange nicht gemessen.
    qualitaet: float | None = None
    modell: str = ""
    skala: uebersicht.Skala = uebersicht.Skala()


class Speichern(BaseModel):
    """Was aus einer Aufnahme werden soll - Ton und Text in einem Schritt."""

    id: str
    start_s: float
    ende_s: float
    # Ohne Teilung bleibt es eine Aufnahme.
    teilung_s: float | None = None
    # Ein Text je Aufnahme, die danach steht: einer, mit Teilung zwei.
    texte: list[str]


class Gespeichert(BaseModel):
    """Die Kennungen der Aufnahmen, die danach stehen, vordere zuerst."""

    ids: list[str]


def version(ablage: Ablage, aufnahme: Aufnahme) -> str:
    """Der Stand einer Datei: Zeit und Größe. Leer, wenn sie fehlt."""
    pfad = ablage.pfad(aufnahme.blob)
    if not pfad.is_file():
        return ""
    stand = pfad.stat()
    return f"{stand.st_mtime_ns:x}-{stand.st_size:x}"


def _ist_korrektur(db: Datenbank, vorlage: Vorlage) -> bool:
    quelle = db.get(Textquelle, vorlage.source_id)
    return quelle is not None and quelle.art == KORREKTUR


def _zeile(
    db: Datenbank, ablage: Ablage, aufnahme: Aufnahme, vorlage: Vorlage
) -> ZuschnittAntwort | None:
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
        text=aufnahme.text_zu(vorlage),
        erstellt=aufnahme.erstellt,
        geaendert=aufnahme.geaendert,
        dauer_s=kurve.dauer_s,
        version=version(ablage, aufnahme),
        korrektur=_ist_korrektur(db, vorlage),
        validiert=bool(aufnahme.validiert),
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
    zeile = _zeile(db, ablage, aufnahme, vorlage) if vorlage is not None else None
    if zeile is None:
        raise HTTPException(status_code=404, detail="Zu dieser Aufnahme liegt kein Audio mehr.")
    modell = uebersicht.diktiermodell(sprecher)
    zeile.modell = modell
    zeile.skala = uebersicht.skala(db, modell)
    zeile.qualitaet = db.scalar(
        select(Erkennung.genauigkeit).where(
            Erkennung.recording_id == aufnahme.id, Erkennung.modell == modell
        )
    )
    return zeile


@router.get("/aufnahmen/{aufnahme_id}/original", dependencies=[Schluessel])
def original(
    sprecher: SprecherId, aufnahme_id: str, db: Datenbank, ablage: Ablage
) -> FileResponse:
    """Die Datei der Aufnahme - zum Abspielen in der Ansicht, ganz oder im Ausschnitt.

    `no-cache`: Der Browser fragt jedes Mal nach, ob seine Fassung noch gilt.
    """
    aufnahme = _eigene(db, sprecher, aufnahme_id)
    pfad = ablage.pfad(aufnahme.blob)
    if not pfad.is_file():
        raise HTTPException(status_code=404, detail="Zu dieser Aufnahme liegt kein Audio mehr.")
    return FileResponse(pfad, media_type="audio/wav", headers={"Cache-Control": "no-cache"})


def _texte(auftrag: Speichern) -> list[str]:
    """Die Texte, an Leerraum geglättet - je Aufnahme einer, keiner leer."""
    texte = [" ".join(text.split()) for text in auftrag.texte]
    if len(texte) != (1 if auftrag.teilung_s is None else 2):
        raise HTTPException(
            status_code=400, detail="Ein Text je Aufnahme - mit Teilung zwei, sonst einer."
        )
    if not all(texte):
        raise HTTPException(status_code=400, detail="Jede Aufnahme braucht Text.")
    return texte


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


@router.post("/speichern", response_model=Gespeichert, dependencies=[Schluessel])
def speichern(
    auftrag: Speichern, sprecher: SprecherId, sprache: Sprache, db: Datenbank, ablage: Ablage
) -> Gespeichert:
    """Kürzen, teilen, den Text berichtigen - was der Editor zeigt, in einem Schritt.

    Gekürzt wird nur nach innen; ein Schnitt lässt sich nicht zurücknehmen.
    """
    aufnahme = _eigene(db, sprecher, auftrag.id)
    vorlage = db.get(Vorlage, aufnahme.prompt_id)
    if vorlage is None:
        raise HTTPException(status_code=404, detail="Zu dieser Aufnahme fehlt die Vorlage.")
    if not 0.0 <= auftrag.start_s < auftrag.ende_s <= aufnahme.dauer_s + GENAUIGKEIT_S:
        raise HTTPException(status_code=400, detail="Anfang und Ende liegen nicht in der Aufnahme.")
    texte = _texte(auftrag)
    korrektur = _ist_korrektur(db, vorlage)

    if auftrag.teilung_s is None:
        return _ohne_teilung(auftrag, texte[0], korrektur, sprache, aufnahme, vorlage, db, ablage)
    return _geteilt(auftrag, texte, korrektur, sprache, aufnahme, db, ablage)


def _ohne_teilung(
    auftrag: Speichern,
    text: str,
    korrektur: bool,
    sprache: str,
    aufnahme: Aufnahme,
    vorlage: Vorlage,
    db: Datenbank,
    ablage: Ablage,
) -> Gespeichert:
    """Eine Aufnahme bleibt: gekürzt, wenn die Marken innen stehen, mit ihrem Text."""
    gekuerzt = (
        auftrag.start_s > GENAUIGKEIT_S or auftrag.ende_s < aufnahme.dauer_s - GENAUIGKEIT_S
    )
    neuer_text = text != aufnahme.text_zu(vorlage)
    erwartet = chunker.dauer(text, sprache)
    if gekuerzt:
        try:
            zuschnitt.schneide(ablage, aufnahme, auftrag.start_s, auftrag.ende_s, erwartet)
        except klang.AudioFehler as ursache:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(ursache)) from ursache
    elif neuer_text:
        zuschnitt.pruefe_neu(aufnahme, erwartet)
    aufnahme.text = text
    aufnahme.geaendert = jetzt()
    if korrektur:
        aufnahme.validiert = True
    if gekuerzt or neuer_text:
        # Die Messwerte am alten Ton oder Text weg, sonst gälten sie als erledigt.
        db.execute(delete(Erkennung).where(Erkennung.recording_id == aufnahme.id))
    db.commit()
    return Gespeichert(ids=[aufnahme.id])


def _geteilt(
    auftrag: Speichern,
    texte: list[str],
    korrektur: bool,
    sprache: str,
    original: Aufnahme,
    db: Datenbank,
    ablage: Ablage,
) -> Gespeichert:
    """Zwei neue Aufnahmen an derselben Vorlage, und das Original geht.

    Jeder Teil bekommt eigene Datei und eigenen Text, dazu das Datum des
    Originals und einen Sortierschlüssel darunter. Pegel und Hinweise kommen
    aus den neuen Dateien; gemessen wird beim nächsten Auswertungslauf.

    Das Original geht danach ganz (`zuschnitt.entferne`); seine Vorlage bleibt
    bei den Teilen, die jetzt ihre gültigen Aufnahmen sind - sie kommt nicht
    wieder in die Warteschlange. Jeder Teil trägt die Kennungen des Originals
    und all seiner Vorfahren (`zuschnitt.vorfahren`) - kein Stand, der einen
    davon im Training hatte, wird an ihm gemessen. Über den Stamm im
    Sortierschlüssel liegen die Teile in der Faltung des Originals.
    """
    teilung_s = float(auftrag.teilung_s or 0.0)
    if not auftrag.start_s < teilung_s < auftrag.ende_s:
        raise HTTPException(
            status_code=400, detail="Die Teilung muss zwischen Anfang und Ende liegen."
        )
    kennungen = [ids.neue_id("rec") for _ in texte]
    ziele = [corpus.audio_relpfad(original.speaker_id, kennung) for kennung in kennungen]
    try:
        befunde = zuschnitt.teile(
            ablage, original, auftrag.start_s, teilung_s, auftrag.ende_s, *ziele
        )
    except klang.AudioFehler as fehler:
        for ziel in ziele:
            ablage.loesche(ziel)
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler

    stamm = original.sortierschluessel or original.id
    erste = _naechste_nummer(db, stamm)
    for nummer, (kennung, ziel, befund, text) in enumerate(
        zip(kennungen, ziele, befunde, texte, strict=True), start=erste
    ):
        db.add(
            Aufnahme(
                id=kennung,
                prompt_id=original.prompt_id,
                speaker_id=original.speaker_id,
                session_id=original.session_id,
                blob=ziel,
                **asdict(befund),
                modus=original.modus,
                status=GUELTIG,
                hinweise=json.dumps(
                    quality.pruefe(befund, chunker.dauer(text, sprache)), ensure_ascii=False
                ),
                externe_id=None,
                # Ein Teil einer Korrektur ist so oft gesprochen wie sie.
                anlaeufe=original.anlaeufe,
                sortierschluessel=f"{stamm}.{nummer}",
                vorfahren=zuschnitt.nachfahren_von(original),
                text=text,
                validiert=korrektur or bool(original.validiert),
                # Das Datum der Aufnahme bleibt; geändert ist sie jetzt.
                erstellt=original.erstellt,
                geaendert=jetzt(),
            )
        )
    db.flush()
    blob = zuschnitt.entferne(db, original)
    db.commit()
    # Die Datei erst, wenn die Zeilen sicher stehen - sonst fehlte sie einer
    # Zeile, die ein gescheitertes Commit stehen ließe.
    ablage.loesche(blob)

    return Gespeichert(ids=kennungen)
