"""Beide Apps in einem Prozess (`apps/gesamt.py`).

Geprüft wird das, was der Verteiler versprechen muss: Jede Anfrage landet bei
der richtigen App, und die Zugangsregeln bleiben dabei die der jeweiligen App.
Ginge das beim Zusammenlegen verloren, stünde der Korpus offen im Netz.

Beide Apps hängen inzwischen hinter dem Zugang eines Sprechers, und es ist
derselbe: Ein Mensch, ein Link, beide Apps. Genau das steht hier geprüft - der
Zugang, den „hören" ausgibt, öffnet ohne weiteres Zutun auch „schreiben".
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.gesamt import _gehoert_zu_schreiben, app
from apps.hoeren.backend import deps as hoeren_deps
from apps.hoeren.backend.config import einstellungen as hoeren_einstellungen
from apps.schreiben.backend import deps as schreiben_deps
from apps.schreiben.backend.config import einstellungen as schreiben_einstellungen

TOKEN = "test-geheim"


@pytest.fixture
def klient(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("WORTLAUT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WORTLAUT_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("WORTLAUT_LLM_PROVIDER", "")
    monkeypatch.setenv("WORTLAUT_MODELL_REF", "")
    monkeypatch.setenv("WORTLAUT_INTAKE_URL", "")
    for leeren in (hoeren_einstellungen.cache_clear, schreiben_einstellungen.cache_clear):
        leeren()
    hoeren_deps._engines.clear()
    schreiben_deps.zwischenspeicher_leeren()

    with TestClient(app) as klient:
        yield klient

    for leeren in (hoeren_einstellungen.cache_clear, schreiben_einstellungen.cache_clear):
        leeren()
    hoeren_deps._engines.clear()
    schreiben_deps.zwischenspeicher_leeren()


@pytest.fixture
def zugang(klient: TestClient) -> str:
    """Ein Sprecher, angelegt in „hören", mit frisch ausgegebenem Zugang."""
    kopf = {"Authorization": f"Bearer {TOKEN}"}
    sprecher = klient.post(
        "/api/speakers", json={"name": "Testperson", "basismodell": "openai/whisper-small"},
        headers=kopf,
    )
    assert sprecher.status_code == 201, sprecher.text
    ausgegeben = klient.post(f"/api/speakers/{sprecher.json()['id']}/zugang", headers=kopf)
    assert ausgegeben.status_code == 201, ausgegeben.text
    return ausgegeben.json()["zugang"]


class TestVerteilung:
    def test_unter_dem_pfad_antwortet_schreiben(self, klient: TestClient, zugang: str) -> None:
        # Derselbe Zugang wie drüben - die Kennung der Antwort fängt mit `dik_`
        # an, das kann nur aus dieser App kommen.
        antwort = klient.post(
            "/schreiben/api/sessions", headers={"Authorization": f"Bearer {zugang}"}
        )
        assert antwort.status_code == 201, antwort.text
        assert antwort.json()["id"].startswith("dik_")

    def test_schreiben_bleibt_hinter_dem_zugang(self, klient: TestClient) -> None:
        # Was hier entsteht, gehört einem Menschen und läuft auf seinem Modell.
        assert klient.post("/schreiben/api/sessions").status_code == 401

    def test_ein_zugang_oeffnet_beide_apps(self, klient: TestClient, zugang: str) -> None:
        # Der eigentliche Gewinn des gemeinsamen Zugangs: Wer seinen Link
        # einmal geöffnet hat, ist in beiden Apps derselbe.
        kopf = {"Authorization": f"Bearer {zugang}"}
        hier = klient.get("/schreiben/api/zugang", headers=kopf).json()
        drueben = klient.get("/api/zugang", headers=kopf).json()

        assert hier["sprecher_id"] == drueben["sprecher_id"]
        assert hier["name"] == drueben["name"] == "Testperson"

    def test_auf_der_wurzel_antwortet_hoeren(self, klient: TestClient) -> None:
        assert klient.get("/api/speakers", headers={"Authorization": f"Bearer {TOKEN}"}).json() == []

    def test_hoeren_bleibt_hinter_dem_token(self, klient: TestClient) -> None:
        # Der Korpus darf durch das Zusammenlegen nicht offen stehen.
        assert klient.get("/api/speakers").status_code == 401

    def test_gesundheit_beantwortet_hoeren(self, klient: TestClient) -> None:
        # Nur eine Wurzel, also nur ein Prüfpunkt - der von „hören".
        assert klient.get("/gesundheit").json() == {"status": "ok"}


class TestPfadgrenze:
    @pytest.mark.parametrize("pfad", ["/schreiben", "/schreiben/", "/schreiben/api/model"])
    def test_gehoert_dazu(self, pfad: str) -> None:
        assert _gehoert_zu_schreiben(pfad)

    @pytest.mark.parametrize("pfad", ["/", "/api/speakers", "/schreibendes", "/gesundheit"])
    def test_gehoert_nicht_dazu(self, pfad: str) -> None:
        assert not _gehoert_zu_schreiben(pfad)
