"""Einstellungen aus der Umgebung - ein Ort, nirgends sonst `os.environ`.

Die Feldnamen entsprechen den Variablen mit dem Präfix `WORTLAUT_`,
`data_dir` also `WORTLAUT_DATA_DIR`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from wortlaut.einstellungen import AUSWERTUNG_MODELLE, Grundeinstellungen


class Einstellungen(Grundeinstellungen):
    storage: str = "local"

    # Textquelle „LLM". Leer heißt: abgeschaltet, es bleibt der Textupload.
    llm_provider: str = ""
    llm_api_key: str = ""
    # Das lokale Ollama-Modell; bei anbieter="anthropic" eine Claude-Kennung.
    llm_model: str = "gemma2:9b"
    # Nur bei anbieter="openai": lokal http://ollama:11434/v1, sonst die URL
    # von Groq, Gemini, Mistral.
    llm_base_url: str = ""

    # Die drei Geheimnisse. Leer heißt jeweils abgeschaltet, nicht offen -
    # keine Installation weiß, ob sie eine Entwicklungsinstallation ist.
    #
    # Verwaltung: Profile anlegen, Zugänge ausgeben und zurückziehen.
    auth_token: str = ""
    # Aufsicht: jeden Korpus einsehen, sichern, löschen.
    admin_token: str = ""
    # Zuschnitt (`api/zuschnitt.py`): Er überschreibt Aufnahmen und verwirft
    # Messwerte - das trägt der Sprecherzugang auf einem Telefon allein nicht.
    editor_key: str = ""

    # Welche Erkenner antreten, in der Reihenfolge der Anzeige
    # (`services/auswertung.py`); die Vorgabe teilt „lernen"
    # (`wortlaut/einstellungen.py`).
    auswertung_modelle: str = AUSWERTUNG_MODELLE

    @model_validator(mode="after")
    def _tokens_muessen_sich_unterscheiden(self) -> Einstellungen:
        """Ein Token für zwei Rollen machte still jeden Verwalter zur Aufsicht -
        also Abbruch beim Start."""
        if self.admin_token and self.admin_token == self.auth_token:
            raise ValueError(
                "WORTLAUT_ADMIN_TOKEN und WORTLAUT_AUTH_TOKEN müssen verschieden sein: "
                "Sonst wäre jeder Verwalter zugleich die Aufsicht."
            )
        return self

    @property
    def migrationsverzeichnis(self) -> Path:
        return Path(__file__).parent / "db" / "migrations"


@lru_cache
def einstellungen() -> Einstellungen:
    """Einmal lesen, überall dieselbe Instanz."""
    return Einstellungen()
