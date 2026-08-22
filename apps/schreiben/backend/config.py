"""Einstellungen aus der Umgebung — ein Ort, nirgends sonst `os.environ`.

Die Feldnamen entsprechen den Variablen mit dem Präfix `WORTLAUT_`,
`modell_ref` also `WORTLAUT_MODELL_REF`.

Eine Instanz dieser App ist auf **einen** Sprecher und **einen** Modellstand
konfiguriert (Grundentscheidung 7). Beides ist deshalb Konfiguration und kein
Laufzeitparameter: Ein Modellwechsel ist eine Änderung mit Neustart, sonst
weiß hinterher niemand, welcher Stand welche Ausgabe erzeugt hat.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Ablage dieser App — bewusst neben und nicht im Korpus: „hören" ist dessen
# einziger Schreiber (Grundentscheidung 6). Was hier liegt, ist Arbeitsstand;
# was bleiben soll, geht als Korrektur an „hören".
#
#     data/diktate/<sprecher_id>/
#     ├── audio/<abschnitt_id>.wav     16 kHz mono, je ein Abschnitt
#     └── schreiben.sqlite             Sitzungen, Abschnitte, Postausgang
#
# Nach Sprecher gegliedert wie der Korpus, obwohl eine Instanz nur einen kennt:
# Sonst fände `scripts/purge_speaker.py` diese Dateien nicht, und eine Löschung
# wäre unvollständig.
DIKTATE = "diktate"
DATENBANKNAME = "schreiben.sqlite"

# Ohne gesetzten Sprecher (Entwicklung) braucht das Verzeichnis trotzdem einen
# Namen — ein leerer wäre ein Pfad, der auf sich selbst zeigt.
OHNE_SPRECHER = "ohne-sprecher"


def sprecher_relpfad(sprecher_id: str) -> str:
    return f"{DIKTATE}/{sprecher_id or OHNE_SPRECHER}"


def audio_relpfad(sprecher_id: str, abschnitt_id: str) -> str:
    """Pfad eines Abschnitts-Audios, relativ zur Wurzel der Ablage."""
    return f"{sprecher_relpfad(sprecher_id)}/audio/{abschnitt_id}.wav"


class Einstellungen(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORTLAUT_", env_file=".env", extra="ignore")

    # gemeinsam
    data_dir: Path = Path("./data")
    storage: str = "local"

    # Wessen Stimme. Bestimmt die eigene Ablage und geht als Behauptung an
    # „hören" mit, das sie gegen den Zugang aus `intake_token` hält.
    sprecher_id: str = ""

    # Modellstand aus der Registry, Form `<sprecher_id>/<version>`. Leer heißt:
    # noch keiner da — dann läuft `asr_modell` als unverändertes Whisper-Modell.
    # Genau so fängt eine Installation an, bevor es „lernen" gibt.
    modell_ref: str = ""
    asr_modell: str = "tiny"

    # local = faster-whisper im eigenen Prozess, remote = fremder Endpunkt.
    # Vorsicht: remote schickt Stimmdaten an Dritte (docs/datenschutz.md).
    asr: str = "local"
    asr_endpoint: str = ""
    asr_api_key: str = ""
    sprache: str = "de"

    # Wohin die bestätigten Korrekturen gehen. Leer heißt: sie bleiben im
    # Postausgang liegen, statt verloren zu gehen.
    intake_url: str = ""
    # Der Zugang dieses Sprechers bei „hören" (`<sprecher_id>.<geheimnis>`,
    # dort ausgegeben). Er bestimmt, in welchen Korpus geschrieben wird —
    # `sprecher_id` oben wird von „hören" nur noch dagegen geprüft.
    intake_token: str = ""

    @property
    def migrationsverzeichnis(self) -> Path:
        return Path(__file__).parent / "db" / "migrations"

    @property
    def datenbank(self) -> Path:
        return self.data_dir / sprecher_relpfad(self.sprecher_id) / DATENBANKNAME


@lru_cache
def einstellungen() -> Einstellungen:
    """Einmal lesen, überall dieselbe Instanz."""
    return Einstellungen()
