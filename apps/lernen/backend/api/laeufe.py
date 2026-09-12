"""Läufe beauftragen und ihnen zusehen.

Vier Wege, und sie teilen sich die Arbeit nach dem, wie oft sie gebraucht
werden - dieselbe Aufteilung wie in der Auswertung von „hören":

* `GET  /lernen/api/laeufe`          die Liste: je Lauf Auftrag und Stand.
  Sie wird abgefragt, solange die Seite offen ist, und trägt deshalb **keine**
  Kurven: Bei zwölf Läufen mit je tausend Schritten wäre das bei jedem Takt ein
  Vielfaches dessen, was gemeint ist.
* `GET  /lernen/api/laeufe/{id}`     ein Lauf im Einzelnen: Kurven, Bewertung,
  Vergleich mit der Grundlinie.
* `POST /lernen/api/laeufe`          einen Lauf beauftragen.
* `POST /lernen/api/laeufe/{id}/abbruch`  einen wartenden zurücknehmen.
* `DELETE /lernen/api/laeufe/{id}`   einen Lauf ersatzlos entfernen, samt dem
  Modell, das aus ihm entstand.

Gerechnet wird in keinem davon. Der Trainer ist ein anderer Container mit einer
Karte darin; hier entsteht nur das Verzeichnis, an dem er ihn erkennt (siehe
`wortlaut/laeufe.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from wortlaut import laeufe as lauf_layout

from wortlaut import registry

from ..config import einstellungen
from ..deps import Datenbank, Korpus, SprecherId
from ..services import aufteilung, auftraege, vergleich

router = APIRouter(prefix="/lernen/api/laeufe", tags=["Läufe"])


class WahlAntwort(BaseModel):
    """Eine Wahlmöglichkeit beim Beauftragen - Schlüssel, Name, Begründung."""

    schluessel: str
    name: str
    erklaerung: str


METHODEN = [
    WahlAntwort(
        schluessel=lauf_layout.VOLL,
        name="Volles Training",
        erklaerung=(
            "Alle Gewichte werden angepasst. Holt am meisten aus wenigen Stunden "
            "Sprache heraus und vergisst am ehesten, was das Modell vorher konnte."
        ),
    ),
    WahlAntwort(
        schluessel=lauf_layout.LORA,
        name="Feintuning (LoRA)",
        erklaerung=(
            "Nur ein kleiner Zusatz wird gelernt, das Grundmodell bleibt stehen. "
            "Schneller, genügsamer im Speicher und schwerer zu verderben."
        ),
    ),
]

DATENSAETZE = [
    WahlAntwort(
        schluessel=lauf_layout.NUR_ORIGINAL,
        name="Nur Originale",
        erklaerung="Jede Aufnahme einmal, so wie sie gesprochen wurde.",
    ),
    WahlAntwort(
        schluessel=lauf_layout.MIT_VARIANTEN,
        name="Mit Abwandlungen",
        erklaerung=(
            "Dazu die drei abgewandelten Fassungen jeder Aufnahme - viermal so "
            "viele Proben, und eine Chance, Pegel und Rauschen zu überhören."
        ),
    ),
]


class Bestellung(BaseModel):
    methode: str
    daten: str


class StandHinweis(BaseModel):
    """Was an einem Lauf hängt, bevor ihn jemand löscht.

    Die Oberfläche fragt damit nicht noch einmal beim Server nach, was
    verschwinden würde - sie hat es schon, als sie die Liste holte, und kann
    es in die Sicherheitsabfrage schreiben.
    """

    version: str
    freigegeben: bool


class LaufAntwort(BaseModel):
    job_id: str
    sprecher_id: str
    methode: str
    daten: str
    basismodell: str
    erstellt: str
    status: str
    # Woran gerade gearbeitet wird: laden, training, export, bewertung.
    stufe: str
    # 0 bis 1, aus Schritt und Schrittzahl - `null`, solange der Trainer noch
    # nicht gesagt hat, wie viele es werden.
    anteil: float | None
    aufnahmen: int
    zeilen: dict[str, int]
    version: str | None
    fehler: str | None
    # Der Modellstand, der aus diesem Lauf hervorging - `null`, solange keiner
    # entstanden ist. Er ginge beim Löschen mit.
    stand: StandHinweis | None
    # Ob sich dieser Lauf löschen lässt. Ein rechnender nicht: In sein
    # Verzeichnis schreibt gerade ein anderer Container.
    loeschbar: bool


class PunktAntwort(BaseModel):
    schritt: int
    epoche: float
    verlust: float | None = None
    lernrate: float | None = None
    wer: float | None = None


class GegenueberAntwort(BaseModel):
    mass: str
    grundlinie: float | None
    trainiert: float | None
    besser: bool | None
    anzahl: int


class EinzelAntwort(BaseModel):
    lauf: LaufAntwort
    methoden: list[WahlAntwort]
    datensaetze: list[WahlAntwort]
    kurve_training: list[PunktAntwort]
    kurve_validierung: list[PunktAntwort]
    # fassung -> die Maße, jeweils vorher und nachher
    vergleich: dict[str, list[GegenueberAntwort]]
    protokoll: str


class ListeAntwort(BaseModel):
    laeufe: list[LaufAntwort]
    methoden: list[WahlAntwort]
    datensaetze: list[WahlAntwort]
    basismodell: str
    # Ob überhaupt beauftragt werden kann, und wenn nicht, warum.
    bereit: bool
    hinweis: str
    # Wie viele brauchbare Aufnahmen es inzwischen gibt, und wie viele davon
    # der jüngste durchgelaufene Lauf noch nicht kannte.
    #
    # Es gibt hier ausdrücklich **keine** Automatik, die daraufhin selbst
    # trainiert: Ein Lauf belegt die Karte für Minuten bis Stunden und
    # entsteht aus einem Schnappschuss, der festhalten soll, worauf ein Modell
    # gelernt hat. Von selbst angestoßen wüsste hinterher niemand mehr, welche
    # Aufnahmen in welchem Stand stecken - und zwei Läufe, die sich eine Karte
    # teilen, wären zusammen langsamer als nacheinander. Dieselbe Überlegung
    # wie beim Lauf der Auswertung in „hören": Wer messen will, sagt es.
    #
    # Was die Zahl stattdessen tut: Sie macht sichtbar, wann es sich lohnt.
    aufnahmen_jetzt: int
    aufnahmen_neu: int


def _anteil(lauf: lauf_layout.Lauf) -> float | None:
    gesamt = lauf.zustand.get("schritte_gesamt")
    schritt = lauf.zustand.get("schritt")
    if not gesamt or schritt is None:
        return None
    return min(1.0, float(schritt) / float(gesamt))


def _stand_zu(lauf: lauf_layout.Lauf) -> StandHinweis | None:
    datenverzeichnis = einstellungen().data_dir
    stand = registry.stand_zu_lauf(datenverzeichnis, lauf.sprecher_id, lauf.job_id)
    if stand is None:
        return None
    return StandHinweis(
        version=str(stand.get("id", "/")).split("/", 1)[-1],
        # Aus der Freigabe und nicht aus dem `status` des Manifests: Seit auch
        # ein Grundmodell freigegeben sein kann, ist die Freigabedatei die
        # Auskunft darüber, was gilt (siehe `wortlaut/registry.py`).
        freigegeben=registry.freigegeben(datenverzeichnis, lauf.sprecher_id)
        == str(stand.get("id", "")),
    )


def _als_antwort(lauf: lauf_layout.Lauf) -> LaufAntwort:
    return LaufAntwort(
        job_id=lauf.job_id,
        sprecher_id=lauf.sprecher_id,
        methode=str(lauf.auftrag.get("methode", "")),
        daten=str(lauf.auftrag.get("daten", "")),
        basismodell=str(lauf.auftrag.get("basismodell", "")),
        erstellt=str(lauf.auftrag.get("erstellt", "")),
        status=lauf.status,
        stufe=str(lauf.zustand.get("stufe", "")),
        anteil=_anteil(lauf),
        aufnahmen=int(lauf.auftrag.get("aufnahmen", 0)),
        zeilen=dict(lauf.auftrag.get("zeilen", {})),
        version=lauf.zustand.get("version"),
        fehler=lauf.zustand.get("fehler"),
        stand=_stand_zu(lauf),
        loeschbar=lauf.status != lauf_layout.LAEUFT,
    )


def _hole(sprecher: str, job_id: str) -> lauf_layout.Lauf:
    lauf = lauf_layout.lies_lauf(einstellungen().data_dir, job_id)
    # Ein fremder Lauf ist hier schlicht unbekannt: Die Kennung stammt aus dem
    # Zugang, und wer nach einem anderen Verzeichnis fragt, hat dort nichts
    # verloren - auch nicht die Auskunft, dass es existiert.
    if lauf is None or lauf.sprecher_id != sprecher:
        raise HTTPException(status_code=404, detail="Unbekannter Lauf.")
    return lauf


@router.get("", response_model=ListeAntwort)
def liste(db: Datenbank, korpus: Korpus, sprecher: SprecherId) -> ListeAntwort:
    konfiguration = einstellungen()
    proben = aufteilung.proben(db, korpus)
    anzahl = aufteilung.zaehle(proben)
    genug = anzahl[lauf_layout.TRAIN] > 0 and anzahl[lauf_layout.TEST] > 0
    alle = lauf_layout.alle_laeufe(konfiguration.data_dir, sprecher)

    # Der jüngste Lauf, der wirklich durchgelaufen ist. Ein abgebrochener oder
    # gescheiterter sagt nichts darüber, was ein Modell kennt.
    fertige = [lauf for lauf in alle if lauf.status == lauf_layout.FERTIG]
    zuletzt = int(fertige[-1].auftrag.get("aufnahmen", 0)) if fertige else 0

    return ListeAntwort(
        laeufe=[_als_antwort(lauf) for lauf in reversed(alle)],
        aufnahmen_jetzt=len(proben),
        # Nie negativ: Wer Aufnahmen löscht, hat nicht „minus drei neue".
        aufnahmen_neu=max(0, len(proben) - zuletzt),
        methoden=METHODEN,
        datensaetze=DATENSAETZE,
        basismodell=konfiguration.lernen_basismodell,
        bereit=genug,
        hinweis=(
            ""
            if genug
            else "Es braucht Aufnahmen zum Lernen und welche zum Prüfen - "
            "beides kommt aus \u201ehören\u201c."
        ),
    )


@router.post("", response_model=LaufAntwort, status_code=201)
def beauftrage(
    bestellung: Bestellung, db: Datenbank, korpus: Korpus, sprecher: SprecherId
) -> LaufAntwort:
    if bestellung.methode not in lauf_layout.METHODEN:
        raise HTTPException(status_code=400, detail=f"Unbekannte Methode: {bestellung.methode}")
    if bestellung.daten not in lauf_layout.DATENSAETZE:
        raise HTTPException(status_code=400, detail=f"Unbekannter Datensatz: {bestellung.daten}")

    konfiguration = einstellungen()
    proben = aufteilung.proben(db, korpus)
    anzahl = aufteilung.zaehle(proben)
    if not anzahl[lauf_layout.TRAIN]:
        raise HTTPException(status_code=409, detail="Keine Aufnahme zum Lernen im Korpus.")
    if not anzahl[lauf_layout.TEST]:
        raise HTTPException(status_code=409, detail="Keine Aufnahme zum Prüfen im Korpus.")

    lauf = auftraege.beauftrage(
        konfiguration.data_dir,
        korpus,
        proben,
        auftraege.Auftrag(
            sprecher_id=sprecher,
            methode=bestellung.methode,
            daten=bestellung.daten,
            basismodell=konfiguration.lernen_basismodell,
        ),
    )
    return _als_antwort(lauf)


@router.get("/{job_id}", response_model=EinzelAntwort)
def einzeln(job_id: str, korpus: Korpus, sprecher: SprecherId) -> EinzelAntwort:
    lauf = _hole(sprecher, job_id)
    kurven = auftraege.lernkurve(lauf)
    protokoll = lauf.verzeichnis / lauf_layout.PROTOKOLL
    return EinzelAntwort(
        lauf=_als_antwort(lauf),
        methoden=METHODEN,
        datensaetze=DATENSAETZE,
        kurve_training=[PunktAntwort(**_punkt(zeile)) for zeile in kurven["training"]],
        kurve_validierung=[PunktAntwort(**_punkt(zeile)) for zeile in kurven["validierung"]],
        vergleich={
            fassung: [
                GegenueberAntwort(
                    mass=eintrag.mass,
                    grundlinie=eintrag.grundlinie,
                    trainiert=eintrag.trainiert,
                    besser=eintrag.besser,
                    anzahl=eintrag.anzahl,
                )
                for eintrag in eintraege
            ]
            for fassung, eintraege in vergleich.je_fassung(lauf, korpus).items()
        },
        # Nur das Ende: Wer ein Protokoll liest, sucht den letzten Satz vor dem
        # Abbruch, nicht den ersten des Ladevorgangs.
        protokoll=protokoll.read_text(encoding="utf-8")[-4000:] if protokoll.is_file() else "",
    )


def _punkt(zeile: dict) -> dict:
    """Nur die Felder, die die Kurve kennt - der Trainer darf mehr schreiben."""
    return {
        "schritt": int(zeile.get("schritt", 0)),
        "epoche": float(zeile.get("epoche", 0.0)),
        "verlust": zeile.get("verlust"),
        "lernrate": zeile.get("lernrate"),
        "wer": zeile.get("wer"),
    }


class GeloeschtAntwort(BaseModel):
    job_id: str
    # Die Version des mitgelöschten Modellstands; leer, wenn es keinen gab.
    version: str
    war_freigegeben: bool


@router.delete("/{job_id}", response_model=GeloeschtAntwort)
def loeschen(job_id: str, sprecher: SprecherId) -> GeloeschtAntwort:
    """Einen Lauf ersatzlos entfernen - samt dem Modell, das aus ihm entstand.

    Ersatzlos heißt ersatzlos: Es gibt keinen Papierkorb und keinen Weg
    zurück. Die Sicherheitsabfrage steht in der Oberfläche und nennt vorher,
    was verschwindet (`frontend/src/routes/Training.svelte`); hier wird nur
    noch getan, was bestätigt wurde.

    Warum das Modell mitgeht und die Aufteilung nicht, steht in
    `services/auftraege.py`.
    """
    _hole(sprecher, job_id)  # 404, wenn er einem anderen gehört
    try:
        geloescht = auftraege.loesche(einstellungen().data_dir, sprecher, job_id)
    except LookupError as ursache:
        raise HTTPException(status_code=404, detail="Unbekannter Lauf.") from ursache
    except RuntimeError as ursache:
        raise HTTPException(status_code=409, detail=str(ursache)) from ursache

    return GeloeschtAntwort(
        job_id=geloescht.job_id,
        version=geloescht.version,
        war_freigegeben=geloescht.war_freigegeben,
    )


@router.post("/{job_id}/abbruch", response_model=LaufAntwort)
def abbrechen(job_id: str, sprecher: SprecherId) -> LaufAntwort:
    lauf = _hole(sprecher, job_id)
    if not auftraege.brich_ab(einstellungen().data_dir, job_id):
        raise HTTPException(
            status_code=409,
            detail="Dieser Lauf wartet nicht mehr - zurücknehmen lässt sich nur ein wartender.",
        )
    return _als_antwort(_hole(sprecher, job_id))
