"""Die Aufteilung: zwei Drittel lernen, ein Drittel prüft - und es bleibt dabei.

Die wichtigste Zusage dieser App steht hier: Eine Aufnahme, die einmal geprüft
hat, trainiert nie. Bricht sie, sieht man das an keiner Zahl - ein Modell, das
seine Prüfung kennt, sieht schlicht gut aus. Deshalb wird sie hier geprüft und
nicht dort, wo sie auffiele.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from wortlaut import laeufe

from apps.lernen.backend.main import app


def _teile(klient: TestClient) -> dict[str, str]:
    """Aufnahme-Kennung → Teil, so wie die Ansicht es zeigt."""
    antwort = klient.get("/lernen/api/aufteilung")
    assert antwort.status_code == 200, antwort.text
    return {probe["aufnahme_id"]: probe["teil"] for probe in antwort.json()["proben"]}


class TestZugriff:
    def test_ohne_zugang_kein_zugriff(self, _umgebung: None) -> None:
        with TestClient(app) as ohne:
            assert ohne.get("/lernen/api/aufteilung").status_code == 401

    def test_verwaltertoken_genuegt_hier_nicht(self, _umgebung: None) -> None:
        # Ein Modell gehört einem Menschen. Wer keinen Sprecherzugang vorlegt,
        # hat hier nichts zu sehen - auch die Verwaltung nicht.
        with TestClient(app, headers={"Authorization": "Bearer test-geheim"}) as verwaltung:
            assert verwaltung.get("/lernen/api/aufteilung").status_code == 401


class TestZuteilung:
    def test_folgt_dem_muster(self, klient: TestClient, quelle: str, sprich) -> None:
        kennungen = sprich(6)
        teile = _teile(klient)
        # Genau das Muster aus `wortlaut/laeufe.py`, in der Reihenfolge des
        # Korpus - also nach Alter der Aufnahme.
        assert [teile[k] for k in kennungen] == list(laeufe.MUSTER)

    def test_zwei_drittel_lernen_ein_drittel_prueft(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(12)
        anzahl = klient.get("/lernen/api/aufteilung").json()["anzahl"]
        lernend = anzahl[laeufe.TRAIN] + anzahl[laeufe.VALIDIERUNG]
        assert lernend == 2 * anzahl[laeufe.TEST]

    def test_neue_aufnahmen_werden_beim_hinsehen_zugeteilt(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(3)
        assert len(_teile(klient)) == 3
        sprich(3)
        # Kein Knopf dazwischen: Wer die Seite ansieht, sieht den aktuellen
        # Stand. Ein Knopf wäre einer, den jemand vergisst.
        assert len(_teile(klient)) == 6

    def test_bestehende_zuteilungen_bleiben_stehen(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        vorher = _teile(klient)
        sprich(6)
        nachher = _teile(klient)
        assert all(nachher[kennung] == teil for kennung, teil in vorher.items())


class TestNachDemLoeschen:
    def test_eine_verworfene_aufnahme_sortiert_die_uebrigen_nicht_um(
        self, klient: TestClient, hoeren: TestClient, quelle: str, sprich
    ) -> None:
        # Der Fall, für den die Tabelle überhaupt existiert: Würde beim
        # Trainieren durchgezählt statt nachgeschlagen, rückte hier alles um
        # einen Platz vor - und Aufnahmen, die bisher geprüft haben, landeten
        # im Training eines Modells, das anschließend an ihnen gemessen wird.
        kennungen = sprich(9)
        vorher = _teile(klient)

        assert hoeren.delete(f"/api/recordings/{kennungen[0]}").status_code == 204

        nachher = _teile(klient)
        assert kennungen[0] not in nachher
        assert all(nachher[k] == vorher[k] for k in kennungen[1:])

    def test_die_naechste_aufnahme_erbt_keinen_freigewordenen_platz(
        self, klient: TestClient, hoeren: TestClient, quelle: str, sprich
    ) -> None:
        kennungen = sprich(6)
        _teile(klient)
        assert hoeren.delete(f"/api/recordings/{kennungen[1]}").status_code == 204
        _teile(klient)

        neu = sprich(1)[0]
        # Platz 1 ist frei geworden, die neue Aufnahme bekommt trotzdem Platz 6:
        # Eine wiederverwendete Nummer wäre genau das Umsortieren, das diese
        # Tabelle verhindern soll.
        proben = klient.get("/lernen/api/aufteilung").json()["proben"]
        gefunden = next(probe for probe in proben if probe["aufnahme_id"] == neu)
        assert gefunden["nummer"] == 6
        assert gefunden["teil"] == laeufe.teil_fuer(6)

    def test_verwaiste_zuteilungen_werden_gezeigt_und_nicht_verschwiegen(
        self, klient: TestClient, hoeren: TestClient, quelle: str, sprich
    ) -> None:
        kennungen = sprich(6)
        _teile(klient)
        assert hoeren.delete(f"/api/recordings/{kennungen[0]}").status_code == 204

        antwort = klient.get("/lernen/api/aufteilung").json()
        assert antwort["verwaist"] == 1
        assert sum(antwort["anzahl"].values()) == 5


class TestOhneAufnahmen:
    def test_leerer_korpus_ist_kein_fehler(self, klient: TestClient) -> None:
        antwort = klient.get("/lernen/api/aufteilung")
        assert antwort.status_code == 200
        assert antwort.json()["proben"] == []
        assert antwort.json()["anzahl"] == {"train": 0, "validierung": 0, "test": 0}
