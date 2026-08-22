"""Testaufbau für „hören".

Es gibt drei Klienten, weil es drei Arten von Zugang gibt (siehe
`backend/deps.py`): `verwalter` legt Profile an und gibt Zugänge aus, `klient`
ist der Zugang **eines** Sprechers und damit der Weg zu dessen Daten, und
`aufsicht` sieht über alle Korpora hinweg.

Die Aufrufe hängen `?sprecher=…` weiterhin an — nicht mehr, um den Sprecher zu
wählen, sondern damit die Behauptung gegen die abgeleitete Kennung geprüft
wird.

Jeder Test bekommt ein eigenes Datenverzeichnis und einen frischen Zustand.
Zwei Dinge werden ersetzt:

* **ffmpeg** — die Umwandlung selbst ist in `packages/wortlaut/tests` geprüft;
  hier soll nicht jeder Endpunkt-Test ein externes Programm brauchen.
* **die zwischengespeicherten Engines und Einstellungen** — sie zeigen sonst
  auf das Datenverzeichnis des vorigen Tests.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import audio

from apps.hoeren.backend import deps
from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.main import app

TOKEN = "test-geheim"
ADMIN_TOKEN = "test-aufsicht"


@pytest.fixture
def _umgebung(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wav_schreiben) -> Iterator[None]:
    monkeypatch.setenv("WORTLAUT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WORTLAUT_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("WORTLAUT_ADMIN_TOKEN", ADMIN_TOKEN)
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
def verwalter(_umgebung: None) -> Iterator[TestClient]:
    """Die Verwaltung: Profile anlegen, Zugänge ausgeben und zurückziehen."""
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as klient:
        yield klient


@pytest.fixture
def aufsicht(_umgebung: None) -> Iterator[TestClient]:
    """Die Aufsicht: über alle Korpora sehen, sichern, umbenennen, löschen."""
    with TestClient(app, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}) as klient:
        yield klient


@pytest.fixture
def klient_ohne_token(_umgebung: None) -> Iterator[TestClient]:
    with TestClient(app) as klient:
        yield klient


@pytest.fixture
def sprecher(verwalter: TestClient) -> str:
    """Ein angelegtes Sprecherprofil; gibt dessen Kennung zurück."""
    antwort = verwalter.post(
        "/api/speakers", json={"name": "Testperson", "basismodell": "openai/whisper-small"}
    )
    assert antwort.status_code == 201
    return antwort.json()["id"]


@pytest.fixture
def zugang_ausgeben(verwalter: TestClient) -> Callable[[str], str]:
    """Einen Zugang ausgeben. Im Klartext gibt es ihn nur an dieser Stelle."""

    def gib(sprecher_id: str) -> str:
        antwort = verwalter.post(f"/api/speakers/{sprecher_id}/zugang")
        assert antwort.status_code == 201
        return antwort.json()["zugang"]

    return gib


@pytest.fixture
def klient_fuer(zugang_ausgeben: Callable[[str], str]) -> Callable[[str], TestClient]:
    """Ein Klient mit frischem Zugang für einen bestimmten Sprecher."""

    def baue(sprecher_id: str) -> TestClient:
        return TestClient(app, headers={"Authorization": f"Bearer {zugang_ausgeben(sprecher_id)}"})

    return baue


@pytest.fixture
def klient(klient_fuer: Callable[[str], TestClient], sprecher: str) -> Iterator[TestClient]:
    """Der Zugang eines Sprechers — der Normalfall in allen Datentests."""
    with klient_fuer(sprecher) as klient:
        yield klient


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
