"""Läufe beauftragen und ihnen zusehen.

Vier Wege, und sie teilen sich die Arbeit nach dem, wie oft sie gebraucht
werden - dieselbe Aufteilung wie in der Auswertung von „hören":

* `GET  /lernen/api/laeufe`          die Liste: je Lauf Auftrag und Stand.
  Sie wird abgefragt, solange die Seite offen ist, und trägt deshalb **keine**
  Kurven: Bei zwölf Läufen mit je tausend Schritten wäre das bei jedem Takt ein
  Vielfaches dessen, was gemeint ist.
* `GET  /lernen/api/laeufe/{id}`     ein Lauf im Einzelnen: Kurven, Bewertung,
  Vergleich mit der Grundlinie.
* `POST /lernen/api/laeufe`          einen Lauf beauftragen. **Der einzige Weg
  hier, der ein zweites Geheimnis verlangt** - den Trainerschlüssel, siehe
  `_pruefe_trainerschluessel`.
* `POST /lernen/api/laeufe/{id}/abbruch`  einen wartenden zurücknehmen.
* `DELETE /lernen/api/laeufe/{id}`   einen Lauf ersatzlos entfernen, samt dem
  Modell, das aus ihm entstand.

Gerechnet wird in keinem davon. Der Trainer ist ein anderer Container mit einer
Karte darin; hier entsteht nur das Verzeichnis, an dem er ihn erkennt (siehe
`wortlaut/laeufe.py`).
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from wortlaut import laeufe as lauf_layout

from wortlaut import registry

from ..config import einstellungen
from ..deps import Datenbank, Korpus, SprecherId
from ..services import aufteilung, auftraege, vergleich

router = APIRouter(prefix="/lernen/api/laeufe", tags=["Läufe"])

# Der Kopf, in dem der Trainerschlüssel steht. Nicht `Authorization`: Dort
# liegt schon der Sprecherzugang, und aus ihm leitet der Server ab, wessen
# Modell entsteht (`deps.py`). Zwei Geheimnisse in einem Kopf hießen, das eine
# gegen das andere zu tauschen - und dann trainierte der Schlüssel für
# niemanden oder der Zugang ohne Erlaubnis.
SCHLUESSEL_KOPF = "X-Trainer-Key"


def _pruefe_trainerschluessel(
    x_trainer_key: Annotated[str | None, Header()] = None,
) -> None:
    """Wächter des einen teuren Weges: einen Lauf beauftragen.

    Ein Lauf belegt die Karte für Minuten bis Stunden, und er kostet Strom,
    Wärme und die Wartezeit aller anderen. Der Sprecherzugang allein reicht
    dafür nicht: Er ist an jeden ausgegeben, der aufnimmt, und er ist die
    Antwort auf „wessen Modell?", nicht auf „wer darf rechnen lassen?".

    Nicht gesetzt heißt abgeschaltet - kein Training für niemanden, auch nicht
    in der Entwicklung (die Begründung steht bei `trainer_key` in der
    `config.py`). Die Oberfläche fragt das vorher ab und zeigt den Knopf dann
    gar nicht erst (`bereit` und `hinweis` in der Liste).

    Zeitkonstant verglichen und über die UTF-8-Bytes, wie in „hören": Sonst
    verriete die Antwortzeit den Anfang des Schlüssels, und ein Umlaut darin
    ergäbe einen 500er statt eines sauberen 401.
    """
    erwartet = einstellungen().trainer_key
    if not erwartet:
        # 401 und nicht 403, weil „hören" es bei Verwaltung und Aufsicht
        # genauso hält: Eine abgeschaltete Tür ist eine, an der niemand
        # angemeldet ist. Zwei Fassungen derselben Absage wären zwei Wege
        # durch die Oberfläche.
        raise HTTPException(
            status_code=401,
            detail=(
                "Training ist abgeschaltet: Auf diesem Server ist kein "
                "Trainerschlüssel hinterlegt (WORTLAUT_TRAINER_KEY)."
            ),
        )
    vorgelegt = x_trainer_key or ""
    if not secrets.compare_digest(vorgelegt.encode("utf-8"), erwartet.encode("utf-8")):
        raise HTTPException(
            status_code=401,
            detail="Falscher oder fehlender Trainerschlüssel.",
        )


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
    # Ob überhaupt beauftragt werden kann, und wenn nicht, warum. Es sind zwei
    # Gründe, aus denen nicht: zu wenige Aufnahmen - oder kein hinterlegter
    # Trainerschlüssel, dann kann es auf diesem Server niemand.
    bereit: bool
    hinweis: str
    # Ob die Oberfläche nach dem Trainerschlüssel fragen muss. Der Server sagt
    # es, statt dass die Seite es errät: Sonst stünde die Regel zweimal da, und
    # die Kopie in der Oberfläche wäre die, die niemand prüft.
    schluessel_noetig: bool
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
    # Ohne hinterlegten Schlüssel ist diese Seite eine Leseseite: Die Läufe von
    # früher bleiben sichtbar, beauftragen kann hier niemand mehr.
    erlaubt = bool(konfiguration.trainer_key)
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
        bereit=genug and erlaubt,
        schluessel_noetig=erlaubt,
        # Der Schlüssel zuerst: Wer ohnehin nicht trainieren darf, soll nicht
        # erst Aufnahmen sammeln, um dann vor derselben Wand zu stehen.
        hinweis=(
            ""
            if genug and erlaubt
            else "Auf diesem Server ist kein Trainerschlüssel hinterlegt - "
            "hier lässt sich kein Training anstoßen."
            if not erlaubt
            else "Es braucht Aufnahmen zum Lernen und welche zum Prüfen - "
            "beides kommt aus \u201ehören\u201c."
        ),
    )


@router.post(
    "",
    response_model=LaufAntwort,
    status_code=201,
    dependencies=[Depends(_pruefe_trainerschluessel)],
)
def beauftrage(
    bestellung: Bestellung, db: Datenbank, korpus: Korpus, sprecher: SprecherId
) -> LaufAntwort:
    """Einen Lauf beauftragen - der einzige Weg, der den Trainerschlüssel verlangt.

    Er steht vor allen anderen Prüfungen, und zwar mit Absicht: Wer nicht
    trainieren darf, soll nicht erfahren, wie viele Aufnahmen im Korpus eines
    Sprechers liegen oder ob eine Methode diesen Server kennt.
    """
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
