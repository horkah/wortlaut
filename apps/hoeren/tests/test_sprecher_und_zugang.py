"""Sprecherprofile, Verwaltung und der Zugang, der zugleich die Kennung ist.

Der Kern steht in `TestBindung`: Der Server leitet den Sprecher aus dem
vorgelegten Zugang ab. Ein `?sprecher=…`, das etwas anderes behauptet, wird
laut abgewiesen, statt still ins falsche Verzeichnis zu schreiben.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from wortlaut import corpus, sprachen

from apps.hoeren.backend import deps
from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.main import app


class TestVerwaltung:
    def test_ohne_token_kein_zugriff(self, klient_ohne_token: TestClient) -> None:
        assert klient_ohne_token.get("/api/speakers").status_code == 401

    def test_falscher_token_reicht_nicht(self, klient_ohne_token: TestClient) -> None:
        antwort = klient_ohne_token.get("/api/speakers", headers={"Authorization": "Bearer falsch"})
        assert antwort.status_code == 401

    def test_ohne_gesetzten_token_ist_die_verwaltung_zu(
        self, _umgebung: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # „Leer" hieß hier einmal „offen", als Bequemlichkeit für die
        # Entwicklung. Nur weiß keine Installation, ob sie Entwicklung ist:
        # Wer den Token beim Aufsetzen vergisst, stellte damit eine Seite ins
        # Netz, auf der jeder Profile anlegt und ausgegebene Zugänge
        # zurückzieht. Ein vergessener Token ist jetzt die zugesperrte, nicht
        # die großzügigste Einstellung.
        monkeypatch.setenv("WORTLAUT_AUTH_TOKEN", "")
        einstellungen.cache_clear()
        with TestClient(app) as offen:
            assert offen.get("/api/speakers").status_code == 401
            assert offen.post("/api/speakers", json={"name": "Wer auch immer"}).status_code == 401
            assert offen.delete("/api/speakers/spr_egal/zugang").status_code == 401

    def test_ohne_gesetzten_token_bleibt_der_sprecher_drin(
        self, _umgebung: None, monkeypatch: pytest.MonkeyPatch, verwalter: TestClient
    ) -> None:
        # Die zugesperrte Verwaltung sperrt niemanden aus, der schon einen
        # Zugang hat: Aufnehmen hängt am Sprecherzugang und nie am
        # Verwaltertoken.
        angelegt = verwalter.post("/api/speakers", json={"name": "Testperson"}).json()["id"]
        zugang = verwalter.post(f"/api/speakers/{angelegt}/zugang").json()["zugang"]
        monkeypatch.setenv("WORTLAUT_AUTH_TOKEN", "")
        einstellungen.cache_clear()
        with TestClient(app, headers={"Authorization": f"Bearer {zugang}"}) as sprechend:
            assert sprechend.get(f"/api/progress?sprecher={angelegt}").status_code == 200
            assert sprechend.get("/api/zugang").json()["art"] == "sprecher"

    def test_gesundheit_ist_offen(self, klient_ohne_token: TestClient) -> None:
        # Proxy und Compose müssen den Dienst ohne Token prüfen können.
        assert klient_ohne_token.get("/gesundheit").json() == {"status": "ok"}

    def test_sprecherzugang_verwaltet_nicht(self, klient: TestClient, sprecher: str) -> None:
        # Ein Sprecherzugang ist kein schwächerer Verwalter, sondern etwas
        # anderes: Er darf keine Profile anlegen und keine Zugänge ausgeben.
        assert klient.get("/api/speakers").status_code == 401
        assert klient.post(f"/api/speakers/{sprecher}/zugang").status_code == 401

    def test_token_mit_umlaut_weist_sauber_ab(
        self, _umgebung: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Ein Token mit Nicht-ASCII-Zeichen (etwa ein Umlaut) brachte
        # secrets.compare_digest zum Abbruch - jede Anfrage endete mit 500
        # statt eines sauberen 401. Ohne Token muss abgewiesen, nicht
        # abgestürzt werden, sonst zeigt das Frontend nie das Token-Feld.
        monkeypatch.setenv("WORTLAUT_AUTH_TOKEN", "geheimnis-öäü")
        einstellungen.cache_clear()
        with TestClient(app) as klient:
            assert klient.get("/api/speakers").status_code == 401

    def test_token_mit_umlaut_wird_angenommen(
        self, _umgebung: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Der Prüfling ist direkt aufgerufen, nicht über den Testklienten: dessen
        # HTTP-Schicht kodiert Kopfzeilen anders als ein Browser. Was der Server
        # im Betrieb tatsächlich sieht, ist der Wert mit echten Umlauten - genau
        # der, den auch die Umgebung trägt. Er muss klaglos durchgehen.
        geheim = "geheimnis-öäü"
        monkeypatch.setenv("WORTLAUT_AUTH_TOKEN", geheim)
        einstellungen.cache_clear()
        deps._pruefe_verwaltung(f"Bearer {geheim}")  # kein Fehler = angenommen
        with pytest.raises(HTTPException) as abweisung:
            deps._pruefe_verwaltung(f"Bearer {geheim}x")
        assert abweisung.value.status_code == 401


class TestSprecher:
    def test_anlegen_erzeugt_ein_korpusverzeichnis(self, sprecher: str, tmp_path: Path) -> None:
        assert corpus.datenbank_pfad(tmp_path / "data", sprecher).is_file()

    def test_liste_zeigt_angelegte_profile(self, verwalter: TestClient, sprecher: str) -> None:
        liste = verwalter.get("/api/speakers").json()
        assert [person["id"] for person in liste] == [sprecher]
        assert liste[0]["name"] == "Testperson"

    def test_einzelabruf(self, verwalter: TestClient, sprecher: str) -> None:
        person = verwalter.get(f"/api/speakers/{sprecher}").json()
        assert person["basismodell"] == "openai/whisper-small"
        assert person["sprache"] == sprachen.VORGABE

    def test_die_sprache_laesst_sich_waehlen(self, verwalter: TestClient) -> None:
        # Die Spalte gab es immer; geschickt hat die Oberfläche sie nie, also
        # war jedes Profil deutsch, ganz gleich was danebenstand.
        antwort = verwalter.post(
            "/api/speakers",
            json={
                "name": "Mit Sprache",
                "sprache": sprachen.VORGABE,
                "basismodell": "openai/whisper-small",
            },
        )
        assert antwort.status_code == 201
        assert antwort.json()["sprache"] == sprachen.VORGABE

    def test_die_sprache_wird_normiert_abgelegt(self, verwalter: TestClient) -> None:
        # Sonst stünden zwei Schreibweisen für dieselbe Sprache im Bestand,
        # und der Vergleich mit der Stimme ginge einmal daneben.
        antwort = verwalter.post(
            "/api/speakers",
            json={"name": "Mit Gebiet", "sprache": "de-DE", "basismodell": "openai/whisper-small"},
        )
        assert antwort.status_code == 201
        assert antwort.json()["sprache"] == "de"

    def test_eine_sprache_die_es_nicht_gibt_wird_abgewiesen(self, verwalter: TestClient) -> None:
        # Ein Profil trägt seine Sprache ein Leben lang - Vorlagen, Feintuning
        # und Bewertung hängen daran und prüfen sie nicht noch einmal nach.
        antwort = verwalter.post(
            "/api/speakers",
            json={"name": "Klingonisch", "sprache": "kl", "basismodell": "openai/whisper-small"},
        )
        assert antwort.status_code == 422

    def test_die_wahl_steht_im_endpunkt(self, klient: TestClient) -> None:
        # Die Oberfläche baut ihr Auswahlfeld daraus und nicht aus einer
        # eigenen Liste (`api/sprachen.py`).
        wahl = klient.get("/api/sprachen").json()
        assert {eintrag["kuerzel"] for eintrag in wahl} == set(sprachen.UNTERSTUETZT)
        assert [eintrag["kuerzel"] for eintrag in wahl if eintrag["vorgabe"]] == [
            sprachen.VORGABE
        ]

    def test_frisches_profil_hat_noch_keinen_zugang(
        self, verwalter: TestClient, sprecher: str, zugang_ausgeben: Callable[[str], str]
    ) -> None:
        # Sonst wüsste die Verwaltung nicht, welches Profil noch niemandem
        # gehört - und ein Profil ohne Zugang ist für niemanden erreichbar.
        assert verwalter.get(f"/api/speakers/{sprecher}").json()["zugang_erneuert"] is None
        zugang_ausgeben(sprecher)
        assert verwalter.get(f"/api/speakers/{sprecher}").json()["zugang_erneuert"] is not None

    def test_unbekannter_sprecher_ist_ein_404(self, verwalter: TestClient) -> None:
        assert verwalter.get("/api/speakers/spr_gibtsnicht").status_code == 404

    def test_name_darf_nicht_leer_sein(self, verwalter: TestClient) -> None:
        antwort = verwalter.post("/api/speakers", json={"name": "", "basismodell": "x"})
        assert antwort.status_code == 422


class TestBindung:
    """Wofür der ganze Umbau da ist: Kennung abgeleitet, Fehlgriff laut."""

    def test_ohne_zugang_keine_daten(self, klient_ohne_token: TestClient, sprecher: str) -> None:
        # Auch mit richtiger Kennung im Parameter: Die Kennung wählt nicht mehr.
        assert klient_ohne_token.get(f"/api/progress?sprecher={sprecher}").status_code == 401

    def test_verwalter_kommt_nicht_an_die_daten(
        self, verwalter: TestClient, sprecher: str
    ) -> None:
        # Der Preis dieses Weges: Es gibt genau einen Zugang zu den Daten, und
        # das ist der des Sprechers. Wer verwaltet, verwaltet nur.
        assert verwalter.get(f"/api/progress?sprecher={sprecher}").status_code == 401

    def test_kennung_kommt_aus_dem_zugang(self, klient: TestClient, sprecher: str) -> None:
        # Ohne jeden Parameter - der Server weiß trotzdem, wessen Korpus er meint.
        antwort = klient.get("/api/progress")
        assert antwort.status_code == 200
        assert antwort.json()["aufnahmen"] == 0

    def test_fremde_kennung_wird_laut_abgewiesen(
        self,
        verwalter: TestClient,
        klient: TestClient,
        klient_fuer: Callable[[str], TestClient],
        sprecher: str,
    ) -> None:
        # Der Fall aus dem alten Lesezeichen: Der Zugang gehört zu A, die
        # Adresse nennt B. Früher wurde in B geschrieben, jetzt gibt es 403.
        fremd = _zweiter_sprecher(verwalter)

        antwort = klient.get(f"/api/progress?sprecher={fremd}")
        assert antwort.status_code == 403
        assert sprecher in antwort.json()["detail"] and fremd in antwort.json()["detail"]

        # Und der fremde Korpus hat davon nichts abbekommen.
        assert klient_fuer(fremd).get("/api/progress").json()["aufnahmen"] == 0

    def test_zugang_des_einen_oeffnet_nicht_den_anderen(
        self, verwalter: TestClient, klient_fuer: Callable[[str], TestClient], quelle: str
    ) -> None:
        fremd = _zweiter_sprecher(verwalter)
        # Die hochgeladene Quelle des einen taucht beim anderen nicht auf.
        assert klient_fuer(fremd).get("/api/sources").json() == []

    def test_erfundener_zugang_gilt_nicht(
        self, klient_ohne_token: TestClient, sprecher: str
    ) -> None:
        # Richtige Kennung, ausgedachtes Geheimnis.
        antwort = klient_ohne_token.get(
            "/api/progress", headers={"Authorization": f"Bearer {sprecher}.ausgedacht"}
        )
        assert antwort.status_code == 401

    def test_zugang_zu_unbekanntem_sprecher_ist_kein_404(
        self, klient_ohne_token: TestClient
    ) -> None:
        # 401 und nicht 404: Die Kennung stammt aus dem Zugang selbst, es hat
        # sie niemand geraten - ein 404 verriete nur, welche Korpora es gibt.
        antwort = klient_ohne_token.get(
            "/api/progress", headers={"Authorization": "Bearer spr_gibtsnicht.egal"}
        )
        assert antwort.status_code == 401


class TestZugangAusgeben:
    def test_auskunft_nennt_den_sprecher(self, klient: TestClient, sprecher: str) -> None:
        # Damit die Oberfläche zeigen kann, wer eingestellt ist - und zwar das,
        # was der Server sieht, nicht das, was der Browser sich gemerkt hat.
        auskunft = klient.get("/api/zugang").json()
        assert auskunft == {
            "art": "sprecher",
            "sprecher_id": sprecher,
            "name": "Testperson",
            # Die Oberfläche braucht sie für die Stimmwahl und holt sie hier,
            # statt Deutsch anzunehmen (`packages/ui/speak.ts`).
            "sprache": sprachen.VORGABE,
        }

    def test_auskunft_nennt_die_verwaltung(self, verwalter: TestClient) -> None:
        assert verwalter.get("/api/zugang").json()["art"] == "verwaltung"

    def test_neuer_zugang_setzt_den_alten_ausser_kraft(
        self, klient: TestClient, sprecher: str, zugang_ausgeben: Callable[[str], str]
    ) -> None:
        # Das ist der Rückzug eines verlorenen Zugangs: einen neuen ausgeben.
        assert klient.get("/api/progress").status_code == 200
        zugang_ausgeben(sprecher)
        assert klient.get("/api/progress").status_code == 401

    def test_zurueckziehen_sperrt_ganz(
        self, verwalter: TestClient, klient: TestClient, sprecher: str
    ) -> None:
        assert verwalter.delete(f"/api/speakers/{sprecher}/zugang").status_code == 204
        assert klient.get("/api/progress").status_code == 401
        assert verwalter.get(f"/api/speakers/{sprecher}").json()["zugang_erneuert"] is None

    def test_neuer_zugang_nach_dem_rueckzug(
        self, verwalter: TestClient, klient_fuer: Callable[[str], TestClient], sprecher: str
    ) -> None:
        verwalter.delete(f"/api/speakers/{sprecher}/zugang")
        assert klient_fuer(sprecher).get("/api/progress").status_code == 200

    def test_zugang_traegt_die_kennung(
        self, sprecher: str, zugang_ausgeben: Callable[[str], str]
    ) -> None:
        assert zugang_ausgeben(sprecher).startswith(f"{sprecher}.")


def _zweiter_sprecher(verwalter: TestClient) -> str:
    antwort = verwalter.post(
        "/api/speakers", json={"name": "Andere", "basismodell": "openai/whisper-small"}
    )
    assert antwort.status_code == 201
    return antwort.json()["id"]
