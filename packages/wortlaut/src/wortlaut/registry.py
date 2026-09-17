"""Die Modell-Registry - Dateien statt Tabelle.

    data/modelle/<sprecher_id>/
    ├── freigabe.json               welches Modell dieser Mensch benutzt
    └── <version>/
        ├── manifest.json
        ├── ct2/                    für faster-whisper exportiert
        └── checkpoint/             Rohgewichte, optional

Ein Modellstand ist damit ein Verzeichnis, das man kopieren, sichern und per
`scp` verschieben kann. Geschrieben wird die Registry von „lernen", gelesen von
„schreiben", das ohne einen Stand mit dem unveränderten Whisper-Modell
arbeitet. Das Format ist die Nahtstelle zwischen beiden und gehört deshalb an
genau eine Stelle.

**Die Freigabe steht daneben und nicht nur in den Manifesten.** Freigegeben
werden kann inzwischen auch ein unverändertes Grundmodell - `small`, `medium`,
`large-v3` -, und für das gibt es hier kein Verzeichnis und kein Manifest. Die
Freigabe ist deshalb eine eigene, winzige Datei je Sprecher, und sie trägt
genau eine Angabe: die Kennung dessen, was gelten soll. Ein Grundmodell heißt
darin `small`, ein trainierter Stand `<sprecher_id>/<version>` - unterscheiden
lassen sich beide am Schrägstrich, und genau deshalb dürfen sie in ein Feld.

Die Manifeste führen ihren `status` weiter mit („active" oder
„zurueckgezogen"): Wer ein Verzeichnis wegkopiert, soll ihm ansehen, was es
einmal war. Geschrieben werden beide in einem Zug, gelesen wird die Freigabe.
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
# Schrägstrich. Daran allein sind beide zu unterscheiden - und das ist der
# Grund, warum beide in dasselbe Feld dürfen.
TRENNER = "/"


# Das Alphabet der Kurzkennung. Ohne `0`, `O`, `1`, `I` und `L`: Diese Kennung
# wird vorgelesen, abgetippt und am Telefon durchgegeben, und dabei ist der
# Unterschied zwischen Null und O keiner.
_ZEICHEN = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

# Fünf Zeichen aus einunddreißig: knapp 29 Millionen Möglichkeiten. Bei den
# paar Dutzend Ständen, die ein Mensch je bekommt, liegt die Wahrscheinlichkeit
# einer Dopplung unter einem Millionstel - und die vollständige Version steht
# ohnehin daneben, falls doch.
_LAENGE = 5


def kurzkennung(version: str) -> str:
    """Ein kurzer Code für einen Modellstand: `K7M2Q`.

    **Wozu.** Ein Stand heißt
    `20260914T0852-medium-lora-augmentiert-voll-geduldig-2.25x`. Das ist
    sprechend und richtig, aber es lässt sich nicht aussprechen, nicht
    vergleichen und nicht über drei Bildschirme hinweg verfolgen. Die
    Kurzkennung tritt **neben** den sprechenden Titel und nicht an seine
    Stelle: Der Titel sagt, was dieser Stand ist, die Kennung sagt, welcher.

    **Warum gerechnet und nicht vergeben.** Eine laufende Nummer müsste
    irgendwo stehen, beim Löschen Lücken lassen und in drei Apps dieselbe sein.
    Aus der Version gerechnet braucht sie keine Buchführung: Jeder, der die
    Version kennt, kommt auf dieselbe Kennung - „lernen" in zwei Ansichten,
    „schreiben" in seiner Kopfzeile, und jeder Stand von früher rückwirkend,
    ohne dass eine Zeile Datenbank angefasst würde.

    **Warum aus der Version und nicht aus der Kennung `<sprecher>/<version>`.**
    Weil sie innerhalb eines Sprechers eindeutig sein soll und nicht darüber
    hinaus. Zwei Menschen dürfen dieselbe Kennung tragen - sie sehen die Stände
    des anderen nie, und eine Kennung, die den Sprecher mitverrechnet, wäre bei
    gleichem Rezept zweimal verschieden, ohne dass es jemandem nützte.
    """
    # SHA-256 und nicht `hash()`: Der eingebaute ist je Prozess anders gesalzen,
    # und eine Kennung, die sich beim Neustart ändert, ist keine.
    roh = int.from_bytes(hashlib.sha256(version.encode("utf-8")).digest()[:8], "big")
    zeichen = []
    for _ in range(_LAENGE):
        roh, rest = divmod(roh, len(_ZEICHEN))
        zeichen.append(_ZEICHEN[rest])
    return "".join(zeichen)


def ist_stand(ref: str) -> bool:
    """Ob diese Kennung einen trainierten Stand meint und kein Grundmodell."""
    return TRENNER in ref


# Wie ein Stand in einer Modellliste heißt. Kurz, weil er in einer Legende
# neben `small` und `large-v3` steht - und mit der Kennung, weil das die Zahl
# ist, die in „lernen" daneben steht und die man am Telefon durchgibt.
def beschriftung(ref: str) -> str:
    """`spr_7f2a/20260912T1420-lora` → `K7M2Q`; ein Grundmodell bleibt es selbst.

    Die Kennung steht für sich, ohne das Wort davor. Sie steht dort, wo
    `small` und `large-v3` stehen - in einer Legende, in einer Achse, in einer
    engen Tabellenspalte -, und ein vorangestelltes „Stand" wäre in jeder
    dieser Zeilen dasselbe Wort und nähme den Platz, an dem die Kennung selbst
    zu lesen sein soll. Fünf Zeichen sind schon die ganze Auskunft: Wer sie
    kennt, findet den Stand in „lernen" und in der Kopfzeile von „schreiben"
    wieder.
    """
    if not ist_stand(ref):
        return ref
    return kurzkennung(ref.split(TRENNER, 1)[1])


def ct2_verzeichnis(datenverzeichnis: Path, ref: str) -> Path:
    """Wo die Gewichte eines Standes liegen, die faster-whisper laden kann.

    Dieselbe Stelle, an die „schreiben" beim Diktieren greift
    (`apps/schreiben/backend/deps.py`) - ein Stand hat genau ein
    ausgeliefertes Modell, und das ist dieses.
    """
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

    Das ganze Verzeichnis, nicht nur sein Manifest: Ein Stand ohne Manifest
    wäre ein Gigabyte Gewichte, das niemand mehr zuordnen kann - und für jede
    Abfrage hier unsichtbar, weil sie über das Manifest geht.
    """
    verzeichnis = stand_verzeichnis(datenverzeichnis, sprecher_id, version)
    if not verzeichnis.is_dir():
        return False
    shutil.rmtree(verzeichnis)
    return True


def stand_zu_lauf(
    datenverzeichnis: Path, sprecher_id: str, job_id: str
) -> dict[str, Any] | None:
    """Der Stand, den dieser Lauf hervorgebracht hat - falls er es tat.

    Die Verbindung steht im Manifest (`job_id`) und nicht im Namen des
    Verzeichnisses: Der Name nennt Zeit, Methode und Datensatz, weil man ihn
    lesen können soll. Eine Kennung darin wäre für Menschen nutzlos und für
    diese Abfrage nicht sicherer.
    """
    for stand in alle_staende(datenverzeichnis, sprecher_id):
        if stand.get("job_id") == job_id:
            return stand
    return None


def sprecher_verzeichnis(datenverzeichnis: Path, sprecher_id: str) -> Path:
    return datenverzeichnis / MODELLE / sprecher_id


def freigegeben(datenverzeichnis: Path, sprecher_id: str) -> str:
    """Was dieser Mensch benutzt: ein Grundmodellname, eine Standkennung - oder nichts.

    **`freigabe.json` ist die Wahrheit.** Sie entsteht nur an einer Stelle: wenn
    ein Mensch in „lernen" auf „freigeben" drückt (`gib_frei`). Steht etwas
    darin, gilt das und sonst nichts.

    Fehlt sie, zählen ersatzweise die Manifeste - für eine Installation, die
    schon Stände freigegeben hatte, bevor es die Datei gab. Dieser Ersatz greift
    aber **nur, wenn er eindeutig ist**: Sagt genau ein Manifest `active`, ist
    das die Antwort; sagen es zwei, gilt keines.

    Der zweite Fall wäre sonst die eine Stelle im Projekt, an der sich ein
    Modell von selbst auswählt - „das neuere von beiden" ist eine Entscheidung,
    und Entscheidungen darüber, womit ein Mensch diktiert, trifft hier kein
    Programm. Zurückzufallen auf das Grundmodell ist die sichere Richtung: Es
    ist die Vorgabe, es ist sichtbar, und ein Griff genügt, um es zu ändern.
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

    Höchstens eines je Sprecher: Zwei freigegebene Modelle wären keine
    Freigabe, sondern eine offene Frage, die irgendwo weiter unten jemand
    beantworten müsste. Geschrieben wird beides zusammen - die Freigabedatei,
    weil sie auch ein Grundmodell benennen kann, und der `status` in jedem
    Manifest, damit ein weggetragenes Verzeichnis seine Geschichte behält.

    Ein leeres `ref` nimmt die Freigabe zurück; dann gilt wieder, womit eine
    Installation anfängt.
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


def aktiver_stand(datenverzeichnis: Path, sprecher_id: str) -> dict[str, Any] | None:
    """Der freigegebene **Stand** - `None`, wenn ein Grundmodell freigegeben ist."""
    ref = freigegeben(datenverzeichnis, sprecher_id)
    if not ref or not ist_stand(ref):
        return None
    ref_sprecher, version = ref.split(TRENNER, 1)
    try:
        return lies_stand(datenverzeichnis, ref_sprecher, version)
    except (OSError, ValueError):
        return None
