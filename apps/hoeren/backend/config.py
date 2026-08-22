"""Einstellungen aus der Umgebung — ein Ort, nirgends sonst `os.environ`.

Die Feldnamen entsprechen den Variablen mit dem Präfix `WORTLAUT_`,
`data_dir` also `WORTLAUT_DATA_DIR`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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

    @property
    def migrationsverzeichnis(self) -> Path:
        return Path(__file__).parent / "db" / "migrations"


@lru_cache
def einstellungen() -> Einstellungen:
    """Einmal lesen, überall dieselbe Instanz."""
    return Einstellungen()
