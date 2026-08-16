"""Sprecherprofile und Token-Prüfung."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from wortlaut import corpus


class TestZugang:
    def test_ohne_token_kein_zugriff(self, klient_ohne_token: TestClient) -> None:
        assert klient_ohne_token.get("/api/speakers").status_code == 401

    def test_falscher_token_reicht_nicht(self, klient_ohne_token: TestClient) -> None:
        antwort = klient_ohne_token.get("/api/speakers", headers={"Authorization": "Bearer falsch"})
        assert antwort.status_code == 401

    def test_gesundheit_ist_offen(self, klient_ohne_token: TestClient) -> None:
        # Proxy und Compose müssen den Dienst ohne Token prüfen können.
        assert klient_ohne_token.get("/gesundheit").json() == {"status": "ok"}


class TestSprecher:
    def test_anlegen_erzeugt_ein_korpusverzeichnis(self, sprecher: str, tmp_path: Path) -> None:
        assert corpus.datenbank_pfad(tmp_path / "data", sprecher).is_file()

    def test_liste_zeigt_angelegte_profile(self, klient: TestClient, sprecher: str) -> None:
        liste = klient.get("/api/speakers").json()
        assert [person["id"] for person in liste] == [sprecher]
        assert liste[0]["name"] == "Testperson"

    def test_einzelabruf(self, klient: TestClient, sprecher: str) -> None:
        person = klient.get(f"/api/speakers/{sprecher}").json()
        assert person["basismodell"] == "openai/whisper-small"
        assert person["sprache"] == "de"  # Voreinstellung

    def test_unbekannter_sprecher_ist_ein_404(self, klient: TestClient) -> None:
        assert klient.get("/api/speakers/spr_gibtsnicht").status_code == 404
        assert klient.get("/api/progress?sprecher=spr_gibtsnicht").status_code == 404

    def test_name_darf_nicht_leer_sein(self, klient: TestClient) -> None:
        assert (
            klient.post("/api/speakers", json={"name": "", "basismodell": "x"}).status_code == 422
        )
