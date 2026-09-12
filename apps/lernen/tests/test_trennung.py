"""Die Grenzen dieser App: fremde Läufe, und der Korpus als Lesesache.

Zwei Zusagen, die nirgends auffallen, wenn sie brechen - und deshalb hier
stehen: Ein Sprecher sieht die Läufe eines anderen nicht, und „lernen"
schreibt nichts in den Korpus.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from wortlaut import corpus

from apps.lernen.backend.main import app as lernen_app


@pytest.fixture
def zweiter_zugang(verwalter: TestClient) -> str:
    antwort = verwalter.post(
        "/api/speakers", json={"name": "Zweite", "basismodell": "openai/whisper-small"}
    )
    assert antwort.status_code == 201
    zweite = antwort.json()["id"]
    return verwalter.post(f"/api/speakers/{zweite}/zugang").json()["zugang"]


@pytest.fixture
def fremder(zweiter_zugang: str) -> Iterator[TestClient]:
    with TestClient(lernen_app, headers={"Authorization": f"Bearer {zweiter_zugang}"}) as klient:
        yield klient


class TestFremdeLaeufe:
    def test_ein_fremder_lauf_taucht_in_der_liste_nicht_auf(
        self, klient: TestClient, fremder: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        klient.post("/lernen/api/laeufe", json={"methode": "lora", "daten": "original"})
        assert fremder.get("/lernen/api/laeufe").json()["laeufe"] == []

    def test_ein_fremder_lauf_ist_auch_einzeln_unbekannt(
        self, klient: TestClient, fremder: TestClient, quelle: str, sprich
    ) -> None:
        # Unbekannt und nicht „verboten": Die Kennung stammt aus dem Zugang,
        # und wer nach einem anderen Verzeichnis fragt, bekommt nicht einmal
        # die Auskunft, dass es existiert.
        sprich(6)
        meiner = klient.post(
            "/lernen/api/laeufe", json={"methode": "lora", "daten": "original"}
        ).json()["job_id"]
        assert fremder.get(f"/lernen/api/laeufe/{meiner}").status_code == 404
        assert fremder.post(f"/lernen/api/laeufe/{meiner}/abbruch").status_code == 404

    def test_die_aufteilung_eines_anderen_bleibt_seine(
        self, klient: TestClient, fremder: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        assert len(klient.get("/lernen/api/aufteilung").json()["proben"]) == 6
        # Der zweite Sprecher hat einen eigenen, leeren Korpus - und eine
        # eigene Datenbank daneben.
        assert fremder.get("/lernen/api/aufteilung").json()["proben"] == []


class TestKorpusBleibtUnberuehrt:
    def test_lernen_legt_keinen_korpus_an(
        self, verwalter: TestClient, datenverzeichnis, _umgebung: None
    ) -> None:
        # Ein Zugang zu einem Sprecher, den es nicht gibt, darf kein
        # Verzeichnis erzeugen. Sonst machte ein Tippfehler in einer Kennung
        # einen leeren Korpus statt eines 401.
        with TestClient(lernen_app, headers={"Authorization": "Bearer spr_erfunden.geheim"}) as k:
            assert k.get("/lernen/api/aufteilung").status_code == 401
        assert not (datenverzeichnis / corpus.KORPUS / "spr_erfunden").exists()

    def test_ein_auftrag_aendert_am_korpus_nichts(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis, sprecher: str
    ) -> None:
        sprich(6)
        korpus = datenverzeichnis / corpus.sprecher_relpfad(sprecher)
        vorher = {
            pfad.relative_to(korpus): pfad.stat().st_mtime_ns for pfad in korpus.rglob("*.wav")
        }

        klient.post("/lernen/api/laeufe", json={"methode": "full", "daten": "augmentiert"})

        nachher = {
            pfad.relative_to(korpus): pfad.stat().st_mtime_ns for pfad in korpus.rglob("*.wav")
        }
        assert nachher == vorher


class TestLoeschung:
    """Was „lernen" führt, verschwindet mit dem Menschen.

    Die Aufteilung ist keine Stimmaufnahme, aber eine Liste von Aufnahmen, die
    es nicht mehr geben soll - und der Schnappschuss eines Laufs enthält jede
    Vorlage im Klartext. Beides gehört zur Löschung, sonst bliebe ausgerechnet
    das stehen, was auf die gelöschten Daten zeigt.
    """

    def test_aufteilung_und_laeufe_gehen_mit(
        self,
        klient: TestClient,
        verwalter: TestClient,
        quelle: str,
        sprich,
        datenverzeichnis,
        sprecher: str,
    ) -> None:
        from apps.hoeren.backend.services import loeschung

        sprich(6)
        klient.post("/lernen/api/laeufe", json={"methode": "lora", "daten": "original"})

        # Beides liegt jetzt da …
        assert (datenverzeichnis / "lernen" / sprecher).is_dir()
        assert loeschung.schnappschuesse(datenverzeichnis, sprecher)

        entfernt = loeschung.loesche(datenverzeichnis, sprecher)

        # … und danach nichts mehr davon.
        assert not (datenverzeichnis / "lernen" / sprecher).exists()
        assert not loeschung.schnappschuesse(datenverzeichnis, sprecher)
        assert not (datenverzeichnis / "korpus" / sprecher).exists()
        assert len(entfernt) >= 3

    def test_der_schnappschuss_traegt_seine_marke(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis, sprecher: str
    ) -> None:
        # Ohne `sprecher.txt` fände `scripts/purge_speaker.py` ihn nicht und
        # meldete ihn zur Prüfung von Hand - Stimmdaten blieben liegen.
        from apps.hoeren.backend.services import loeschung

        sprich(6)
        klient.post("/lernen/api/laeufe", json={"methode": "full", "daten": "original"})
        assert not loeschung.ohne_marke(datenverzeichnis)
