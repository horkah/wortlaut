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

**Warum auf allen vier Fassungen.** Weil die interessantere Hälfte der Frage
lautet, ob das Modell den Sprecher verstanden hat oder bloß seine
Aufnahmesituation. Das Manifest trägt die Testaufnahmen deshalb in allen vier
Fassungen, unabhängig davon, womit trainiert wurde.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from wortlaut import corpus, laeufe, metriken, registry

from .daten import zeilen_fuer


def _version(auftrag: dict[str, Any]) -> str:
    """Der Name des Standes: Zeit, Methode, Datensatz.

    Alle drei, weil vier Stände nebeneinander liegen, die sich in genau diesen
    Punkten unterscheiden. Eine Zeitmarke allein ließe offen, welcher von den
    vieren gemeint ist - und ein Verzeichnisname, den man nachschlagen muss,
    ist keiner.
    """
    marke = str(auftrag.get("erstellt", laeufe.jetzt()))[:16].replace(":", "").replace("-", "")
    return f"{marke}-{auftrag.get('methode', '?')}-{auftrag.get('daten', '?')}"


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
    erkenner = LokalerTranskriptor(str(ct2), geraet="auto", rechenart="float16")
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
        }
        laeufe.haenge_an(verzeichnis / laeufe.BEWERTUNG, eintrag)
        ergebnis.append(eintrag)
        if nummer % 10 == 0 or nummer == len(zeilen):
            bericht.sage(f"  bewertet: {nummer}/{len(zeilen)}")

    return _zusammengefasst(ergebnis)


def _zusammengefasst(zeilen: list[dict[str, Any]]) -> dict[str, Any]:
    """Die Mittel über alle Testzeilen - die Zahlen, die ins Manifest gehen.

    Über alle Fassungen zusammen, denn das ist die Zahl, die einen Stand in
    einer Zeile beschreibt. Aufgeschlüsselt liegt sie in `bewertung.jsonl`
    daneben; die Ansicht in „lernen" liest sie von dort und stellt sie der
    Grundlinie je Fassung gegenüber.
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
    }


def bewerte_und_gib_frei(
    verzeichnis: Path,
    datenverzeichnis: Path,
    gewichte: Path,
    auftrag: dict[str, Any],
    bericht,
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
            "job_id": auftrag.get("job_id"),
            "erstellt": laeufe.jetzt(),
            "daten_umfang": auftrag.get("zeilen", {}),
            "metriken": gemessen,
            "laufzeit": "faster-whisper>=1.1",
            "status": "fertig",
        },
    )

    # Die Rohgewichte sind ein Vielfaches des umgewandelten Standes und werden
    # von nichts in diesem Projekt gelesen. Sie liegen zu lassen hieße, je Lauf
    # ein Gigabyte aufzuheben, das niemand je öffnet.
    _raeume_auf(gewichte, verzeichnis / "arbeitsstand")

    bericht.fertig(version, gemessen)
    return version


def _raeume_auf(*verzeichnisse: Path) -> None:
    import shutil

    for verzeichnis in verzeichnisse:
        if verzeichnis.is_dir():
            shutil.rmtree(verzeichnis, ignore_errors=True)
