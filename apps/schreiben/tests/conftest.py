"""Testaufbau für „schreiben".

Jeder Test bekommt ein eigenes Datenverzeichnis und einen frischen Zustand.
Drei Dinge sind ersetzt, alles andere ist echt — echte SQLite-Datei, echte
Endpunkte, echte WAV-Dateien:

* **ffmpeg** — die Umwandlung selbst ist in `packages/wortlaut/tests` geprüft.
* **Whisper** — sonst bräuchte jeder Testlauf ein Modell, eine GPU und Geduld.
  Der Ersatz liefert feste Abschnitte mit Zeitmarken, wie das echte auch.
* **der Weg zu „hören"** — `outbox.liefere_ein` wird aufgezeichnet statt
  gesendet; ob die Zustellung klappt, ist je Test einstellbar.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import audio
from wortlaut.whisper import Abschnitt, Transkript

from apps.schreiben.backend import deps
from apps.schreiben.backend.config import einstellungen
from apps.schreiben.backend.main import app
from apps.schreiben.backend.services import outbox

INTAKE_URL = "https://hoeren.example.org/api/korpus/intake"
SPRECHER = "spr_test"

# Was der Ersatz für Whisper aus jedem Diktat macht: drei Abschnitte mit
# Zeitmarken, wie sie das echte Modell liefert.
VORGABE = [
    Abschnitt(start_s=0.0, ende_s=2.0, text="Ich möchte einen Kaffee."),
    Abschnitt(start_s=2.0, ende_s=4.0, text="Mit wenig Milch."),
    Abschnitt(start_s=4.0, ende_s=6.0, text="Und ein Stück Kuchen."),
]


@dataclass
class Testtranskriptor:
    """Ein Transkriptor, der sagt, was der Test ihm vorgibt."""

    abschnitte: list[Abschnitt] = field(default_factory=lambda: list(VORGABE))
    aufrufe: int = 0

    def transkribiere(self, wav: Path, sprache: str = "de") -> Transkript:
        self.aufrufe += 1
        return Transkript(
            text=" ".join(a.text for a in self.abschnitte).strip(), abschnitte=self.abschnitte
        )


@dataclass
class Testintake:
    """Nimmt entgegen, was an „hören" gegangen wäre — oder scheitert absichtlich."""

    lieferungen: list[dict] = field(default_factory=list)
    scheitert: bool = False

    def __call__(self, konfiguration, *, wav: Path, text: str, externe_id: str) -> None:
        if self.scheitert:
            raise ConnectionError("hören ist nicht erreichbar")
        self.lieferungen.append({"text": text, "externe_id": externe_id, "bytes": wav.read_bytes()})


@pytest.fixture
def datenverzeichnis(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def audioverzeichnis(datenverzeichnis: Path) -> Path:
    """Wo die WAV-Dateien der Abschnitte liegen — je Sprecher ein Ordner."""
    return datenverzeichnis / "diktate" / SPRECHER / "audio"


@pytest.fixture
def _umgebung(
    tmp_path: Path, datenverzeichnis: Path, monkeypatch: pytest.MonkeyPatch, wav_schreiben
) -> Iterator[None]:
    monkeypatch.setenv("WORTLAUT_DATA_DIR", str(datenverzeichnis))
    monkeypatch.setenv("WORTLAUT_SPRECHER_ID", SPRECHER)
    monkeypatch.setenv("WORTLAUT_MODELL_REF", "")
    monkeypatch.setenv("WORTLAUT_ASR_MODELL", "tiny")
    monkeypatch.setenv("WORTLAUT_INTAKE_URL", INTAKE_URL)
    monkeypatch.setenv("WORTLAUT_INTAKE_TOKEN", "")
    einstellungen.cache_clear()
    deps.zwischenspeicher_leeren()

    # Statt ffmpeg: eine echte Aufnahme, lang genug für alle Zeitmarken oben.
    vorlage = wav_schreiben(tmp_path / "vorlage.wav", sekunden=8.0)
    monkeypatch.setattr(audio, "wandle_in_wav", lambda quelle, ziel: shutil.copy(vorlage, ziel))

    yield

    einstellungen.cache_clear()
    deps.zwischenspeicher_leeren()


@pytest.fixture
def whisper(_umgebung: None) -> Iterator[Testtranskriptor]:
    """Der Ersatz für Whisper — die Abschnitte sind im Test veränderbar."""
    ersatz = Testtranskriptor()
    app.dependency_overrides[deps.transkriptor] = lambda: ersatz
    yield ersatz
    app.dependency_overrides.clear()


@pytest.fixture
def intake(monkeypatch: pytest.MonkeyPatch) -> Testintake:
    ersatz = Testintake()
    monkeypatch.setattr(outbox, "liefere_ein", ersatz)
    return ersatz


@pytest.fixture
def klient(whisper: Testtranskriptor) -> Iterator[TestClient]:
    with TestClient(app) as klient:
        yield klient


@pytest.fixture
def aufnahme() -> dict[str, tuple[str, bytes, str]]:
    """Der Inhalt ist gleichgültig — die Umwandlung ist ersetzt."""
    return {"audio": ("aufnahme.webm", b"opus-artige Bytes", "audio/webm")}


@pytest.fixture
def sitzung(klient: TestClient) -> str:
    antwort = klient.post("/api/sessions")
    assert antwort.status_code == 201, antwort.text
    return antwort.json()["id"]


@pytest.fixture
def diktat(klient: TestClient, sitzung: str, aufnahme: dict) -> dict:
    """Eine Sitzung mit den drei Abschnitten aus `VORGABE`."""
    antwort = klient.post(f"/api/sessions/{sitzung}/segments", files=aufnahme)
    assert antwort.status_code == 201, antwort.text
    return antwort.json()
