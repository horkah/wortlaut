"""Jede Aufnahme einmal ungehört - und der Stand, der ausgeliefert wird.

Je Faltung hört das eben trainierte Modell das Sechstel, das es nicht kannte
(`services/aufteilung.py`); danach liegt zu jeder Aufnahme eine Messung von
einem Modell vor, das sie nie gehört hat.

**Zwei Modelle, eine Zeile.** Die Zahlen stammen aus den sechs Faltungen. Das
Modell, das „schreiben" anbietet, ist ein siebtes: auf allem trainiert, mit den
Einstellungen der Faltungen - besser als jedes der sechs und darum nicht
ehrlich messbar. Die Zahl daneben ist die vorsichtige.

Gemessen im Trainer, wo das Modell schon auf der Karte liegt, mit
`wortlaut/metriken.py` wie die Baseline in „hören", auf allen Fassungen.
"""

from __future__ import annotations

import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from wortlaut import (
    augmentierung,
    corpus,
    laeufe,
    metriken,
    registry,
    sprachen,
    streuung,
    tempo,
)

from apps.lernen.backend.config import einstellungen


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

    lora = rezept.get("lora") or {}
    return {
        "lernrate": rezept.get("lernrate"),
        "warmlauf_schritte": rezept.get("warmlauf_schritte"),
        "stapel": rezept.get("stapel"),
        "akkumulation": rezept.get("akkumulation"),
        "epochen": rezept.get("epochen"),
        "epochen_hoechstens": rezept.get("epochen_hoechstens"),
        "geduld": rezept.get("geduld"),
        "gradientensparsam": bool(rezept.get("gradientensparsam", False)),
        "lora_rang": lora.get("rang"),
        "lora_alpha": lora.get("alpha"),
        "lora_ziele": list(lora.get("ziele") or []),
    }


def geltendes_tempo(auftrag: dict[str, Any], mitgenommen: dict[str, Any] | None) -> float:
    """Mit welcher Geschwindigkeit dieser Stand wirklich gerechnet hat.

    Ohne Tempowahl der Wert aus dem Auftrag, sonst der aus den Faltungen
    mitgenommene. Er geht in Name und Manifest, und „schreiben" spult danach
    beim Diktieren vor.
    """
    if laeufe.tempowahl_aus(auftrag) != laeufe.TEMPO_AUS:
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
    # Der Ausgangsstand mit seiner Kennung.
    ausgang = str(auftrag.get(laeufe.AUSGANGSSTAND) or "")
    if ausgang:
        marke = f"{marke}-{registry.beschriftung(ausgang)}"
    name = f"{marke}-{auftrag.get('methode', '?')}-{auftrag.get('daten', '?')}"
    # Der Kern hinter dem Datensatz, wie im Optionscode.
    if laeufe.auswahl_aus(auftrag) == laeufe.AUSWAHL_KERN:
        name = f"{name}-kern"
    art = str(auftrag.get("abschluss") or laeufe.ABSCHLUSS_BESTER)
    if art != laeufe.ABSCHLUSS_BESTER:
        name = f"{name}-{art}"
    abwandlung = str(auftrag.get("augmentierung") or laeufe.AUG_KEINE)
    if abwandlung != laeufe.AUG_KEINE:
        name = f"{name}-{abwandlung}"
    dauer = str(auftrag.get("dauer") or laeufe.DAUER_FEST)
    if dauer != laeufe.DAUER_FEST:
        name = f"{name}-{dauer}"
    # Zuletzt das Tempo - sonst trügen zwei Stände, die sich nur darin
    # unterscheiden, denselben Namen.
    wirklich = geltendes_tempo(auftrag, None) if faktor is None else faktor
    return name if wirklich == tempo.VORGABE else f"{name}-{tempo.marke(wirklich)}"


def freie_version(datenverzeichnis: Path, auftrag: dict[str, Any], version: str) -> str:
    """Der Name aus `_version` - oder, wenn ihn schon ein anderer Lauf trägt, einer daneben.

    Die Zeitmarke reicht auf die Minute; dasselbe Rezept kurz hintereinander
    ergäbe denselben Namen, und ein Lauf überschriebe den anderen. Derselbe
    Lauf behält ihn (`nachziehen`); ein fremder bekommt seine Folge (`-43c`),
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

    # Erst hier: `daten` zieht numpy und torch nach, `befund_ueber` braucht sie nicht.
    from .daten import zeilen_fuer_faltung

    sprecher_id = str(auftrag["sprecher_id"])
    korpuswurzel = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id)
    # Beim Kern nur seine Aufnahmen auf seinen Faltungen; den Rest hört das
    # Endmodell in „hören" (`wortlaut/laeufe.py`, „Die Auswahl").
    _lern, zeilen = zeilen_fuer_faltung(
        verzeichnis,
        faltung,
        str(auftrag.get("daten") or laeufe.NUR_ORIGINAL),
        kern=laeufe.kernfaltungen_aus(verzeichnis, auftrag),
    )

    bericht.stufe("bewerten", test_zeilen=len(zeilen))
    bericht.sage(f"Faltung {faltung + 1}: {len(zeilen)} Zeilen über alle Fassungen")

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
    das Auswahlmodell vor der ersten Faltung, im Original und mit seinem Tempo
    wie in der Auswertung von „hören". Dann wird gewählt und verteilt
    (`laeufe.mit_kern`). Ein fertiger Kern bleibt - auch nach einem Neustart
    (`services/auftraege.UEBERNOMMEN`).

    `erkenner` für die Tests; sonst Stand aus seinen Gewichten, Grundmodell
    über seinen Namen.
    """
    if laeufe.auswahl_aus(auftrag) != laeufe.AUSWAHL_KERN:
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
    # Das Original jeder offenen Aufnahme; Verworfenes fällt heraus
    # (`daten.zeilen_fuer_faltung`).
    zeilen = [
        zeile
        for zeile in laeufe.manifestzeilen(verzeichnis)
        if str(zeile.get("recording_id")) in offen
        and str(zeile.get("variante")) == augmentierung.ORIGINAL
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
        "variante": zeile.get("variante"),
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

    Zwei Mediane über Originale: das Endmodell auf Bekanntem, seine Faltungen
    auf Ungehörtem. Das Endmodell hat den leichteren Teil und muss mindestens
    gleichauf liegen.
    """
    eigen = statistics.median(float(z["wer"]) for z in gemessen) if gemessen else 0.0
    ungehoert = [
        float(z["wer"])
        for z in faltungszeilen
        if str(z.get("variante")) == augmentierung.ORIGINAL
    ]
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
        # Verworfenes fehlt, wie beim Lernen (`daten.zeilen_fuer_faltung`).
        if str(zeile.get("variante")) == augmentierung.ORIGINAL
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
    auch ohne `bewertung.jsonl` trägt. Je Aufnahme gezogen - ihre Fassungen
    sind Messungen an einem Gegenstand (`wortlaut/streuung.py`).
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
        bereich = streuung.intervall(streuung.bilde(paare, blockart), verfahren)
        if bereich is not None:
            ergebnis[name] = bereich.als_dict()
    return ergebnis


def _zusammengefasst(
    zeilen: list[dict[str, Any]], blockart: str = streuung.BLOCK_AUFNAHME
) -> dict[str, Any]:
    """Die Mittel über alle gemessenen Zeilen und Fassungen - fürs Manifest.

    Je Fassung liegt es in `bewertung.jsonl`; `streuung` sagt, wie weit die
    Mittel tragen.
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


def gib_frei(
    verzeichnis: Path,
    datenverzeichnis: Path,
    gewichte: Path,
    auftrag: dict[str, Any],
    bericht,
    abschluss=None,
    zeilen: list[dict[str, Any]] | None = None,
    mitgenommen: dict[str, Any] | None = None,
) -> str:
    """Das Endmodell umwandeln, prüfen und eintragen. Gibt die Version zurück.

    Die Zahlen sind die der Faltungen (`zeilen`); das Endmodell wird nur
    geprüft (`pruefe_endmodell`). Eingetragen als `fertig`, freigegeben wird
    von Hand (`apps/lernen/backend/api/modelle.py`).
    """
    from .finetune import wandle_um

    sprecher_id = str(auftrag["sprecher_id"])
    faktor = geltendes_tempo(auftrag, mitgenommen)
    version = freie_version(datenverzeichnis, auftrag, _version(auftrag, faktor))
    ziel = registry.stand_verzeichnis(datenverzeichnis, sprecher_id, version)
    ct2 = ziel / "ct2"

    wandle_um(gewichte, ct2, bericht)
    gemessen = _zusammengefasst(zeilen or [])
    pruefung = pruefe_endmodell(
        verzeichnis, datenverzeichnis, ct2, auftrag, bericht, zeilen or [], faktor
    )

    registry.schreibe_stand(
        datenverzeichnis,
        {
            "id": f"{sprecher_id}/{version}",
            "sprecher_id": sprecher_id,
            "basismodell": auftrag.get("basismodell"),
            # Leer ohne Ausgangsstand.
            laeufe.AUSGANGSSTAND: auftrag.get(laeufe.AUSGANGSSTAND) or "",
            "methode": auftrag.get("methode"),
            "daten": auftrag.get("daten"),
            "auswahl": laeufe.auswahl_aus(auftrag),
            # Die Achsen des Auftrags, und daneben, was herauskam.
            "abschluss": str(auftrag.get("abschluss") or laeufe.ABSCHLUSS_BESTER),
            "augmentierung": str(auftrag.get("augmentierung") or laeufe.AUG_KEINE),
            "dauer": str(auftrag.get("dauer") or laeufe.DAUER_FEST),
            "tempowahl": laeufe.tempowahl_aus(auftrag),
            # Die Folge (`/43b`), damit der Stand sie auch ohne Lauf trägt.
            laeufe.FOLGE: auftrag.get(laeufe.FOLGE),
            # „schreiben" spult beim Diktieren genauso vor (`wortlaut/tempo.py`).
            "tempo": faktor,
            # Womit gerechnet wurde - die Rezeptdatei kann sich ändern.
            "rezept": _rezeptauszug(auftrag),
            "abschluss_bericht": abschluss.als_dict() if abschluss is not None else None,
            # Was das Endmodell aus den Faltungen übernahm.
            "kreuzvalidierung": mitgenommen or {},
            # Das Lebenszeichen (`pruefe_endmodell`).
            "pruefung": pruefung,
            "job_id": auftrag.get("job_id"),
            "erstellt": laeufe.jetzt(),
            "daten_umfang": auftrag.get("zeilen", {}),
            "metriken": gemessen,
            "laufzeit": "faster-whisper>=1.1",
            "status": "fertig",
        },
    )

    # Rohgewichte und Arbeitsstand räumt `finetune.main` weg, auch nach Fehlern.
    bericht.fertig(version, gemessen)
    return version
