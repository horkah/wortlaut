"""Einstellungen aus der Umgebung — ein Ort, nirgends sonst `os.environ`.

Die Feldnamen entsprechen den Variablen mit dem Präfix `WORTLAUT_`,
`data_dir` also `WORTLAUT_DATA_DIR`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Einstellungen(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORTLAUT_", env_file=".env", extra="ignore")

    # gemeinsam
    data_dir: Path = Path("./data")
    storage: str = "local"

    # Textquelle „LLM". Leer heißt: abgeschaltet, es bleibt der Textupload.
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model: str = "claude-opus-4-8"
    # Nur für OpenAI-kompatible Anbieter (anbieter="openai"): wohin die Anfrage
    # geht. Lokal etwa http://ollama:11434/v1, sonst die URL von Groq, Gemini,
    # Mistral … Bei anbieter="anthropic" ohne Bedeutung.
    llm_base_url: str = ""

    # Leer heißt: keine Authentifizierung. Nur für die lokale Entwicklung.
    auth_token: str = ""

    # Die Aufsicht: sieht jeden Korpus, sichert ihn und löscht daraus. Leer
    # heißt hier — anders als oben — **abgeschaltet** und nicht „offen": Ein
    # Zugang, der löschen darf, darf nicht versehentlich offenstehen.
    admin_token: str = ""

    @model_validator(mode="after")
    def _tokens_muessen_sich_unterscheiden(self) -> Einstellungen:
        """Ein Token, zwei Rollen wäre eine stille Rechteausweitung.

        Wer beide Werte gleich setzt — etwa beim Kopieren der `.env` —, macht
        jeden Verwalter unbemerkt zur Aufsicht: Der Server prüft die Aufsicht
        zuerst und käme gar nicht mehr zur Verwaltung. Das fällt niemandem auf,
        weil nichts fehlschlägt; es geht bloß plötzlich mehr. Also lieber
        gleich beim Start abbrechen als später rätseln.
        """
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
