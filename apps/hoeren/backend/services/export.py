"""Ausleitung: eine Sicherung zum Zurückspielen, ein Datensatz zum Arbeiten.

Zwei Formate, weil es zwei Fragen sind:

* **Sicherung** (`.tgz`, `wortlaut/sicherung.py`) — „Der Server ist weg, ich
  will den Stand zurück." Sie enthält die Dateien, wie sie unter
  `WORTLAUT_DATA_DIR` liegen, Datenbank inbegriffen. Nichts darin ist
  aufbereitet; genau deshalb lässt sie sich vollständig zurückspielen.

* **Datensatz** (`.zip`, hier) — „Ich will die Paare aus Text und Audio ansehen
  oder trainieren, mit Werkzeugen, die von wortlaut nichts wissen." Er enthält
  keine Datenbank, sondern ein Verzeichnis Audiodateien, neben jeder ihren Text
  als `.txt`, dazu eine `metadaten.csv` und eine `metadaten.jsonl`.

Der Datensatz ist bewusst **keine** Sicherung: Aus ihm lässt sich der Betrieb
nicht wiederherstellen (Sitzungen, Warteschlange und Messwerte fehlen zum Teil).
Wer sichert, nimmt die `.tgz`.
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

# Die Spalten der `metadaten.csv`. `file_name` und `transcription` stehen
# vorn und heißen englisch, weil genau diese beiden Namen das
# `audiofolder`-Format von Hugging Face erwartet — damit lädt der Datensatz
# ohne eine Zeile Anpassungscode. Alles Weitere steht dahinter und stört dort
# niemanden.
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

    Der Text steht doppelt darin: in der Tabelle für das Training, als
    Textdatei neben dem Audio für alles, was sich nur eine Datei ansehen will.
    Das kostet ein paar Kilobyte und spart jedem Werkzeug den Umweg über die
    Tabelle.

    Aufgenommen wird nur, was Status `ok` hat: Verworfene Aufnahmen haben kein
    Audio mehr (siehe `api/recordings.py`) und wären leere Zeilen.
    """
    # Die Datenbank kann eine Aufnahme kennen, deren Datei fehlt. Das ist ein
    # Befund und kein Grund, den ganzen Auszug abzubrechen: Die Zeile entfällt,
    # damit Tabelle und Verzeichnis zueinander passen, der Rest steht.
    zeilen = [
        (zeile, aufnahme, pfad)
        for zeile, aufnahme in _zeilen(sitzung, sprecher.id)
        if (pfad := ablage.pfad(aufnahme.blob)).is_file()
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
    """Aufnahme, Vorlage und Herkunft in einem Zug — eine Zeile je Paar."""
    treffer = sitzung.execute(
        select(Aufnahme, Vorlage, Textquelle)
        .join(Vorlage, Vorlage.id == Aufnahme.prompt_id)
        .join(Textquelle, Textquelle.id == Vorlage.source_id)
        .where(Aufnahme.speaker_id == sprecher_id, Aufnahme.status == "ok")
        .order_by(Aufnahme.erstellt)
    ).all()

    return [
        (
            {
                "file_name": f"{AUDIO}/{aufnahme.id}.wav",
                "transcription": vorlage.text,
                "aufnahme_id": aufnahme.id,
                "dauer_s": round(aufnahme.dauer_s, 3),
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
    """Was in diesem Archiv liegt — für den, der es in einem Jahr wiederfindet."""
    return f"""Datensatz aus wortlaut · hören

Sprecher     {sprecher.name} ({sprecher.id})
Sprache      {sprecher.sprache}
Basismodell  {sprecher.basismodell}
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
Korrekturen sind schwächere Daten — der Text ist keine Vorgabe, sondern eine
abgenickte Maschinenausgabe. Wer sie gleichrangig einspeist, trainiert dem
Modell seine eigenen Fehler an.

Dies ist KEINE Sicherung: Datenbank, Sitzungen und die offene Warteschlange
fehlen. Zum Zurückspielen dient die Sicherung im Format .tgz.

Diese Dateien sind Stimmaufnahmen einer Person und damit Gesundheitsdaten
nach Art. 9 DSGVO. Entsprechend aufbewahren.
"""
