"""Hat es etwas gebracht? - der trainierte Stand gegen die Grundlinie.

Der Trainer läuft hier nicht, also wird sein Ergebnis nachgestellt: ein
`zustand.json`, eine `bewertung.jsonl` und ein Manifest in der Registry. Genau
das hinterlässt ein fertiger Lauf, und genau daraus baut die Ansicht ihren
Vergleich.

Die Grundlinie dagegen ist echt: Sie entsteht wie im Betrieb, indem die
Auswertung von „hören" über den Korpus läuft - mit einem Platzhalter statt
Whisper, denn geprüft wird die Verrechnung und nicht das Hören.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import augmentierung, laeufe, registry
from wortlaut.whisper import Transkript

from apps.hoeren.backend.services import auswertung


class PlatzhalterErkenner:
    """Ein Erkenner, der immer dasselbe sagt - hier genügt das vollauf."""

    def __init__(self, antwort: str) -> None:
        self.antwort = antwort

    def transkribiere(self, wav: Path, sprache: str = "de") -> Transkript:
        return Transkript(text=self.antwort, abschnitte=[])


@pytest.fixture(autouse=True)
def _grundlinienmodell(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Dasselbe Modell, auf das „lernen" trainiert - sonst wäre die Grundlinie
    # keine.
    monkeypatch.setenv("WORTLAUT_AUSWERTUNG_MODELLE", "small")
    monkeypatch.setattr(
        auswertung,
        "transkriptor_fuer",
        lambda modell, geraet, rechenart: PlatzhalterErkenner("völlig daneben gehört"),
    )
    auswertung.vergiss_lauf()
    yield
    auswertung.vergiss_lauf()


@pytest.fixture
def aufnahmen(quelle: str, sprich) -> list[str]:
    """Neun Aufnahmen - genug für ein volles Muster plus Rest."""
    return sprich(9)


@pytest.fixture
def grundlinie(hoeren: TestClient, aufnahmen: list[str]) -> None:
    """Die Auswertung von „hören" über dieselben Aufnahmen laufen lassen.

    Hängt ausdrücklich an `aufnahmen`: Eine Grundlinie über einen leeren
    Korpus wäre keine, und die Reihenfolge der Testbausteine ist nichts, auf
    das man sich verlassen sollte, wenn man sie auch hinschreiben kann.
    """
    assert hoeren.post("/api/auswertung/start").status_code == 200
    ende = time.monotonic() + 20.0
    while time.monotonic() < ende:
        if not hoeren.get("/api/auswertung").json()["stand"]["laeuft"]:
            return
    raise AssertionError("Die Grundlinie wurde nicht fertig.")


def _lauf_fertigstellen(
    datenverzeichnis: Path, job_id: str, sprecher_id: str, *, genauigkeit: float
) -> str:
    """Nachstellen, was ein durchgelaufener Trainer hinterlässt."""
    verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job_id)
    zeilen = [
        json.loads(zeile)
        for zeile in (verzeichnis / laeufe.MANIFEST).read_text(encoding="utf-8").splitlines()
    ]
    for zeile in zeilen:
        if zeile["split"] != laeufe.TEST:
            continue
        laeufe.haenge_an(
            verzeichnis / laeufe.BEWERTUNG,
            {
                "recording_id": zeile["recording_id"],
                "variante": zeile["variante"],
                "text": zeile["text"],
                "wer": 0.1,
                "cer": 0.05,
                "mer": 0.1,
                "wil": 0.15,
                "genauigkeit": genauigkeit,
                "rechenzeit_s": 0.4,
            },
        )

    version = f"20260912T1200-lora-original-{genauigkeit:.0f}"
    registry.schreibe_stand(
        datenverzeichnis,
        {
            "id": f"{sprecher_id}/{version}",
            "sprecher_id": sprecher_id,
            "basismodell": "openai/whisper-small",
            "methode": "lora",
            "daten": "original",
            "job_id": job_id,
            "erstellt": "2026-09-12T12:00:00+00:00",
            "metriken": {"wer": 0.1, "genauigkeit": genauigkeit, "test_einheiten": 8},
            "status": "fertig",
        },
    )
    laeufe.schreibe_json(
        verzeichnis / laeufe.ZUSTAND,
        {"status": laeufe.FERTIG, "beendet": laeufe.jetzt(), "version": version},
    )
    return version


@pytest.fixture
def fertiger_lauf(klient: TestClient, aufnahmen: list[str], datenverzeichnis, sprecher: str):
    lauf = klient.post(
        "/lernen/api/laeufe", json={"methode": "lora", "daten": "original"}
    ).json()
    version = _lauf_fertigstellen(
        datenverzeichnis, lauf["job_id"], sprecher, genauigkeit=88.0
    )
    return lauf["job_id"], version


class TestVergleich:
    def test_stellt_jede_fassung_der_grundlinie_gegenueber(
        self, klient: TestClient, grundlinie: None, fertiger_lauf
    ) -> None:
        job_id, _ = fertiger_lauf
        antwort = klient.get(f"/lernen/api/laeufe/{job_id}").json()

        assert set(antwort["vergleich"]) == set(augmentierung.VARIANTEN)
        genauigkeit = next(
            eintrag
            for eintrag in antwort["vergleich"]["original"]
            if eintrag["mass"] == "genauigkeit"
        )
        # Der Platzhalter hört Unsinn, der nachgestellte Stand trifft fast -
        # also hat sich etwas verbessert.
        assert genauigkeit["trainiert"] == pytest.approx(88.0)
        assert genauigkeit["grundlinie"] < genauigkeit["trainiert"]
        assert genauigkeit["besser"] is True

    def test_bei_den_fehlerraten_ist_kleiner_besser(
        self, klient: TestClient, grundlinie: None, fertiger_lauf
    ) -> None:
        job_id, _ = fertiger_lauf
        antwort = klient.get(f"/lernen/api/laeufe/{job_id}").json()
        wer = next(e for e in antwort["vergleich"]["original"] if e["mass"] == "wer")
        assert wer["trainiert"] < wer["grundlinie"]
        assert wer["besser"] is True

    def test_ohne_grundlinie_gibt_es_nichts_zu_vergleichen(
        self, klient: TestClient, fertiger_lauf
    ) -> None:
        # Die Auswertung in „hören" ist hier nie gelaufen. Dann steht der
        # trainierte Stand allein da - und die Ansicht behauptet keine
        # Verbesserung gegen eine Zahl, die es nicht gibt.
        job_id, _ = fertiger_lauf
        assert klient.get(f"/lernen/api/laeufe/{job_id}").json()["vergleich"] == {}

    def test_verglichen_wird_nur_was_beide_gemessen_haben(
        self, klient: TestClient, grundlinie: None, fertiger_lauf
    ) -> None:
        job_id, _ = fertiger_lauf
        antwort = klient.get(f"/lernen/api/laeufe/{job_id}").json()
        anzahlen = {
            eintrag["anzahl"]
            for eintraege in antwort["vergleich"].values()
            for eintrag in eintraege
        }
        # Je Fassung dieselbe Zahl auf beiden Seiten - sonst stünde ein Mittel
        # über zwanzig gegen eines über achtzehn.
        assert anzahlen and 0 not in anzahlen


class TestModellstaende:
    def test_ein_fertiger_lauf_erscheint_in_der_liste(
        self, klient: TestClient, fertiger_lauf
    ) -> None:
        _, version = fertiger_lauf
        staende = klient.get("/lernen/api/modelle").json()["staende"]
        assert [stand["version"] for stand in staende] == [version]
        # Die Beschriftung nennt alle vier unterscheidenden Angaben.
        assert "lora" in staende[0]["beschriftung"].lower()
        assert "Originale" in staende[0]["beschriftung"]

    def test_fertig_heisst_noch_nicht_freigegeben(
        self, klient: TestClient, fertiger_lauf
    ) -> None:
        # Zwischen „hat gerechnet" und „damit diktiere ich" liegt der Blick auf
        # die Zahlen.
        assert klient.get("/lernen/api/modelle").json()["staende"][0]["status"] == "fertig"

    def test_freigeben_zieht_jeden_anderen_zurueck(
        self, klient: TestClient, fertiger_lauf, datenverzeichnis, sprecher: str
    ) -> None:
        _, erste = fertiger_lauf
        zweiter = klient.post(
            "/lernen/api/laeufe", json={"methode": "full", "daten": "augmentiert"}
        ).json()
        zweite = _lauf_fertigstellen(
            datenverzeichnis, zweiter["job_id"], sprecher, genauigkeit=91.0
        )

        assert klient.post(f"/lernen/api/modelle/{erste}/freigabe").status_code == 200
        antwort = klient.post(f"/lernen/api/modelle/{zweite}/freigabe").json()

        nach_version = {stand["version"]: stand["status"] for stand in antwort["staende"]}
        assert nach_version[zweite] == "active"
        assert nach_version[erste] == "zurueckgezogen"
        # Und die Registry selbst sagt dasselbe - das Manifest ist die Wahrheit.
        aktiv = registry.aktiver_stand(datenverzeichnis, sprecher)
        assert aktiv is not None and aktiv["id"].endswith(zweite)

    def test_unbekannter_stand_ist_vierhundertvier(self, klient: TestClient) -> None:
        assert klient.post("/lernen/api/modelle/gibtesnicht/freigabe").status_code == 404
