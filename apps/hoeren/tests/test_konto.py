"""Ein Sprecher sieht sich selbst — dieselben Zahlen wie die Aufsicht, aber nur die eigenen.

`/api/konto/…` nennt keine Kennung in der Adresse: Sie kommt aus dem
vorgelegten Zugang, genau wie bei jedem anderen Weg dieser App. Ein zweiter
Sprecher, der denselben Weg mit seinem eigenen Zugang ruft, sieht darum
zwangsläufig nur seine eigenen Daten — das prüft `test_sieht_nur_die_eigenen_aufnahmen`.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient


class TestZugriff:
    def test_ohne_zugang_kein_zugriff(self, klient_ohne_token: TestClient) -> None:
        assert klient_ohne_token.get("/api/konto").status_code == 401

    def test_verwaltung_kommt_nicht_heran(self, verwalter: TestClient) -> None:
        # Die Verwaltung führt keinen eigenen Sprecher — sie legt Profile an.
        assert verwalter.get("/api/konto").status_code == 401

    def test_aufsicht_kommt_nicht_heran(self, aufsicht: TestClient) -> None:
        # Die Aufsicht hat ebenfalls keinen eigenen Sprecher; sie sieht über
        # `/api/admin/…`, nicht über den eigenen Weg eines Sprechers.
        assert aufsicht.get("/api/konto").status_code == 401


class TestEigeneDaten:
    def test_zeigt_profil_und_quellen(self, klient: TestClient, quelle: str) -> None:
        konto = klient.get("/api/konto").json()
        assert konto["sprecher"]["name"] == "Testperson"
        assert [q["art"] for q in konto["quellen"]] == ["upload"]

    def test_sieht_nur_die_eigenen_aufnahmen(
        self,
        klient_fuer: Callable[[str], TestClient],
        verwalter: TestClient,
        klient: TestClient,
        quelle: str,
        audio_datei: dict,
    ) -> None:
        naechste = klient.get("/api/prompts/next").json()["aktuell"]
        antwort = klient.post(
            "/api/recordings",
            files=audio_datei,
            data={"prompt_id": naechste["id"], "modus": "gelesen"},
        )
        assert antwort.status_code == 201

        zweiter = verwalter.post(
            "/api/speakers", json={"name": "Andere", "basismodell": "openai/whisper-small"}
        ).json()["id"]
        with klient_fuer(zweiter) as andere:
            seite = andere.get("/api/konto/recordings").json()
            assert seite["gesamt"] == 0

        eigene = klient.get("/api/konto/recordings").json()
        assert eigene["gesamt"] == 1
        assert eigene["aufnahmen"][0]["text"]

    def test_sitzungen_werden_geseitet(self, klient: TestClient) -> None:
        for _ in range(3):
            assert klient.post("/api/sessions").status_code == 201

        erste_seite = klient.get("/api/konto/sessions?ab=0&anzahl=2").json()
        assert erste_seite["gesamt"] == 3
        assert len(erste_seite["sitzungen"]) == 2

    def test_anhoeren_und_verwerfen_bleiben_bei_recordings(
        self, klient: TestClient, quelle: str, audio_datei: dict
    ) -> None:
        # Kein eigener Weg unter `/api/konto/…` dafür — die bestehenden,
        # ebenfalls sprecherbezogenen Wege genügen (siehe `konto.py`).
        naechste = klient.get("/api/prompts/next").json()["aktuell"]
        aufnahme = klient.post(
            "/api/recordings",
            files=audio_datei,
            data={"prompt_id": naechste["id"], "modus": "gelesen"},
        ).json()

        eigene = klient.get("/api/konto/recordings").json()["aufnahmen"][0]
        assert eigene["id"] == aufnahme["id"]
        assert klient.get(f"/api/recordings/{aufnahme['id']}/audio").status_code == 200

        assert klient.delete(f"/api/recordings/{aufnahme['id']}").status_code == 204
        nach_dem_verwerfen = klient.get("/api/konto/recordings").json()["aufnahmen"][0]
        assert nach_dem_verwerfen["status"] == "verworfen"
