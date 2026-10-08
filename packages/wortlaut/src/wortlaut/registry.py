"""Die Modell-Registry - Dateien statt Tabelle.

    data/modelle/<sprecher_id>/
    ├── freigabe.json               welches Modell dieser Mensch benutzt
    └── <version>/
        ├── manifest.json
        ├── ct2/                    für faster-whisper exportiert

Ein Modellstand ist ein Verzeichnis, das sich kopieren und sichern lässt.
„lernen" schreibt die Registry, „schreiben" liest sie; das Format gehört an
genau eine Stelle.

**Die Freigabe steht in einer eigenen Datei**, weil auch ein Grundmodell
freigegeben sein kann, das kein Verzeichnis hat. Sie trägt eine Kennung:
`small` für ein Grundmodell, `<sprecher_id>/<version>` für einen Stand -
unterscheidbar am Schrägstrich. Die Manifeste führen ihren `status` mit,
damit ein weggetragenes Verzeichnis zeigt, was es war; gelesen wird die
Freigabedatei.
"""

from __future__ import annotations

import hashlib

import json
import shutil
from pathlib import Path
from typing import Any

MODELLE = "modelle"
MANIFEST = "manifest.json"
FREIGABE = "freigabe.json"

# Ein Stand heißt `<sprecher_id>/<version>`; ein Whisper-Name enthält keinen
# Schrägstrich.
TRENNER = "/"


# Ohne `0`, `O`, `1`, `I` und `L` - die Kennung wird vorgelesen und abgetippt.
_ZEICHEN = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

# Fünf aus 31: knapp 29 Millionen, bei ein paar Dutzend Ständen je Mensch
# kollisionsarm genug.
_LAENGE = 5


def kurzkennung(version: str) -> str:
    """Ein kurzer Code für einen Modellstand: `K7M2Q`.

    Neben dem sprechenden Namen (`20260914T0852-medium-lora-…-2.25x`), der
    sich nicht aussprechen lässt: Der Name sagt, was ein Stand ist, die
    Kennung, welcher. Aus der Version gerechnet statt vergeben - jede App
    kommt ohne Buchführung auf dieselbe. Eindeutig innerhalb eines Sprechers;
    wer die Stände des anderen nie sieht, darf dieselbe Kennung tragen.
    """
    # SHA-256, weil `hash()` je Prozess anders gesalzen ist.
    roh = int.from_bytes(hashlib.sha256(version.encode("utf-8")).digest()[:8], "big")
    zeichen = []
    for _ in range(_LAENGE):
        roh, rest = divmod(roh, len(_ZEICHEN))
        zeichen.append(_ZEICHEN[rest])
    return "".join(zeichen)


def ist_stand(ref: str) -> bool:
    """Ob diese Kennung einen trainierten Stand meint und kein Grundmodell."""
    return TRENNER in ref


def beschriftung(ref: str) -> str:
    """`spr_7f2a/20260912T1420-lora` → `K7M2Q`; ein Grundmodell bleibt es selbst.

    Kurz und ohne vorangestelltes Wort, denn sie steht in Legenden und engen
    Spalten neben `small` und `large-v3`.
    """
    if not ist_stand(ref):
        return ref
    return kurzkennung(ref.split(TRENNER, 1)[1])


def ct2_verzeichnis(datenverzeichnis: Path, ref: str) -> Path:
    """Wo die Gewichte eines Standes liegen, die faster-whisper lädt."""
    sprecher_id, version = ref.split(TRENNER, 1)
    return stand_verzeichnis(datenverzeichnis, sprecher_id, version) / "ct2"


def stand_verzeichnis(datenverzeichnis: Path, sprecher_id: str, version: str) -> Path:
    return datenverzeichnis / MODELLE / sprecher_id / version


def lies_stand(datenverzeichnis: Path, sprecher_id: str, version: str) -> dict[str, Any]:
    pfad = stand_verzeichnis(datenverzeichnis, sprecher_id, version) / MANIFEST
    return json.loads(pfad.read_text(encoding="utf-8"))


def schreibe_stand(datenverzeichnis: Path, manifest: dict[str, Any]) -> Path:
    """Legt `manifest.json` an; `id` hat die Form `<sprecher_id>/<version>`."""
    sprecher_id, version = str(manifest["id"]).split("/", 1)
    verzeichnis = stand_verzeichnis(datenverzeichnis, sprecher_id, version)
    verzeichnis.mkdir(parents=True, exist_ok=True)
    pfad = verzeichnis / MANIFEST
    pfad.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return pfad


def alle_staende(datenverzeichnis: Path, sprecher_id: str) -> list[dict[str, Any]]:
    """Alle Modellstände eines Sprechers, älteste zuerst."""
    wurzel = datenverzeichnis / MODELLE / sprecher_id
    if not wurzel.is_dir():
        return []
    return [
        json.loads((eintrag / MANIFEST).read_text(encoding="utf-8"))
        for eintrag in sorted(wurzel.iterdir())
        if (eintrag / MANIFEST).is_file()
    ]


def loesche_stand(datenverzeichnis: Path, sprecher_id: str, version: str) -> bool:
    """Einen Modellstand vollständig entfernen; `False`, wenn es ihn nicht gab.

    Das ganze Verzeichnis - Gewichte ohne Manifest könnte niemand mehr
    zuordnen.
    """
    verzeichnis = stand_verzeichnis(datenverzeichnis, sprecher_id, version)
    if not verzeichnis.is_dir():
        return False
    shutil.rmtree(verzeichnis)
    return True


def stand_zu_lauf(
    datenverzeichnis: Path, sprecher_id: str, job_id: str
) -> dict[str, Any] | None:
    """Der Stand, den dieser Lauf hervorgebracht hat - über `job_id` im Manifest."""
    for stand in alle_staende(datenverzeichnis, sprecher_id):
        if stand.get("job_id") == job_id:
            return stand
    return None


def sprecher_verzeichnis(datenverzeichnis: Path, sprecher_id: str) -> Path:
    return datenverzeichnis / MODELLE / sprecher_id


def freigegeben(datenverzeichnis: Path, sprecher_id: str) -> str:
    """Was dieser Mensch benutzt: ein Grundmodellname, eine Standkennung - oder nichts.

    `freigabe.json` gilt. Fehlt sie, zählt ein Manifest mit `active` - aber
    nur, wenn es genau eines gibt: Welches von zweien gilt, entscheidet kein
    Programm. Sonst bleibt es beim Grundmodell.
    """
    datei = sprecher_verzeichnis(datenverzeichnis, sprecher_id) / FREIGABE
    try:
        ref = str(json.loads(datei.read_text(encoding="utf-8")).get("ref", ""))
    except (OSError, ValueError):
        ref = ""
    if ref:
        return ref

    aktive = [
        str(stand.get("id", ""))
        for stand in alle_staende(datenverzeichnis, sprecher_id)
        if stand.get("status") == "active"
    ]
    return aktive[0] if len(aktive) == 1 else ""


def gib_frei(datenverzeichnis: Path, sprecher_id: str, ref: str) -> str:
    """Dieses Modell freigeben - und damit jedes andere zurückziehen.

    Höchstens eines je Sprecher. Geschrieben werden Freigabedatei und der
    `status` jedes Manifests. Ein leeres `ref` nimmt die Freigabe zurück.
    """
    verzeichnis = sprecher_verzeichnis(datenverzeichnis, sprecher_id)
    verzeichnis.mkdir(parents=True, exist_ok=True)
    (verzeichnis / FREIGABE).write_text(
        json.dumps({"ref": ref}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for stand in alle_staende(datenverzeichnis, sprecher_id):
        soll = str(stand.get("id", "")) == ref
        if (stand.get("status") == "active") != soll:
            stand["status"] = "active" if soll else "zurueckgezogen"
            schreibe_stand(datenverzeichnis, stand)
    return ref

