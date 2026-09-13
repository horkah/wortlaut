"""Testaufbau für „schreiben".

Jeder Test bekommt ein eigenes Datenverzeichnis und einen frischen Zustand.
Drei Dinge sind ersetzt, alles andere ist echt - echte SQLite-Datei, echte
Endpunkte, echte WAV-Dateien:

* **ffmpeg** - die Umwandlung selbst ist in `packages/wortlaut/tests` geprüft.
* **Whisper** - sonst bräuchte jeder Testlauf ein Modell, eine GPU und Geduld.
  Der Ersatz liefert feste Abschnitte mit Zeitmarken, wie das echte auch.
* **der Weg zu „hören"** - `outbox.liefere_ein` wird aufgezeichnet statt
  gesendet; ob die Zustellung klappt, ist je Test einstellbar.

Nicht ersetzt ist der Zugang: Jeder Test legt einen echten Korpus mit einem
echten Sprecher an und ruft mit einem echten Zugang. Diese App leitet ihren
Sprecher daraus ab (`backend/deps.py`), und was abgeleitet wird, soll auch im
Test abgeleitet werden - ein untergeschobener Sprecher prüfte den Weg nicht,
auf dem er im Betrieb entsteht.
"""

from __future__ import annotations

import pathlib
import shutil
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import sqlite3

import pytest
from fastapi.testclient import TestClient
from wortlaut import audio, corpus, db
from wortlaut import zugang as zugangsdienst
from wortlaut.whisper import Abschnitt, Transkript

from apps.hoeren.backend import config as hoeren_config
from apps.schreiben.backend import deps
from apps.schreiben.backend.config import einstellungen
from apps.schreiben.backend.main import app
from apps.schreiben.backend.services import outbox

INTAKE_URL = "https://hoeren.example.org/api/korpus/intake"
SPRECHER = "spr_test"
NAME = "Testperson"

# Der Korpus gehört „hören"; „schreiben" liest ihn nur, um einen Zugang zu
# prüfen. Für den Test muss er trotzdem echt sein - also mit den Migrationen
# von „hören" angelegt und nicht mit einem nachgebauten Schema, das mit dem
# ersten Spaltenwechsel drüben auseinanderliefe.
HOEREN_MIGRATIONEN = pathlib.Path(hoeren_config.__file__).parent / "db" / "migrations"

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
    # Die Spitze der Datei, die zuletzt zu hören war. Sie belegte einmal, dass
    # vor dem Erkennen ausgesteuert wurde; die Aufbereitung ist weg
    # (`004_ohne_aussteuern.sql`), der Wert bleibt als Beleg dafür, dass das
    # Modell genau die aufgenommene Datei zu hören bekommt.
    gehoerte_spitze: int = 0

    def transkribiere(self, wav: Path, sprache: str = "de") -> Transkript:
        self.aufrufe += 1
        self.gehoerte_spitze = _spitze(wav)
        return Transkript(
            text=" ".join(a.text for a in self.abschnitte).strip(), abschnitte=self.abschnitte
        )


def _spitze(wav: Path) -> int:
    """Der lauteste Abtastwert einer WAV-Datei, als Betrag."""
    import array
    import wave

    with wave.open(str(wav), "rb") as datei:
        werte = array.array("h")
        werte.frombytes(datei.readframes(datei.getnframes()))
    return max(max(werte), -min(werte)) if werte else 0


@dataclass
class Testintake:
    """Nimmt entgegen, was an „hören" gegangen wäre - oder scheitert absichtlich."""

    lieferungen: list[dict] = field(default_factory=list)
    scheitert: bool = False

    def __call__(
        self,
        konfiguration,
        *,
        wav: Path,
        text: str,
        externe_id: str,
        sprecher_id: str,
        token: str,
    ) -> None:
        if self.scheitert:
            raise ConnectionError("hören ist nicht erreichbar")
        self.lieferungen.append(
            {
                "text": text,
                "externe_id": externe_id,
                "bytes": wav.read_bytes(),
                "sprecher_id": sprecher_id,
                "token": token,
            }
        )


@pytest.fixture
def datenverzeichnis(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def audioverzeichnis(datenverzeichnis: Path) -> Path:
    """Wo die WAV-Dateien der Abschnitte liegen - je Sprecher ein Ordner."""
    return datenverzeichnis / "diktate" / SPRECHER / "audio"


def lege_sprecher_an(datenverzeichnis: Path, sprecher_id: str = SPRECHER) -> str:
    """Einen Sprecher im Korpus anlegen und seinen Zugang zurückgeben.

    Dasselbe, was „hören" beim Anlegen eines Profils und beim Ausgeben eines
    Zugangs tut - hier ohne dessen App, damit die Tests dieser App keinen
    zweiten Server brauchen.
    """
    pfad = corpus.datenbank_pfad(datenverzeichnis, sprecher_id)
    db.wende_migrationen_an(pfad, HOEREN_MIGRATIONEN)
    neuer, hash_ = zugangsdienst.erzeuge(sprecher_id)
    with sqlite3.connect(pfad) as verbindung:
        verbindung.execute(
            "INSERT INTO speakers (id, name, sprache, basismodell, erstellt, zugang_hash)"
            " VALUES (?, ?, 'de', 'openai/whisper-small', '2026-01-01T00:00:00+00:00', ?)",
            (sprecher_id, NAME, hash_),
        )
    return neuer


@pytest.fixture
def sprecher() -> str:
    """Die Kennung des Testsprechers - dieselbe, die sein Zugang trägt."""
    return SPRECHER


@pytest.fixture
def zugang(datenverzeichnis: Path) -> str:
    """Der Zugang des Testsprechers - dasselbe Format wie im Betrieb."""
    return lege_sprecher_an(datenverzeichnis)


@pytest.fixture
def _umgebung(
    tmp_path: Path, datenverzeichnis: Path, monkeypatch: pytest.MonkeyPatch, wav_schreiben
) -> Iterator[None]:
    monkeypatch.setenv("WORTLAUT_DATA_DIR", str(datenverzeichnis))
    monkeypatch.setenv("WORTLAUT_MODELL_REF", "")
    monkeypatch.setenv("WORTLAUT_ASR_MODELL", "small")
    monkeypatch.setenv("WORTLAUT_INTAKE_URL", INTAKE_URL)
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
    """Der Ersatz für Whisper - die Abschnitte sind im Test veränderbar."""
    ersatz = Testtranskriptor()
    app.dependency_overrides[deps._transkriptor] = lambda: ersatz
    yield ersatz
    app.dependency_overrides.clear()


@pytest.fixture
def intake(monkeypatch: pytest.MonkeyPatch) -> Testintake:
    ersatz = Testintake()
    monkeypatch.setattr(outbox, "liefere_ein", ersatz)
    return ersatz


@pytest.fixture
def klient(whisper: Testtranskriptor, zugang: str) -> Iterator[TestClient]:
    """Der Zugang eines Sprechers - der Normalfall in allen Tests dieser App."""
    with TestClient(app, headers={"Authorization": f"Bearer {zugang}"}) as klient:
        yield klient


@pytest.fixture
def klient_ohne_zugang(whisper: Testtranskriptor) -> Iterator[TestClient]:
    """Ein Browser, in dem noch kein persönlicher Link geöffnet wurde."""
    with TestClient(app) as klient:
        yield klient


@pytest.fixture
def aufnahme() -> dict[str, tuple[str, bytes, str]]:
    """Der Inhalt ist gleichgültig - die Umwandlung ist ersetzt."""
    return {"audio": ("aufnahme.webm", b"opus-artige Bytes", "audio/webm")}


@pytest.fixture
def sitzung(klient: TestClient) -> str:
    antwort = klient.post("/schreiben/api/sessions")
    assert antwort.status_code == 201, antwort.text
    return antwort.json()["id"]


@pytest.fixture
def diktat(klient: TestClient, sitzung: str, aufnahme: dict) -> dict:
    """Eine Sitzung mit den drei Abschnitten aus `VORGABE`."""
    antwort = klient.post(f"/schreiben/api/sessions/{sitzung}/segments", files=aufnahme)
    assert antwort.status_code == 201, antwort.text
    return antwort.json()
