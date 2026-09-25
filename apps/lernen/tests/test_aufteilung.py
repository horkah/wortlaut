"""Die Faltungen: sechs, nach Zählerstand vergeben, nirgends gespeichert.

Hier stand bis September 2026 die wichtigste Zusage dieser App - eine Aufnahme,
die einmal geprüft hat, trainiert nie. Es gibt sie nicht mehr, weil es das
Testdrittel nicht mehr gibt: Gemessen wird mit sechsfacher Kreuzvalidierung
über den ganzen Korpus, und dabei trainiert jede Aufnahme in fünf von sechs
Faltungen.

Was an ihre Stelle tritt, ist eine schwächere, aber immer noch tragende Zusage:
**Eine Aufnahme trägt genau eine Faltung.** Trüge sie zwei, hörte ein Modell
die Aufnahme, an der es gemessen wird - und das sieht gut aus. Geprüft wird das
dort, wo es entsteht: am Manifest (`test_laeufe.py`).

Hier bleibt die Ansicht: dass sie die Zahlen nennt, ohne die Aufnahmen ein
zweites Mal aufzuzählen.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from wortlaut import laeufe

from apps.lernen.backend.main import app


def _uebersicht(klient: TestClient) -> dict:
    antwort = klient.get("/lernen/api/aufteilung")
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


class TestZugriff:
    def test_ohne_zugang_kein_zugriff(self, _umgebung: None) -> None:
        with TestClient(app) as ohne:
            assert ohne.get("/lernen/api/aufteilung").status_code == 401

    def test_verwaltertoken_genuegt_hier_nicht(self, _umgebung: None) -> None:
        # Ein Modell gehört einem Menschen. Wer keinen Sprecherzugang vorlegt,
        # hat hier nichts zu sehen - auch die Verwaltung nicht.
        with TestClient(app, headers={"Authorization": "Bearer test-geheim"}) as verwaltung:
            assert verwaltung.get("/lernen/api/aufteilung").status_code == 401


class TestFaltungen:
    def test_folgen_der_reihenfolge(self, klient: TestClient, quelle: str, sprich) -> None:
        # Sechs Aufnahmen, sechs Faltungen, je eine.
        sprich(6)
        daten = _uebersicht(klient)
        assert daten["faltungen"] == laeufe.FALTUNGEN
        assert daten["aufnahmen"] == 6
        assert daten["je_faltung"] == {str(nummer): 1 for nummer in range(laeufe.FALTUNGEN)}
        assert daten["genug"] is True

    def test_die_siebte_faengt_wieder_vorn_an(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(8)
        je_faltung = _uebersicht(klient)["je_faltung"]
        assert je_faltung["0"] == 2
        assert je_faltung["1"] == 2
        assert je_faltung["2"] == 1

    def test_neue_aufnahmen_zaehlen_sofort_mit(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        # Kein Knopf „jetzt zuteilen": Die Faltung folgt der Reihenfolge des
        # Korpus und wird bei jedem Hinsehen neu gerechnet.
        sprich(6)
        assert _uebersicht(klient)["aufnahmen"] == 6
        sprich(3)
        assert _uebersicht(klient)["aufnahmen"] == 9

    def test_zu_wenige_aufnahmen_sind_nicht_genug(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        # Unter sechs bliebe eine Faltung leer - ein Training, das auf nichts
        # misst, und eine Zahl, die keine ist.
        sprich(3)
        daten = _uebersicht(klient)
        assert daten["genug"] is False
        assert daten["je_faltung"]["5"] == 0

    def test_leerer_korpus_ist_kein_fehler(self, klient: TestClient) -> None:
        daten = _uebersicht(klient)
        assert daten["aufnahmen"] == 0
        assert daten["sekunden"] == 0
        assert daten["genug"] is False

    def test_die_aufnahmen_selbst_stehen_hier_nicht(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        # Sie stehen unter „Meine Daten", einmal und vollständig. Zwei Listen
        # über dieselbe Sache sind eine zu viel.
        sprich(6)
        daten = _uebersicht(klient)
        assert "proben" not in daten
        assert not any(isinstance(wert, list) for wert in daten.values())
