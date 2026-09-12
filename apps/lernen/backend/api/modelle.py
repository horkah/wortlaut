"""Alle Modelle eines Sprechers an einem Ort - gemessen, verglichen, freigegeben.

Dieser eine Weg beantwortet die ganze Frage „womit spreche ich?": Er stellt die
unveränderten Grundmodelle und die selbst trainierten Stände nebeneinander,
misst sie an denselben Testaufnahmen (siehe `services/messwerte.py`) und sagt,
welches davon freigegeben ist. Freigegeben heißt: Damit diktiert „schreiben".

**Warum beide Sorten in einer Liste.** Weil die Frage eine ist. Früher stand
das Freigeben in „lernen" und die Auswahl der Grundmodelle in „schreiben" -
zwei Ansichten, zwei Listen, zwei Begriffe für dieselbe Entscheidung, und
keine von beiden zeigte, ob sich das Training überhaupt gelohnt hat. Wer
wissen will, ob sein eigenes Modell `medium` schlägt, braucht beide in einer
Tabelle.

**Warum Freigeben ein eigener Schritt bleibt.** Ein durchgelaufenes Training
ist noch kein Modell, das jemand benutzen soll. Zwischen „hat gerechnet" und
„damit diktiere ich" liegt der Blick auf die Zahlen, und den nimmt einem
nichts ab. Deshalb entsteht ein Stand mit `status: fertig` und nicht `active`.

**Warum trotzdem alle stehen bleiben.** Vier Läufe ergeben vier Stände, und
welcher der beste ist, beantwortet man nicht, indem man drei wegwirft.
Freigegeben ist höchstens einer; die übrigen bleiben messbar daneben stehen.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from wortlaut import augmentierung, laeufe as lauf_layout, registry

from ..config import einstellungen
from ..deps import Datenbank, Korpus, SprecherId
from ..services import messwerte

router = APIRouter(prefix="/lernen/api/modelle", tags=["Modelle"])

GRUNDMODELL = "grundmodell"
TRAINIERT = "trainiert"

METHODEN = {"full": "Volles Training", "lora": "Feintuning (LoRA)"}
DATEN = {"original": "Nur Originale", "augmentiert": "Mit Abwandlungen"}


class MassAntwort(BaseModel):
    """Ein Maß, wie die Tabelle es beschriftet - die Liste kommt vom Server.

    Aus demselben Grund wie in „hören": Ein Maß dazu ist eine Zeile in
    `metriken.py` und ein Eintrag hier, und nicht zusätzlich eine Liste im
    Browser, die jemand nachzupflegen vergisst.
    """

    schluessel: str
    name: str
    kurz: str
    erklaerung: str
    hoch_ist_gut: bool
    einheit: str
    # Nachkommastellen in der Tabelle. Eine Wortfehlerrate von „0,1" ist keine
    # Auskunft; eine Genauigkeit von „91,3421 %" auch nicht.
    stellen: int


MASSE = [
    MassAntwort(
        schluessel="genauigkeit",
        name="Genauigkeit",
        kurz="Genauigkeit",
        erklaerung="Die vier Fehlermaße zu einer Zahl zusammengefasst, 0 bis 100.",
        hoch_ist_gut=True,
        einheit=" %",
        stellen=1,
    ),
    MassAntwort(
        schluessel="wer",
        name="Wortfehlerrate (WER)",
        kurz="WER",
        erklaerung="Anteil falscher, fehlender und zusätzlicher Wörter.",
        hoch_ist_gut=False,
        einheit="",
        stellen=3,
    ),
    MassAntwort(
        schluessel="cer",
        name="Zeichenfehlerrate (CER)",
        kurz="CER",
        erklaerung="Dasselbe auf Zeichen - feiner, aber blind für den Sinn.",
        hoch_ist_gut=False,
        einheit="",
        stellen=3,
    ),
    MassAntwort(
        schluessel="rechenzeit_s",
        name="Rechenzeit",
        kurz="Zeit",
        erklaerung=(
            "Sekunden je Testaufnahme - die andere Hälfte jeder Modellwahl. "
            "Gemessen dort, wo das Modell lief; zwischen Karte und Prozessor "
            "liegen Größenordnungen."
        ),
        hoch_ist_gut=False,
        einheit=" s",
        stellen=2,
    ),
]


class FassungAntwort(BaseModel):
    schluessel: str
    name: str
    erklaerung: str


FASSUNGEN = [
    FassungAntwort(
        schluessel=messwerte.ALLE,
        name="Alle Fassungen",
        erklaerung="Original und Abwandlungen zusammen - die Zahl, die einen Stand beschreibt.",
    ),
    FassungAntwort(
        schluessel=augmentierung.ORIGINAL,
        name="Original",
        erklaerung="Die Aufnahme, wie sie gesprochen wurde.",
    ),
    *(
        FassungAntwort(
            schluessel=abwandlung.name,
            name=abwandlung.titel,
            erklaerung=abwandlung.erklaerung,
        )
        for abwandlung in augmentierung.ABWANDLUNGEN
    ),
]


class ModellAntwort(BaseModel):
    """Eine Zeile der Tabelle - ein Grundmodell oder ein trainierter Stand."""

    ref: str
    art: str  # grundmodell | trainiert
    # Die Hauptzeile: „whisper-medium" oder „Feintuning (LoRA) · Mit Abwandlungen".
    name: str
    # Die Nebenzeile: Herkunft, Datum, Version.
    herkunft: str
    basismodell: str
    methode: str | None
    daten: str | None
    erstellt: str | None
    version: str | None
    job_id: str | None
    freigegeben: bool
    # fassung -> maß -> Wert. Leer heißt: für dieses Modell liegt auf den
    # gemeinsamen Testaufnahmen nichts vor.
    werte: dict[str, dict[str, float]]
    # fassung -> wie viele Einheiten in diesem Mittel stecken.
    einheiten: dict[str, int]


class UebersichtAntwort(BaseModel):
    modelle: list[ModellAntwort]
    masse: list[MassAntwort]
    fassungen: list[FassungAntwort]
    # Was gerade gilt; leer heißt: es gilt, womit die Installation anfängt.
    freigegeben: str
    # Wie viele Aufnahmen im Testteil liegen und wie viele Einheiten (Aufnahme
    # mal Fassung) wirklich von allen gemessen wurden.
    testaufnahmen: int
    gemeinsame_einheiten: int
    # Ob alle Zahlen auf demselben Boden stehen. `false` heißt: Es gibt keine
    # Einheit, die jedes messende Modell hat - jede Zeile rechnet dann auf dem,
    # was sie hat, und die Ansicht sagt es dazu.
    vergleichbar: bool
    hinweis: str


class Freigabe(BaseModel):
    """Was gelten soll. Leer nimmt die Freigabe zurück."""

    ref: str = ""


def _grundmodellnamen() -> list[str]:
    konfiguration = einstellungen()
    namen = [
        teil.strip() for teil in konfiguration.auswertung_modelle.split(",") if teil.strip()
    ]
    # Das Grundmodell, auf das trainiert wird, steht immer dabei - sonst fehlte
    # ausgerechnet die Grundlinie, gegen die jeder Stand antritt.
    kurz = konfiguration.lernen_basismodell.rsplit("/", 1)[-1].removeprefix("whisper-")
    if kurz not in namen:
        namen.append(kurz)
    return namen


def _stand_name(manifest: dict) -> str:
    methode = METHODEN.get(str(manifest.get("methode")), str(manifest.get("methode", "?")))
    daten = DATEN.get(str(manifest.get("daten")), str(manifest.get("daten", "?")))
    return f"{methode} · {daten}"


def _stand_herkunft(manifest: dict) -> str:
    grund = str(manifest.get("basismodell", "?")).rsplit("/", 1)[-1]
    datum = str(manifest.get("erstellt", ""))[:10]
    return " · ".join(teil for teil in (f"aus {grund}", datum) if teil.strip(" ·"))


@router.get("", response_model=UebersichtAntwort)
def uebersicht(db: Datenbank, korpus: Korpus, sprecher: SprecherId) -> UebersichtAntwort:
    """Alle Modelle mit ihren Zahlen auf den gemeinsamen Testaufnahmen."""
    konfiguration = einstellungen()
    aufnahmen = messwerte.testaufnahmen(db, korpus)
    namen = _grundmodellnamen()

    reihen = messwerte.grundmodelle(korpus, namen, aufnahmen)
    staende = registry.alle_staende(konfiguration.data_dir, sprecher)
    for manifest in staende:
        lauf = (
            lauf_layout.lies_lauf(konfiguration.data_dir, str(manifest.get("job_id")))
            if manifest.get("job_id")
            else None
        )
        reihen[str(manifest.get("id", ""))] = (
            messwerte.stand(lauf, aufnahmen) if lauf is not None else messwerte.Messreihe()
        )

    gemeinsam = messwerte.gemeinsame_einheiten(list(reihen.values()))
    # Vergleichbar heißt: Es gibt mindestens zwei Modelle mit Zahlen, und diese
    # Zahlen stehen auf denselben Messeinheiten. Ein einzelnes gemessenes
    # Modell ergibt zwar eine Schnittmenge mit sich selbst, aber keinen
    # Vergleich - und die Ansicht soll nicht so tun, als gäbe es einen.
    #
    # Ohne gemeinsamen Boden rechnet jede Zeile auf dem, was sie hat. Eine
    # leere Tabelle verschwiege, dass überhaupt gemessen wurde; der Vorbehalt
    # steht stattdessen als Hinweis darüber.
    messende = [ref for ref, reihe in reihen.items() if reihe.werte]
    vergleichbar = len(messende) > 1 and bool(gemeinsam)
    freigegeben = registry.freigegeben(konfiguration.data_dir, sprecher)

    def zeile(ref: str, art: str, name: str, herkunft: str, manifest: dict) -> ModellAntwort:
        reihe = reihen[ref]
        boden = gemeinsam if vergleichbar else set(reihe.werte)
        return ModellAntwort(
            ref=ref,
            art=art,
            name=name,
            herkunft=herkunft,
            basismodell=str(manifest.get("basismodell", ref)),
            methode=manifest.get("methode"),
            daten=manifest.get("daten"),
            erstellt=manifest.get("erstellt"),
            version=str(manifest["id"]).split("/", 1)[-1] if manifest.get("id") else None,
            job_id=manifest.get("job_id"),
            freigegeben=ref == freigegeben,
            werte=reihe.mittel(boden),
            einheiten=reihe.einheiten_je_fassung(boden),
        )

    modelle = [
        zeile(name, GRUNDMODELL, f"whisper-{name}", "unverändert, so wie Whisper es ausliefert", {})
        for name in namen
    ]
    # Jüngster Stand zuerst: Wer hierherkommt, sucht meist den, der gerade
    # fertig wurde. Die Grundmodelle stehen darüber - sie sind die Grundlinie.
    modelle += [
        zeile(
            str(manifest.get("id", "")),
            TRAINIERT,
            _stand_name(manifest),
            _stand_herkunft(manifest),
            manifest,
        )
        for manifest in reversed(staende)
    ]

    return UebersichtAntwort(
        modelle=modelle,
        masse=MASSE,
        fassungen=FASSUNGEN,
        freigegeben=freigegeben,
        testaufnahmen=len(aufnahmen),
        gemeinsame_einheiten=len(gemeinsam),
        vergleichbar=vergleichbar,
        hinweis=_hinweis(aufnahmen, reihen, namen, staende),
    )


def _hinweis(
    aufnahmen: set[str],
    reihen: dict[str, messwerte.Messreihe],
    namen: list[str],
    staende: list[dict],
) -> str:
    """Was fehlt, damit die Tabelle etwas taugt - höchstens eine Zeile davon.

    In der Reihenfolge, in der es fehlt: erst Aufnahmen, dann die Messung der
    Grundmodelle, dann ein eigenes Modell. Alle drei auf einmal zu nennen wäre
    eine Mängelliste; gefragt ist der nächste Schritt.
    """
    if not aufnahmen:
        return (
            "Noch keine Testaufnahmen. Ein Drittel des Korpus wird zum Prüfen "
            "zurückgelegt, sobald in \u201ehören\u201c gesprochen wird."
        )
    if not any(reihen[name].werte for name in namen):
        return (
            "Die Grundmodelle haben auf diesen Aufnahmen noch nichts gemessen. "
            "In \u201ehören\u201c unter \u201eAuswertung\u201c laufen sie über den Korpus - "
            "danach steht hier eine Grundlinie, gegen die sich vergleichen lässt."
        )
    if not staende:
        return (
            "Noch kein eigenes Modell. Unter \u201eTraining\u201c wird ein Lauf beauftragt; "
            "sein Stand tritt danach hier gegen die Grundmodelle an."
        )
    if not messwerte.gemeinsame_einheiten(list(reihen.values())):
        return (
            "Die Zahlen stehen nicht auf demselben Boden: Es gibt keine Testaufnahme, "
            "die jedes Modell gemessen hat. Ein erneuter Lauf der Auswertung in "
            "\u201ehören\u201c holt die fehlenden nach."
        )
    return ""


@router.post("/freigabe", response_model=UebersichtAntwort)
def gib_frei(
    freigabe: Freigabe, db: Datenbank, korpus: Korpus, sprecher: SprecherId
) -> UebersichtAntwort:
    """Dieses Modell freigeben - und damit jedes andere zurückziehen.

    Geprüft wird gegen die Liste, die dieser Weg selbst anbietet, und nicht
    gegen das Dateisystem: Ein beliebiger Pfad im Feld wäre sonst ein Weg,
    fremde Verzeichnisse laden zu lassen - und der Stand eines anderen
    Sprechers ist fremde Stimme.
    """
    konfiguration = einstellungen()
    erlaubt = {
        *(_grundmodellnamen()),
        *(
            str(manifest.get("id", ""))
            for manifest in registry.alle_staende(konfiguration.data_dir, sprecher)
        ),
    }
    if freigabe.ref and freigabe.ref not in erlaubt:
        raise HTTPException(status_code=404, detail="Dieses Modell steht hier nicht zur Wahl.")

    registry.gib_frei(konfiguration.data_dir, sprecher, freigabe.ref)
    return uebersicht(db, korpus, sprecher)
