"""Einen Lauf beauftragen: was dabei auf die Platte kommt, und was nicht.

Trainiert wird hier nicht - das tut ein eigener Container mit einer Karte
(`apps/lernen/training/`). Geprüft wird der Weg davor und danach: dass der
Auftrag vollständig dasteht, dass das Manifest die Zusagen der Aufteilung
einhält, dass die Oberfläche den Stand daraus lesen kann und dass ein fremder
Lauf unsichtbar bleibt.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from wortlaut import augmentierung, laeufe


def _manifest(datenverzeichnis, job_id: str) -> list[dict]:
    pfad = laeufe.lauf_verzeichnis(datenverzeichnis, job_id) / laeufe.MANIFEST
    return [json.loads(zeile) for zeile in pfad.read_text(encoding="utf-8").splitlines()]


def _beauftrage(klient: TestClient, methode: str = "lora", daten: str = "original") -> dict:
    antwort = klient.post("/lernen/api/laeufe", json={"methode": methode, "daten": daten})
    assert antwort.status_code == 201, antwort.text
    return antwort.json()


class TestBeauftragen:
    def test_ohne_aufnahmen_gibt_es_nichts_zu_lernen(self, klient: TestClient) -> None:
        antwort = klient.post("/lernen/api/laeufe", json={"methode": "lora", "daten": "original"})
        assert antwort.status_code == 409
        assert not klient.get("/lernen/api/laeufe").json()["bereit"]

    def test_unbekannte_methode_wird_abgewiesen(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        antwort = klient.post(
            "/lernen/api/laeufe", json={"methode": "zauberei", "daten": "original"}
        )
        assert antwort.status_code == 400

    def test_der_auftrag_steht_vollstaendig_da(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient, "full", "augmentiert")

        verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"])
        auftrag = json.loads((verzeichnis / laeufe.AUFTRAG).read_text(encoding="utf-8"))
        assert auftrag["methode"] == "full"
        assert auftrag["daten"] == "augmentiert"
        assert auftrag["basismodell"] == "openai/whisper-small"
        # Die Zusage an die Löschung: `scripts/purge_speaker.py` findet den
        # Schnappschuss an dieser Datei, ohne das Manifest zu deuten.
        marke = (verzeichnis / laeufe.SPRECHER_MARKE).read_text(encoding="utf-8").strip()
        assert marke == auftrag["sprecher_id"]

    def test_ein_frischer_lauf_wartet(self, klient: TestClient, quelle: str, sprich) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        assert lauf["status"] == laeufe.WARTET
        assert lauf["version"] is None


class TestManifest:
    def test_keine_testaufnahme_im_training(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        # Die Zusage, an der alles hängt. Bricht sie, misst der Test das
        # Auswendiggelernte - und das sieht gut aus.
        sprich(12)
        lauf = _beauftrage(klient, "lora", "augmentiert")

        zeilen = _manifest(datenverzeichnis, lauf["job_id"])
        pruefend = {z["recording_id"] for z in zeilen if z["split"] == laeufe.TEST}
        lernend = {z["recording_id"] for z in zeilen if z["split"] != laeufe.TEST}
        assert pruefend and lernend
        assert not (pruefend & lernend)

    def test_nur_originale_heisst_nur_originale(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient, "lora", "original")
        zeilen = _manifest(datenverzeichnis, lauf["job_id"])

        gelernt = [z for z in zeilen if z["split"] != laeufe.TEST]
        assert {z["variante"] for z in gelernt} == {augmentierung.ORIGINAL}

    def test_mit_abwandlungen_heisst_viermal_so_viele_proben(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        sprich(6)
        schlicht = _manifest(datenverzeichnis, _beauftrage(klient, "lora", "original")["job_id"])
        reich = _manifest(datenverzeichnis, _beauftrage(klient, "lora", "augmentiert")["job_id"])

        gelernt = lambda zeilen: [z for z in zeilen if z["split"] != laeufe.TEST]  # noqa: E731
        assert len(gelernt(reich)) == 4 * len(gelernt(schlicht))

    def test_geprueft_wird_immer_auf_allen_vier_fassungen(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        # Auch beim Lauf „nur Originale": Die zu vergleichenden Modelle sollen
        # sich in ihren Trainingsdaten unterscheiden und in nichts sonst -
        # schon gar nicht in dem, woran sie gemessen werden.
        sprich(6)
        for daten in ("original", "augmentiert"):
            zeilen = _manifest(datenverzeichnis, _beauftrage(klient, "lora", daten)["job_id"])
            pruefend = [z for z in zeilen if z["split"] == laeufe.TEST]
            assert {z["variante"] for z in pruefend} == set(augmentierung.VARIANTEN)

    def test_jede_zeile_zeigt_auf_eine_vorhandene_datei(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis, sprecher: str
    ) -> None:
        from wortlaut import corpus

        sprich(6)
        lauf = _beauftrage(klient, "lora", "augmentiert")
        korpus = datenverzeichnis / corpus.sprecher_relpfad(sprecher)
        for zeile in _manifest(datenverzeichnis, lauf["job_id"]):
            assert (korpus / zeile["audio"]).is_file(), zeile["audio"]

    def test_der_text_steht_daneben(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient, "lora")
        for zeile in _manifest(datenverzeichnis, lauf["job_id"]):
            assert zeile["text"].strip()
            assert zeile["quelle"] == "vorlage"
            assert zeile["gewicht"] == 1.0


class TestListeUndAbbruch:
    def test_juengster_lauf_steht_oben(self, klient: TestClient, quelle: str, sprich) -> None:
        sprich(6)
        erster = _beauftrage(klient, "lora")
        zweiter = _beauftrage(klient, "full")
        kennungen = [lauf["job_id"] for lauf in klient.get("/lernen/api/laeufe").json()["laeufe"]]
        assert kennungen == [zweiter["job_id"], erster["job_id"]]

    def test_ein_wartender_laesst_sich_zuruecknehmen(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        antwort = klient.post(f"/lernen/api/laeufe/{lauf['job_id']}/abbruch")
        assert antwort.status_code == 200
        assert antwort.json()["status"] == laeufe.ABGEBROCHEN

    def test_ein_zurueckgenommener_wird_nicht_mehr_gerechnet(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        klient.post(f"/lernen/api/laeufe/{lauf['job_id']}/abbruch")
        # Genau das liest der Läufer im Trainings-Container ab.
        assert laeufe.naechster_offener(datenverzeichnis) is None

    def test_zweimal_zuruecknehmen_geht_nicht(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        klient.post(f"/lernen/api/laeufe/{lauf['job_id']}/abbruch")
        assert klient.post(f"/lernen/api/laeufe/{lauf['job_id']}/abbruch").status_code == 409

    def test_unbekannter_lauf_ist_vierhundertvier(self, klient: TestClient) -> None:
        assert klient.get("/lernen/api/laeufe/job_gibtesnicht").status_code == 404

    def test_die_warteschlange_ist_die_reihenfolge_der_auftraege(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        sprich(6)
        erster = _beauftrage(klient, "lora")
        _beauftrage(klient, "full")
        offen = laeufe.naechster_offener(datenverzeichnis)
        assert offen is not None and offen.job_id == erster["job_id"]
