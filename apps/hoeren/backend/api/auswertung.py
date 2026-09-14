"""Die Auswertung: Modelle gegeneinander, gemessen an den eigenen Aufnahmen.

Vier Wege, und sie teilen sich die Arbeit nach dem, wie oft sie gebraucht
werden:

* `GET /api/auswertung` liefert die Kurve - je Aufnahme eine Nummer und je
  Modell und Fassung die Maße dazu. **Ohne Texte.** Diese Auskunft wird abgefragt, solange
  die Seite offen ist; die erkannten Texte je Modell und Aufnahme
  mitzuschicken hieße, bei jeder Abfrage ein Vielfaches der Zahlen über die
  Leitung zu schicken, die sie eigentlich meint.
* `GET /api/auswertung/{aufnahme}` liefert genau diese Texte, für eine
  einzelne Aufnahme - der Klick auf einen Balken.
* `POST /api/auswertung/start` stößt den Lauf an, `…/stopp` bricht ihn ab.

Alles hängt am Zugang eines Sprechers und misst dessen eigenen Korpus. Eine
Auswertung über alle Sprecher hinweg gibt es bewusst nicht: Wie gut ein Modell
hört, hängt an der Stimme, und der Mittelwert über mehrere Menschen wäre eine
Zahl, die für keinen von ihnen gilt.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from wortlaut import rechenwerk

from ..config import einstellungen
from ..db.models import Aufnahme, Erkennung, Sprecher, Vorlage
from ..deps import Ablage, Datenbank, SprecherId, engine_fuer
from ..services import augmentierung, auswertung

router = APIRouter(prefix="/api/auswertung", tags=["Auswertung"])


class MetrikAntwort(BaseModel):
    """Ein wählbares Maß - die Oberfläche baut daraus ihre Auswahlliste.

    Sie kommt vom Server und steht nicht im Frontend, weil der Server sie
    rechnet: Ein Maß dazu ist eine Spalte, eine Zeile in `metriken.py` und ein
    Eintrag hier - und nicht zusätzlich eine Liste im Browser, die jemand
    nachzupflegen vergisst.
    """

    schluessel: str
    name: str
    erklaerung: str
    # Ob ein hoher Wert der bessere ist. Die Fehlerraten sind andersherum, und
    # ohne diese Angabe zeigte die Kurve nach oben, wo es schlechter wird.
    hoch_ist_gut: bool
    einheit: str
    # Die feste Obergrenze der Achse, falls es eine gibt. `null` heißt: Die
    # Achse richtet sich nach den Daten - WER und CER können über 1 steigen.
    obergrenze: float | None


METRIKEN = [
    MetrikAntwort(
        schluessel="genauigkeit",
        name="Genauigkeit",
        erklaerung="Die vier Maße unten zu einer Zahl zusammengefasst, 0 bis 100.",
        hoch_ist_gut=True,
        einheit="%",
        obergrenze=100,
    ),
    MetrikAntwort(
        schluessel="wer",
        name="Wortfehlerrate (WER)",
        erklaerung="Anteil falscher, fehlender und zusätzlicher Wörter.",
        hoch_ist_gut=False,
        einheit="",
        obergrenze=None,
    ),
    MetrikAntwort(
        schluessel="cer",
        name="Zeichenfehlerrate (CER)",
        erklaerung="Dasselbe auf Zeichen - feiner, aber blind für den Sinn.",
        hoch_ist_gut=False,
        einheit="",
        obergrenze=None,
    ),
    MetrikAntwort(
        schluessel="mer",
        name="Trefferfehlerrate (MER)",
        erklaerung="Fehler im Verhältnis zu allem Gesagten; nie über 1.",
        hoch_ist_gut=False,
        einheit="",
        obergrenze=1,
    ),
    MetrikAntwort(
        schluessel="wil",
        name="Wortinformationsverlust (WIL)",
        erklaerung="Wie viel Wortinformation verloren ging; nie über 1.",
        hoch_ist_gut=False,
        einheit="",
        obergrenze=1,
    ),
    MetrikAntwort(
        schluessel="rechenzeit_s",
        name="Rechenzeit",
        erklaerung="Sekunden je Aufnahme - die andere Hälfte jeder Modellwahl.",
        hoch_ist_gut=False,
        einheit="s",
        obergrenze=None,
    ),
]


class VarianteAntwort(BaseModel):
    """Eine Fassung der Aufnahme - die Oberfläche beschriftet damit ihre Zeilen.

    Wie bei den Maßen kommt die Liste vom Server: Was es an Fassungen gibt,
    entscheidet `wortlaut/augmentierung.py`, und eine zweite Liste im Browser
    wäre eine, die jemand nachzupflegen vergisst.
    """

    schluessel: str
    name: str
    erklaerung: str


VARIANTEN = [
    VarianteAntwort(
        schluessel=augmentierung.ORIGINAL,
        name="Original",
        erklaerung="Die Aufnahme, wie sie gesprochen wurde.",
    ),
    *(
        VarianteAntwort(
            schluessel=abwandlung.name,
            name=abwandlung.titel,
            erklaerung=abwandlung.erklaerung,
        )
        for abwandlung in augmentierung.ABWANDLUNGEN
    ),
]


class StandAntwort(BaseModel):
    laeuft: bool
    erledigt: int
    gesamt: int
    uebersprungen: int
    aktuell: str
    fehler: str | None
    # Ob gerade für einen **anderen** Sprecher gerechnet wird. Es läuft immer
    # nur einer (siehe `services/auswertung.py`); ohne diese Auskunft sähe die
    # Seite bloß einen Startknopf, der nichts tut.
    fremder_lauf: bool


class PunktAntwort(BaseModel):
    """Eine Aufnahme in der Kurve: ihre Nummer und die Maße je Modell und Fassung.

    Ausgerechnet wird hier nichts. Die Kurve zeigt je Modell nur eine Zahl,
    aber welche, hängt am gewählten Maß - und die Tabelle darunter zeigt
    ohnehin jede. Der Server schickt deshalb, was gemessen wurde,
    und die Ansicht sucht sich heraus, was sie gerade braucht; sonst wäre bei
    jedem Wechsel des Maßes eine neue Anfrage fällig, für die kein Byte fehlt.
    """

    nummer: int
    aufnahme_id: str
    dauer_s: float
    erstellt: str
    # modell -> fassung -> maß -> Wert. Fehlt ein Eintrag, ist er noch nicht
    # gerechnet - die Kurve lässt die Stelle dann frei, statt eine Null zu
    # behaupten.
    werte: dict[str, dict[str, dict[str, float]]]


class AuswertungAntwort(BaseModel):
    modelle: list[str]
    varianten: list[VarianteAntwort]
    metriken: list[MetrikAntwort]
    stand: StandAntwort
    punkte: list[PunktAntwort]


class ErkennungAntwort(BaseModel):
    modell: str
    variante: str
    text: str
    wer: float
    cer: float
    mer: float
    wil: float
    genauigkeit: float
    rechenzeit_s: float


class VergleichAntwort(BaseModel):
    """Eine Aufnahme im Klartext: was dastand und was jedes Modell daraus machte."""

    nummer: int
    aufnahme_id: str
    referenz: str
    dauer_s: float
    erkennungen: list[ErkennungAntwort]


def _namen() -> list[str]:
    return auswertung.modelle(einstellungen().auswertung_modelle)


def _werk() -> str:
    """Das Rechenwerk, unter dem hier gemessen wird - `cuda/int8_float16` o. Ä.

    Es entscheidet mit, was als gerechnet gilt: Eine Zeile, die auf einem
    anderen entstand, trägt eine Rechenzeit, die nicht neben die übrigen passt
    (siehe `services/auswertung.py`).
    """
    return rechenwerk.marke(*einstellungen().rechenwerk())


def _stand(db: Datenbank, sprecher: str) -> StandAntwort:
    roh = auswertung.stand(db, _namen(), _werk())
    laeuft_fuer = auswertung.laeuft_fuer()
    return StandAntwort(
        laeuft=roh.laeuft and laeuft_fuer == sprecher,
        erledigt=roh.erledigt,
        gesamt=roh.gesamt,
        uebersprungen=roh.uebersprungen,
        aktuell=roh.aktuell,
        fehler=roh.fehler,
        fremder_lauf=bool(laeuft_fuer) and laeuft_fuer != sprecher,
    )


def _nummeriert(db: Datenbank) -> list[tuple[int, Aufnahme, Vorlage]]:
    """Die brauchbaren Aufnahmen, von 1 an durchgezählt, älteste zuerst.

    Die Nummer ist die x-Achse der Kurve. Sie steht in keiner Tabelle, und das
    ist Absicht: Wer eine Aufnahme verwirft, soll keine Lücke in der Achse
    hinterlassen - die Zählung ergibt sich aus dem, was gerade gilt.
    """
    return [
        (nummer, aufnahme, vorlage)
        for nummer, (aufnahme, vorlage) in enumerate(
            auswertung.gueltige_aufnahmen(db), start=1
        )
    ]


@router.get("", response_model=AuswertungAntwort)
def uebersicht(db: Datenbank, sprecher: SprecherId) -> AuswertungAntwort:
    """Die Kurve und der Stand des Laufs - die Auskunft, die die Seite abfragt."""
    namen = _namen()
    # Nur die Zeilen der Geschwindigkeit, die gerade gilt.
    #
    # Ohne diese Bedingung stand hier ein Widerspruch: Nach dem Umstellen auf
    # Faktor 2 meldete der Balken „0 von 96 erledigt" - und darunter lag die
    # volle Kurve aus den Zeilen von Faktor 1. Beide Zahlen stimmten für sich,
    # nebeneinander behaupteten sie Unsinn. Der Zähler siebte nach Tempo
    # (`services/auswertung.py`), die Kurve nicht.
    faktor = auswertung.tempo_des_sprechers(db)
    nach_aufnahme: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    for erkennung in db.scalars(
        select(Erkennung).where(
            Erkennung.modell.in_(namen),
            Erkennung.variante.in_(augmentierung.VARIANTEN),
            Erkennung.tempo == faktor,
        )
    ):
        je_modell = nach_aufnahme.setdefault(erkennung.recording_id, {})
        je_modell.setdefault(erkennung.modell, {})[erkennung.variante] = {
            "wer": erkennung.wer,
            "cer": erkennung.cer,
            "mer": erkennung.mer,
            "wil": erkennung.wil,
            "genauigkeit": erkennung.genauigkeit,
            "rechenzeit_s": erkennung.rechenzeit_s,
        }

    return AuswertungAntwort(
        modelle=namen,
        varianten=VARIANTEN,
        metriken=METRIKEN,
        stand=_stand(db, sprecher),
        punkte=[
            PunktAntwort(
                nummer=nummer,
                aufnahme_id=aufnahme.id,
                dauer_s=aufnahme.dauer_s,
                erstellt=aufnahme.erstellt,
                werte=nach_aufnahme.get(aufnahme.id, {}),
            )
            for nummer, aufnahme, _vorlage in _nummeriert(db)
        ],
    )


@router.post("/start", response_model=StandAntwort)
async def start(db: Datenbank, sprecher: SprecherId, ablage: Ablage) -> StandAntwort:
    """Den Lauf anstoßen. Läuft schon einer, ändert sich nichts.

    `async`, und das ist keine Geschmacksfrage: Der Lauf ist eine
    `asyncio`-Aufgabe, und die lässt sich nur dort anlegen, wo eine
    Ereignisschleife läuft. Ein `def`-Endpunkt läge in einem Arbeitsfaden des
    Servers und scheiterte mit „no running event loop" - erst zur Laufzeit und
    nur auf diesem einen Weg.
    """
    laeuft_fuer = auswertung.laeuft_fuer()
    if laeuft_fuer and laeuft_fuer != sprecher:
        raise HTTPException(
            status_code=409,
            detail="Es läuft bereits eine Auswertung für einen anderen Sprecher.",
        )

    person = db.get(Sprecher, sprecher)
    assert person is not None  # `SprecherId` hat die Datenbank schon geöffnet.
    konfiguration = einstellungen()
    auswertung.starte(
        sprecher_id=sprecher,
        engine=engine_fuer(sprecher),
        ablage=ablage,
        namen=_namen(),
        sprache=person.sprache,
        geraet=konfiguration.geraet,
        rechenart=konfiguration.rechenart,
    )
    return _stand(db, sprecher)


@router.post("/stopp", response_model=StandAntwort)
async def stopp(db: Datenbank, sprecher: SprecherId) -> StandAntwort:
    """Abbrechen. Was fertig gerechnet ist, bleibt stehen und wird nicht wiederholt.

    `async` aus demselben Grund wie `start`: Eine Aufgabe abzubrechen gehört
    auf die Schleife, auf der sie läuft, nicht in einen fremden Faden.
    """
    if auswertung.laeuft_fuer() == sprecher:
        auswertung.stoppe()
    return _stand(db, sprecher)


@router.get("/{aufnahme_id}", response_model=VergleichAntwort)
def vergleich(aufnahme_id: str, db: Datenbank, sprecher: SprecherId) -> VergleichAntwort:
    """Was dastand und was jedes Modell daraus machte - der Klick auf einen Balken."""
    namen = _namen()
    for nummer, aufnahme, vorlage in _nummeriert(db):
        if aufnahme.id != aufnahme_id:
            continue

        # Auch hier nur die geltende Geschwindigkeit, und hier wiegt es
        # schwerer als in der Kurve: Seit je Tempo eine Zeile dastehen darf
        # (`011_tempo.sql`), gibt es zu einem Modell und einer Fassung
        # mehrere - und dieses Wörterbuch behielte stillschweigend die
        # zuletzt gelesene. Welche das ist, sagt die Reihenfolge der
        # Datenbank, also niemand.
        gerechnet = {
            (erkennung.modell, erkennung.variante): erkennung
            for erkennung in db.scalars(
                select(Erkennung).where(
                    Erkennung.recording_id == aufnahme_id,
                    Erkennung.tempo == auswertung.tempo_des_sprechers(db),
                )
            )
        }
        return VergleichAntwort(
            nummer=nummer,
            aufnahme_id=aufnahme.id,
            referenz=vorlage.text,
            dauer_s=aufnahme.dauer_s,
            # In der Reihenfolge der Konfiguration, nicht in der der Datenbank:
            # Die Ansicht legt die Fassungen untereinander, und sie sollen bei
            # jeder Aufnahme in derselben Reihenfolge stehen. Fassung innen,
            # Modell außen - wer eine Fassung liest, vergleicht die Modelle
            # darin, und nicht dasselbe Modell mit sich selbst.
            erkennungen=[
                ErkennungAntwort(
                    modell=name,
                    variante=variante,
                    text=zeile.text,
                    wer=zeile.wer,
                    cer=zeile.cer,
                    mer=zeile.mer,
                    wil=zeile.wil,
                    genauigkeit=zeile.genauigkeit,
                    rechenzeit_s=zeile.rechenzeit_s,
                )
                for name in namen
                for variante in augmentierung.VARIANTEN
                if (zeile := gerechnet.get((name, variante))) is not None
            ],
        )

    raise HTTPException(status_code=404, detail="Unbekannte oder verworfene Aufnahme.")
