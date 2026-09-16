"""Alle drei Apps in einem Prozess (`apps/gesamt.py`).

Geprüft wird das, was der Verteiler versprechen muss: Jede Anfrage landet bei
der richtigen App, und die Zugangsregeln bleiben dabei die der jeweiligen App.
Ginge das beim Zusammenlegen verloren, stünde der Korpus offen im Netz.

Alle drei hängen hinter dem Zugang eines Sprechers, und es ist derselbe: Ein
Mensch, ein Link, drei Apps. Genau das steht hier geprüft - der Zugang, den
„hören" ausgibt, öffnet ohne weiteres Zutun auch „lernen" und „schreiben".
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.gesamt import _zustaendig, app
from apps.hoeren.backend import deps as hoeren_deps
from apps.hoeren.backend.config import einstellungen as hoeren_einstellungen
from apps.lernen.backend import deps as lernen_deps
from apps.lernen.backend.config import einstellungen as lernen_einstellungen
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
    _leeren()

    with TestClient(app) as klient:
        yield klient

    _leeren()


def _leeren() -> None:
    for leeren in (
        hoeren_einstellungen.cache_clear,
        lernen_einstellungen.cache_clear,
        schreiben_einstellungen.cache_clear,
    ):
        leeren()
    hoeren_deps._engines.clear()
    lernen_deps.vergiss_engines()
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

    def test_eine_auskunft_darueber_wer_ruft(self, klient: TestClient, zugang: str) -> None:
        """Wer dieser Browser ist, beantwortet allein „hören" - für alle drei Apps.

        Dass derselbe Zugang überall gilt, prüfen die beiden Tests daneben an
        den Wegen, die die Apps wirklich haben. Hier geht es um die *Auskunft*
        darüber: Sie liegt unter `/api/zugang`, also auf der Wurzel der
        gemeinsamen Domain, und ist damit aus jeder App erreichbar
        (`packages/ui/wer.ts`).

        „schreiben" hatte dafür einmal eine eigene. Sie war eine zweite
        Wahrheit über denselben Menschen: Ihre API lässt mit gutem Grund nur
        Sprecherzugänge durch, also wies sie einen gültigen Verwalter- oder
        Aufsichtstoken ab, während dasselbe Feld in „hören" ihn annahm.
        Deshalb steht hier beides nebeneinander - die eine Stelle kennt beide
        Arten.
        """
        sprechend = klient.get(
            "/api/zugang", headers={"Authorization": f"Bearer {zugang}"}
        ).json()
        assert sprechend["art"] == "sprecher"
        assert sprechend["name"] == "Testperson"

        verwaltend = klient.get(
            "/api/zugang", headers={"Authorization": f"Bearer {TOKEN}"}
        ).json()
        assert verwaltend["art"] == "verwaltung"

    def test_unter_dem_pfad_antwortet_lernen(self, klient: TestClient, zugang: str) -> None:
        # Derselbe Zugang, dritte App. Die Aufteilung ist leer - es wurde noch
        # nichts aufgenommen -, aber sie antwortet, und das ist der Punkt.
        antwort = klient.get(
            "/lernen/api/aufteilung", headers={"Authorization": f"Bearer {zugang}"}
        )
        assert antwort.status_code == 200, antwort.text
        assert antwort.json()["aufnahmen"] == 0

    def test_lernen_bleibt_hinter_dem_zugang(self, klient: TestClient) -> None:
        # Ein Modell gehört einem Menschen - ohne dessen Zugang gibt es hier
        # nichts zu sehen, auch nicht mit dem Verwaltertoken.
        assert klient.get("/lernen/api/aufteilung").status_code == 401
        assert (
            klient.get(
                "/lernen/api/aufteilung", headers={"Authorization": f"Bearer {TOKEN}"}
            ).status_code
            == 401
        )

    def test_auf_der_wurzel_antwortet_hoeren(self, klient: TestClient) -> None:
        assert klient.get("/api/speakers", headers={"Authorization": f"Bearer {TOKEN}"}).json() == []

    def test_hoeren_bleibt_hinter_dem_token(self, klient: TestClient) -> None:
        # Der Korpus darf durch das Zusammenlegen nicht offen stehen.
        assert klient.get("/api/speakers").status_code == 401

    def test_gesundheit_beantwortet_hoeren(self, klient: TestClient) -> None:
        # Nur eine Wurzel, also nur ein Prüfpunkt - der von „hören".
        assert klient.get("/gesundheit").json() == {"status": "ok"}


class TestPfadgrenze:
    """Wer bekommt welchen Pfad - die eine Entscheidung des Verteilers."""

    @pytest.mark.parametrize(
        ("pfad", "titel"),
        [
            ("/schreiben", "schreiben"),
            ("/schreiben/", "schreiben"),
            ("/schreiben/api/model", "schreiben"),
            ("/lernen", "lernen"),
            ("/lernen/", "lernen"),
            ("/lernen/api/laeufe", "lernen"),
            ("/", "hören"),
            ("/api/speakers", "hören"),
            ("/gesundheit", "hören"),
            # Die Gleichheit steht mit Absicht neben dem Präfix: Ohne sie
            # landete ein Tippfehler in einer fremden Oberfläche statt in
            # einem 404.
            ("/schreibendes", "hören"),
            ("/lernendes", "hören"),
        ],
    )
    def test_landet_bei_der_richtigen_app(self, pfad: str, titel: str) -> None:
        assert _zustaendig(pfad).title == f"wortlaut · {titel}"
