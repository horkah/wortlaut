"""Testaufbau für „hören".

Jeder Test bekommt ein eigenes Datenverzeichnis und einen frischen Zustand.
Zwei Dinge werden ersetzt:

* **ffmpeg** — die Umwandlung selbst ist in `packages/wortlaut/tests` geprüft;
  hier soll nicht jeder Endpunkt-Test ein externes Programm brauchen.
* **die zwischengespeicherten Engines und Einstellungen** — sie zeigen sonst
  auf das Datenverzeichnis des vorigen Tests.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import audio

from apps.hoeren.backend import deps
from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.main import app

TOKEN = "test-geheim"


@pytest.fixture
def _umgebung(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wav_schreiben) -> Iterator[None]:
    monkeypatch.setenv("WORTLAUT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WORTLAUT_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("WORTLAUT_LLM_PROVIDER", "")  # Textquelle „LLM" aus
    einstellungen.cache_clear()
    deps._engines.clear()

    # Statt ffmpeg: eine echte, gleichbleibende Aufnahme von vier Sekunden.
    vorlage = wav_schreiben(tmp_path / "vorlage.wav")
    monkeypatch.setattr(audio, "wandle_in_wav", lambda quelle, ziel: shutil.copy(vorlage, ziel))

    yield

    einstellungen.cache_clear()
    deps._engines.clear()


@pytest.fixture
def klient(_umgebung: None) -> Iterator[TestClient]:
    """Angemeldeter Zugriff — der Normalfall in allen Tests."""
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as klient:
        yield klient


@pytest.fixture
def klient_ohne_token(_umgebung: None) -> Iterator[TestClient]:
    with TestClient(app) as klient:
        yield klient


@pytest.fixture
def sprecher(klient: TestClient) -> str:
    """Ein angelegtes Sprecherprofil; gibt dessen Kennung zurück."""
    antwort = klient.post(
        "/api/speakers", json={"name": "Testperson", "basismodell": "openai/whisper-small"}
    )
    assert antwort.status_code == 201
    return antwort.json()["id"]


@pytest.fixture
def quelle(klient: TestClient, sprecher: str) -> str:
    """Eine hochgeladene Textquelle mit mehreren Sprecheinheiten."""
    text = (
        "Der Hund lief über die Wiese. Am Zaun blieb er stehen. "
        "Dann fing es an zu regnen, und alle gingen nach Hause.\n\n"
        "Am nächsten Morgen war die Wiese nass. Die Sonne kam trotzdem heraus."
    )
    antwort = klient.post(
        f"/api/sources/upload?sprecher={sprecher}",
        files={"datei": ("text.txt", text.encode("utf-8"), "text/plain")},
    )
    assert antwort.status_code == 201
    return antwort.json()["id"]


@pytest.fixture
def audio_datei() -> dict[str, tuple[str, bytes, str]]:
    """Der Inhalt ist gleichgültig — die Umwandlung ist ersetzt."""
    return {"audio": ("aufnahme.webm", b"opus-artige Bytes", "audio/webm")}
