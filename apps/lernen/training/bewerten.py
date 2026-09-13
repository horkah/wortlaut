"""Das fertige Modell hört die Testaufnahmen - und wird eingetragen.

Der letzte Teil eines Laufs, und der einzige, der eine Zahl hervorbringt, die
etwas heißt. Die Testaufnahmen hat das Modell nie gesehen: Ihre Zuteilung steht
seit ihrer ersten Aufnahme fest und ändert sich nie wieder (siehe
`apps/lernen/backend/services/aufteilung.py`).

**Warum hier und nicht im Webdienst.** Weil das Modell hier schon liegt - eben
umgewandelt, auf einer Maschine mit Karte. Es dafür in einen anderen Container
zu laden hieße, mehrere Gigabyte über ein Volume zu schieben, um dasselbe
Ergebnis langsamer zu bekommen.

**Warum dieselben Maße wie in „hören".** Verglichen wird mit der Grundlinie:
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

import time
from pathlib import Path
from typing import Any

from wortlaut import corpus, laeufe, metriken, registry, streuung

from apps.lernen.backend.config import einstellungen

from .daten import zeilen_fuer


def _version(auftrag: dict[str, Any]) -> str:
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
    name = f"{marke}-{auftrag.get('methode', '?')}-{auftrag.get('daten', '?')}"
    art = str(auftrag.get("abschluss") or laeufe.ABSCHLUSS_BESTER)
    if art != laeufe.ABSCHLUSS_BESTER:
        name = f"{name}-{art}"
    abwandlung = str(auftrag.get("augmentierung") or laeufe.AUG_KEINE)
    if abwandlung != laeufe.AUG_KEINE:
        name = f"{name}-{abwandlung}"
    dauer = str(auftrag.get("dauer") or laeufe.DAUER_FEST)
    return name if dauer == laeufe.DAUER_FEST else f"{name}-{dauer}"


def bewerte(
    verzeichnis: Path, datenverzeichnis: Path, ct2: Path, auftrag: dict[str, Any], bericht
) -> dict[str, Any]:
    """Jede Testzeile durch das neue Modell; schreibt `bewertung.jsonl`."""
    from wortlaut.whisper.local import LokalerTranskriptor

    sprecher_id = str(auftrag["sprecher_id"])
    korpuswurzel = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id)
    zeilen = zeilen_fuer(verzeichnis, {laeufe.TEST})

    bericht.stufe("bewerten", test_zeilen=len(zeilen))
    bericht.sage(f"Testaufnahmen: {len(zeilen)} Zeilen über alle Fassungen")

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
    sprache = str(auftrag.get("sprache") or "de")

    ergebnis = []
    for nummer, zeile in enumerate(zeilen, start=1):
        begonnen = time.monotonic()
        transkript = erkenner.transkribiere(korpuswurzel / str(zeile["audio"]), sprache=sprache)
        dauer = time.monotonic() - begonnen
        guete = metriken.bewerte(str(zeile["text"]), transkript.text)
        eintrag = {
            "recording_id": zeile.get("recording_id"),
            "variante": zeile.get("variante"),
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

    return _zusammengefasst(ergebnis)


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
    Grundlinie je Fassung gegenüber.

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


def bewerte_und_gib_frei(
    verzeichnis: Path,
    datenverzeichnis: Path,
    gewichte: Path,
    auftrag: dict[str, Any],
    bericht,
    abschluss=None,
) -> str:
    """Umwandeln, bewerten, in die Registry eintragen. Gibt die Version zurück.

    Eingetragen wird mit `status: fertig` und nicht `active`: Ein durchgelaufenes
    Training ist noch kein Modell, das jemand benutzen soll. Zwischen „hat
    gerechnet" und „damit diktiere ich" liegt der Blick auf die Zahlen, und den
    nimmt einem nichts ab (siehe `apps/lernen/backend/api/modelle.py`).
    """
    from .finetune import wandle_um

    sprecher_id = str(auftrag["sprecher_id"])
    version = _version(auftrag)
    ziel = registry.stand_verzeichnis(datenverzeichnis, sprecher_id, version)
    ct2 = ziel / "ct2"

    wandle_um(gewichte, ct2, bericht)
    gemessen = bewerte(verzeichnis, datenverzeichnis, ct2, auftrag, bericht)

    registry.schreibe_stand(
        datenverzeichnis,
        {
            "id": f"{sprecher_id}/{version}",
            "sprecher_id": sprecher_id,
            "basismodell": auftrag.get("basismodell"),
            "methode": auftrag.get("methode"),
            "daten": auftrag.get("daten"),
            # Die dritte Achse, als schlichte Zeichenkette neben den beiden
            # anderen - und daneben, was dabei herauskam: die gemittelten
            # Zwischenstände, das gewählte α, die Verluste davor und danach.
            # Ein Stand, dessen α niemand mehr nachsehen kann, ist mit keinem
            # anderen zu vergleichen.
            "abschluss": str(auftrag.get("abschluss") or laeufe.ABSCHLUSS_BESTER),
            "augmentierung": str(auftrag.get("augmentierung") or laeufe.AUG_KEINE),
            "dauer": str(auftrag.get("dauer") or laeufe.DAUER_FEST),
            "abschluss_bericht": abschluss.als_dict() if abschluss is not None else None,
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
