"""Alle Modelle eines Sprechers an einem Ort - gemessen, verglichen, freigegeben.

Dieser eine Weg beantwortet die ganze Frage „womit spreche ich?": Er stellt die
unveränderten Grundmodelle und die selbst trainierten Stände nebeneinander,
misst sie an denselben Aufnahmen (siehe `services/messwerte.py`) und sagt,
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
from wortlaut import augmentierung, laeufe as lauf_layout, registry, streuung

from ..config import einstellungen
from ..deps import Korpus, SprecherId
from ..services import messwerte

router = APIRouter(prefix="/lernen/api/modelle", tags=["Modelle"])

GRUNDMODELL = "grundmodell"
TRAINIERT = "trainiert"

METHODEN = {"full": "Volles Training", "lora": "Feintuning (LoRA)"}
DATEN = {"original": "Nur Originale", "augmentiert": "Mit Abwandlungen"}
# Die übrigen Achsen, kurz beschriftet - sie stehen seit September 2026 im
# **Titel** einer Zeile und müssen deshalb in eine Tabellenspalte passen.
#
# Die Vorgabewerte fehlen überall (`bester`, `keine`, `fest`): Sie sind das
# Verfahren, nach dem jeder Stand davor entstand, und sie in jede Zeile zu
# schreiben ergäbe Wörter, die nichts unterscheiden.
ABSCHLUESSE = {
    "mittel": "gemittelt",
    "interpoliert": "interpoliert",
    "beides": "gemittelt+interpoliert",
}
AUGMENTIERUNGEN = {
    "masken": "Masken",
    "umgebung": "Umgebung",
    "voll": "Umgebung+Tempo",
}
DAUERN = {"geduldig": "geduldig"}


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
            "Sekunden je Aufnahme - die andere Hälfte jeder Modellwahl. "
            "Sie hängt an der Maschine und nicht am Modell: Zwischen Karte und "
            "Prozessor liegt das Zehn- bis Zwanzigfache. Verglichen wird sie "
            "deshalb nur, wenn alle Zeilen dasselbe Rechenwerk nennen."
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
    # Worauf die Zahlen dieser Zeile gemessen wurden - `cuda/int8_float16`,
    # `cpu/int8`, leer bei Unbekanntem oder Gemischtem. Nur die **Rechenzeit**
    # hängt daran; Genauigkeit und Fehlerraten ändern sich mit der Maschine
    # nicht nennenswert.
    rechenwerk: str
    # fassung -> maß -> Wert. Leer heißt: für dieses Modell liegt auf den
    # gemeinsamen Aufnahmen nichts vor.
    werte: dict[str, dict[str, float]]
    # fassung -> wie viele Einheiten in diesem Mittel stecken.
    einheiten: dict[str, int]
    # fassung -> maß -> Vertrauensbereich. Leer, solange keiner angefordert
    # wurde (`?intervall=aus`, die Vorgabe) - die Werte darüber sind dieselben
    # mit oder ohne.
    intervalle: dict[str, dict[str, dict]] = {}
    # fassung -> maß -> der gepaarte Abstand zu dem Modell aus `vergleich_mit`.
    # Leer, solange keines genannt wurde.
    unterschied: dict[str, dict[str, dict]] = {}


class UebersichtAntwort(BaseModel):
    modelle: list[ModellAntwort]
    masse: list[MassAntwort]
    fassungen: list[FassungAntwort]
    # Was gerade gilt; leer heißt: es gilt, womit die Installation anfängt.
    freigegeben: str
    # Wie viele Aufnahmen es gibt und wie viele Einheiten (Aufnahme mal
    # Fassung) wirklich von allen gemessen wurden. Seit der Kreuzvalidierung
    # sind das alle: Jede Aufnahme ist einmal von einem Modell gehört worden,
    # das sie nicht kannte (`training/bewerten.py`).
    messaufnahmen: int
    gemeinsame_einheiten: int
    # Ob alle Zahlen auf demselben Boden stehen. `false` heißt: Es gibt keine
    # Einheit, die jedes messende Modell hat - jede Zeile rechnet dann auf dem,
    # was sie hat, und die Ansicht sagt es dazu.
    vergleichbar: bool
    # Ob die **Rechenzeiten** untereinander etwas aussagen: Sie tun es nur,
    # wenn alle messenden Modelle dasselbe Rechenwerk nennen. Ein Prozessor
    # und eine Karte trennen sie um eine Größenordnung, und das sagt nichts
    # über das Modell.
    zeit_vergleichbar: bool
    hinweis: str
    # Welche Blockart angefordert wurde: `aus`, `aufnahme` oder `einheit`.
    intervall: str = streuung.AUS
    # Gegen welches Modell gepaart verglichen wurde; leer heißt: gegen keines.
    vergleich_mit: str = ""
    # Womit gerechnet wurde, in einer Zeichenkette - damit eine Zahl, die
    # jemand herausschreibt, ihr Verfahren bei sich trägt. Leer bei `aus`.
    streuung_marke: str = ""


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
    kurz = lauf_layout.kurzname(konfiguration.lernen_basismodell)
    if kurz not in namen:
        namen.append(kurz)
    return namen


def _achsen(manifest: dict) -> list[str]:
    """Die Achsen, in denen dieser Stand von der Vorgabe abweicht.

    **Warum das in den Titel gehört und nicht in die Nebenzeile.** Bis
    September 2026 hieß ein Stand nach Methode und Datensatz, und das genügte,
    solange es nur diese beiden Achsen gab. Inzwischen sind es sechs - und zwei
    Läufe, die sich nur im Abschluss unterschieden, trugen damit **denselben
    Titel**. In einer Liste, in der je Zeile ein Knopf „freigeben" steht, ist
    das kein Schönheitsfehler, sondern die Falle, in die man tritt: Zwei Stände
    hießen beide „Feintuning (LoRA) · Mit Abwandlungen", unterschieden nur
    durch ein Fragment tief in der grauen Nebenzeile - und freigegeben wurde
    daraufhin der falsche.

    Das Grundmodell steht mit dabei, sobald es nicht die Vorgabe ist: Es ist
    der stärkste Unterschied zwischen zwei Ständen überhaupt.
    """
    teile = []
    grund = lauf_layout.kurzname(str(manifest.get("basismodell", "")))
    if grund and grund != lauf_layout.kurzname(einstellungen().lernen_basismodell):
        teile.append(f"whisper-{grund}")
    for karte, wert in (
        (ABSCHLUESSE, manifest.get("abschluss")),
        (AUGMENTIERUNGEN, manifest.get("augmentierung")),
        (DAUERN, manifest.get("dauer")),
    ):
        beschriftung = karte.get(str(wert or ""), "")
        if beschriftung:
            teile.append(beschriftung)
    return teile


def _stand_name(manifest: dict) -> str:
    """Der Titel einer Zeile - und er muss diese Zeile von jeder anderen trennen."""
    methode = METHODEN.get(str(manifest.get("methode")), str(manifest.get("methode", "?")))
    daten = DATEN.get(str(manifest.get("daten")), str(manifest.get("daten", "?")))
    return " · ".join([methode, daten, *_achsen(manifest)])


def _abschluss_befund(manifest: dict) -> str:
    """Was beim Abschluss herauskam - α, oder dass er zurückgenommen wurde.

    Das gehört in die Nebenzeile und nicht in den Titel: Es unterscheidet zwei
    Zeilen nicht, es erklärt eine.
    """
    name = ABSCHLUESSE.get(str(manifest.get("abschluss", "")), "")
    if not name:
        return ""
    # Zurückgenommen heißt: Der Abschluss hat auf der Validierung nicht
    # geholfen, ausgeliefert wurde der beste Durchgang. Das als „gemittelt" zu
    # beschriften wäre die Behauptung eines Gewinns, den es nicht gab.
    if (manifest.get("abschluss_bericht") or {}).get("zurueckgenommen"):
        return "zurückgenommen"
    alpha = (manifest.get("abschluss_bericht") or {}).get("alpha")
    if alpha is None:
        return ""
    # Auch die Null: α = 0 heißt, dass die Wahl auf der Validierung den
    # feingetunten Stand behalten hat - eine Auskunft über diesen Lauf, und
    # nicht dasselbe wie ein Stand, bei dem nie interpoliert wurde.
    return f"α={float(alpha):.2f}".replace(".", ",")


def _stand_herkunft(manifest: dict) -> str:
    """Die Nebenzeile: woher der Stand kommt und **wann** er entstand.

    Die Uhrzeit und nicht nur das Datum. Wer an einem Nachmittag drei Läufe
    rechnet, hat sonst drei Zeilen mit demselben Datum - und wenn zwei davon
    dasselbe Rezept tragen, wieder nichts, woran man sie auseinanderhält.
    """
    grund = f"whisper-{lauf_layout.kurzname(str(manifest.get('basismodell', '?')))}"
    wann = str(manifest.get("erstellt", "")).replace("T", " ")[:16]
    return " · ".join(
        teil
        for teil in (f"aus {grund}", _abschluss_befund(manifest), wann)
        if teil.strip(" ·")
    )


@router.get("", response_model=UebersichtAntwort)
def uebersicht(
    korpus: Korpus,
    sprecher: SprecherId,
    intervall: str = streuung.AUS,
    vergleich_mit: str = "",
) -> UebersichtAntwort:
    """Alle Modelle mit ihren Zahlen auf den gemeinsamen Aufnahmen.

    **Was `intervall` tut - und was es ausdrücklich nicht tut.** Es legt neben
    jede Zahl den Bereich, in dem sie liegen dürfte (`wortlaut/streuung.py`).
    Die Zahl selbst ändert sich dadurch nicht um eine Stelle; wer den
    Parameter wegläßt, bekommt Byte für Byte die Antwort von vorher. Das ist
    hier keine Bequemlichkeit, sondern Bedingung: Diese Tabelle ist der Ort,
    an dem Modelle verglichen werden, und ein Vergleich taugt nur, solange
    dieselbe Messung bei jedem Aufruf dieselbe Zahl ergibt.

    `aufnahme` ist die statistisch richtige Wahl, sobald mehrere Fassungen
    derselben Aufnahme in der Reihe stehen - also immer, wenn die Fassung
    „alle" gezeigt wird. `einheit` zieht naiv je Messeinheit; der Bereich fällt
    dann etwa halb so breit aus. Wählbar ist es trotzdem, weil es das in der
    Literatur übliche Verfahren ist und die Zahlen dieses Projekts sonst mit
    keiner Veröffentlichung vergleichbar wären.

    **`vergleich_mit`** nennt ein Modell, gegen das jede andere Zeile gepaart
    antritt: auf denselben Aufnahmen, Differenz mit Bereich und p-Wert. Das ist
    die schärfere Frage - „ist mein Stand besser als `small`?" - und sie ist
    mit zwei einzelnen Bereichen nicht zu beantworten, weil diese sich auch
    dann überlappen, wenn der Abstand belastbar ist.
    """
    if intervall not in streuung.BLOCKARTEN:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannte Blockart. Zur Wahl stehen: {', '.join(streuung.BLOCKARTEN)}.",
        )
    konfiguration = einstellungen()
    aufnahmen = messwerte.messaufnahmen(korpus)
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
    # Die Rechenzeit ist eine Eigenschaft der Maschine, nicht des Modells:
    # Dasselbe whisper-small braucht auf einem Prozessor das Zehn- bis
    # Zwanzigfache dessen, was es auf einer Karte braucht. Verglichen werden
    # darf die Spalte nur, wenn alle dasselbe Rechenwerk nennen - und ein
    # unbekanntes zählt nicht als dasselbe.
    werke = {reihen[ref].werk for ref in messende}
    zeit_vergleichbar = len(werke) == 1 and "" not in werke
    freigegeben = registry.freigegeben(konfiguration.data_dir, sprecher)

    # Gegen wen gepaart verglichen wird. Ein Name, den die Tabelle nicht führt,
    # wird stillschweigend zu „gegen keinen": Der Vergleich ist eine Zugabe,
    # und eine Zugabe soll die Auskunft nicht mit einem Fehler ersetzen.
    gegen = reihen.get(vergleich_mit) if vergleich_mit else None

    def zeile(ref: str, art: str, name: str, herkunft: str, manifest: dict) -> ModellAntwort:
        reihe = reihen[ref]
        boden = gemeinsam if vergleichbar else set(reihe.werte)
        return ModellAntwort(
            ref=ref,
            art=art,
            name=name,
            herkunft=herkunft,
            rechenwerk=reihe.werk,
            basismodell=str(manifest.get("basismodell", ref)),
            methode=manifest.get("methode"),
            daten=manifest.get("daten"),
            erstellt=manifest.get("erstellt"),
            version=str(manifest["id"]).split("/", 1)[-1] if manifest.get("id") else None,
            job_id=manifest.get("job_id"),
            freigegeben=ref == freigegeben,
            werte=reihe.mittel(boden),
            einheiten=reihe.einheiten_je_fassung(boden),
            intervalle=reihe.intervalle(boden, intervall),
            # Gegen sich selbst zu vergleichen ergäbe eine Spalte Nullen mit
            # einem p-Wert von 1 - richtig, aber keine Auskunft.
            unterschied=(
                reihe.unterschied_zu(gegen, boden, intervall)
                if gegen is not None and ref != vergleich_mit
                else {}
            ),
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
        messaufnahmen=len(aufnahmen),
        gemeinsame_einheiten=len(gemeinsam),
        vergleichbar=vergleichbar,
        zeit_vergleichbar=zeit_vergleichbar,
        hinweis=_hinweis(aufnahmen, reihen, namen, staende),
        intervall=intervall,
        vergleich_mit=vergleich_mit if gegen is not None else "",
        streuung_marke=(
            streuung.Verfahren(blockart=intervall).marke if intervall != streuung.AUS else ""
        ),
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
            "Noch keine Aufnahmen im Korpus. Gemessen wird über alle, sobald in "
            "\u201ehören\u201c gesprochen wird."
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
            "Die Zahlen stehen nicht auf demselben Boden: Es gibt keine Aufnahme, "
            "die jedes Modell gemessen hat. Ein erneuter Lauf der Auswertung in "
            "\u201ehören\u201c holt die fehlenden nach."
        )
    return ""


@router.post("/freigabe", response_model=UebersichtAntwort)
def gib_frei(
    freigabe: Freigabe,
    korpus: Korpus,
    sprecher: SprecherId,
    intervall: str = streuung.AUS,
    vergleich_mit: str = "",
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
    # Dieselben Parameter zurückgegeben, mit denen die Tabelle gerade angezeigt
    # wird: Sonst verlöre sie beim Freigeben ihre Bereiche und die Ansicht
    # müsste ein zweites Mal fragen.
    return uebersicht(korpus, sprecher, intervall, vergleich_mit)
