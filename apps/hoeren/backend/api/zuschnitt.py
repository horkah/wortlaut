"""Die Zuschnittansicht: Stille an den Rändern sehen, hören und wegschneiden.

Aufgenommen wird äußerungsweise, mit einem Knopf davor und einem danach.
Zwischen dem Druck und dem ersten Laut liegt regelmäßig eine Sekunde, hinten
oft mehr - und bei jemandem, der langsam spricht und den Knopf schlecht
trifft, deutlich mehr. Das wird mittrainiert und mitgemessen, obwohl niemand
es gesprochen hat.

Diese Wege zeigen den Lautstärkeverlauf jeder Aufnahme, schlagen Anfang und
Ende der Stimme vor und schreiben, was ein Mensch daraus gemacht hat. Was mit
den Dateien geschieht, steht in `services/zuschnitt.py`; hier steht, wer das
darf und in welcher Reihenfolge es passiert.

## Der Schlüssel

Vor dem Schreiben steht ein zweites Geheimnis (`WORTLAUT_EDITOR_KEY`,
Kopfzeile `X-Editor-Key`) - dieselbe Bauart wie der Trainerschlüssel in
„lernen" und aus demselben Grund. Der Zugang eines Sprechers beantwortet
„wessen Aufnahmen?"; er ist an jeden ausgegeben, der aufnimmt, und liegt auf
einem Telefon. Er beantwortet nicht „wer darf in den Bestand greifen?" - und
genau das tut ein Zuschnitt: Er entscheidet für jede folgende Messung und
jedes folgende Training, welcher Ton gilt, und er wirft die vorhandenen
Messwerte weg.

Anders als in „lernen" hängt der Schlüssel hier vor **allen** Wegen dieser
Datei, auch den lesenden. Dort ist Zusehen das, was jeder darf, und nur das
Rechnenlassen kostet; hier ist auch das Ansehen schon die Werkbank - eine
Liste mit Kurven, Reglern und einem Knopf „Schreiben" darunter. Sie jemandem
zu zeigen, der sie nicht bedienen darf, wäre keine Offenheit, sondern eine
Einladung zum Fehlgriff.

## Die Reihenfolge beim Schreiben

Zuerst der Schnitt, dann die Zeile, dann das Abgeleitete:

1. Die zugeschnittene Datei entsteht aus dem **Original** (`zuschnitt.schneide`).
2. Die Grenzen kommen in die Zeile - ab hier gilt der Zuschnitt überall.
3. Die abgewandelten Fassungen werden verworfen und neu gerechnet: Sie sind
   aus der Arbeitsdatei abgeleitet, und die ist eine andere geworden.
4. Die Messwerte dieser Aufnahme werden gelöscht. Sie wurden am ungeschnittenen
   Ton gemessen und beschreiben eine Datei, mit der von nun an niemand mehr
   arbeitet. Der nächste Auswertungslauf rechnet sie neu - er rechnet ohnehin
   nur, was fehlt (`services/auswertung.py`).

Punkt 4 ist derselbe Griff wie beim Verwerfen einer Aufnahme
(`api/recordings.py`): Wer den Ton ändert, wirft weg, was Modelle aus dem
alten gemacht haben. Übernommene Faltungsmessungen gehen mit und kommen nicht
wieder - was der Korpus nicht mehr führt, holt die Auswertung nicht zurück.

## Warum das Abspielen des Ausschnitts nichts kostet

Es gibt hier keinen Weg, der eine vorläufige Datei schreibt. Der Browser hat
die ganze Aufnahme ohnehin geladen, um die Kurve zu zeichnen; den Ausschnitt
daraus spielt er selbst ab (`packages/ui/Pegelverlauf.svelte`). Temporäre
Dateien auf dem Server wären Gesundheitsdaten mit ungeklärter Lebensdauer -
für ein Ergebnis, das ohne sie schneller da ist.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from wortlaut import audio as klang

from ..config import einstellungen
from ..db.models import Aufnahme, Erkennung, Vorlage
from ..deps import Ablage, Datenbank, SprecherId
from ..services import augmentierung, zuschnitt

router = APIRouter(prefix="/api/zuschnitt", tags=["Zuschnitt"])

# Der Kopf, in dem der Schlüssel steht. Nicht `Authorization`: Dort liegt schon
# der Sprecherzugang, und aus ihm leitet der Server ab, wessen Aufnahmen das
# sind (`deps.py`). Zwei Geheimnisse in einem Kopf hießen, das eine gegen das
# andere zu tauschen - dieselbe Überlegung wie bei `X-Trainer-Key`.
SCHLUESSEL_KOPF = "X-Editor-Key"

# Wie viele Aufnahmen eine Seite höchstens trägt. Zehn ist die Vorgabe der
# Oberfläche; darüber hinaus darf sie mehr anfordern, aber nicht beliebig
# viel - je Aufnahme geht ein Lautstärkeverlauf mit, und der wird aus der
# Datei gerechnet.
SEITE_MAX = 100


def _pruefe_schluessel(
    x_editor_key: Annotated[str | None, Header()] = None,
) -> None:
    """Wächter aller Wege dieser Datei.

    Nicht gesetzt heißt abgeschaltet - kein Zuschneiden für niemanden, auch
    nicht in der Entwicklung (die Begründung steht bei `editor_key` in der
    `config.py`). Die Oberfläche fragt `GET .../stand` vorher ab und zeigt den
    Punkt dann gar nicht erst.

    Zeitkonstant verglichen und über die UTF-8-Bytes, wie überall in diesem
    Projekt: Sonst verriete die Antwortzeit den Anfang des Schlüssels, und ein
    Umlaut darin ergäbe einen 500er statt eines sauberen 401.
    """
    erwartet = einstellungen().editor_key
    if not erwartet:
        raise HTTPException(
            status_code=401,
            detail=(
                "Der Zuschnitt ist abgeschaltet: Auf diesem Server ist kein "
                "Bearbeitungsschlüssel hinterlegt (WORTLAUT_EDITOR_KEY)."
            ),
        )
    vorgelegt = x_editor_key or ""
    if not secrets.compare_digest(vorgelegt.encode("utf-8"), erwartet.encode("utf-8")):
        raise HTTPException(
            status_code=401, detail="Falscher oder fehlender Bearbeitungsschlüssel."
        )


Schluessel = Depends(_pruefe_schluessel)


class StandAntwort(BaseModel):
    """Ob auf diesem Server überhaupt zugeschnitten werden kann."""

    bereit: bool
    hinweis: str


class ZuschnittAntwort(BaseModel):
    """Eine Aufnahme, wie die Zuschnittansicht sie braucht."""

    id: str
    text: str
    erstellt: str
    # Die Dauer des Originals. Sie ist die Breite der Kurve und der Maßstab
    # für jede Zeitmarke darin - auch dann, wenn schon zugeschnitten wurde:
    # Geschnitten wird immer wieder aus dem Original (`zuschnitt.schneide`).
    dauer_s: float
    # Der Lautstärkeverlauf, ein Wert je Fenster, bezogen auf Vollausschlag.
    verlauf: list[float]
    fenster_s: float
    # Ab welchem Wert ein Fenster als Stimme zählt - die Ansicht zeichnet sie
    # als blasse Linie, damit sichtbar wird, woher der Vorschlag kommt.
    schwelle: float
    # Wo die Stimme nach dem Pegel anfängt und aufhört. Ein Vorschlag, keine
    # Festlegung (siehe `audio.stimmgrenzen`).
    vorschlag_start_s: float
    vorschlag_ende_s: float
    # Was in der Zeile steht - `null`, solange niemand geschnitten hat.
    zuschnitt_start_s: float | None
    zuschnitt_ende_s: float | None


class Seite(BaseModel):
    gesamt: int
    ab: int
    aufnahmen: list[ZuschnittAntwort]


class Grenze(BaseModel):
    """Wohin eine einzelne Aufnahme geschnitten werden soll."""

    id: str
    start_s: float
    ende_s: float


class Auftrag(BaseModel):
    grenzen: list[Grenze]


class Ergebnis(BaseModel):
    geschrieben: int
    # Was nicht ging, je Aufnahme ein Satz. Ein Fehlgriff bei einer von zwanzig
    # soll die anderen neunzehn nicht zurücknehmen - er soll nur dastehen.
    fehler: dict[str, str]


@router.get("/stand", response_model=StandAntwort)
def stand() -> StandAntwort:
    """Ob zugeschnitten werden kann - ohne Wächter, denn davon hängt ab, ob gefragt wird.

    Dieselbe Rolle wie `GET /api/konto/pin`: Die Oberfläche muss wissen, ob sie
    nach einem Schlüssel fragen soll, bevor sie danach fragen kann. Ausgegeben
    wird dabei nichts als ein Ja oder Nein - der Schlüssel selbst steht hier
    nicht, und auch nicht seine Länge.
    """
    if einstellungen().editor_key:
        return StandAntwort(bereit=True, hinweis="")
    return StandAntwort(
        bereit=False,
        hinweis=(
            "Der Zuschnitt ist auf diesem Server abgeschaltet: "
            "WORTLAUT_EDITOR_KEY ist nicht gesetzt."
        ),
    )


@router.get("/aufnahmen", response_model=Seite, dependencies=[Schluessel])
def aufnahmen(
    sprecher: SprecherId, db: Datenbank, ablage: Ablage, ab: int = 0, anzahl: int = 10
) -> Seite:
    """Die eigenen Aufnahmen mit Kurve, Vorschlag und bisherigem Zuschnitt.

    Älteste zuerst, und das ist der Unterschied zu „Meine Daten", wo die
    neueste oben steht. Hier wird eine Liste **abgearbeitet**, nicht
    nachgesehen: Wer sich durch seinen Korpus schneidet, will beim nächsten Mal
    dort weitermachen, wo er aufgehört hat, und nicht von einer Seite begrüßt
    werden, die sich durch jede neue Aufnahme verschiebt.

    Gerechnet wird je Zeile ein Lautstärkeverlauf - das ist ein Durchgang über
    die Abtastwerte einer Datei von wenigen Sekunden, für eine Seite von zehn
    also Millisekunden. Nur für die Seite, die gerade gezeigt wird: Über einen
    ganzen Korpus wäre es eine Wartezeit, und niemand sieht tausend Kurven auf
    einmal an.

    Fehlt zu einer Aufnahme das Audio (verworfen), entfällt sie - es gibt
    nichts zu schneiden. Fehlt die zugeschnittene Datei, während die Zeile
    einen Zuschnitt führt, entsteht sie hier neu (`zuschnitt.stelle_her`); das
    ist der eine Ort, an dem so ein Bestand sich selbst einholt.
    """
    gueltig = Aufnahme.status == "ok"
    gesamt = db.scalar(select(func.count()).select_from(Aufnahme).where(gueltig)) or 0
    treffer = db.execute(
        select(Aufnahme, Vorlage)
        .join(Vorlage, Vorlage.id == Aufnahme.prompt_id)
        .where(gueltig)
        .order_by(Aufnahme.erstellt)
        .offset(max(ab, 0))
        .limit(min(max(anzahl, 1), SEITE_MAX))
    ).all()

    zeilen = []
    nachgeholt = False
    for aufnahme, vorlage in treffer:
        pfad = ablage.pfad(aufnahme.blob)
        if not pfad.is_file():
            continue
        try:
            kurve = klang.verlauf(pfad)
            nachgeholt |= zuschnitt.stelle_her(ablage, aufnahme)
        except klang.AudioFehler:
            # Eine unlesbare Datei ist ein Befund und kein Grund, die Seite
            # hinzuwerfen - die übrigen Aufnahmen sind davon unberührt.
            continue
        vorschlag = klang.stimmgrenzen(kurve)
        zeilen.append(
            ZuschnittAntwort(
                id=aufnahme.id,
                text=vorlage.text,
                erstellt=aufnahme.erstellt,
                dauer_s=kurve.dauer_s,
                verlauf=[round(wert, 5) for wert in kurve.werte],
                fenster_s=kurve.fenster_s,
                schwelle=round(kurve.schwelle, 5),
                vorschlag_start_s=round(vorschlag[0], 3),
                vorschlag_ende_s=round(vorschlag[1], 3),
                zuschnitt_start_s=aufnahme.zuschnitt_start_s,
                zuschnitt_ende_s=aufnahme.zuschnitt_ende_s,
            )
        )
    if nachgeholt:
        db.commit()

    return Seite(gesamt=gesamt, ab=max(ab, 0), aufnahmen=zeilen)


@router.get("/aufnahmen/{aufnahme_id}/original", dependencies=[Schluessel])
def original(
    sprecher: SprecherId, aufnahme_id: str, db: Datenbank, ablage: Ablage
) -> FileResponse:
    """Das ungeschnittene Original - die eine Stelle, die es ausdrücklich liefert.

    Überall sonst liefert `GET /api/recordings/{id}/audio` die **Arbeitsdatei**
    (`services/zuschnitt.py`), und das soll auch so bleiben: Wer eine Aufnahme
    anhört, soll hören, was gilt.

    Hier ist es umgekehrt, und zwar notwendig: Diese Ansicht zeichnet die Kurve
    des Originals und setzt zwei Linien hinein. Bekäme sie den Zuschnitt, wäre
    die Kurve so breit wie das letzte Ergebnis, und die Grenzen ließen sich nur
    noch nach innen schieben - ein zweiter Durchgang könnte einen zu engen
    Schnitt nicht mehr aufmachen. Geschnitten wird immer aus dem Original, also
    wird auch immer das Original gezeigt.
    """
    aufnahme = db.get(Aufnahme, aufnahme_id)
    if aufnahme is None or aufnahme.speaker_id != sprecher or aufnahme.status != "ok":
        raise HTTPException(status_code=404, detail="Unbekannte Aufnahme")
    pfad = ablage.pfad(aufnahme.blob)
    if not pfad.is_file():
        raise HTTPException(status_code=404, detail="Zu dieser Aufnahme liegt kein Audio mehr.")
    return FileResponse(pfad, media_type="audio/wav")


@router.post("/schreiben", response_model=Ergebnis, dependencies=[Schluessel])
def schreiben(auftrag: Auftrag, sprecher: SprecherId, db: Datenbank, ablage: Ablage) -> Ergebnis:
    """Die markierten Zuschnitte in den Bestand schreiben.

    Ab hier arbeitet jede App mit den geschnittenen Dateien: die Auswertung in
    „hören", das Manifest eines Trainingslaufs in „lernen", der Datensatz zum
    Mitnehmen und das Anhören in „Meine Daten". Das Original bleibt liegen und
    unverändert.

    Lag zu einer Aufnahme schon ein Zuschnitt, wird er ersetzt - geschnitten
    wird erneut aus dem Original, nicht aus dem vorherigen Ergebnis. Sonst
    wanderte die Grenze mit jedem Durchgang nach innen.

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
        if aufnahme is None or aufnahme.speaker_id != sprecher or aufnahme.status != "ok":
            fehler[grenze.id] = "Unbekannte Aufnahme."
            continue
        try:
            zuschnitt.schneide(ablage, aufnahme, grenze.start_s, grenze.ende_s)
        except klang.AudioFehler as ursache:
            db.rollback()
            fehler[grenze.id] = str(ursache)
            continue

        # Die Abwandlungen sind aus der Arbeitsdatei abgeleitet, und die ist
        # eine andere geworden: erst wegräumen, dann neu rechnen. Ohne das
        # erste passiert das zweite nicht - `stelle_her` lässt eine vorhandene
        # Datei stehen (`services/augmentierung.py`).
        augmentierung.loesche(ablage, aufnahme)

        # Und mit dem Ton gehen die Messwerte. Sie entstanden am
        # ungeschnittenen Klang und beschreiben eine Datei, mit der von nun an
        # niemand mehr arbeitet; stehen zu bleiben hieße, dass die Auswertung
        # sie für erledigt hält und nie neu rechnet (`_fertig` in
        # `services/auswertung.py`). Derselbe Griff wie beim Verwerfen einer
        # Aufnahme - übernommene Faltungsmessungen gehen mit und kommen nicht
        # wieder.
        db.execute(delete(Erkennung).where(Erkennung.recording_id == aufnahme.id))
        db.commit()
        geschrieben += 1

        # Nach dem Commit und nicht davor, wie beim Hochladen einer Aufnahme:
        # Die Fassungen sind abgeleitet und jederzeit neu zu rechnen, der
        # Zuschnitt ist es nicht mehr, sobald er in der Zeile steht. Scheitert
        # das Rechnen, holt der nächste Auswertungslauf es ohnehin nach.
        try:
            augmentierung.stelle_alle_her(ablage, aufnahme)
        except klang.AudioFehler:
            pass

    return Ergebnis(geschrieben=geschrieben, fehler=fehler)


@router.post("/zuruecknehmen", response_model=Ergebnis, dependencies=[Schluessel])
def zuruecknehmen(auftrag: Auftrag, sprecher: SprecherId, db: Datenbank, ablage: Ablage) -> Ergebnis:
    """Zuschnitte verwerfen; ab dann gelten wieder die Originale.

    Der Rückweg zu `schreiben`, und er ist kein Luxus: Ein Zuschnitt ist eine
    Entscheidung über den ganzen folgenden Bestand, und eine Entscheidung ohne
    Rückweg ist ein Unfall mit Bedenkzeit. Möglich ist er, weil das Original
    liegen bleibt - es ist nie überschrieben worden.

    Dieselben drei Schritte wie beim Schreiben, in derselben Reihenfolge und
    mit derselben Begründung: Datei und Zeile zurück, Abwandlungen neu, Zahlen
    weg. Auch das Zurücknehmen ändert die Arbeitsdatei.

    `grenzen` trägt hier nur Kennungen; `start_s` und `ende_s` werden nicht
    gelesen. Eine eigene Form für eine Liste von Kennungen wäre eine zweite
    Gestalt derselben Auswahl - die Ansicht schickt schlicht, was markiert ist.
    """
    geschrieben = 0
    fehler: dict[str, str] = {}

    for grenze in auftrag.grenzen:
        aufnahme = db.get(Aufnahme, grenze.id)
        if aufnahme is None or aufnahme.speaker_id != sprecher:
            fehler[grenze.id] = "Unbekannte Aufnahme."
            continue
        if not zuschnitt.nimm_zurueck(ablage, aufnahme):
            continue

        augmentierung.loesche(ablage, aufnahme)
        db.execute(delete(Erkennung).where(Erkennung.recording_id == aufnahme.id))
        db.commit()
        geschrieben += 1

        try:
            augmentierung.stelle_alle_her(ablage, aufnahme)
        except klang.AudioFehler:
            pass

    return Ergebnis(geschrieben=geschrieben, fehler=fehler)
