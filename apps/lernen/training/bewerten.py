"""Jede Aufnahme einmal ungehört - und der Stand, der ausgeliefert wird.

Je Faltung hört das eben trainierte Modell das Sechstel, das es nicht kannte
(`services/aufteilung.py`); danach liegt zu jeder Aufnahme eine Messung von
einem Modell vor, das sie nie gehört hat.

**Zwei Modelle, eine Zeile.** Die Zahlen stammen aus den sechs Faltungen. Das
Modell, das „schreiben" anbietet, ist ihr Mittel (`endmodell.py`) - jede
Aufnahme steckt in fünf der sechs, darum ist es nicht ehrlich messbar. Die Zahl
daneben ist die der Faltungen.

Gemessen im Trainer, wo das Modell schon auf der Karte liegt, mit
`wortlaut/metriken.py` wie die Baseline in „hören".
"""

from __future__ import annotations

import sqlite3
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from wortlaut import (
    corpus,
    laeufe,
    metriken,
    registry,
    sprachen,
    streuung,
    tempo,
)

from wortlaut.whisper.local import startprompt

from apps.lernen.backend.config import einstellungen

from .adapter import adapter_fuer


# Das Grundmodell, das der Name eines Standes nicht nennt.
VORGABE_GRUNDMODELL = "small"


def _rezeptauszug(auftrag: dict[str, Any]) -> dict[str, Any]:
    """Die Stellschrauben des Rezepts, wie sie für diesen Lauf galten.

    Was man zum Wiederholen und Vergleichen braucht; die Augmentierungsstufe
    steht im Auftrag.
    """
    from .finetune import _rezept_fuer

    try:
        rezept = _rezept_fuer(
            str(auftrag.get("methode", "")), str(auftrag.get("basismodell", ""))
        )
    except Exception:  # noqa: BLE001 - ein fehlendes Rezept kostet den Stand nicht
        return {}

    lora = (
        adapter_fuer(rezept, auftrag).als_dict()
        if str(auftrag.get("methode")) == laeufe.LORA
        else {}
    )
    return {
        "lernrate": rezept.get("lernrate"),
        "warmlauf_schritte": rezept.get("warmlauf_schritte"),
        # Wirksam; wie er auf die Karte kam, steht unter `zuschnitt` im Manifest.
        "stapel": rezept.get("stapel"),
        "epochen": rezept.get("epochen"),
        "epochen_hoechstens": rezept.get("epochen_hoechstens"),
        "geduld": rezept.get("geduld"),
        # Bei LoRA Rang, α, Ausfall, Projektionen und Teile (`adapter.py`).
        **lora,
    }


def geltendes_tempo(auftrag: dict[str, Any], mitgenommen: dict[str, Any] | None) -> float:
    """Mit welcher Geschwindigkeit dieser Stand wirklich gerechnet hat.

    Ohne Tempowahl der Wert aus dem Auftrag, sonst der aus den Faltungen
    mitgenommene. Er geht in Name und Manifest, und „schreiben" spult danach
    beim Diktieren vor.
    """
    if laeufe.achse(auftrag, "tempowahl") != laeufe.TEMPO_AUS:
        gefunden = (mitgenommen or {}).get("tempo")
        if gefunden is not None:
            return float(gefunden)
    return float(auftrag.get("tempo", tempo.VORGABE))


def _version(auftrag: dict[str, Any], faktor: float | None = None) -> str:
    """Der Name des Standes: Zeit, Methode, Datensatz - und der Abschluss, wenn einer.

    Jede Achse erscheint nur, wenn sie nicht auf ihrer Vorgabe steht - so
    bleibt ein Name stabil, wenn Achsen dazukommen.
    """
    marke = str(auftrag.get("erstellt", laeufe.jetzt()))[:16].replace(":", "").replace("-", "")
    # Das Grundmodell direkt hinter der Zeit - der stärkste Unterschied.
    grund = laeufe.kurzname(str(auftrag.get("basismodell", "")))
    if grund and grund != VORGABE_GRUNDMODELL:
        marke = f"{marke}-{grund}"
    name = f"{marke}-{auftrag.get('methode', '?')}"
    # Der Zusatz direkt hinter der Methode, wie im Optionscode.
    ziele = laeufe.achse(auftrag, "lora_ziele")
    if ziele != laeufe.ZIELE_QV:
        name = f"{name}-{ziele}"
    rang = laeufe.achse(auftrag, "lora_rang")
    if rang != laeufe.RANG_VORGABE:
        name = f"{name}-r{rang}"
    # Der Kern hinter dem Zusatz, wie im Optionscode.
    if laeufe.achse(auftrag, "auswahl") == laeufe.AUSWAHL_KERN:
        name = f"{name}-kern"
    gewicht = laeufe.achse(auftrag, "korrekturgewicht")
    if gewicht != laeufe.GEWICHT_VORGABE:
        name = f"{name}-{laeufe.CODE_KORREKTURGEWICHT.get(gewicht, gewicht).lower()}"
    if laeufe.achse(auftrag, "selbsttraining") == laeufe.SELBST_AN:
        name = f"{name}-selbst"
    art = laeufe.achse(auftrag, "abschluss")
    if art != laeufe.ABSCHLUSS_BESTER:
        name = f"{name}-{art}"
    abwandlung = laeufe.achse(auftrag, "augmentierung")
    if abwandlung != laeufe.AUG_KEINE:
        name = f"{name}-{abwandlung}"
    dauer = laeufe.achse(auftrag, "dauer")
    if dauer != laeufe.DAUER_FEST:
        name = f"{name}-{dauer}"
    steuerung = laeufe.achse(auftrag, "steuerung")
    if steuerung != laeufe.STEUERUNG_VERLUST:
        name = f"{name}-{steuerung}"
    fenster = laeufe.achse(auftrag, "fenster")
    if fenster != laeufe.FENSTER_VOLL:
        name = f"{name}-{fenster}"
    kontext = laeufe.achse(auftrag, "kontext")
    if kontext != laeufe.KONTEXT_AUS:
        name = f"{name}-{kontext}"
    # Zuletzt das Tempo - sonst trügen zwei Stände, die sich nur darin
    # unterscheiden, denselben Namen.
    wirklich = geltendes_tempo(auftrag, None) if faktor is None else faktor
    return name if wirklich == tempo.VORGABE else f"{name}-{tempo.marke(wirklich)}"


def freie_version(datenverzeichnis: Path, auftrag: dict[str, Any], version: str) -> str:
    """Der Name aus `_version` - oder, wenn ihn schon ein anderer Lauf trägt, einer daneben.

    Die Zeitmarke reicht auf die Minute; dasselbe Rezept kurz hintereinander
    ergäbe denselben Namen, und ein Lauf überschriebe den anderen. Derselbe
    Lauf behält ihn; ein fremder bekommt seine Folge (`-43c`),
    sonst seine Kennung.
    """
    sprecher_id = str(auftrag["sprecher_id"])
    job_id = str(auftrag.get("job_id") or "")

    def frei(kandidat: str) -> bool:
        try:
            stand = registry.lies_stand(datenverzeichnis, sprecher_id, kandidat)
        except (OSError, ValueError):
            # Ohne Manifest herrenlos, etwa nach abgebrochener Umwandlung.
            return True
        return str(stand.get("job_id") or "") == job_id

    if frei(version):
        return version
    folge = str(auftrag.get(laeufe.FOLGE) or "")
    for anhang in (folge, job_id):
        if anhang and frei(kandidat := f"{version}-{anhang}"):
            return kandidat
    raise RuntimeError(f"Kein freier Name für den Stand {version} von {job_id}.")


# Wie lange der Trainer auf eine belegte Karte wartet - zusammen rund zehn
# Minuten.
#
# Die Karte teilen sich Trainer, Auswertung, Diktat und das Sprachmodell der
# Textquelle. Die anderen weichen auf den Prozessor aus; der Trainer nicht,
# denn seine Rechenzeiten stehen in der Modelltafel. Kurze Belegungen sind in
# zehn Minuten vorbei; eine stundenlange Auswertung auszusitzen hieße, die
# Karte zu blockieren.
WARTEZEITEN_S = (5, 10, 20, 30, 60, 60, 60, 60, 60, 60, 60, 60)


def _hole_karte(erkenner, bericht) -> None:
    """Den Erkenner jetzt laden - und warten, wenn die Karte gerade belegt ist.

    Hier und nicht im Transkriptor: Hinter einem Diktat wartet ein Mensch.
    Wiederholt wird nur bei Speichermangel; jeder andere Fehler steht sofort da.
    """
    from .finetune import raeume_karte

    # Gezählt über den Index, nicht die Pausenlänge.
    versuche = len(WARTEZEITEN_S) + 1
    for nummer in range(1, versuche + 1):
        try:
            erkenner.lade()
            if nummer > 1:
                bericht.sage(f"  Karte frei nach {nummer - 1} vergeblichen Versuchen.")
            return
        except Exception as ursache:  # noqa: BLE001 - CTranslate2 wirft nackte RuntimeError
            if "out of memory" not in str(ursache).lower() or nummer == versuche:
                raise
            if nummer == 1:
                # Vielleicht hält torch noch selbst etwas (`finetune.raeume_karte`).
                raeume_karte(bericht)
                bericht.sage("  Karte belegt - es wird gewartet.")
            time.sleep(WARTEZEITEN_S[nummer - 1])


def bewerte_faltung(
    verzeichnis: Path,
    datenverzeichnis: Path,
    ct2: Path,
    auftrag: dict[str, Any],
    faltung: int,
    bericht,
    faktor: float | None = None,
) -> list[dict[str, Any]]:
    """Das Modell dieser Faltung hört ihr Sechstel; hängt an `bewertung.jsonl` an.

    Gibt die Zeilen zurück, damit sie über alle Faltungen gesammelt werden.
    """
    from wortlaut.whisper.local import LokalerTranskriptor

    sprecher_id = str(auftrag["sprecher_id"])
    korpuswurzel = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id)
    # Beim Kern nur seine Aufnahmen auf seinen Faltungen; den Rest hört das
    # Endmodell in „hören" (`wortlaut/laeufe.py`, „Die Auswahl").
    _lern, zeilen = laeufe.zeilen_fuer_faltung(
        verzeichnis, faltung, kern=laeufe.kernfaltungen_aus(verzeichnis, auftrag)
    )

    bericht.stufe("bewerten", test_zeilen=len(zeilen))
    bericht.sage(f"Faltung {faltung + 1}: {len(zeilen)} Aufnahmen")

    # Der Pfad, damit sicher dieser Stand lädt. Gerät und Rechenart wie in
    # „hören" und „schreiben" (`wortlaut/rechenwerk.py`), damit Rechenzeiten
    # vergleichbar sind.
    geraet, rechenart = einstellungen().rechenwerk()
    erkenner = LokalerTranskriptor(str(ct2), geraet=geraet, rechenart=rechenart)
    _hole_karte(erkenner, bericht)
    sprache = str(auftrag.get("sprache") or sprachen.VORGABE)

    ergebnis = []
    try:
        ergebnis = _miss(
            erkenner, zeilen, korpuswurzel, sprache, faltung, verzeichnis, bericht,
            float(auftrag.get("tempo", tempo.VORGABE)) if faktor is None else faktor,
        )
    finally:
        # Auch nach einem Fehler: Die Karte gehört der nächsten Faltung.
        erkenner.entlade()
    return ergebnis


def vervollstaendige_kern(
    verzeichnis: Path,
    datenverzeichnis: Path,
    auftrag: dict[str, Any],
    bericht,
    erkenner=None,
) -> None:
    """Was dem Auswahlmodell fehlt, nachmessen - und dann den Kern wählen.

    Die `offen`en Aufnahmen der Kernauswahl (`services/kernauswahl.py`) hört
    das Auswahlmodell vor der ersten Faltung, mit seinem Tempo wie in der
    Auswertung von „hören". Dann wird gewählt und verteilt
    (`laeufe.mit_kern`). Ein fertiger Kern bleibt - auch nach einem Neustart
    (`services/auftraege.UEBERNOMMEN`).

    `erkenner` für die Tests; sonst Stand aus seinen Gewichten, Grundmodell
    über seinen Namen.
    """
    if laeufe.achse(auftrag, "auswahl") != laeufe.AUSWAHL_KERN:
        return
    pfad = verzeichnis / laeufe.KERNAUSWAHL
    inhalt = laeufe.lies_json(pfad)
    if inhalt is None:
        raise RuntimeError(f"Der Auftrag verlangt den Kern, aber {laeufe.KERNAUSWAHL} fehlt.")
    if "kern" in inhalt:
        return

    sprecher_id = str(auftrag["sprecher_id"])
    korpuswurzel = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id)
    sprache = str(auftrag.get("sprache") or sprachen.VORGABE)
    modell = str(inhalt.get("modell") or "")
    faktor = float(inhalt.get("tempo") or tempo.VORGABE)
    offen = {str(kennung) for kennung in inhalt.get("offen") or []}
    # Jede offene Aufnahme; Verworfenes fällt heraus (`laeufe.zeilen_fuer_faltung`).
    zeilen = [
        zeile
        for zeile in laeufe.manifestzeilen(verzeichnis)
        if str(zeile.get("recording_id")) in offen
        and (korpuswurzel / str(zeile["audio"])).is_file()
    ]

    wer = {str(kennung): float(wert) for kennung, wert in dict(inhalt.get("wer") or {}).items()}
    if zeilen:
        bericht.stufe("kernauswahl", test_zeilen=len(zeilen))
        bericht.sage(
            f"Kernauswahl: {registry.beschriftung(modell)} hört {len(zeilen)} Aufnahmen, "
            "die es noch nicht kennt"
        )
        eigener = erkenner is None
        if eigener:
            from wortlaut.whisper.local import LokalerTranskriptor

            quelle: str | Path = modell
            if registry.ist_stand(modell):
                quelle = registry.ct2_verzeichnis(datenverzeichnis, modell)
            geraet, rechenart = einstellungen().rechenwerk()
            erkenner = LokalerTranskriptor(str(quelle), geraet=geraet, rechenart=rechenart)
            _hole_karte(erkenner, bericht)
        try:
            for nummer, zeile in enumerate(zeilen, start=1):
                gemessen = _eine_zeile(erkenner, zeile, korpuswurzel, sprache, faktor)
                wer[str(zeile["recording_id"])] = float(gemessen["wer"])
                bericht.schritt(nummer, len(zeilen))
                if nummer % 10 == 0 or nummer == len(zeilen):
                    bericht.sage(f"  gehört: {nummer}/{len(zeilen)}")
        finally:
            if eigener:
                erkenner.entlade()

    gewaehlt = laeufe.mit_kern(
        {**inhalt, "wer": wer, "nachgemessen": sorted(str(zeile["recording_id"]) for zeile in zeilen)}
    )
    laeufe.schreibe_json(pfad, gewaehlt)
    bericht.sage(
        f"Kernauswahl: {len(gewaehlt['kern'])} von {len(wer)} Aufnahmen, "
        f"WER bis {gewaehlt['schwelle']:.2f}"
    )


def _eine_zeile(
    erkenner, zeile: dict[str, Any], korpuswurzel: Path, sprache: str, faktor: float
) -> dict[str, Any]:
    """Eine Manifestzeile erkennen und bewerten - ohne sie irgendwo abzulegen.

    Mit dem Tempo, mit dem gelernt und diktiert wird
    (`apps/schreiben/.../segmenter.py`).
    """
    with tempfile.TemporaryDirectory() as ablage_tmp:
        wav = korpuswurzel / str(zeile["audio"])
        if tempo.vorspulen_noetig(faktor):
            schnell = Path(ablage_tmp) / "vorgespult.wav"
            tempo.spule_vor(wav, schnell, faktor)
            wav = schnell
        begonnen = time.monotonic()
        transkript = erkenner.transkribiere(wav, sprache=sprache)
        dauer = time.monotonic() - begonnen
    guete = metriken.bewerte(str(zeile["text"]), transkript.text)
    return {
        "recording_id": zeile.get("recording_id"),
        "text": transkript.text,
        "wer": guete.wer,
        "cer": guete.cer,
        "mer": guete.mer,
        "wil": guete.wil,
        "genauigkeit": guete.genauigkeit,
        "rechenzeit_s": dauer,
        # Worauf gemessen wurde, wie in „hören" (`008_rechenwerk.sql`).
        "rechenwerk": erkenner.marke,
    }


# Wie viele Aufnahmen die Prüfung des Endmodells hört, gleichmäßig verteilt -
# es geht um „funktioniert überhaupt", nicht um Nachkommastellen.
STICHPROBE = 12

# Auf Gelerntem muss das Endmodell mindestens so gut sein wie die Faltungen
# auf Ungehörtem; deutlich schlechter heißt, der Stand taugt nicht.
PRUEF_SPIELRAUM = 1.5

# Ohne Vergleich: wie viel der Stichprobe länger geraten darf als alles
# Gesagte (WER über 1). Nötig, weil bei schwerem Korpus die Faltungen selbst
# nahe 1,0 stehen und die Schwelle oben unerreichbar wird.
AUSGEFRANST_ANTEIL = 0.25


def befund_ueber(
    gemessen: list[dict[str, Any]], faltungszeilen: list[dict[str, Any]]
) -> dict[str, Any]:
    """Das Urteil über eine Prüfstichprobe - die Rechnung ohne das Rechnen.

    Zwei Mediane: das Endmodell auf Bekanntem, seine Faltungen auf Ungehörtem. Das Endmodell hat den leichteren Teil und muss mindestens
    gleichauf liegen.
    """
    eigen = statistics.median(float(z["wer"]) for z in gemessen) if gemessen else 0.0
    ungehoert = [float(z["wer"]) for z in faltungszeilen]
    faltungen = statistics.median(ungehoert) if ungehoert else 0.0
    # Ausgaben länger als alles Gesagte: Der Stand redet weiter.
    ausgefranst = sum(1 for z in gemessen if float(z["wer"]) > 1.0)

    grund = ""
    if gemessen and ausgefranst >= max(1, round(AUSGEFRANST_ANTEIL * len(gemessen))):
        grund = "ausgefranst"
    elif gemessen and faltungen and eigen > max(0.1, faltungen * PRUEF_SPIELRAUM):
        grund = "schlechter"
    return {
        "stichprobe": len(gemessen),
        "wer_median": round(eigen, 4),
        "faltungen_wer_median": round(faltungen, 4),
        "ausgefranst": ausgefranst,
        # Die Gründe verlangen verschiedene Antworten.
        "grund": grund,
        "auffaellig": bool(grund),
    }


def pruefe_endmodell(
    verzeichnis: Path,
    datenverzeichnis: Path,
    ct2: Path,
    auftrag: dict[str, Any],
    bericht,
    faltungszeilen: list[dict[str, Any]],
    faktor: float,
) -> dict[str, Any]:
    """Hört der Stand, der ausgeliefert wird, überhaupt noch zu?

    Keine Note, ein Lebenszeichen: Das Endmodell kennt den Korpus, seine Zahl
    darauf gehört in keine Tabelle. Aber ein Stand, der ausfranst, franst auch
    auf Bekanntem aus - auch wenn seine Faltungen tadellos stehen.

    Der Befund wandert ins Manifest und steht in „lernen" neben dem Modell;
    die Freigabe blockiert er nicht.
    """
    from wortlaut.whisper.local import LokalerTranskriptor

    sprecher_id = str(auftrag["sprecher_id"])
    korpuswurzel = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id)
    sprache = str(auftrag.get("sprache") or sprachen.VORGABE)
    # Beim Kern kennt das Endmodell nur ihn.
    kern = laeufe.kern_aus(verzeichnis, auftrag)
    alle = [
        zeile
        for zeile in laeufe.manifestzeilen(verzeichnis)
        # Verworfenes fehlt, wie beim Lernen (`laeufe.zeilen_fuer_faltung`);
        # Selbstbeschriftetes hat keinen Text, an dem sich prüfen ließe.
        if str(zeile.get("quelle")) != laeufe.QUELLE_SELBST
        and (korpuswurzel / str(zeile["audio"])).is_file()
        and (kern is None or str(zeile.get("recording_id")) in kern)
    ]
    if not alle:
        return {}
    schritt = max(1, len(alle) // STICHPROBE)
    stichprobe = alle[::schritt][:STICHPROBE]

    bericht.stufe("bewerten", test_zeilen=len(stichprobe))
    bericht.sage(f"Endmodell: Plausibilitätsprüfung an {len(stichprobe)} Aufnahmen")

    geraet, rechenart = einstellungen().rechenwerk()
    erkenner = LokalerTranskriptor(str(ct2), geraet=geraet, rechenart=rechenart)
    gemessen: list[dict[str, Any]] = []
    try:
        _hole_karte(erkenner, bericht)
        for zeile in stichprobe:
            gemessen.append(_eine_zeile(erkenner, zeile, korpuswurzel, sprache, faktor))
    finally:
        erkenner.entlade()

    befund = befund_ueber(gemessen, faltungszeilen)
    eigen = befund["wer_median"]
    faltungen = befund["faltungen_wer_median"]
    ausgefranst = befund["ausgefranst"]
    if befund["grund"] == "ausgefranst":
        bericht.sage(
            f"ACHTUNG: {ausgefranst} von {len(gemessen)} Ausgaben sind länger als alles "
            f"Gesagte - der Stand wiederholt oder erfindet weiter, und zwar auf Aufnahmen, "
            f"die er gelernt hat (WER {eigen:.2f})."
        )
    elif befund["auffaellig"]:
        bericht.sage(
            f"ACHTUNG: Das Endmodell kommt auf WER {eigen:.2f} - auf Aufnahmen, die es "
            f"gelernt hat. Seine Faltungen standen auf Ungehörtem bei {faltungen:.2f}. "
            "Dieser Stand taugt nicht zum Diktieren; die Zahlen der Faltungen sagen "
            "darüber nichts."
        )
    else:
        bericht.sage(
            f"Endmodell geprüft: WER {eigen:.2f} auf Bekanntem, Faltungen {faltungen:.2f} "
            "auf Ungehörtem - unauffällig."
        )
    return befund


def _miss(
    erkenner,
    zeilen: list[dict[str, Any]],
    korpuswurzel: Path,
    sprache: str,
    faltung: int,
    verzeichnis: Path,
    bericht,
    faktor: float = tempo.VORGABE,
) -> list[dict[str, Any]]:
    """Zeile für Zeile erkennen und bewerten - der Rumpf von `bewerte_faltung`."""
    ergebnis = []
    for nummer, zeile in enumerate(zeilen, start=1):
        eintrag = {
            **_eine_zeile(erkenner, zeile, korpuswurzel, sprache, faktor),
            # Welches Faltungsmodell sie gehört hat.
            "faltung": faltung,
        }
        laeufe.haenge_an(verzeichnis / laeufe.BEWERTUNG, eintrag)
        ergebnis.append(eintrag)
        if nummer % 10 == 0 or nummer == len(zeilen):
            bericht.sage(f"  bewertet: {nummer}/{len(zeilen)}")

    return ergebnis


# Die Maße mit Vertrauensbereich - ohne Rechenzeit, sie beschreibt die Maschine.
GEMESSEN = ("wer", "cer", "mer", "wil", "genauigkeit")


def _streuung(zeilen: list[dict[str, Any]], blockart: str) -> dict[str, Any]:
    """Zu jedem Mittel der Bereich, in dem er liegen dürfte - blockweise gezogen.

    Hier, wo alle Einzelmessungen vorliegen, damit der Stand seine Streuung
    auch ohne `bewertung.jsonl` trägt (`wortlaut/streuung.py`).
    """
    if blockart == streuung.AUS:
        return {}
    verfahren = streuung.Verfahren(blockart=blockart)
    ergebnis: dict[str, Any] = {}
    for name in GEMESSEN:
        paare = [
            (str(zeile.get("recording_id", "")), float(zeile[name]))
            for zeile in zeilen
            if zeile.get(name) is not None
        ]
        bereich = streuung.intervall(streuung.bilde(paare), verfahren)
        if bereich is not None:
            ergebnis[name] = bereich.als_dict()
    return ergebnis


def _zusammengefasst(
    zeilen: list[dict[str, Any]], blockart: str = streuung.BLOCK_AUFNAHME
) -> dict[str, Any]:
    """Die Mittel über alle gemessenen Aufnahmen - fürs Manifest.

    `streuung` sagt, wie weit die Mittel tragen.
    """
    if not zeilen:
        return {"test_einheiten": 0}

    def mittel(name: str) -> float:
        return round(sum(float(zeile[name]) for zeile in zeilen) / len(zeilen), 6)

    return {
        "wer": mittel("wer"),
        "cer": mittel("cer"),
        "mer": mittel("mer"),
        "wil": mittel("wil"),
        "genauigkeit": mittel("genauigkeit"),
        "test_einheiten": len(zeilen),
        # Ein Rechenwerk je Lauf - die erste Zeile genügt.
        "rechenwerk": str(zeilen[0].get("rechenwerk", "")),
        "streuung": _streuung(zeilen, blockart),
    }


def _grundzeilen(datenverzeichnis: Path, sprecher_id: str, modell: str) -> dict[str, dict]:
    """Was „hören" für dieses Grundmodell gemessen hat - je Aufnahme.

    Nur lesend: Den Korpus schreibt „hören" allein (Grundentscheidung 6).
    """
    pfad = corpus.datenbank_pfad(datenverzeichnis, sprecher_id)
    if not pfad.is_file():
        return {}
    verbindung = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    try:
        return {
            str(aufnahme): {"wer": float(wer), "cer": float(cer)}
            for aufnahme, wer, cer in verbindung.execute(
                "SELECT recording_id, wer, cer FROM erkennungen WHERE modell = ?",
                (modell,),
            )
        }
    except sqlite3.Error:
        return {}
    finally:
        verbindung.close()


def gegen_grundmodell(
    datenverzeichnis: Path, auftrag: dict[str, Any], zeilen: list[dict[str, Any]], bericht
) -> dict[str, Any]:
    """WER und CER dieses Laufs und des unveränderten Grundmodells, auf denselben Messungen.

    Das Grundmodell misst die Auswertung von „hören" - neu gemessen wird hier
    nicht, wie beim Vergleich in der Oberfläche (`services/vergleich.py`).
    Gezählt wird, was beide haben; was dem Grundmodell fehlt, steht als Zahl
    daneben.
    """
    kurz = laeufe.kurzname(str(auftrag.get("basismodell", "")))
    grund = _grundzeilen(datenverzeichnis, str(auftrag["sprecher_id"]), kurz)
    gemeinsam = [
        (zeile, grund[schluessel])
        for zeile in zeilen
        if (schluessel := str(zeile.get("recording_id"))) in grund
    ]
    ergebnis: dict[str, Any] = {
        "modell": kurz,
        "einheiten": len(gemeinsam),
        "ohne_grundmodell": len(zeilen) - len(gemeinsam),
    }
    if gemeinsam:
        for seite, auswahl in (("dieser_stand", 0), ("grundmodell", 1)):
            ergebnis[seite] = {
                mass: round(sum(float(paar[auswahl][mass]) for paar in gemeinsam) / len(gemeinsam), 6)
                for mass in ("wer", "cer")
            }
    bericht.sage(bericht_gegen_grundmodell(ergebnis))
    return ergebnis


def bericht_gegen_grundmodell(ergebnis: dict[str, Any]) -> str:
    """Die Gegenüberstellung als Text - fürs Protokoll und für `make train`."""
    if not ergebnis.get("einheiten"):
        return (
            f"Gegen {ergebnis.get('modell')}: keine gemeinsame Messung - in „hören“ unter "
            "„Auswertung“ rechnet das Grundmodell über den Korpus."
        )

    def zeile(name: str, werte: dict[str, float]) -> str:
        return f"  {name:<26} WER {werte['wer']:.3f}   CER {werte['cer']:.3f}"

    teile = [
        f"Ergebnis auf {ergebnis['einheiten']} Messungen - nur Vorlagen, jede von einem "
        "Modell, das sie nicht gelernt hat:",
        zeile(f"{ergebnis['modell']} unverändert", ergebnis["grundmodell"]),
        zeile("dieser Stand", ergebnis["dieser_stand"]),
    ]
    if ergebnis.get("ohne_grundmodell"):
        teile.append(
            f"  ({ergebnis['ohne_grundmodell']} Messungen ohne Wert von {ergebnis['modell']} - "
            "in „hören“ unter „Auswertung“ nachzuholen)"
        )
    return "\n".join(teile)


def gib_frei(
    verzeichnis: Path,
    datenverzeichnis: Path,
    gewichte: Path,
    auftrag: dict[str, Any],
    bericht,
    abschluss_bericht: dict[str, Any] | None = None,
    zeilen: list[dict[str, Any]] | None = None,
    mitgenommen: dict[str, Any] | None = None,
    zuschnitt: dict[str, Any] | None = None,
    endmodell: dict[str, Any] | None = None,
) -> str:
    """Das Endmodell umwandeln, prüfen und eintragen. Gibt die Version zurück.

    Das Endmodell ist das Mittel der Faltungen (`endmodell.py`); `endmodell`
    sagt, welche es sind und welche draußen blieben. Die Zahlen sind die der
    Faltungen (`zeilen`); das Endmodell wird nur geprüft (`pruefe_endmodell`).
    Daneben das unveränderte Grundmodell auf denselben Messungen
    (`gegen_grundmodell`). Eingetragen als `fertig`,
    freigegeben wird von Hand - in „Modelle" oder mit `make release`
    (`apps/lernen/backend/services/freigabe.py`).
    """
    from .finetune import wandle_um

    sprecher_id = str(auftrag["sprecher_id"])
    faktor = geltendes_tempo(auftrag, mitgenommen)
    version = freie_version(datenverzeichnis, auftrag, _version(auftrag, faktor))
    ziel = registry.stand_verzeichnis(datenverzeichnis, sprecher_id, version)
    ct2 = ziel / "ct2"

    wandle_um(gewichte, ct2, bericht)
    gemessen = _zusammengefasst(zeilen or [])
    grundmodell = gegen_grundmodell(datenverzeichnis, auftrag, zeilen or [], bericht)
    pruefung = pruefe_endmodell(
        verzeichnis, datenverzeichnis, ct2, auftrag, bericht, zeilen or [], faktor
    )

    registry.schreibe_stand(
        datenverzeichnis,
        {
            "id": f"{sprecher_id}/{version}",
            "sprecher_id": sprecher_id,
            "basismodell": auftrag.get("basismodell"),
            "methode": auftrag.get("methode"),
            # Die Achsen des Auftrags, und daneben, was herauskam.
            **{achse.feld: achse.wert(auftrag) for achse in laeufe.ACHSEN},
            # Womit jede Erkennung dieses Standes beginnt (`kontext.py`).
            "startprompt": startprompt(ct2) or "",
            # Die Folge (`/43b`), damit der Stand sie auch ohne Lauf trägt.
            laeufe.FOLGE: auftrag.get(laeufe.FOLGE),
            # „schreiben" spult beim Diktieren genauso vor (`wortlaut/tempo.py`).
            "tempo": faktor,
            # Womit gerechnet wurde - die Rezeptdatei kann sich ändern.
            "rezept": _rezeptauszug(auftrag),
            "abschluss_bericht": abschluss_bericht,
            # Welche Faltungen gemittelt wurden und welche warum nicht.
            "endmodell": endmodell or {},
            # Was die Faltungen herausfanden - Durchgänge, α, Tempo, je Faltung.
            "kreuzvalidierung": mitgenommen or {},
            # Das Lebenszeichen (`pruefe_endmodell`).
            "pruefung": pruefung,
            "job_id": auftrag.get("job_id"),
            "erstellt": laeufe.jetzt(),
            "daten_umfang": auftrag.get("zeilen", {}),
            "metriken": gemessen,
            # Das unveränderte Grundmodell auf denselben Messungen.
            "grundmodell": grundmodell,
            # Worauf und wie das Endmodell gerechnet wurde (`kartenplan.py`).
            "zuschnitt": zuschnitt or {},
            "laufzeit": "faster-whisper>=1.1",
            "status": "fertig",
        },
    )

    # Rohgewichte und Arbeitsstand räumt `finetune.main` weg, auch nach Fehlern.
    bericht.fertig(version, gemessen)
    return version
