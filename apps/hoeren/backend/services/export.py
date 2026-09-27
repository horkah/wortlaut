"""Ausleitung: eine Sicherung zum Zurückspielen, ein Datensatz zum Arbeiten.

Zwei Formate, weil es zwei Fragen sind:

* **Sicherung** (`.tgz`, `wortlaut/sicherung.py`) - „Der Server ist weg, ich
  will den Stand zurück." Sie enthält die Dateien, wie sie unter
  `WORTLAUT_DATA_DIR` liegen, Datenbank inbegriffen. Nichts darin ist
  aufbereitet; genau deshalb lässt sie sich vollständig zurückspielen.

* **Datensatz** (`.zip`, hier) - „Ich will die Paare aus Text und Audio ansehen
  oder trainieren, mit Werkzeugen, die von wortlaut nichts wissen." Er enthält
  keine Datenbank, sondern ein Verzeichnis Audiodateien, neben jeder ihren Text
  als `.txt`, dazu eine `metadaten.csv` und eine `metadaten.jsonl`.

Der Datensatz ist keine Sicherung: Sitzungen, Warteschlange und Messwerte
fehlen.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import storage

from ..db.models import Aufnahme, Sprecher, Textquelle, Vorlage
from . import zuschnitt

# `file_name` und `transcription` vorn und englisch: das `audiofolder`-Format
# von Hugging Face lädt so ohne Anpassung.
SPALTEN = (
    "file_name",
    "transcription",
    "aufnahme_id",
    "dauer_s",
    "modus",
    "quelle",
    "quelle_titel",
    "pegel_dbfs",
    "erstellt",
)

AUDIO = "audio"
LIESMICH = "LIESMICH.txt"


def datensatz_zip(
    sitzung: Session, sprecher: Sprecher, ablage: storage.Ablage, ziel: Path
) -> Path:
    """Schreibt den Datensatz eines Sprechers nach `ziel` und gibt ihn zurück.

        <sprecher_id>/
        ├── LIESMICH.txt
        ├── metadaten.csv        file_name, transcription, …
        ├── metadaten.jsonl      dieselben Zeilen, eine je Aufnahme
        └── audio/
            ├── rec_….wav        16 kHz mono, PCM 16 bit
            └── rec_….txt        der gesprochene Text, sonst nichts

    Der Text steht in der Tabelle und als `.txt` neben dem Audio. Nur Status
    `ok` - verworfene Aufnahmen haben kein Audio.
    """
    # Fehlt eine Datei, entfällt ihre Zeile, und der Rest steht.
    zeilen = [
        (zeile, aufnahme, pfad)
        for zeile, aufnahme in _zeilen(sitzung, sprecher.id)
        # Die Arbeitsdatei - derselbe Ton wie beim Training.
        if (pfad := ablage.pfad(zuschnitt.arbeitsblob(aufnahme))).is_file()
    ]
    tabelle = [zeile for zeile, _, _ in zeilen]

    ziel.parent.mkdir(parents=True, exist_ok=True)
    wurzel = sprecher.id
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as archiv:
        for zeile, aufnahme, pfad in zeilen:
            archiv.write(pfad, f"{wurzel}/{zeile['file_name']}")
            archiv.writestr(f"{wurzel}/{AUDIO}/{aufnahme.id}.txt", f"{zeile['transcription']}\n")

        archiv.writestr(f"{wurzel}/metadaten.csv", _als_csv(tabelle))
        archiv.writestr(f"{wurzel}/metadaten.jsonl", _als_jsonl(tabelle))
        archiv.writestr(f"{wurzel}/{LIESMICH}", _liesmich(sprecher, len(tabelle)))

    return ziel


def _zeilen(sitzung: Session, sprecher_id: str) -> list[tuple[dict[str, object], Aufnahme]]:
    """Aufnahme, Vorlage und Herkunft in einem Zug - eine Zeile je Paar."""
    treffer = sitzung.execute(
        select(Aufnahme, Vorlage, Textquelle)
        .join(Vorlage, Vorlage.id == Aufnahme.prompt_id)
        .join(Textquelle, Textquelle.id == Vorlage.source_id)
        .where(Aufnahme.speaker_id == sprecher_id, Aufnahme.status == "ok")
        .order_by(*zuschnitt.reihenfolge())
    ).all()

    return [
        (
            {
                "file_name": f"{AUDIO}/{aufnahme.id}.wav",
                "transcription": vorlage.text,
                "aufnahme_id": aufnahme.id,
                "dauer_s": round(zuschnitt.arbeitsdauer(aufnahme), 3),
                "modus": aufnahme.modus,
                "quelle": quelle.art,
                "quelle_titel": quelle.titel,
                "pegel_dbfs": round(aufnahme.pegel_dbfs, 1),
                "erstellt": aufnahme.erstellt,
            },
            aufnahme,
        )
        for aufnahme, vorlage, quelle in treffer
    ]


def _als_csv(zeilen: list[dict[str, object]]) -> str:
    puffer = io.StringIO()
    schreiber = csv.DictWriter(puffer, fieldnames=SPALTEN, lineterminator="\n")
    schreiber.writeheader()
    schreiber.writerows(zeilen)
    return puffer.getvalue()


def _als_jsonl(zeilen: list[dict[str, object]]) -> str:
    return "".join(json.dumps(zeile, ensure_ascii=False) + "\n" for zeile in zeilen)


def _liesmich(sprecher: Sprecher, anzahl: int) -> str:
    """Was in diesem Archiv liegt - für den, der es in einem Jahr wiederfindet."""
    return f"""Datensatz aus wortlaut · hören

Sprecher     {sprecher.name} ({sprecher.id})
Sprache      {sprecher.sprache}
Aufnahmen    {anzahl}

Aufbau
------
audio/<aufnahme_id>.wav    16 kHz mono, PCM 16 bit
audio/<aufnahme_id>.txt    der gesprochene Text zu genau dieser Datei
metadaten.csv              eine Zeile je Aufnahme; die Spalten `file_name`
                           und `transcription` entsprechen dem Format
                           `audiofolder` von Hugging Face
metadaten.jsonl            dieselben Zeilen als JSON, eine je Zeile

Spalte `modus`: gelesen | nachgesprochen | frei.
Spalte `quelle`: vorlage-Herkunft (llm, upload) oder korrektur.
Korrekturen sind schwächere Daten - der Text ist keine Vorgabe, sondern eine
abgenickte Maschinenausgabe. Wer sie gleichrangig einspeist, trainiert dem
Modell seine eigenen Fehler an.

Dies ist KEINE Sicherung: Datenbank, Sitzungen und die offene Warteschlange
fehlen. Zum Zurückspielen dient die Sicherung im Format .tgz.

Diese Dateien sind Stimmaufnahmen einer Person und damit Gesundheitsdaten
nach Art. 9 DSGVO. Entsprechend aufbewahren.
"""
