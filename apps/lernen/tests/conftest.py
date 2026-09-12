"""Testaufbau für „lernen".

Diese App hat keine eigenen Aufnahmen - sie liest den Korpus, den „hören"
schreibt. Der Aufbau besteht deshalb aus zwei Klienten: einem für „hören", der
Sprecher, Texte und Aufnahmen anlegt, und einem für „lernen", der dieselbe
Kennung vorlegt.

Dass beide denselben Zugang benutzen, ist kein Testkniff, sondern der
Betriebsfall: Ein Mensch, ein Link, drei Apps.

Gerechnet wird hier nichts. Der Trainer läuft in einem eigenen Container
(`apps/lernen/training/`); geprüft wird der Weg drumherum - wie zugeteilt wird,
was ein Auftrag hinterlässt und was die Oberfläche daraus liest.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import audio

from apps.hoeren.backend import deps as hoeren_deps
from apps.hoeren.backend.config import einstellungen as hoeren_einstellungen
from apps.hoeren.backend.main import app as hoeren_app
from apps.lernen.backend import deps as lernen_deps
from apps.lernen.backend.config import einstellungen as lernen_einstellungen
from apps.lernen.backend.main import app as lernen_app

TOKEN = "test-geheim"
# Der Trainerschlüssel. Er steht hier und nicht in den einzelnen Tests, weil
# ihn jeder Auftrag braucht - geprüft wird er dort, wo es um ihn geht
# (`test_trainerschluessel.py`).
TRAINERSCHLUESSEL = "test-trainer"


@pytest.fixture
def _umgebung(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wav_schreiben) -> Iterator[None]:
    monkeypatch.setenv("WORTLAUT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WORTLAUT_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("WORTLAUT_ADMIN_TOKEN", "test-aufsicht")
    monkeypatch.setenv("WORTLAUT_TRAINER_KEY", TRAINERSCHLUESSEL)
    monkeypatch.setenv("WORTLAUT_LLM_PROVIDER", "")
    for leeren in (hoeren_einstellungen, lernen_einstellungen):
        leeren.cache_clear()
    hoeren_deps._engines.clear()
    lernen_deps.vergiss_engines()

    vorlage = wav_schreiben(tmp_path / "vorlage.wav")
    monkeypatch.setattr(audio, "wandle_in_wav", lambda quelle, ziel: shutil.copy(vorlage, ziel))

    yield

    for leeren in (hoeren_einstellungen, lernen_einstellungen):
        leeren.cache_clear()
    hoeren_deps._engines.clear()
    lernen_deps.vergiss_engines()


@pytest.fixture
def datenverzeichnis(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def verwalter(_umgebung: None) -> Iterator[TestClient]:
    with TestClient(hoeren_app, headers={"Authorization": f"Bearer {TOKEN}"}) as klient:
        yield klient


@pytest.fixture
def sprecher(verwalter: TestClient) -> str:
    antwort = verwalter.post(
        "/api/speakers", json={"name": "Testperson", "basismodell": "openai/whisper-small"}
    )
    assert antwort.status_code == 201
    return antwort.json()["id"]


@pytest.fixture
def zugang(verwalter: TestClient, sprecher: str) -> str:
    antwort = verwalter.post(f"/api/speakers/{sprecher}/zugang")
    assert antwort.status_code == 201
    return antwort.json()["zugang"]


@pytest.fixture
def hoeren(zugang: str) -> Iterator[TestClient]:
    """Der Klient, der aufnimmt - dieselbe App, die den Korpus schreibt."""
    with TestClient(hoeren_app, headers={"Authorization": f"Bearer {zugang}"}) as klient:
        yield klient


@pytest.fixture
def klient(zugang: str) -> Iterator[TestClient]:
    """Der Klient von „lernen", mit demselben Zugang - und mit dem Trainerschlüssel.

    Der Schlüssel hängt an jeder Anfrage, obwohl ihn nur eine braucht. Das ist
    der bequeme Weg und der richtige: Er ist die Erlaubnis eines Menschen, nicht
    das Merkmal eines Aufrufs, und ein Server, der ihn dort liest, wo er nichts
    zu suchen hat, fiele in `test_trainerschluessel.py` auf.
    """
    with TestClient(
        lernen_app,
        headers={"Authorization": f"Bearer {zugang}", "X-Trainer-Key": TRAINERSCHLUESSEL},
    ) as klient:
        yield klient


@pytest.fixture
def quelle(hoeren: TestClient) -> str:
    """Genug Text für ein paar Dutzend Sprecheinheiten."""
    satz = (
        "Der Hund lief über die Wiese. Am Zaun blieb er stehen. "
        "Dann fing es an zu regnen. Alle gingen nach Hause. "
        "Am Morgen war die Wiese nass. Die Sonne kam trotzdem heraus. "
    )
    antwort = hoeren.post(
        "/api/sources/upload",
        files={"datei": ("text.txt", (satz * 8).encode("utf-8"), "text/plain")},
    )
    assert antwort.status_code == 201
    return antwort.json()["id"]


@pytest.fixture
def sprich(hoeren: TestClient) -> Callable[[int], list[str]]:
    """So viele Aufnahmen machen, wie gebraucht werden; gibt deren Kennungen zurück."""

    def einige(anzahl: int) -> list[str]:
        kennungen = []
        for _ in range(anzahl):
            naechste = hoeren.get("/api/prompts/next").json()["aktuell"]
            assert naechste is not None, "Der Textvorrat ist aufgebraucht."
            antwort = hoeren.post(
                "/api/recordings",
                files={"audio": ("aufnahme.webm", b"opus-artige Bytes", "audio/webm")},
                data={"prompt_id": naechste["id"], "modus": "gelesen"},
            )
            assert antwort.status_code == 201, antwort.text
            kennungen.append(antwort.json()["id"])
        return kennungen

    return einige
