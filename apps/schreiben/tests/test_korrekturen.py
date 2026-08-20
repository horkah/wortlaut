"""Bestätigen und der Weg zurück zu „hören".

Der Postausgang muss zwei Dinge können: nichts verlieren, wenn „hören" nicht
erreichbar ist, und nichts doppelt einliefern, wenn er es noch einmal
versucht.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

if TYPE_CHECKING:  # nur für Editoren; zur Laufzeit reicht pytest die Fixtures durch
    from apps.schreiben.tests.conftest import Testintake


def audiodateien(verzeichnis: Path) -> list[Path]:
    return sorted(verzeichnis.glob("*.wav"))


class TestBestaetigen:
    def test_schickt_jeden_abschnitt_als_korrekturpaar(
        self, klient: TestClient, sitzung: str, diktat: dict, intake: Testintake
    ) -> None:
        antwort = klient.post(f"/schreiben/api/sessions/{sitzung}/bestaetigen")

        assert antwort.status_code == 200
        assert antwort.json() == {"eingestellt": 3, "gesendet": 3, "offen": 0, "fehler": None}
        # Die Abschnittskennung geht als `externe_id` mit — daran erkennt
        # „hören" eine Wiederholung.
        assert [lieferung["externe_id"] for lieferung in intake.lieferungen] == [
            a["id"] for a in diktat["abschnitte"]
        ]
        assert intake.lieferungen[0]["text"] == "Ich möchte einen Kaffee."
        assert intake.lieferungen[0]["bytes"].startswith(b"RIFF")

    def test_loescht_das_audio_nach_der_uebergabe(
        self,
        klient: TestClient,
        sitzung: str,
        diktat: dict,
        intake: Testintake,
        audioverzeichnis: Path,
    ) -> None:
        # Angekommen heißt: die Aufnahme liegt im Korpus. Eine zweite Kopie
        # wäre nur mehr Gesundheitsdaten.
        klient.post(f"/schreiben/api/sessions/{sitzung}/bestaetigen")

        assert audiodateien(audioverzeichnis) == []
        zeilen = klient.get(f"/schreiben/api/sessions/{sitzung}").json()["abschnitte"]
        assert all(zeile["hat_audio"] is False for zeile in zeilen)
        assert klient.get(f"/schreiben/api/segments/{zeilen[0]['id']}/audio").status_code == 404

    def test_schliesst_die_sitzung(
        self, klient: TestClient, sitzung: str, diktat: dict, intake: Testintake
    ) -> None:
        klient.post(f"/schreiben/api/sessions/{sitzung}/bestaetigen")

        assert klient.get(f"/schreiben/api/sessions/{sitzung}").json()["status"] == "bestaetigt"
        # Ein bestätigter Text wird nicht mehr verändert.
        assert (
            klient.post(
                f"/schreiben/api/sessions/{sitzung}/segments",
                files={"audio": ("a.webm", b"x", "audio/webm")},
            ).status_code
            == 409
        )

    def test_zweites_bestaetigen_stellt_nichts_nach(
        self, klient: TestClient, sitzung: str, diktat: dict, intake: Testintake
    ) -> None:
        klient.post(f"/schreiben/api/sessions/{sitzung}/bestaetigen")
        antwort = klient.post(f"/schreiben/api/sessions/{sitzung}/bestaetigen")

        assert antwort.json()["eingestellt"] == 0
        assert len(intake.lieferungen) == 3

    def test_lehnt_leere_sitzung_ab(self, klient: TestClient, sitzung: str) -> None:
        assert klient.post(f"/schreiben/api/sessions/{sitzung}/bestaetigen").status_code == 400


class TestPostausgang:
    def test_haelt_fest_was_nicht_ankam(
        self,
        klient: TestClient,
        sitzung: str,
        diktat: dict,
        intake: Testintake,
        audioverzeichnis: Path,
    ) -> None:
        intake.scheitert = True

        antwort = klient.post(f"/schreiben/api/sessions/{sitzung}/bestaetigen").json()

        assert (antwort["gesendet"], antwort["offen"]) == (0, 3)
        assert "hören ist nicht erreichbar" in antwort["fehler"]
        # Solange nichts übergeben ist, bleibt die Aufnahme liegen.
        assert len(audiodateien(audioverzeichnis)) == 3
        assert klient.get("/schreiben/api/outbox").json()["offen"] == 3

    def test_holt_den_versand_spaeter_nach(
        self, klient: TestClient, sitzung: str, diktat: dict, intake: Testintake
    ) -> None:
        intake.scheitert = True
        klient.post(f"/schreiben/api/sessions/{sitzung}/bestaetigen")

        intake.scheitert = False
        antwort = klient.post("/schreiben/api/outbox/senden").json()

        assert (antwort["gesendet"], antwort["offen"]) == (3, 0)
        assert len(intake.lieferungen) == 3
        assert klient.get("/schreiben/api/outbox").json() == {
            "offen": 0,
            "gesendet": 3,
            "letzter_fehler": None,
        }

    def test_sendet_gesendetes_nicht_noch_einmal(
        self, klient: TestClient, sitzung: str, diktat: dict, intake: Testintake
    ) -> None:
        klient.post(f"/schreiben/api/sessions/{sitzung}/bestaetigen")
        antwort = klient.post("/schreiben/api/outbox/senden").json()

        assert antwort["gesendet"] == 0
        assert len(intake.lieferungen) == 3

    def test_ohne_adresse_bleibt_alles_liegen(
        self,
        klient: TestClient,
        sitzung: str,
        diktat: dict,
        intake: Testintake,
        monkeypatch,
    ) -> None:
        # Keine Intake-Adresse konfiguriert: puffern statt verwerfen.
        from apps.schreiben.backend.config import einstellungen

        monkeypatch.setenv("WORTLAUT_INTAKE_URL", "")
        einstellungen.cache_clear()

        antwort = klient.post(f"/schreiben/api/sessions/{sitzung}/bestaetigen").json()

        assert (antwort["eingestellt"], antwort["gesendet"], antwort["offen"]) == (3, 0, 3)
        assert intake.lieferungen == []
        assert klient.get("/schreiben/api/outbox").json()["offen"] == 3
