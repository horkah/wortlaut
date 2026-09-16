"""Jede Aufnahme einmal ungehört - und der Stand, der ausgeliefert wird.

Der Teil eines Laufs, der die Zahl hervorbringt, und er steht nicht am Ende,
sondern sechsmal mittendrin. Je Faltung hört das eben trainierte Modell das
Sechstel, das es nicht kannte (`services/aufteilung.py`); nach sechs Faltungen
liegt zu **jeder** Aufnahme eine Messung von einem Modell vor, das sie nie
gesehen hat.

**Zwei Modelle, eine Zeile in der Tabelle - und das muss man wissen.** Die
Zahlen eines Laufs stammen aus den sechs Faltungsmodellen. Das Modell, das
gespeichert und in „schreiben" angeboten wird, ist ein siebtes: auf dem ganzen
Korpus trainiert, mit den Einstellungen, die sich in den Faltungen bewährt
haben. Es ist damit besser als jedes der sechs - es hat mehr gesehen -, und
gerade deshalb lässt es sich nicht mehr ehrlich messen. Die Zahl daneben ist
die vorsichtige.

**Warum hier und nicht im Webdienst.** Weil das Modell hier schon liegt - eben
umgewandelt, auf einer Maschine mit Karte. Es dafür in einen anderen Container
zu laden hieße, mehrere Gigabyte über ein Volume zu schieben, um dasselbe
Ergebnis langsamer zu bekommen.

**Warum dieselben Maße wie in „hören".** Verglichen wird mit der Baseline:
dem, was das unveränderte Grundmodell in der Auswertung von „hören" auf
denselben Aufnahmen erreicht hat. Ein anderes Maß, eine andere Angleichung des
Textes oder eine andere Quantisierung machten aus dem Vergleich zwei getrennte
Messungen. Gerechnet wird deshalb mit `wortlaut/metriken.py` - derselben Datei.

**Warum auf allen Fassungen.** Weil die interessantere Hälfte der Frage
lautet, ob das Modell den Sprecher verstanden hat oder bloß seine
Aufnahmesituation. Das Manifest trägt die Testaufnahmen deshalb in allen
Fassungen, unabhängig davon, womit trainiert wurde.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from wortlaut import corpus, laeufe, metriken, registry, sprachen, streuung, tempo

from apps.lernen.backend.config import einstellungen

from .daten import zeilen_fuer_faltung

# Das Grundmodell, das nicht im Namen eines Standes auftaucht - es war lange
# das einzige, und jeder Stand von früher heißt ohne es.
VORGABE_GRUNDMODELL = "small"


def _rezeptauszug(auftrag: dict[str, Any]) -> dict[str, Any]:
    """Die Stellschrauben des Rezepts, wie sie für diesen Lauf galten.

    Nur die, die man wissen will, um einen Lauf zu wiederholen oder zwei zu
    vergleichen - nicht das ganze Rezept. Die Augmentierungsparameter etwa
    stehen nicht darin: Welche Stufe galt, sagt der Auftrag, und die Zahlen
    dahinter sind für den Leser eines Steckbriefs kein Unterschied.
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

    Bei `wie_eingestellt` der Wert aus dem Auftrag - der, der beim Beauftragen
    im Profil stand. Bei `optimal` der Median über die sechs Faltungen, denn
    genau damit ist das Endmodell trainiert worden.

    **Warum das nicht egal ist.** Diese Zahl geht in den Namen des Standes und
    in sein Manifest, und „schreiben" liest sie, um beim Diktieren genauso
    vorzuspulen. Stünde hier der bestellte statt des gefundenen Faktors, bekäme
    ein Modell, das auf 1,75 gelernt hat, beim Diktieren 1,0 zu hören - und der
    ganze Lauf wäre umsonst gewesen, ohne dass irgendwo ein Fehler stünde.
    """
    if laeufe.tempowahl_aus(auftrag) != laeufe.TEMPO_AUS:
        gefunden = (mitgenommen or {}).get("tempo")
        if gefunden is not None:
            return float(gefunden)
    return float(auftrag.get("tempo", tempo.VORGABE))


def _version(auftrag: dict[str, Any], faktor: float | None = None) -> str:
    """Der Name des Standes: Zeit, Methode, Datensatz - und der Abschluss, wenn einer.

    Alle drei, weil vier Stände nebeneinander liegen, die sich in genau diesen
    Punkten unterscheiden. Eine Zeitmarke allein ließe offen, welcher von den
    vieren gemeint ist - und ein Verzeichnisname, den man nachschlagen muss,
    ist keiner.

    Der Abschluss steht nur dann dabei, wenn er nicht `bester` ist. Das ist
    keine Sparsamkeit: Ein Stand von früher soll heute genauso heißen wie
    damals, sonst zeigt jeder Verweis auf ihn ins Leere.
    """
    marke = str(auftrag.get("erstellt", laeufe.jetzt()))[:16].replace(":", "").replace("-", "")
    # Das Grundmodell direkt hinter der Zeit, und nur wenn es nicht `small`
    # ist: Es ist der stärkste Unterschied zwischen zwei Ständen, und ein
    # Stand von früher soll heute heißen wie damals.
    grund = laeufe.kurzname(str(auftrag.get("basismodell", "")))
    if grund and grund != VORGABE_GRUNDMODELL:
        marke = f"{marke}-{grund}"
    name = f"{marke}-{auftrag.get('methode', '?')}-{auftrag.get('daten', '?')}"
    art = str(auftrag.get("abschluss") or laeufe.ABSCHLUSS_BESTER)
    if art != laeufe.ABSCHLUSS_BESTER:
        name = f"{name}-{art}"
    abwandlung = str(auftrag.get("augmentierung") or laeufe.AUG_KEINE)
    if abwandlung != laeufe.AUG_KEINE:
        name = f"{name}-{abwandlung}"
    dauer = str(auftrag.get("dauer") or laeufe.DAUER_FEST)
    if dauer != laeufe.DAUER_FEST:
        name = f"{name}-{dauer}"
    # Zuletzt die Geschwindigkeit, und wieder nur, wenn sie nicht die
    # gewöhnliche ist: Jeder Stand von vor dieser Spalte heißt damit heute, wie
    # er damals hieß. Im Namen und nicht nur im Manifest, weil zwei Stände mit
    # gleichem Rezept und verschiedenem Tempo sonst denselben Namen trügen -
    # und genau daran ist im September 2026 schon einmal die falsche Freigabe
    # gehangen.
    wirklich = geltendes_tempo(auftrag, None) if faktor is None else faktor
    return name if wirklich == tempo.VORGABE else f"{name}-{tempo.marke(wirklich)}"


# Wie lange der Trainer auf die Karte wartet, wenn sie gerade belegt ist, und
# in welchen Abständen er nachsieht. Zusammen rund zehn Minuten.
#
# **Warum überhaupt gewartet wird.** Auf dieser Karte rechnen vier: der
# Trainer, die Auswertung in „hören", das Diktat in „schreiben" und das
# Sprachmodell der Textquelle. Die ersten drei sprechen sich nicht ab, und der
# vierte hält seine fünf Gigabyte noch eine Weile nach der letzten Frage.
#
# Für drei von ihnen ist eine belegte Karte kein Unglück: Sie fallen auf den
# Prozessor zurück und werden langsamer (`whisper/local.py`). Der Trainer tut
# das mit Absicht nicht - er misst hier Rechenzeiten, und eine, die vom
# Prozessor stammt, wäre in der Modelltafel eine Falle. Er scheitert also.
#
# Nur ist das die teuerste aller Antworten: Ein Lauf, der seit einer Stunde
# rechnet, ist verloren, weil jemand einen Satz diktiert hat. Zehn Minuten
# warten kostet dagegen zehn Minuten, und die kürzeren Belegungen - eine
# Diktatsitzung, das Sprachmodell nach seiner Minute - sind in dieser Zeit
# vorbei.
#
# **Warum nicht länger.** Weil ein Auswertungslauf über alle Aufnahmen Stunden
# dauern kann. Den auszusitzen hieße, die Karte zu blockieren statt zu teilen,
# und am Ende stünde dieselbe Frage bloß später. Wer eine Auswertung und ein
# Training zugleich startet, soll das erfahren.
WARTEZEITEN_S = (5, 10, 20, 30, 60, 60, 60, 60, 60, 60, 60, 60)


def _hole_karte(erkenner, bericht) -> None:
    """Den Erkenner jetzt laden - und warten, wenn die Karte gerade belegt ist.

    Ausdrücklich hier und nicht im Transkriptor: Warten ist die richtige
    Antwort für einen Lauf, der Stunden gerechnet hat, und die falsche für ein
    Diktat, hinter dem ein Mensch sitzt. Derselbe Griff wäre an der anderen
    Stelle ein Fehler.

    Wiederholt wird **nur** bei Speichermangel. Ein Modell, das nicht zu laden
    ist, weil es fehlt oder beschädigt ist, wird davon in zehn Minuten nicht
    heil - und der Fehler soll sofort dastehen.
    """
    from .finetune import raeume_karte

    # Gezählt wird über den Index und nicht über die Pausenlänge: Eine Pause
    # von null Sekunden heißt „gleich noch einmal" und nicht „aufgeben", und
    # beides in eine Zahl zu legen ist genau die Art Abkürzung, die später
    # jemand falsch liest.
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
                # Vielleicht sind wir es selbst: Was der Trainer eben noch
                # hielt, gibt torch nicht von sich aus an den Treiber zurück
                # (siehe `finetune.raeume_karte`).
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

    Gibt die Zeilen zurück, damit `main` sie über alle sechs Faltungen sammeln
    kann - sie zusammen sind die Auskunft über dieses Rezept.
    """
    from wortlaut.whisper.local import LokalerTranskriptor

    sprecher_id = str(auftrag["sprecher_id"])
    korpuswurzel = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id)
    _lern, zeilen = zeilen_fuer_faltung(
        verzeichnis, faltung, str(auftrag.get("daten") or laeufe.NUR_ORIGINAL)
    )

    bericht.stufe("bewerten", test_zeilen=len(zeilen))
    bericht.sage(f"Faltung {faltung + 1}: {len(zeilen)} Zeilen über alle Fassungen")

    # Der Pfad des umgewandelten Modells statt eines Namens - faster-whisper
    # nimmt beides, und so wird sicher dieser Stand geladen und nicht ein
    # gleichnamiger aus dem Zwischenspeicher.
    #
    # Gerät und Rechenart kommen aus derselben Konfiguration wie in „hören" und
    # „schreiben" (`wortlaut/rechenwerk.py`) und stehen hier **nicht** fest.
    # Sie standen einmal fest, auf `float16` und der Karte, und das war der
    # Fehler: Die Auswertung maß dieselben Modelle auf dem Prozessor, und in
    # der Modellübersicht standen danach vier Sekunden neben einer
    # Viertelsekunde. Zwei richtige Zahlen, die nebeneinander etwas Falsches
    # behaupteten.
    geraet, rechenart = einstellungen().rechenwerk()
    erkenner = LokalerTranskriptor(str(ct2), geraet=geraet, rechenart=rechenart)
    _hole_karte(erkenner, bericht)
    # Der Rückfall gilt Aufträgen, die älter sind als das Feld - seit
    # `services/auftraege.py` schreibt jeder neue Lauf seine Sprache selbst.
    sprache = str(auftrag.get("sprache") or sprachen.VORGABE)

    ergebnis = []
    try:
        ergebnis = _miss(
            erkenner, zeilen, korpuswurzel, sprache, faltung, verzeichnis, bericht,
            float(auftrag.get("tempo", tempo.VORGABE)) if faktor is None else faktor,
        )
    finally:
        # Auch wenn das Messen scheitert: Die Karte gehört danach der nächsten
        # Faltung. Ein Erkenner, der bis zum nächsten Sammellauf liegen bleibt,
        # ist derselbe Fehler wie der, der diesen Aufruf nötig gemacht hat -
        # nur in die andere Richtung (siehe `finetune.raeume_karte`).
        erkenner.entlade()
    return ergebnis


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
        # Gemessen wird auf demselben Klang, auf dem gelernt wurde. Ein Modell,
        # das nur vorgespulte Sprache gehört hat, an ungespulter zu messen,
        # ergäbe eine Zahl über eine Lage, die es nie gibt: Beim Diktieren
        # bekommt es ebenfalls Vorgespultes (`apps/schreiben/.../segmenter.py`).
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
        eintrag = {
            "recording_id": zeile.get("recording_id"),
            "variante": zeile.get("variante"),
            # Welche Faltung diese Zeile gemessen hat - und damit, welches der
            # sechs Modelle sie gehört hat, ohne sie zu kennen.
            "faltung": faltung,
            "text": transkript.text,
            "wer": guete.wer,
            "cer": guete.cer,
            "mer": guete.mer,
            "wil": guete.wil,
            "genauigkeit": guete.genauigkeit,
            "rechenzeit_s": dauer,
            # Worauf gemessen wurde - dieselbe Angabe, die „hören" neben jede
            # seiner Zeilen schreibt (`008_rechenwerk.sql`). Ohne sie ist die
            # Rechenzeit daneben keine Auskunft, sondern eine Zahl.
            "rechenwerk": erkenner.marke,
        }
        laeufe.haenge_an(verzeichnis / laeufe.BEWERTUNG, eintrag)
        ergebnis.append(eintrag)
        if nummer % 10 == 0 or nummer == len(zeilen):
            bericht.sage(f"  bewertet: {nummer}/{len(zeilen)}")

    return ergebnis


# Die Maße, zu denen ein Vertrauensbereich mitgeschrieben wird. Die Rechenzeit
# fehlt mit Absicht: Sie ist eine Eigenschaft der Maschine und nicht des
# Modells, und ein Bereich darum beschriebe die Maschine.
GEMESSEN = ("wer", "cer", "mer", "wil", "genauigkeit")


def _streuung(zeilen: list[dict[str, Any]], blockart: str) -> dict[str, Any]:
    """Zu jedem Mittel der Bereich, in dem er liegen dürfte - blockweise gezogen.

    **Warum das hier mitgeschrieben wird und nicht erst in der Ansicht.** Weil
    es der Ort ist, an dem die Einzelmessungen noch vollständig vorliegen, und
    weil ein Stand seine Streuung dann für immer bei sich trägt - auch wenn
    seine `bewertung.jsonl` später einmal fehlt. Es kostet einen Wimpernschlag
    am Ende eines Laufs, der Stunden gerechnet hat.

    **Warum je Aufnahme gezogen wird.** Die Fassungen einer Aufnahme sind
    mehrere Messungen an einem Gegenstand, nicht unabhängige Auskünfte. Wer
    sie einzeln zieht, bekommt einen Bereich heraus, der etwa halb so breit ist
    wie der richtige (siehe `wortlaut/streuung.py`).

    **Was sich dadurch an den bisherigen Zahlen ändert: nichts.** Die Mittel
    daneben sind dieselben wie vorher, Stelle für Stelle. Hier kommt eine
    Auskunft dazu, es geht keine verloren.
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
    """Die Mittel über alle Testzeilen - die Zahlen, die ins Manifest gehen.

    Über alle Fassungen zusammen, denn das ist die Zahl, die einen Stand in
    einer Zeile beschreibt. Aufgeschlüsselt liegt sie in `bewertung.jsonl`
    daneben; die Ansicht in „lernen" liest sie von dort und stellt sie der
    Baseline je Fassung gegenüber.

    Unter `streuung` steht seit September 2026 zusätzlich, wie weit diese
    Mittel tragen. Zusätzlich heißt zusätzlich: Die Schlüssel darüber sind
    unverändert, und ein Stand von vorher hat den neuen schlicht nicht - die
    Ansicht kommt mit beidem zurecht.
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
        # Alle Zeilen eines Laufs stammen aus demselben Rechenwerk - der
        # Erkenner wird einmal geladen. Deshalb genügt hier die erste.
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
    """Das Endmodell umwandeln und eintragen. Gibt die Version zurück.

    **Gemessen wird hier nichts mehr.** Die Zahlen dieses Standes sind die der
    sechs Faltungen (`zeilen`) - jede Aufnahme einmal, von einem Modell, das
    sie nicht kannte. Das Endmodell selbst kennt den ganzen Korpus; es an ihm
    zu messen ergäbe eine schöne Zahl ohne Aussage.

    Eingetragen wird mit `status: fertig` und nicht `active`: Ein durchgelaufenes
    Training ist noch kein Modell, das jemand benutzen soll. Zwischen „hat
    gerechnet" und „damit diktiere ich" liegt der Blick auf die Zahlen, und den
    nimmt einem nichts ab (siehe `apps/lernen/backend/api/modelle.py`).
    """
    from .finetune import wandle_um

    sprecher_id = str(auftrag["sprecher_id"])
    faktor = geltendes_tempo(auftrag, mitgenommen)
    version = _version(auftrag, faktor)
    ziel = registry.stand_verzeichnis(datenverzeichnis, sprecher_id, version)
    ct2 = ziel / "ct2"

    wandle_um(gewichte, ct2, bericht)
    gemessen = _zusammengefasst(zeilen or [])

    registry.schreibe_stand(
        datenverzeichnis,
        {
            "id": f"{sprecher_id}/{version}",
            "sprecher_id": sprecher_id,
            "basismodell": auftrag.get("basismodell"),
            "methode": auftrag.get("methode"),
            "daten": auftrag.get("daten"),
            # Die Achsen des Auftrags, als schlichte Zeichenketten - und
            # daneben, was dabei herauskam. Ein Stand, dessen α niemand mehr
            # nachsehen kann, ist mit keinem anderen zu vergleichen.
            "abschluss": str(auftrag.get("abschluss") or laeufe.ABSCHLUSS_BESTER),
            "augmentierung": str(auftrag.get("augmentierung") or laeufe.AUG_KEINE),
            "dauer": str(auftrag.get("dauer") or laeufe.DAUER_FEST),
            # Bei welcher Geschwindigkeit dieser Stand gelernt und gemessen
            # wurde. „schreiben" liest es und spult beim Diktieren genauso vor;
            # ohne die Angabe träfe ein Modell für schnelle Sprache auf einen
            # langsamen Sprecher (`wortlaut/tempo.py`).
            "tempo": faktor,
            # Die Zahlen, mit denen wirklich gerechnet wurde. Sie standen
            # bisher nur im Rezept - und ein Rezept ist eine Datei, die sich
            # ändert. Wer in einem halben Jahr wissen will, mit welcher
            # Lernrate dieser Stand entstand, soll nicht die Git-Historie einer
            # YAML-Datei lesen müssen.
            "rezept": _rezeptauszug(auftrag),
            "abschluss_bericht": abschluss.als_dict() if abschluss is not None else None,
            # Woher die Einstellungen des Endmodells stammen: der Median über
            # die sechs Faltungen. Ohne diese Zeile wäre nicht mehr zu sagen,
            # wie lange dieser Stand trainiert hat.
            "kreuzvalidierung": mitgenommen or {},
            "job_id": auftrag.get("job_id"),
            "erstellt": laeufe.jetzt(),
            "daten_umfang": auftrag.get("zeilen", {}),
            "metriken": gemessen,
            "laufzeit": "faster-whisper>=1.1",
            "status": "fertig",
        },
    )

    # Die Rohgewichte und der Arbeitsstand bleiben hier liegen - weggeräumt
    # werden sie von `finetune.main`, und zwar auf beiden Wegen. Der Aufruf
    # stand einmal hier, und das war die halbe Lösung: Ein Lauf, der vorher
    # scheiterte, kam nie an ihm vorbei und hinterließ knapp drei Gigabyte.
    bericht.fertig(version, gemessen)
    return version
