"""Einstellungen aus der Umgebung - ein Ort, nirgends sonst `os.environ`.

Die Feldnamen entsprechen den Variablen mit dem Präfix `WORTLAUT_`,
`modell_ref` also `WORTLAUT_MODELL_REF`.

Wer hier spricht, steht **nicht** mehr in der Konfiguration: Diese App führt
denselben Sprecher wie „hören", und den bringt der Aufrufer als Zugang mit
(siehe `deps.py`). Eine Instanz bedient damit so viele Sprecher, wie Zugänge
vorgelegt werden - nötig geworden, weil jeder Sprecher sein eigenes,
feingetuntes Modell bekommt und weil seine Diktate als Korrekturen in seinen
Korpus zurückfließen. Beides braucht die Kennung, und geraten werden darf sie
nicht.

Was bleibt, gehört der Maschine und nicht der Person: wo die Daten liegen, wie
Whisper läuft und wohin die Korrekturen gehen.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from wortlaut import rechenwerk

# Ablage dieser App - bewusst neben und nicht im Korpus: „hören" ist dessen
# einziger Schreiber (Grundentscheidung 6). Was hier liegt, ist Arbeitsstand;
# was bleiben soll, geht als Korrektur an „hören".
#
#     data/diktate/<sprecher_id>/
#     ├── audio/<abschnitt_id>.wav     16 kHz mono, je ein Abschnitt
#     └── schreiben.sqlite             Sitzungen, Abschnitte, Postausgang
#
# Nach Sprecher gegliedert wie der Korpus: Jeder Mensch hat hier seine eigene
# Datei, und `scripts/purge_speaker.py` löscht mit dem Verzeichnis alles, was
# von ihm da war. Eine gemeinsame Datenbank mit einer Spalte „sprecher" wäre
# ein Filter, den man vergessen kann - ein Verzeichnis nicht.
DIKTATE = "diktate"
DATENBANKNAME = "schreiben.sqlite"


def sprecher_relpfad(sprecher_id: str) -> str:
    return f"{DIKTATE}/{sprecher_id}"


def audio_relpfad(sprecher_id: str, abschnitt_id: str) -> str:
    """Pfad eines Abschnitts-Audios, relativ zur Wurzel der Ablage."""
    return f"{sprecher_relpfad(sprecher_id)}/audio/{abschnitt_id}.wav"


class Einstellungen(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORTLAUT_", env_file=".env", extra="ignore")

    # gemeinsam
    data_dir: Path = Path("./data")
    storage: str = "local"

    # Ein fest vorgegebener Modellstand, Form `<sprecher_id>/<version>`. Leer
    # ist der Normalfall: Dann bekommt jeder Sprecher den Stand, den „lernen"
    # für ihn freigegeben hat (`registry.freigegeben`), und solange es keine
    # Freigabe gibt, das unveränderte `asr_modell`. Gesetzt gilt der eine Stand für
    # jeden, der hier ruft - gedacht zum Erproben eines Standes, nicht für den
    # Betrieb.
    modell_ref: str = ""
    # Das unveränderte Grundmodell, wenn kein Stand da ist. `small` ist die
    # kleinste Stufe, die noch ganze Sätze trifft; kleiner zu werden spart
    # Rechenzeit, liefert aber Text, an dem niemand ablesen kann, ob das
    # Diktat angekommen ist.
    asr_modell: str = "small"
    # Worauf gerechnet wird - dieselbe Einstellung in allen drei Apps und beim
    # Trainer, und das ist der ganze Sinn: „schreiben", die Auswertung in
    # „hören" und die Bewertung eines Laufs schicken dieselben Modelle über
    # dieselben Aufnahmen, und ihre Rechenzeiten sind nur vergleichbar, wenn
    # sie auf demselben Rechenwerk entstanden sind. Was `auto` bedeutet und
    # warum auf der Karte `int8_float16` gilt, steht in
    # `wortlaut/rechenwerk.py`.
    geraet: str = rechenwerk.AUTO  # auto | cuda | cpu
    rechenart: str = rechenwerk.AUTO  # auto | int8 | int8_float16 | float16 | float32

    def rechenwerk(self) -> tuple[str, str]:
        """`(geraet, rechenart)` - aufgelöst, `auto` beantwortet."""
        return rechenwerk.waehle(self.geraet, self.rechenart)

    # local = faster-whisper im eigenen Prozess, remote = fremder Endpunkt.
    # Vorsicht: remote schickt Stimmdaten an Dritte (docs/datenschutz.md).
    asr: str = "local"
    asr_endpoint: str = ""
    asr_api_key: str = ""
    sprache: str = "de"

    # Wohin die bestätigten Korrekturen gehen. Leer heißt: sie bleiben im
    # Postausgang liegen, statt verloren zu gehen.
    #
    # Einen Token braucht es hier nicht mehr: Gesendet wird mit dem Zugang, den
    # der Sprecher gerade vorgelegt hat (siehe `services/outbox.py`). Damit
    # liegt kein fremdes Geheimnis in der Umgebung, und die Korrektur landet
    # zwingend im Korpus dessen, der sie bestätigt hat.
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
