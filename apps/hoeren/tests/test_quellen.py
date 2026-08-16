"""Textquellen: Upload, LLM-Schalter, Reihenfolge der entstehenden Vorlagen."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class TestUpload:
    def test_erzeugt_sprecheinheiten(self, klient: TestClient, sprecher: str, quelle: str) -> None:
        liste = klient.get(f"/api/sources?sprecher={sprecher}").json()
        assert len(liste) == 1
        assert liste[0]["art"] == "upload"
        assert liste[0]["einheiten"] > 1

    def test_zweite_quelle_haengt_hinten_an(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        vorher = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()

        klient.post(
            f"/api/sources/upload?sprecher={sprecher}",
            files={"datei": ("mehr.txt", b"Ein ganz neuer Satz kommt hinzu.", "text/plain")},
        )

        # Die Warteschlange arbeitet weiter vorne ab, statt vorzuspringen.
        danach = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        assert danach["aktuell"]["id"] == vorher["aktuell"]["id"]
        assert danach["gesamt"] > vorher["gesamt"]

    def test_lehnt_unbekanntes_format_ab(self, klient: TestClient, sprecher: str) -> None:
        antwort = klient.post(
            f"/api/sources/upload?sprecher={sprecher}",
            files={"datei": ("lied.mp3", b"...", "audio/mpeg")},
        )
        assert antwort.status_code == 400

    def test_lehnt_leeren_text_ab(self, klient: TestClient, sprecher: str) -> None:
        antwort = klient.post(
            f"/api/sources/upload?sprecher={sprecher}",
            files={"datei": ("leer.txt", b"   \n  ", "text/plain")},
        )
        assert antwort.status_code == 400


class TestLLM:
    def test_ohne_anbieter_klare_ansage(self, klient: TestClient, sprecher: str) -> None:
        # WORTLAUT_LLM_PROVIDER ist im Test leer: die Quelle ist abgeschaltet.
        antwort = klient.post(
            f"/api/sources/llm?sprecher={sprecher}",
            json={"thema": "Einkaufen", "altersspanne": "Erwachsene", "umfang": 200},
        )
        assert antwort.status_code == 400
        assert "WORTLAUT_LLM_PROVIDER" in antwort.json()["detail"]

    def test_erzeugt_vorlagen_aus_dem_gelieferten_text(
        self, klient: TestClient, sprecher: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Der Anbieter selbst wird nicht angerufen: geprüft wird der Weg vom
        # gelieferten Text zu den Vorlagen.
        from apps.hoeren.backend.api import sources

        monkeypatch.setattr(
            sources.llm,
            "erzeuge_text",
            lambda *_, **__: "Auf dem Markt gibt es Obst. Der Stand nebenan verkauft Blumen.",
        )

        antwort = klient.post(
            f"/api/sources/llm?sprecher={sprecher}",
            json={"thema": "Wochenmarkt", "altersspanne": "8-12", "umfang": 120},
        )

        assert antwort.status_code == 201
        assert antwort.json()["art"] == "llm"
        assert antwort.json()["titel"] == "Wochenmarkt"
        assert antwort.json()["einheiten"] >= 1
