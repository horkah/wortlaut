"""Wer hier diktiert - und dass niemand in fremde Diktate sieht.

Diese App führt seit dem Wegfall der Einzelnutzer-Instanz denselben Sprecher
wie „hören": Sie leitet ihn aus dem vorgelegten Zugang ab (`backend/deps.py`).
Zwei Dinge hängen daran, und beide wären teuer, wenn sie stillschweigend
danebengriffen - das Modell, auf dem jemand spricht, und der Korpus, in den
seine Korrekturen zurückfließen.

Geprüft wird deshalb nicht nur, dass ein gültiger Zugang hereinkommt, sondern
vor allem, dass ohne ihn nichts geht und dass zwei Sprecher einander nicht
sehen.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from wortlaut import sprachen

from apps.schreiben.backend.main import app

from conftest import NAME, lege_sprecher_an


class TestOhneZugang:
    """Ohne gültigen Zugang gibt es hier nichts - auch nichts zum Anlegen."""

    def test_sitzung_beginnen_wird_abgewiesen(self, klient_ohne_zugang: TestClient) -> None:
        assert klient_ohne_zugang.post("/schreiben/api/sessions").status_code == 401

    def test_modellauskunft_wird_abgewiesen(self, klient_ohne_zugang: TestClient) -> None:
        # Auch die Kopfzeile bekommt nichts: Welches Modell für wen läuft, ist
        # eine Auskunft über einen Menschen.
        assert klient_ohne_zugang.get("/schreiben/api/model").status_code == 401

    def test_postausgang_wird_abgewiesen(self, klient_ohne_zugang: TestClient) -> None:
        assert klient_ohne_zugang.get("/schreiben/api/outbox").status_code == 401

    def test_ein_erfundener_zugang_gilt_nicht(self, klient_ohne_zugang: TestClient) -> None:
        antwort = klient_ohne_zugang.post(
            "/schreiben/api/sessions", headers={"Authorization": "Bearer spr_test.erfunden"}
        )
        assert antwort.status_code == 401

    def test_ein_verwaltertoken_ist_kein_sprecherzugang(
        self, klient_ohne_zugang: TestClient
    ) -> None:
        # Diese App hat nichts zu verwalten; sie spricht für einen Menschen.
        antwort = klient_ohne_zugang.post(
            "/schreiben/api/sessions", headers={"Authorization": "Bearer test-geheim"}
        )
        assert antwort.status_code == 401


class TestAuskunft:
    def test_nennt_kennung_und_namen(self, klient: TestClient, sprecher: str) -> None:
        # Dieselbe Auskunft wie in „hören", damit die Kopfzeile in beiden Apps
        # denselben Namen zeigt.
        antwort = klient.get("/schreiben/api/zugang").json()

        assert antwort == {
            "art": "sprecher",
            "sprecher_id": sprecher,
            "name": NAME,
            "sprache": sprachen.VORGABE,
        }


class TestGetrennteAblage:
    """Je Sprecher eine Datenbank und ein Audioverzeichnis."""

    def test_die_datenbank_liegt_unter_dem_eigenen_sprecher(
        self, klient: TestClient, datenverzeichnis: Path, sprecher: str
    ) -> None:
        assert klient.post("/schreiben/api/sessions").status_code == 201

        assert (datenverzeichnis / "diktate" / sprecher / "schreiben.sqlite").is_file()

    def test_ein_anderer_sprecher_sieht_die_sitzung_nicht(
        self, klient: TestClient, datenverzeichnis: Path
    ) -> None:
        sitzung = klient.post("/schreiben/api/sessions").json()["id"]

        # Ein zweiter Mensch, ein zweiter Zugang, eine zweite Datenbank.
        fremder = lege_sprecher_an(datenverzeichnis, "spr_zweiter")
        with TestClient(app, headers={"Authorization": f"Bearer {fremder}"}) as anderer:
            assert anderer.get(f"/schreiben/api/sessions/{sitzung}").status_code == 404

    def test_jeder_bekommt_seine_eigene_datei(
        self, klient: TestClient, datenverzeichnis: Path
    ) -> None:
        klient.post("/schreiben/api/sessions")
        fremder = lege_sprecher_an(datenverzeichnis, "spr_zweiter")
        with TestClient(app, headers={"Authorization": f"Bearer {fremder}"}) as anderer:
            anderer.post("/schreiben/api/sessions")

        assert (datenverzeichnis / "diktate" / "spr_test" / "schreiben.sqlite").is_file()
        assert (datenverzeichnis / "diktate" / "spr_zweiter" / "schreiben.sqlite").is_file()


class TestRueckwegInDenKorpus:
    """Was bestätigt wird, geht mit dem Zugang dessen, der bestätigt hat."""

    def test_sendet_mit_dem_zugang_des_bestaetigenden(
        self, klient: TestClient, diktat: dict, intake, zugang: str, sprecher: str
    ) -> None:
        antwort = klient.post(f"/schreiben/api/sessions/{diktat['id']}/bestaetigen")
        assert antwort.status_code == 200, antwort.text

        # Kein Token aus der Umgebung mehr: „hören" leitet den Korpus aus genau
        # dem Zugang ab, mit dem hier jemand seinen Text abgenickt hat.
        assert {lieferung["token"] for lieferung in intake.lieferungen} == {zugang}
        assert {lieferung["sprecher_id"] for lieferung in intake.lieferungen} == {sprecher}
