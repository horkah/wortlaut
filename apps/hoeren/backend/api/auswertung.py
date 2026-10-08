"""Die Auswertung: Modelle gegeneinander, gemessen an den eigenen Aufnahmen.

* `GET /api/auswertung` - die Kurve, ohne Texte, denn sie wird im Takt
  abgefragt.
* `GET /api/auswertung/{aufnahme}` - die Texte einer Aufnahme.
* `POST /api/auswertung/start` und `…/stopp`.

Gemessen wird der Korpus des Zugangs; ein Mittel über mehrere Stimmen gälte
für keine.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from wortlaut import metriken, rechenwerk, registry

from ..config import einstellungen
from ..db.models import Aufnahme, Erkennung, Sprecher, Vorlage
from ..deps import Ablage, Datenbank, SprecherId, engine_fuer
from ..services import auswertung

router = APIRouter(prefix="/api/auswertung", tags=["Auswertung"])


class MetrikAntwort(BaseModel):
    """Ein wählbares Maß - die Liste kommt vom Server, der rechnet."""

    schluessel: str
    name: str
    erklaerung: str
    # Bei den Fehlerraten ist niedrig besser.
    hoch_ist_gut: bool
    einheit: str
    # Feste Achsengrenze; `null` bei WER und CER, die über 1 steigen können.
    obergrenze: float | None


# Wie die Kurve jedes Maß zeigt: Einheit und feste Achsengrenze - `None` bei
# WER und CER, die über 1 steigen können.
_DARSTELLUNG = {
    "genauigkeit": ("%", 100),
    "wer": ("", None),
    "cer": ("", None),
    "mer": ("", 1),
    "wil": ("", 1),
    "rechenzeit_s": ("s", None),
}
METRIKEN = [
    MetrikAntwort(
        schluessel=mass.schluessel,
        name=mass.name,
        erklaerung=mass.erklaerung,
        hoch_ist_gut=mass.hoch_ist_gut,
        einheit=_DARSTELLUNG[mass.schluessel][0],
        obergrenze=_DARSTELLUNG[mass.schluessel][1],
    )
    for mass in metriken.MASSE
]


class StandAntwort(BaseModel):
    laeuft: bool
    erledigt: int
    gesamt: int
    uebersprungen: int
    aktuell: str
    fehler: str | None
    # Ob gerade für einen anderen Sprecher gerechnet wird - es läuft einer zur Zeit.
    fremder_lauf: bool


class PunktAntwort(BaseModel):
    """Eine Aufnahme in der Kurve: ihre Nummer und die Maße je Modell.

    Alles Gemessene; die Ansicht wählt, sodass ein Maßwechsel keine Anfrage
    braucht.
    """

    nummer: int
    aufnahme_id: str
    dauer_s: float
    erstellt: str
    # modell -> maß -> Wert; ein fehlender Eintrag ist nicht gerechnet.
    werte: dict[str, dict[str, float]]


class AuswertungAntwort(BaseModel):
    modelle: list[str]
    # Ein Stand heißt nach seiner Kurzkennung.
    beschriftungen: dict[str, str] = {}
    # Stand -> der Lauf, aus dem er kam: der Weg in seine Einzelansicht in
    # „lernen". Ein Grundmodell hat keinen.
    laeufe: dict[str, str] = {}
    metriken: list[MetrikAntwort]
    stand: StandAntwort
    punkte: list[PunktAntwort]


class ErkennungAntwort(BaseModel):
    modell: str
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


def _namen(sprecher: str) -> list[str]:
    """Wogegen hier gemessen wird: die Grundmodelle **und** die eigenen Stände.

    Für einen Stand wird nur gerechnet, was er nicht kannte
    (`services/auswertung.py`).
    """
    konfiguration = einstellungen()
    return auswertung.messbare_modelle(
        konfiguration.data_dir, sprecher, konfiguration.auswertung_modelle
    )


def _beschriftungen(namen: list[str]) -> dict[str, str]:
    """`small` bleibt `small`, ein Stand wird zu `K7M2Q` (`wortlaut/registry.py`)."""
    return {name: registry.beschriftung(name) for name in namen}


def _laeufe(sprecher: str) -> dict[str, str]:
    """Zu jedem Stand die Kennung seines Laufs, aus dem Manifest."""
    return {
        str(manifest["id"]): str(manifest["job_id"])
        for manifest in registry.alle_staende(einstellungen().data_dir, sprecher)
        if manifest.get("id") and manifest.get("job_id")
    }


def _werk() -> str:
    """Das Rechenwerk, unter dem hier gemessen wird - `cuda/int8_float16` o. Ä.

    Eine Zeile von einem anderen Rechenwerk gilt als offen.
    """
    return rechenwerk.marke(*einstellungen().rechenwerk())


def _stand(db: Datenbank, sprecher: str) -> StandAntwort:
    # Wer rechnet, aus derselben Momentaufnahme wie die Zählung - ein zweites
    # Nachfragen (`laeuft_fuer`) sähe womöglich schon das Ende des Laufs.
    roh = auswertung.stand(db, _namen(sprecher), _werk(), einstellungen().data_dir)
    return StandAntwort(
        laeuft=roh.laeuft and roh.sprecher_id == sprecher,
        erledigt=roh.erledigt,
        gesamt=roh.gesamt,
        uebersprungen=roh.uebersprungen,
        aktuell=roh.aktuell,
        fehler=roh.fehler,
        fremder_lauf=roh.laeuft and roh.sprecher_id != sprecher,
    )


def _nummeriert(db: Datenbank) -> list[tuple[int, Aufnahme, Vorlage]]:
    """Die gemessenen Aufnahmen, von 1 an durchgezählt, älteste zuerst.

    Die Nummer ist die x-Achse, gezählt aus dem, was gilt - ohne Lücken.
    """
    return [
        (nummer, aufnahme, vorlage)
        for nummer, (aufnahme, vorlage) in enumerate(
            auswertung.gemessene_aufnahmen(db), start=1
        )
    ]


@router.get("", response_model=AuswertungAntwort)
def uebersicht(db: Datenbank, sprecher: SprecherId) -> AuswertungAntwort:
    """Die Kurve und der Stand des Laufs - die Auskunft, die die Seite abfragt.

    Zuerst der Abgleich mit den Ständen (`auswertung.gleiche_ab`): Ihre
    Faltungen gehören sofort in Vergleich und Zählung.
    """
    auswertung.gleiche_ab(db, einstellungen().data_dir, sprecher)
    # Vor den Messwerten: Was der Stand zählt, steht dann auch in der Kurve.
    stand = _stand(db, sprecher)
    namen = _namen(sprecher)
    nach_aufnahme: dict[str, dict[str, dict[str, float]]] = {}
    for erkennung in db.scalars(select(Erkennung).where(Erkennung.modell.in_(namen))):
        nach_aufnahme.setdefault(erkennung.recording_id, {})[erkennung.modell] = {
            feld: getattr(erkennung, feld) for feld in metriken.MESSFELDER
        }

    return AuswertungAntwort(
        modelle=namen,
        beschriftungen=_beschriftungen(namen),
        laeufe=_laeufe(sprecher),
        metriken=METRIKEN,
        stand=stand,
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

    `async`, weil der Lauf eine `asyncio`-Aufgabe ist; ein `def`-Endpunkt
    liefe im Arbeitsfaden ohne Ereignisschleife.
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
        namen=_namen(sprecher),
        datenverzeichnis=konfiguration.data_dir,
        sprache=person.sprache,
        geraet=konfiguration.geraet,
        rechenart=konfiguration.rechenart,
    )
    return _stand(db, sprecher)


@router.post("/stopp", response_model=StandAntwort)
async def stopp(db: Datenbank, sprecher: SprecherId) -> StandAntwort:
    """Abbrechen. Was fertig gerechnet ist, bleibt stehen und wird nicht wiederholt.

    `async` wie `start` - abgebrochen wird auf der Schleife der Aufgabe.
    """
    if auswertung.laeuft_fuer() == sprecher:
        auswertung.stoppe()
    return _stand(db, sprecher)


@router.get("/{aufnahme_id}", response_model=VergleichAntwort)
def vergleich(aufnahme_id: str, db: Datenbank, sprecher: SprecherId) -> VergleichAntwort:
    """Was dastand und was jedes Modell daraus machte - der Klick auf einen Balken."""
    namen = _namen(sprecher)
    for nummer, aufnahme, vorlage in _nummeriert(db):
        if aufnahme.id != aufnahme_id:
            continue

        gerechnet = {
            erkennung.modell: erkennung
            for erkennung in db.scalars(
                select(Erkennung).where(Erkennung.recording_id == aufnahme_id)
            )
        }
        return VergleichAntwort(
            nummer=nummer,
            aufnahme_id=aufnahme.id,
            referenz=vorlage.text,
            dauer_s=aufnahme.dauer_s,
            # In der Reihenfolge der Konfiguration.
            erkennungen=[
                ErkennungAntwort(
                    modell=name,
                    text=zeile.text,
                    **{feld: getattr(zeile, feld) for feld in metriken.MESSFELDER},
                )
                for name in namen
                if (zeile := gerechnet.get(name)) is not None
            ],
        )

    raise HTTPException(status_code=404, detail="Unbekannte oder verworfene Aufnahme.")
