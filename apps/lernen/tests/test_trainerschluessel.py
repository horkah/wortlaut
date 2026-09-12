"""Wer ein Training anstoßen darf - und wer nur zusieht.

Ein Lauf belegt die Karte für Minuten bis Stunden. Der Sprecherzugang sagt,
wessen Modell dabei entsteht; er sagt nicht, dass dieser Mensch die Maschine
dafür beschäftigen darf. Deshalb ein zweites Geheimnis vor genau einem Weg -
`POST /lernen/api/laeufe`, und vor keinem anderen.

Geprüft wird hier beides: dass der Schlüssel die teure Tür wirklich zuhält,
und dass er vor keiner billigen steht.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.lernen.backend.config import einstellungen

from apps.lernen.tests.conftest import TRAINERSCHLUESSEL


def _bestellung() -> dict[str, str]:
    return {"methode": "lora", "daten": "original"}


class TestBeauftragen:
    def test_mit_schluessel_wird_beauftragt(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        antwort = klient.post("/lernen/api/laeufe", json=_bestellung())
        assert antwort.status_code == 201, antwort.text

    def test_ohne_schluessel_kein_lauf(self, klient: TestClient, quelle: str, sprich) -> None:
        sprich(6)
        antwort = klient.post(
            "/lernen/api/laeufe", json=_bestellung(), headers={"X-Trainer-Key": ""}
        )
        assert antwort.status_code == 401
        assert "Trainerschlüssel" in antwort.json()["detail"]

    def test_falscher_schluessel_kein_lauf(self, klient: TestClient, quelle: str, sprich) -> None:
        sprich(6)
        antwort = klient.post(
            "/lernen/api/laeufe", json=_bestellung(), headers={"X-Trainer-Key": "daneben"}
        )
        assert antwort.status_code == 401

    def test_gescheiterter_versuch_hinterlaesst_nichts(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        """Kein halber Auftrag: Der Wächter steht vor der ersten Datei."""
        sprich(6)
        klient.post("/lernen/api/laeufe", json=_bestellung(), headers={"X-Trainer-Key": "daneben"})
        assert not (datenverzeichnis / "snapshots").exists()
        assert klient.get("/lernen/api/laeufe").json()["laeufe"] == []

    def test_der_schluessel_kommt_vor_der_bestellung(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        """Erst die Erlaubnis, dann der Inhalt.

        Eine unbekannte Methode ist sonst ein 400 - wer den Schlüssel nicht
        hat, soll daran aber nicht ablesen können, welche Methoden dieser
        Server kennt.
        """
        sprich(6)
        antwort = klient.post(
            "/lernen/api/laeufe",
            json={"methode": "zauberei", "daten": "original"},
            headers={"X-Trainer-Key": "daneben"},
        )
        assert antwort.status_code == 401

    def test_ohne_aufnahmen_bleibt_es_beim_409(self, klient: TestClient) -> None:
        """Der Schlüssel stimmt, es fehlt der Stoff - das ist ein anderer Fehler."""
        assert klient.post("/lernen/api/laeufe", json=_bestellung()).status_code == 409


class TestDerRestBleibtOffen:
    """Zusehen, zurücknehmen, löschen: alles ohne Schlüssel.

    Das ist die Grenze dieser Sperre. Sie beschränkt, was Rechenzeit kostet -
    nicht, was jemandem gehört. Wer seine Stimme hergegeben hat, kommt an
    seine Läufe, auch wenn er nie einen anstoßen darf.
    """

    def test_liste_ohne_schluessel(self, klient: TestClient) -> None:
        antwort = klient.get("/lernen/api/laeufe", headers={"X-Trainer-Key": ""})
        assert antwort.status_code == 200

    def test_zuruecknehmen_und_loeschen_ohne_schluessel(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        job_id = klient.post("/lernen/api/laeufe", json=_bestellung()).json()["job_id"]
        ohne = {"X-Trainer-Key": ""}
        assert klient.post(f"/lernen/api/laeufe/{job_id}/abbruch", headers=ohne).status_code == 200
        assert klient.get(f"/lernen/api/laeufe/{job_id}", headers=ohne).status_code == 200
        assert klient.delete(f"/lernen/api/laeufe/{job_id}", headers=ohne).status_code == 200


class TestOhneHinterlegtenSchluessel:
    """Leer heißt abgeschaltet, nicht offen - wie bei Verwaltung und Aufsicht."""

    @pytest.fixture
    def abgeschaltet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORTLAUT_TRAINER_KEY", "")
        einstellungen.cache_clear()
        yield
        einstellungen.cache_clear()

    def test_niemand_trainiert(
        self, klient: TestClient, quelle: str, sprich, abgeschaltet: None
    ) -> None:
        sprich(6)
        antwort = klient.post("/lernen/api/laeufe", json=_bestellung())
        assert antwort.status_code == 401
        assert "abgeschaltet" in antwort.json()["detail"]

    def test_auch_der_leere_schluessel_nicht(
        self, klient: TestClient, quelle: str, sprich, abgeschaltet: None
    ) -> None:
        """Sonst öffnete ein vergessener Eintrag die Tür für jeden."""
        sprich(6)
        antwort = klient.post(
            "/lernen/api/laeufe", json=_bestellung(), headers={"X-Trainer-Key": ""}
        )
        assert antwort.status_code == 401

    def test_die_oberflaeche_erfaehrt_es_vorher(
        self, klient: TestClient, quelle: str, sprich, abgeschaltet: None
    ) -> None:
        sprich(6)
        liste = klient.get("/lernen/api/laeufe").json()
        assert liste["bereit"] is False
        assert liste["schluessel_noetig"] is False
        assert "Trainerschlüssel" in liste["hinweis"]

    def test_zusehen_bleibt_moeglich(self, klient: TestClient, abgeschaltet: None) -> None:
        assert klient.get("/lernen/api/laeufe").status_code == 200


class TestWasDieOberflaecheErfaehrt:
    def test_mit_schluessel_fragt_die_seite_danach(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        liste = klient.get("/lernen/api/laeufe").json()
        assert liste["schluessel_noetig"] is True
        assert liste["bereit"] is True
        assert liste["hinweis"] == ""

    def test_der_schluessel_steht_in_keiner_antwort(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        """Er ist ein Geheimnis und kein Zustand, den die Seite anzeigt."""
        sprich(6)
        assert TRAINERSCHLUESSEL not in klient.get("/lernen/api/laeufe").text
