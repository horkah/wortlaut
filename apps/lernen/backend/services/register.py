"""Das Register der Läufe - was ein Lauf war, auch wenn sein Modell gelöscht ist.

    data/lernen/<sprecher_id>/register.sqlite

Ein Lauf und sein Modell sind Dateien auf der Trainingsablage, und beide gehen
beim Löschen (`auftraege.loesche`). Das Register hält fest, was es braucht, um
einen Lauf wissenschaftlich auszuwerten und neu zu rechnen; das Schema samt
Bedeutung jeder Spalte steht in `db/migrations/001_register.sql`.

**Eingetragen wird an drei Stellen**, jedes Mal mit `trage_ein`:

* wenn ein Lauf endet, gleich wie - vom Läufer, der als Einziger die Umgebung
  kennt, in der gerechnet wurde (`training/laeufer.py`);
* bevor ein Lauf gelöscht wird, samt dem, was „hören" mit seinem Modell
  gemessen hat (`trage_vor_dem_loeschen_ein`); scheitert das, wird nicht gelöscht;
* von Hand für alle vorhandenen Läufe (`scripts/register.py`).

Ein zweites Eintragen ersetzt, was aus dem Laufverzeichnis kommt. Was nur hier
steht, bleibt: die Umgebung, die übernommenen Messungen des Endmodells, der
Zeitpunkt des Löschens und der Fingerabdruck jeder Audiodatei, wie sie beim
ersten Eintragen war.

Kein Weg der Oberfläche führt hierher.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import asdict
from importlib import metadata
from pathlib import Path
from typing import Any

from wortlaut import corpus, db, kartenplan, laeufe, registry

from apps.lernen.backend.config import sprecher_relpfad

REGISTER = "register.sqlite"
MIGRATIONEN = Path(__file__).resolve().parents[1] / "db" / "migrations"

FALTUNG = "faltung"
ENDMODELL = "endmodell"

# Was in eine eigene Spalte kommt; alles Übrige einer Zeile steht in `weitere`.
_DATENSPALTEN = (
    "recording_id",
    "variante",
    "faltung",
    "gewicht",
    "quelle",
    "modus",
    "dauer_s",
    "text",
    "audio",
)
_MESSSPALTEN = (
    "faltung",
    "recording_id",
    "variante",
    "text",
    "wer",
    "cer",
    "mer",
    "wil",
    "genauigkeit",
    "rechenzeit_s",
    "rechenwerk",
    "tempo",
)

# Die Bibliotheken, von denen das Ergebnis eines Trainings abhängt.
_BIBLIOTHEKEN = (
    "torch",
    "transformers",
    "peft",
    "accelerate",
    "tokenizers",
    "faster-whisper",
    "ctranslate2",
    "numpy",
)


def pfad(datenverzeichnis: Path, sprecher_id: str) -> Path:
    return datenverzeichnis / sprecher_relpfad(sprecher_id) / REGISTER


@contextmanager
def oeffne(datenverzeichnis: Path, sprecher_id: str) -> Iterator[sqlite3.Connection]:
    """Das Register dieses Sprechers, auf dem neuesten Schema, in einer Transaktion."""
    datei = pfad(datenverzeichnis, sprecher_id)
    db.wende_migrationen_an(datei, MIGRATIONEN)
    with closing(sqlite3.connect(datei, timeout=30)) as verbindung:
        verbindung.execute("PRAGMA foreign_keys = ON")
        with verbindung:
            yield verbindung


def _json(wert: Any) -> str | None:
    return None if wert is None else json.dumps(wert, ensure_ascii=False, sort_keys=True)


def _sha256(datei: Path) -> str | None:
    if not datei.is_file():
        return None
    summe = hashlib.sha256()
    with datei.open("rb") as quelle:
        for stueck in iter(lambda: quelle.read(1 << 20), b""):
            summe.update(stueck)
    return summe.hexdigest()


def _aufgeteilt(zeile: dict[str, Any], spalten: tuple[str, ...]) -> tuple[list[Any], str | None]:
    """Die Werte der eigenen Spalten und der Rest als JSON."""
    rest = {schluessel: wert for schluessel, wert in zeile.items() if schluessel not in spalten}
    return [zeile.get(spalte) for spalte in spalten], _json(rest) if rest else None


def trage_ein(
    datenverzeichnis: Path, job_id: str, umgebung: dict[str, Any] | None = None
) -> bool:
    """Diesen Lauf ins Register seines Sprechers schreiben; `False`, wenn es ihn nicht gibt.

    `umgebung` gibt nur der Läufer mit (`umgebung()`); fehlt sie, bleibt eine
    schon eingetragene stehen.
    """
    lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
    if lauf is None or not lauf.sprecher_id:
        return False
    sprecher_id = lauf.sprecher_id
    stand = registry.stand_zu_lauf(datenverzeichnis, sprecher_id, job_id)
    modell = str(stand["id"]) if stand and stand.get("id") else None
    korpus = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id)
    protokoll = lauf.verzeichnis / laeufe.PROTOKOLL
    jetzt = laeufe.jetzt()

    with oeffne(datenverzeichnis, sprecher_id) as register:
        register.execute(
            """
            INSERT INTO laeufe (
                job_id, sprecher_id, titel, status, erstellt, begonnen, beendet,
                modell, kennung, auftrag, zustand, stand, kernauswahl, umgebung,
                protokoll, eingetragen, aktualisiert
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (job_id) DO UPDATE SET
                titel = excluded.titel,
                status = excluded.status,
                erstellt = excluded.erstellt,
                begonnen = excluded.begonnen,
                beendet = excluded.beendet,
                modell = coalesce(excluded.modell, laeufe.modell),
                kennung = coalesce(excluded.kennung, laeufe.kennung),
                auftrag = excluded.auftrag,
                zustand = excluded.zustand,
                stand = coalesce(excluded.stand, laeufe.stand),
                kernauswahl = excluded.kernauswahl,
                umgebung = coalesce(excluded.umgebung, laeufe.umgebung),
                protokoll = excluded.protokoll,
                aktualisiert = excluded.aktualisiert
            """,
            (
                job_id,
                sprecher_id,
                laeufe.titel(lauf.auftrag),
                lauf.status,
                lauf.auftrag.get("erstellt"),
                lauf.zustand.get("begonnen"),
                lauf.zustand.get("beendet"),
                modell,
                registry.beschriftung(modell) if modell else None,
                _json(lauf.auftrag),
                _json(lauf.zustand) if (lauf.verzeichnis / laeufe.ZUSTAND).is_file() else None,
                _json(stand),
                _json(laeufe.lies_json(lauf.verzeichnis / laeufe.KERNAUSWAHL)),
                _json(umgebung),
                protokoll.read_text(encoding="utf-8", errors="replace")
                if protokoll.is_file()
                else None,
                jetzt,
                jetzt,
            ),
        )

        # Der Fingerabdruck bleibt der vom ersten Eintragen - sonst zeigte er
        # nach einem Nachschnitt einen Klang, auf dem nie gelernt wurde.
        fingerabdruecke = {
            (zeile, audio): sha
            for zeile, audio, sha in register.execute(
                "SELECT zeile, audio, audio_sha256 FROM daten WHERE job_id = ?", (job_id,)
            )
        }
        register.execute("DELETE FROM daten WHERE job_id = ?", (job_id,))
        for nummer, zeile in enumerate(laeufe.lies_zeilen(lauf.verzeichnis / laeufe.MANIFEST)):
            werte, weitere = _aufgeteilt(zeile, _DATENSPALTEN)
            audio = zeile.get("audio")
            sha = fingerabdruecke.get((nummer, audio))
            if sha is None and audio:
                sha = _sha256(korpus / str(audio))
            register.execute(
                f"INSERT INTO daten (job_id, zeile, {', '.join(_DATENSPALTEN)}, audio_sha256, weitere)"
                f" VALUES (?, ?, {', '.join('?' * len(_DATENSPALTEN))}, ?, ?)",
                (job_id, nummer, *werte, sha, weitere),
            )

        register.execute(
            "UPDATE laeufe SET datensatz = ? WHERE job_id = ?",
            (datensatz(register, job_id), job_id),
        )

        register.execute(
            "DELETE FROM messungen WHERE job_id = ? AND herkunft = ?", (job_id, FALTUNG)
        )
        for nummer, zeile in enumerate(laeufe.lies_zeilen(lauf.verzeichnis / laeufe.BEWERTUNG)):
            _messung(register, job_id, FALTUNG, nummer, zeile)

        register.execute("DELETE FROM ereignisse WHERE job_id = ?", (job_id,))
        for nummer, zeile in enumerate(laeufe.lies_zeilen(lauf.verzeichnis / laeufe.FORTSCHRITT)):
            register.execute(
                "INSERT INTO ereignisse (job_id, nummer, zeit, art, daten) VALUES (?, ?, ?, ?, ?)",
                (job_id, nummer, zeile.get("zeit"), zeile.get("art"), _json(zeile)),
            )
    return True


# Was einen Datensatz ausmacht - das Gewicht nicht, es ist eine Achse des Auftrags.
_DATENSATZ = ("recording_id", "variante", "faltung", "quelle", "text", "audio_sha256")


def datensatz(register: sqlite3.Connection, job_id: str) -> str:
    """Der Fingerabdruck der Daten dieses Laufs: gleich genau dann, wenn zwei
    Läufe auf denselben Daten lernten und maßen (`002_datensatz.sql`).

    SHA-256 über die sortierten Zeilen, je Zeile die Felder aus `_DATENSATZ`
    als JSON-Liste - unabhängig von der Reihenfolge im Manifest.
    """
    zeilen = sorted(
        json.dumps(list(zeile), ensure_ascii=False)
        for zeile in register.execute(
            f"SELECT {', '.join(_DATENSATZ)} FROM daten WHERE job_id = ?", (job_id,)
        )
    )
    summe = hashlib.sha256()
    for zeile in zeilen:
        summe.update(zeile.encode("utf-8"))
        summe.update(b"\n")
    return summe.hexdigest()


def _messung(
    register: sqlite3.Connection, job_id: str, herkunft: str, nummer: int, zeile: dict[str, Any]
) -> None:
    werte, weitere = _aufgeteilt(zeile, _MESSSPALTEN)
    register.execute(
        f"INSERT INTO messungen (job_id, herkunft, nummer, {', '.join(_MESSSPALTEN)}, weitere)"
        f" VALUES (?, ?, ?, {', '.join('?' * len(_MESSSPALTEN))}, ?)",
        (job_id, herkunft, nummer, *werte, weitere),
    )


def trage_vor_dem_loeschen_ein(datenverzeichnis: Path, sprecher_id: str, job_id: str) -> None:
    """Alles eintragen, was mit dem Lauf verschwindet - und dass er verschwindet.

    Dazu gehört, was „hören" mit dem Endmodell gemessen hat: Ohne Modell räumt
    die Auswertung diese Zeilen weg (`hoeren/services/auswertung.py`), neu
    rechnen ließe sich keine. Die Zeilen aus der Kreuzvalidierung stehen schon
    aus `bewertung.jsonl` hier.
    """
    if not trage_ein(datenverzeichnis, job_id):
        return
    with oeffne(datenverzeichnis, sprecher_id) as register:
        (modell,) = register.execute(
            "SELECT modell FROM laeufe WHERE job_id = ?", (job_id,)
        ).fetchone()
        if modell:
            register.execute(
                "DELETE FROM messungen WHERE job_id = ? AND herkunft = ?", (job_id, ENDMODELL)
            )
            for nummer, zeile in enumerate(
                _erkennungen(datenverzeichnis, sprecher_id, str(modell))
            ):
                _messung(register, job_id, ENDMODELL, nummer, zeile)
        register.execute(
            "UPDATE laeufe SET entfernt = ?, aktualisiert = ? WHERE job_id = ?",
            (laeufe.jetzt(), laeufe.jetzt(), job_id),
        )


def _erkennungen(datenverzeichnis: Path, sprecher_id: str, modell: str) -> list[dict[str, Any]]:
    """Was die Auswertung von „hören" mit diesem Stand selbst gemessen hat - lesend."""
    datei = corpus.datenbank_pfad(datenverzeichnis, sprecher_id)
    if not datei.is_file():
        return []
    with closing(sqlite3.connect(f"file:{datei}?mode=ro", uri=True, timeout=30)) as korpus:
        korpus.row_factory = sqlite3.Row
        return [
            dict(zeile)
            for zeile in korpus.execute(
                "SELECT recording_id, variante, text, wer, cer, mer, wil, genauigkeit,"
                " rechenzeit_s, rechenwerk, tempo, erstellt FROM erkennungen"
                " WHERE modell = ? AND herkunft = 'gemessen' ORDER BY recording_id, variante",
                (modell,),
            )
        ]


# ── Die Umgebung ───────────────────────────────────────────────────────────

# Der Code, der rechnet: der Trainer, das Backend von „lernen", das er
# mitbenutzt, und die gemeinsame Bibliothek.
_WURZEL = Path(__file__).resolve().parents[4]
_QUELLEN = (
    ("apps/lernen/training", ("*.py", "*.yaml")),
    ("apps/lernen/backend", ("*.py", "*.sql")),
    ("packages/wortlaut/src/wortlaut", ("*.py",)),
)


def quellstand() -> str:
    """SHA-256 über Pfad und Inhalt jeder Quelldatei, die ein Training bestimmt.

    Im Abbild steht kein Git; dieselbe Zahl, über einen Checkout gerechnet,
    findet den Commit.
    """
    summe = hashlib.sha256()
    dateien = sorted(
        datei
        for ordner, muster in _QUELLEN
        for maske in muster
        for datei in (_WURZEL / ordner).rglob(maske)
        if "__pycache__" not in datei.parts and "tests" not in datei.parts
    )
    for datei in dateien:
        summe.update(datei.relative_to(_WURZEL).as_posix().encode())
        summe.update(b"\0")
        summe.update(datei.read_bytes())
    return summe.hexdigest()


def _revision(basismodell: str) -> str | None:
    """Welcher Commit des Grundmodells im Zwischenspeicher von Hugging Face liegt."""
    wurzel = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    ref = wurzel / "hub" / f"models--{basismodell.replace('/', '--')}" / "refs" / "main"
    return ref.read_text(encoding="utf-8").strip() if ref.is_file() else None


def umgebung(datenverzeichnis: Path, auftrag: dict[str, Any]) -> dict[str, Any]:
    """Worin dieser Lauf gerechnet wurde - vom Läufer, im Container des Trainers."""
    versionen = {}
    for name in _BIBLIOTHEKEN:
        try:
            versionen[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    karte = kartenplan.lies_karte(laeufe.wurzel(datenverzeichnis))
    basismodell = str(auftrag.get("basismodell") or "")
    return {
        "quellstand": quellstand(),
        "python": platform.python_version(),
        "plattform": platform.platform(),
        "bibliotheken": versionen,
        "grundmodell": basismodell,
        "grundmodell_revision": _revision(basismodell) if basismodell else None,
        "karte": asdict(karte) if karte else None,
    }
