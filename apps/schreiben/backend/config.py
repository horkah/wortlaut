"""Einstellungen aus der Umgebung - ein Ort, nirgends sonst `os.environ`.

Die Feldnamen entsprechen den Variablen mit dem Präfix `WORTLAUT_`,
`modell_ref` also `WORTLAUT_MODELL_REF`.

Wer spricht, bringt der Zugang mit (`deps.py`); hier steht nur, was der
Maschine gehört: Ablage, Whisper, Ziel der Korrekturen.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from wortlaut.einstellungen import Grundeinstellungen

# Ablage neben dem Korpus, dessen einziger Schreiber „hören" ist
# (Grundentscheidung 6). Was bleiben soll, geht als Korrektur dorthin.
#
#     data/diktate/<sprecher_id>/
#     ├── audio/<abschnitt_id>.wav     16 kHz mono, je ein Abschnitt
#     └── schreiben.sqlite             Sitzungen, Abschnitte, Postausgang
#
# Je Sprecher ein Verzeichnis - die Löschung nimmt es ganz
# (`scripts/purge_speaker.py`).
DIKTATE = "diktate"
DATENBANKNAME = "schreiben.sqlite"


def sprecher_relpfad(sprecher_id: str) -> str:
    return f"{DIKTATE}/{sprecher_id}"


def audio_relpfad(sprecher_id: str, abschnitt_id: str) -> str:
    """Pfad eines Abschnitts-Audios, relativ zur Wurzel der Ablage."""
    return f"{sprecher_relpfad(sprecher_id)}/audio/{abschnitt_id}.wav"


class Einstellungen(Grundeinstellungen):
    # Ein fester Stand `<sprecher_id>/<version>` für alle - zum Erproben. Leer:
    # die Freigabe aus „lernen" (`registry.freigegeben`), sonst `asr_modell`.
    modell_ref: str = ""
    # Ohne Freigabe; `small` ist die kleinste Stufe, die ganze Sätze trifft.
    asr_modell: str = "small"

    # local = faster-whisper im eigenen Prozess, remote = fremder Endpunkt.
    # Vorsicht: remote schickt Stimmdaten an Dritte (docs/datenschutz.md).
    asr: str = "local"
    asr_endpoint: str = ""
    asr_api_key: str = ""

    # Wohin bestätigte Korrekturen gehen; leer: Sie bleiben im Postausgang.
    # Gesendet wird mit dem Zugang des Sprechers (`services/outbox.py`).
    intake_url: str = ""

    @property
    def migrationsverzeichnis(self) -> Path:
        return Path(__file__).parent / "db" / "migrations"

    def datenbank(self, sprecher_id: str) -> Path:
        """Die Diktatdatenbank eines Sprechers. Je Sprecher eine Datei."""
        return self.data_dir / sprecher_relpfad(sprecher_id) / DATENBANKNAME


@lru_cache
def einstellungen() -> Einstellungen:
    """Einmal lesen, überall dieselbe Instanz."""
    return Einstellungen()
