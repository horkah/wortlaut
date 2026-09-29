"""Alle Modelle eines Sprechers an einem Ort - gemessen, verglichen, freigegeben.

Grundmodelle und trainierte Stände in einer Tabelle, gemessen an denselben
Aufnahmen (`services/messwerte.py`) - wer wissen will, ob sein Modell `medium`
schlägt, braucht beide nebeneinander. Mit dem freigegebenen diktiert
„schreiben".

**Freigeben ist ein eigener Schritt:** Zwischen „hat gerechnet" und „damit
diktiere ich" liegt der Blick auf die Zahlen; ein Stand entsteht als `fertig`.
Freigegeben ist höchstens einer, die übrigen bleiben messbar daneben.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from wortlaut import augmentierung, laeufe as lauf_layout, registry, streuung

from ..config import einstellungen
from ..deps import Korpus, SprecherId
from ..services import freigabe, grundmodelle, messwerte
from .laeufe import METHODEN, SteckbriefZeile

router = APIRouter(prefix="/lernen/api/modelle", tags=["Modelle"])

GRUNDMODELL = "grundmodell"
TRAINIERT = "trainiert"

class MassAntwort(BaseModel):
    """Ein Maß, wie die Tabelle es beschriftet - die Liste kommt vom Server."""

    schluessel: str
    name: str
    kurz: str
    erklaerung: str
    hoch_ist_gut: bool
    einheit: str
    # Nachkommastellen in der Tabelle.
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
            "Sekunden je Aufnahme. Sie hängt an der Maschine: Zwischen Karte und "
            "Prozessor liegt das Zehn- bis Zwanzigfache. Vergleichbar nur, wenn "
            "alle Zeilen dasselbe Rechenwerk nennen."
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


def _vorbehalt(manifest: dict) -> str:
    """Was gegen diesen Stand spricht - in einem Satz, sonst leer.

    Die Prüfung lässt das Endmodell gelernte Aufnahmen hören. Bleibt es hinter
    seinen Faltungen auf Ungehörtem zurück, taugt es nicht - und die Zahlen
    seiner Zeile stammen von den Faltungen (`training/bewerten.py`).
    """
    pruefung = manifest.get("pruefung") or {}
    if not pruefung.get("auffaellig"):
        return ""
    if pruefung.get("grund") == "ausgefranst":
        return (
            f"Geprüft: {pruefung['ausgefranst']} von {pruefung['stichprobe']} Ausgaben sind "
            "länger als alles Gesagte - dieser Stand wiederholt oder erfindet weiter, und "
            "zwar auf Aufnahmen, die er gelernt hat. Meist hilft dagegen nur mehr Material."
        )
    return (
        f"Geprüft und durchgefallen: WER {pruefung['wer_median']:.2f} auf Aufnahmen, die "
        f"dieser Stand gelernt hat - seine Faltungen standen auf Ungehörtem bei "
        f"{pruefung['faltungen_wer_median']:.2f}. Die Zahlen rechts stammen von den "
        "Faltungen und sagen über diesen Stand nichts."
    )


class ModellAntwort(BaseModel):
    """Eine Zeile der Tabelle - ein Grundmodell oder ein trainierter Stand."""

    ref: str
    art: str  # grundmodell | trainiert
    # Die Hauptzeile: „whisper-medium" oder der Optionscode, etwa „ML-A-C".
    name: str
    # Die Nebenzeile: Herkunft, Datum, Version.
    herkunft: str
    basismodell: str
    methode: str | None
    daten: str | None
    erstellt: str | None
    version: str | None
    # Der kurze Code (`K7M2Q`, `registry.kurzkennung`); `null` bei einem Grundmodell.
    kennung: str | None
    # Ein Satz, wenn der Stand die Prüfung nicht bestand (`_vorbehalt`), sonst leer.
    vorbehalt: str
    # „nur 5 von 6 Faltungen", wenn das Endmodell nicht alle mittelt - die Zahlen
    # der Zeile stammen dann nur von den gemittelten (`_gemittelte_faltungen`).
    faltungen_hinweis: str = ""
    job_id: str | None
    freigegeben: bool
    # Worauf gemessen wurde; leer bei Unbekanntem oder Gemischtem. Betrifft nur
    # die Rechenzeit.
    rechenwerk: str
    # fassung -> maß -> Wert.
    werte: dict[str, dict[str, float]]
    # fassung -> wie viele Einheiten in diesem Mittel stecken.
    einheiten: dict[str, int]
    # fassung -> maß -> Vertrauensbereich; leer bei `?intervall=aus`.
    intervalle: dict[str, dict[str, dict]] = {}
    # fassung -> maß -> gepaarter Abstand zu `vergleich_mit`.
    unterschied: dict[str, dict[str, dict]] = {}


class UebersichtAntwort(BaseModel):
    modelle: list[ModellAntwort]
    masse: list[MassAntwort]
    fassungen: list[FassungAntwort]
    # Leer: die Vorgabe der Installation.
    freigegeben: str
    # Aufnahmen, und Einheiten (Aufnahme mal Fassung), die alle gemessen haben.
    messaufnahmen: int
    gemeinsame_einheiten: int
    # `false`: Jede Zeile rechnet auf ihrem eigenen Boden.
    vergleichbar: bool
    # Ob alle messenden Modelle dasselbe Rechenwerk nennen.
    zeit_vergleichbar: bool
    hinweis: str
    # `aus`, `aufnahme` oder `einheit`.
    intervall: str = streuung.AUS
    # Gegen welches Modell gepaart verglichen wurde.
    vergleich_mit: str = ""
    # Das Verfahren in einer Zeichenkette, damit es herausgeschriebene Zahlen
    # begleitet. Leer bei `aus`.
    streuung_marke: str = ""


class Freigabe(BaseModel):
    """Was gelten soll. Leer nimmt die Freigabe zurück."""

    ref: str = ""


def _gemittelte_faltungen(manifest: dict) -> tuple[set[int], str] | None:
    """Welche Faltungen im Endmodell stecken - `None`, wenn es alle sind.

    Die Tabelle dient der Wahl eines Modells, also zählt, was ausgeliefert
    wird: Eine ausgelassene Faltung hat nichts zum Endmodell beigetragen, ihre
    Messungen sagen über es nichts. Die Zahl des Laufs in seiner Einzelansicht
    zählt sie weiter mit - sie beschreibt das Training.
    """
    befund = dict(manifest.get("endmodell") or {})
    ausgelassen = list(befund.get("ausgelassen") or [])
    if not ausgelassen:
        return None
    gemittelt = {int(faltung) for faltung in befund.get("faltungen") or []}
    return gemittelt, f"nur {len(gemittelt)} von {len(gemittelt) + len(ausgelassen)} Faltungen"


def _stand_name(manifest: dict) -> str:
    """Der Titel einer Zeile: Optionscode und Folge des Laufs, aus dem der Stand kam.

    Aus dem Auftrag, solange es ihn gibt, sonst aus dem Manifest.
    """
    job_id = str(manifest.get("job_id") or "")
    lauf = lauf_layout.lies_lauf(einstellungen().data_dir, job_id) if job_id else None
    return lauf_layout.titel(lauf.auftrag if lauf is not None else manifest)


def _abschluss_befund(manifest: dict) -> str:
    """Was beim Abschluss herauskam - α, oder dass er zurückgenommen wurde.

    Nebenzeile statt Titel: Es erklärt eine Zeile, statt zwei zu unterscheiden.
    """
    if str(manifest.get("abschluss") or "") in ("", lauf_layout.ABSCHLUSS_BESTER):
        return ""
    # Der Abschluss half auf der Validierung nicht; ausgeliefert wurde der
    # beste Durchgang.
    if (manifest.get("abschluss_bericht") or {}).get("zurueckgenommen"):
        return "zurückgenommen"
    alpha = (manifest.get("abschluss_bericht") or {}).get("alpha")
    if alpha is None:
        return ""
    # Auch α = 0: gewählt, nicht nie interpoliert.
    return f"α={float(alpha):.2f}".replace(".", ",")


def _tempo_befund(manifest: dict) -> str:
    """Bei welcher Geschwindigkeit dieser Stand gelernt hat - wenn nicht 1,0.

    Neben dem α: Es erklärt, warum ein Stand deutlich besser dastehen kann.
    """
    faktor = float(manifest.get("tempo", 1.0) or 1.0)
    if faktor == 1.0:
        return ""
    return f"Tempo {faktor:.2f}".replace(".", ",").rstrip("0").rstrip(",") + "×"


def _stand_herkunft(manifest: dict) -> str:
    """Die Nebenzeile: woher der Stand kommt.

    Ohne Zeit: `erstellt` formatiert die Ansicht in der Zeitzone des Lesers
    (`packages/ui/zeit.ts`).
    """
    grund = f"whisper-{lauf_layout.kurzname(str(manifest.get('basismodell', '?')))}"
    ausgang = str(manifest.get(lauf_layout.AUSGANGSSTAND) or "")
    if ausgang:
        grund = f"{registry.beschriftung(ausgang)} auf {grund}"
    return " · ".join(
        teil
        for teil in (f"aus {grund}", _abschluss_befund(manifest), _tempo_befund(manifest))
        if teil.strip(" ·")
    )


# Aus oder je Aufnahme - die Ziehung je Einheit wäre hier zu schmal.
ANGEBOTEN = (streuung.AUS, streuung.BLOCK_AUFNAHME)


@router.get("", response_model=UebersichtAntwort)
def uebersicht(
    korpus: Korpus,
    sprecher: SprecherId,
    intervall: str = streuung.AUS,
    vergleich_mit: str = "",
) -> UebersichtAntwort:
    """Alle Modelle mit ihren Zahlen auf den gemeinsamen Aufnahmen.

    `intervall=aufnahme` legt neben jede Zahl ihren Bereich
    (`wortlaut/streuung.py`); die Zahlen selbst bleiben dieselben. Gezogen
    wird blockweise je Aufnahme - ihre Fassungen sind nicht unabhängig, und je
    Einheit gezogen wäre der Bereich etwa halb so breit wie der richtige.

    `vergleich_mit` paart jede andere Zeile gegen ein Modell: Differenz mit
    Bereich und p-Wert - schärfer als zwei überlappende Bereiche.
    """
    if intervall not in ANGEBOTEN:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannte Blockart. Zur Wahl stehen: {', '.join(ANGEBOTEN)}.",
        )
    konfiguration = einstellungen()
    aufnahmen = messwerte.messaufnahmen(korpus)
    namen = freigabe.grundmodellnamen()

    reihen = messwerte.grundmodelle(korpus, namen, aufnahmen)
    staende = registry.alle_staende(konfiguration.data_dir, sprecher)
    # Die Zeile eines Standes, dessen Endmodell nicht alle Faltungen mittelt,
    # rechnet nur mit den gemittelten. Den gemeinsamen Boden bestimmt weiter
    # seine volle Reihe - die übrigen Zeilen verlieren dadurch keine Einheit,
    # auch wenn seine dann auf weniger Einheiten steht als ihre. Der Hinweis
    # unter dem Namen sagt es.
    gezeigt: dict[str, messwerte.Messreihe] = {}
    hinweise: dict[str, str] = {}
    for manifest in staende:
        lauf = (
            lauf_layout.lies_lauf(konfiguration.data_dir, str(manifest.get("job_id")))
            if manifest.get("job_id")
            else None
        )
        ref = str(manifest.get("id", ""))
        # Später Aufgenommenes steht im Korpus (`services/messwerte.stand`).
        reihen[ref] = (
            messwerte.stand(lauf, aufnahmen, korpus, ref)
            if lauf is not None
            else messwerte.Messreihe()
        )
        teil = _gemittelte_faltungen(manifest)
        if teil is not None:
            gemittelt, hinweise[ref] = teil
            gezeigt[ref] = reihen[ref].nur_aus(gemittelt)

    # Das Tempo trennt nichts: Ein Stand bringt es mit, „schreiben" spult
    # beim Diktieren genauso vor (`schreiben/deps.tempo_fuer`). Es gehört zum
    # Modell, nicht zu den Prüfbedingungen.
    gemeinsam = messwerte.gemeinsame_einheiten(list(reihen.values()))
    # Mindestens zwei gemessene Modelle auf denselben Einheiten. Sonst rechnet
    # jede Zeile auf ihrem, und der Hinweis sagt es.
    messende = [ref for ref, reihe in reihen.items() if reihe.werte]
    vergleichbar = len(messende) > 1 and bool(gemeinsam)
    # Ein unbekanntes Rechenwerk zählt nicht als dasselbe.
    werke = {reihen[ref].werk for ref in messende}
    zeit_vergleichbar = len(werke) == 1 and "" not in werke
    freigegeben = registry.freigegeben(konfiguration.data_dir, sprecher)

    # Ein unbekannter Name heißt „gegen keinen" - eine Zugabe, kein Fehler.
    gegen = gezeigt.get(vergleich_mit, reihen.get(vergleich_mit)) if vergleich_mit else None

    def zeile(ref: str, art: str, name: str, herkunft: str, manifest: dict) -> ModellAntwort:
        reihe = gezeigt.get(ref, reihen[ref])
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
            kennung=(
                registry.kurzkennung(str(manifest["id"]).split("/", 1)[-1])
                if manifest.get("id")
                else None
            ),
            vorbehalt=_vorbehalt(manifest),
            faltungen_hinweis=hinweise.get(ref, ""),
            job_id=manifest.get("job_id"),
            freigegeben=ref == freigegeben,
            werte=reihe.mittel(boden),
            einheiten=reihe.einheiten_je_fassung(boden),
            intervalle=reihe.intervalle(boden, intervall),
            # Nicht gegen sich selbst.
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
    # Unter der Baseline der jüngste Stand zuerst.
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


def bodenbegrenzer(reihen: dict[str, messwerte.Messreihe]) -> tuple[str, int, int]:
    """Welche Zeile den gemeinsamen Boden schmal hält - und wie breit er ohne sie wäre.

    Jede Zahl läuft über die Einheiten, die alle gemessen haben - also ändert
    das Verschwinden einer Zeile jede andere Zahl, bei einem Stand mit wenig
    gehörten Aufnahmen um ein Zehntel WER und mehr. Die Ansicht sagt das vor
    dem Löschen.

    `("", boden, boden)`, wenn keine Zeile den Boden nennenswert schmälert.
    """
    messende = {ref: reihe for ref, reihe in reihen.items() if reihe.werte}
    jetzt = len(messwerte.gemeinsame_einheiten(list(messende.values())))
    if len(messende) < 2:
        return "", jetzt, jetzt

    begrenzer, breiteste = "", jetzt
    for ref in messende:
        ohne = [reihe for schluessel, reihe in messende.items() if schluessel != ref]
        breite = len(messwerte.gemeinsame_einheiten(ohne))
        if breite > breiteste:
            begrenzer, breiteste = ref, breite
    # Erst ab einem Viertel mehr Boden - eine Warnung, die immer angeht, liest niemand.
    if breiteste < jetzt * 1.25:
        return "", jetzt, jetzt
    return begrenzer, jetzt, breiteste


def _hinweis(
    aufnahmen: set[str],
    reihen: dict[str, messwerte.Messreihe],
    namen: list[str],
    staende: list[dict],
) -> str:
    """Was fehlt, damit die Tabelle etwas taugt - höchstens eine Zeile davon.

    Der nächste Schritt, keine Mängelliste.
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
            "danach steht hier eine Baseline, gegen die sich vergleichen lässt."
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

    begrenzer, jetzt, ohne = bodenbegrenzer(reihen)
    if begrenzer:
        return (
            f"Alle Zahlen stehen auf {jetzt} gemeinsamen Einheiten - mehr hat "
            f"\u201e{_zeilenname(begrenzer, staende)}\u201c nicht gemessen. Ohne diese "
            f"Zeile wären es {ohne}, und dann fiele jede Zahl der Tabelle anders aus. "
            "Auch beim Löschen."
        )
    return ""


def _zeilenname(ref: str, staende: list[dict]) -> str:
    """Wie eine Zeile heißt - ob Grundmodell oder eigener Stand."""
    for manifest in staende:
        if str(manifest.get("id", "")) == ref:
            return _stand_name(manifest)
    return f"whisper-{ref}"


@router.post("/freigabe", response_model=UebersichtAntwort)
def gib_frei(
    wunsch: Freigabe,
    korpus: Korpus,
    sprecher: SprecherId,
    intervall: str = streuung.AUS,
    vergleich_mit: str = "",
) -> UebersichtAntwort:
    """Dieses Modell freigeben - und damit jedes andere zurückziehen
    (`services/freigabe.py`, dieselbe Stelle wie `make release`)."""
    try:
        freigabe.gib_frei(einstellungen().data_dir, sprecher, wunsch.ref)
    except freigabe.NichtFreigebbar as ursache:
        raise HTTPException(status_code=404, detail=str(ursache)) from ursache
    # Mit denselben Parametern, damit die Tabelle ihre Bereiche behält.
    return uebersicht(korpus, sprecher, intervall, vergleich_mit)


# ── Ein Grundmodell im Einzelnen ────────────────────────────────────────────


class GrundmodellEinzeln(BaseModel):
    """Die Einzelansicht eines Grundmodells - das Gegenstück zu der eines Laufs.

    Zwei Steckbriefe statt einem: was das Modell ist (`steckbrief`, aus der
    Modellkarte) und was davon hier liegt und läuft (`vor_ort`, gelesen).
    Darunter die Zahlen dieses Menschen, aus derselben Rechnung wie die Tabelle
    - neben denen des freigegebenen Modells, wenn das ein anderes ist.
    """

    name: str
    titel: str
    erklaerung: str
    freigegeben: bool
    steckbrief: list[SteckbriefZeile]
    vor_ort: list[SteckbriefZeile]
    # Die Zeile aus der Tabelle; `None`, solange „hören" nichts gemessen hat.
    modell: ModellAntwort | None
    # Die Zeile des freigegebenen Modells - `None`, wenn es dieses ist.
    freigabe: ModellAntwort | None
    masse: list[MassAntwort]
    fassungen: list[FassungAntwort]
    vergleichbar: bool


def _datum(iso: str) -> str:
    """`2022-09-21` → `21.09.2022` - ein Tag, kein Zeitpunkt."""
    jahr, monat, tag = iso.split("-")
    return f"{tag}.{monat}.{jahr}"


def _mio(anzahl: float) -> str:
    return f"{anzahl:,.0f} Mio.".replace(",", ".")


def _modellkarte(
    karte: grundmodelle.Modellkarte, erkennen: grundmodelle.Cacheeintrag | None
) -> list[SteckbriefZeile]:
    auskunft = grundmodelle.selbstauskunft(erkennen) if erkennen else None
    zeilen = [
        SteckbriefZeile(
            begriff="Herkunft",
            wert="OpenAI, Whisper",
            hinweis="Radford et al., \u201eRobust Speech Recognition via Large-Scale Weak Supervision\u201c",
        ),
        SteckbriefZeile(begriff="Veröffentlicht", wert=_datum(karte.veroeffentlicht)),
        SteckbriefZeile(
            begriff="Parameter",
            wert=_mio(karte.parameter_mio),
            # Gegenprobe an den Gewichten hier: float16, zwei Byte je Parameter.
            hinweis=(
                f"die Gewichte hier ergeben {_mio(erkennen.gewichte_bytes / 2e6)} (float16)"
                if erkennen and erkennen.gewichte_bytes
                else ""
            ),
        ),
        SteckbriefZeile(
            begriff="Aufbau",
            wert=(
                f"Encoder und Decoder je {karte.schichten} Schichten, "
                f"Breite {karte.breite}, {karte.koepfe} Köpfe"
            ),
            hinweis="Transformer",
        ),
        SteckbriefZeile(
            begriff="Eingang",
            wert=(
                f"Log-Mel-Spektrogramm, {(auskunft and auskunft.mel_kanaele) or karte.mel_kanaele} "
                f"Kanäle, Fenster {grundmodelle.FENSTER_S} s"
            ),
            hinweis="16 kHz mono",
        ),
        SteckbriefZeile(
            begriff="Ausgabe",
            wert=f"höchstens {grundmodelle.AUSGABE_TOKEN} Token je Fenster",
            hinweis=(
                f"Wortschatz {auskunft.wortschatz:,} Token".replace(",", ".")
                if auskunft and auskunft.wortschatz
                else ""
            ),
        ),
        SteckbriefZeile(
            begriff="Sprachen",
            wert=str((auskunft and auskunft.sprachen) or karte.sprachen),
            hinweis="eine Mischung, kein Modell je Sprache - Deutsch ist eine davon",
        ),
        SteckbriefZeile(begriff="Trainingsdaten", wert=karte.trainingsdaten),
        SteckbriefZeile(begriff="Lizenz", wert=grundmodelle.LIZENZ),
    ]
    return zeilen


def _hier(
    name: str,
    erkennen: grundmodelle.Cacheeintrag | None,
    zeile: ModellAntwort | None,
    sprecher: str,
    freigegeben: bool,
) -> list[SteckbriefZeile]:
    konfiguration = einstellungen()
    zeilen: list[SteckbriefZeile] = []
    if erkennen:
        zeilen += [
            SteckbriefZeile(
                begriff="Erkennen mit",
                wert=erkennen.repo,
                hinweis="CTranslate2-Fassung für faster-whisper - dieselbe in \u201ehören\u201c und \u201eschreiben\u201c",
            ),
            SteckbriefZeile(begriff="Revision", wert=erkennen.revision[:12], hinweis=erkennen.revision),
            SteckbriefZeile(begriff="Heruntergeladen", wert=erkennen.geladen, art="zeit"),
            SteckbriefZeile(
                begriff="Auf der Platte",
                wert=grundmodelle.groesse(erkennen.bytes),
                hinweis=f"davon {erkennen.gewichte} {grundmodelle.groesse(erkennen.gewichte_bytes)}",
            ),
        ]
    else:
        zeilen.append(
            SteckbriefZeile(
                begriff="Erkennen mit",
                wert=grundmodelle.repo_erkennen(name),
                hinweis="noch nicht im Cache - wird beim ersten Gebrauch geladen",
            )
        )
    if zeile and zeile.rechenwerk:
        zeilen.append(
            SteckbriefZeile(
                begriff="Gerechnet als",
                wert=zeile.rechenwerk,
                hinweis="Rechenwerk und Genauigkeit der Auswertung in \u201ehören\u201c",
            )
        )

    # Trainieren: nur, was `lernen` zur Wahl stellt - mit den Originalen von OpenAI.
    repo = grundmodelle.repo_trainieren(name)
    trainierbar = repo in konfiguration.grundmodelle()
    if trainierbar:
        namen = {wahl.schluessel: wahl.name for wahl in METHODEN}
        methoden = ", ".join(
            namen.get(methode, methode) for methode in konfiguration.methoden_fuer(repo)
        )
        original = grundmodelle.im_cache(repo)
        zeilen.append(
            SteckbriefZeile(
                begriff="Trainierbar",
                wert=methoden,
                hinweis=(
                    f"auf {repo}, Revision {original.revision[:12]}, "
                    f"{grundmodelle.groesse(original.bytes)}"
                    if original
                    else f"auf {repo} - noch nicht im Cache"
                ),
            )
        )
    else:
        zeilen.append(
            SteckbriefZeile(
                begriff="Trainierbar",
                wert="nicht zur Wahl",
                hinweis="nur als Baseline gemessen (WORTLAUT_LERNEN_GRUNDMODELLE)",
            )
        )

    staende = [
        manifest
        for manifest in registry.alle_staende(konfiguration.data_dir, sprecher)
        if lauf_layout.kurzname(str(manifest.get("basismodell", ""))) == name
    ]
    zeilen.append(
        SteckbriefZeile(
            begriff="Eigene Stände darauf",
            wert=str(len(staende)),
            hinweis=", ".join(
                registry.kurzkennung(str(manifest["id"]).split("/", 1)[-1])
                for manifest in staende
                if manifest.get("id")
            ),
        )
    )
    zeilen.append(
        SteckbriefZeile(
            begriff="Freigegeben",
            wert="ja" if freigegeben else "nein",
            hinweis="damit diktiert \u201eschreiben\u201c" if freigegeben else "",
        )
    )
    return zeilen


@router.get("/grundmodell/{name}", response_model=GrundmodellEinzeln)
def grundmodell(name: str, korpus: Korpus, sprecher: SprecherId) -> GrundmodellEinzeln:
    """Ein unverändertes Whisper-Modell im Einzelnen - was es ist, was hier liegt, wie es misst.

    Ohne Modellkarte (ein Grundmodell außerhalb von `KARTEN`) bleibt der erste
    Steckbrief leer; was hier liegt, steht trotzdem da.
    """
    if name not in freigabe.grundmodellnamen():
        raise HTTPException(status_code=404, detail="Dieses Grundmodell steht hier nicht zur Wahl.")
    karte = grundmodelle.KARTEN.get(name)

    tafel = uebersicht(korpus, sprecher)
    zeile = next((m for m in tafel.modelle if m.ref == name), None)
    # Nicht `freigabe` - so heißt das Modul, das oben die Namen liefert.
    freigegebenes = next((m for m in tafel.modelle if m.freigegeben and m.ref != name), None)
    freigegeben = tafel.freigegeben == name
    erkennen = grundmodelle.im_cache(grundmodelle.repo_erkennen(name))
    return GrundmodellEinzeln(
        name=name,
        titel=f"whisper-{name}",
        erklaerung=karte.erklaerung if karte else "",
        freigegeben=freigegeben,
        steckbrief=_modellkarte(karte, erkennen) if karte else [],
        vor_ort=_hier(name, erkennen, zeile, sprecher, freigegeben),
        modell=zeile,
        freigabe=freigegebenes,
        masse=MASSE,
        # Je Fassung einzeln, wie beim gelernten Stand - ohne das Mittel über alle.
        fassungen=[fassung for fassung in FASSUNGEN if fassung.schluessel != messwerte.ALLE],
        vergleichbar=tafel.vergleichbar,
    )
