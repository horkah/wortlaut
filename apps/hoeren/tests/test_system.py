"""`GET /api/system` - für jeden gültigen Zugang, für niemanden sonst."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_ohne_zugang_keine_auskunft(klient_ohne_token: TestClient) -> None:
    assert klient_ohne_token.get("/api/system").status_code == 401


def test_der_sprecher_sieht_die_maschine(klient: TestClient, sprecher: str) -> None:
    antwort = klient.get("/api/system")
    assert antwort.status_code == 200, antwort.text
    daten = antwort.json()
    assert {"prozessor", "speicher", "karten", "ablagen"} <= daten.keys()
    assert daten["ablagen"][0]["name"] == "Daten"


def test_die_verwaltung_ebenso(verwalter: TestClient) -> None:
    assert verwalter.get("/api/system").status_code == 200
