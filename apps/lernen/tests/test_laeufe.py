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
    def test_jede_aufnahme_traegt_genau_eine_faltung(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        # Die Zusage, an der alles hängt: Eine Aufnahme wird in genau einer
        # Faltung gemessen und in den anderen fünf gelernt. Trüge sie zwei,
        # hörte ein Modell die Aufnahme, an der es gemessen wird - und das
        # sieht gut aus.
        sprich(12)
        lauf = _beauftrage(klient, "lora", "augmentiert")

        zeilen = _manifest(datenverzeichnis, lauf["job_id"])
        je_aufnahme: dict[str, set[int]] = {}
        for zeile in zeilen:
            je_aufnahme.setdefault(zeile["recording_id"], set()).add(zeile["faltung"])
        assert je_aufnahme
        assert all(len(faltungen) == 1 for faltungen in je_aufnahme.values())

    def test_die_faltungen_folgen_der_reihenfolge(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        # 1, 2, 3, 4, 5, 6, 1, 2, … - und keine Aufnahme bleibt ohne.
        sprich(12)
        lauf = _beauftrage(klient, "lora", "original")

        zeilen = _manifest(datenverzeichnis, lauf["job_id"])
        vergeben = sorted({z["faltung"] for z in zeilen})
        assert vergeben == list(range(laeufe.FALTUNGEN))

    def test_alle_fassungen_stehen_im_manifest(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        # Auch beim Lauf „nur Originale": Gemessen wird immer auf allen
        # Fassungen, gelernt je nach Auftrag - und die Auswahl trifft der
        # Trainer, nicht das Manifest. Der Schnappschuss ist der Korpus, nicht
        # die Anweisung.
        sprich(6)
        for daten in ("original", "augmentiert"):
            zeilen = _manifest(datenverzeichnis, _beauftrage(klient, "lora", daten)["job_id"])
            assert {z["variante"] for z in zeilen} == set(augmentierung.VARIANTEN)

    def test_das_manifest_ist_fuer_beide_datensaetze_dasselbe(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        sprich(6)
        schlicht = _manifest(datenverzeichnis, _beauftrage(klient, "lora", "original")["job_id"])
        reich = _manifest(datenverzeichnis, _beauftrage(klient, "lora", "augmentiert")["job_id"])
        assert len(schlicht) == len(reich)

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


class TestLoeschen:
    """Ersatzlos - und ohne etwas Zeigendes zurückzulassen.

    Ein Lauf hängt an drei Dingen: seinem Verzeichnis, dem Modell, das aus ihm
    entstand, und der Aufteilung, aus der er seine Proben zog. Die ersten
    beiden gehören ihm und gehen mit. Die dritte gehört den Aufnahmen und
    bleibt - sie mit zu löschen hieße, sie beim nächsten Lauf neu zu würfeln
    und damit Testaufnahmen ins Training zu lassen, die vorher geprüft haben.
    """

    def test_ein_wartender_verschwindet_ganz(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"])
        assert verzeichnis.is_dir()

        antwort = klient.delete(f"/lernen/api/laeufe/{lauf['job_id']}")
        assert antwort.status_code == 200, antwort.text
        assert antwort.json()["version"] == ""

        assert not verzeichnis.exists()
        assert klient.get("/lernen/api/laeufe").json()["laeufe"] == []
        assert klient.get(f"/lernen/api/laeufe/{lauf['job_id']}").status_code == 404

    def test_er_steht_danach_nicht_mehr_in_der_warteschlange(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        # Genau das liest der Läufer im Trainings-Container ab.
        sprich(6)
        lauf = _beauftrage(klient)
        klient.delete(f"/lernen/api/laeufe/{lauf['job_id']}")
        assert laeufe.naechster_offener(datenverzeichnis) is None

    def test_das_modell_geht_mit(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis, sprecher: str
    ) -> None:
        # Bliebe es stehen, zeigte es auf ein Verzeichnis, das es nicht mehr
        # gibt - und worauf es trainiert wurde, wäre nicht mehr zu beantworten.
        from wortlaut import registry

        sprich(6)
        lauf = _beauftrage(klient)
        version = "20260912T1200-lora-original"
        registry.schreibe_stand(
            datenverzeichnis,
            {
                "id": f"{sprecher}/{version}",
                "sprecher_id": sprecher,
                "job_id": lauf["job_id"],
                "methode": "lora",
                "daten": "original",
                "basismodell": "openai/whisper-small",
                "erstellt": "2026-09-12T12:00:00+00:00",
                "status": "fertig",
            },
        )
        eigene = [
            modell
            for modell in klient.get("/lernen/api/modelle").json()["modelle"]
            if modell["art"] == "trainiert"
        ]
        assert eigene

        antwort = klient.delete(f"/lernen/api/laeufe/{lauf['job_id']}").json()

        assert antwort["version"] == version
        assert antwort["war_freigegeben"] is False
        eigene = [
            modell
            for modell in klient.get("/lernen/api/modelle").json()["modelle"]
            if modell["art"] == "trainiert"
        ]
        assert eigene == []
        assert not registry.stand_verzeichnis(datenverzeichnis, sprecher, version).exists()

    def test_die_liste_sagt_vorher_was_mitginge(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis, sprecher: str
    ) -> None:
        # Die Oberfläche schreibt das in die Sicherheitsabfrage; sie soll dafür
        # nicht noch einmal nachfragen müssen.
        from wortlaut import registry

        sprich(6)
        lauf = _beauftrage(klient)
        registry.schreibe_stand(
            datenverzeichnis,
            {
                "id": f"{sprecher}/20260912T1200-lora-original",
                "job_id": lauf["job_id"],
                "status": "active",
            },
        )
        zeile = klient.get("/lernen/api/laeufe").json()["laeufe"][0]
        assert zeile["stand"] == {
            "version": "20260912T1200-lora-original",
            "freigegeben": True,
        }
        assert zeile["loeschbar"] is True

    def test_ohne_modell_steht_dort_nichts(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        _beauftrage(klient)
        assert klient.get("/lernen/api/laeufe").json()["laeufe"][0]["stand"] is None

    def test_ein_rechnender_laesst_sich_nicht_loeschen(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        # In sein Verzeichnis schreibt gerade ein anderer Container.
        sprich(6)
        lauf = _beauftrage(klient)
        laeufe.schreibe_json(
            laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"]) / laeufe.ZUSTAND,
            {"status": laeufe.LAEUFT, "stufe": "training"},
        )

        assert klient.get("/lernen/api/laeufe").json()["laeufe"][0]["loeschbar"] is False
        antwort = klient.delete(f"/lernen/api/laeufe/{lauf['job_id']}")
        assert antwort.status_code == 409
        assert laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"]).is_dir()

    def test_die_faltungen_bleiben_unberuehrt(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        # Läufe zu löschen fasst den Korpus nicht an - und damit auch die
        # Faltungen nicht, die aus seiner Reihenfolge kommen.
        sprich(9)
        vorher = klient.get("/lernen/api/aufteilung").json()
        for methode in ("lora", "full"):
            lauf = _beauftrage(klient, methode)
            assert klient.delete(f"/lernen/api/laeufe/{lauf['job_id']}").status_code == 200

        assert klient.get("/lernen/api/aufteilung").json() == vorher

    def test_unbekannter_lauf_ist_vierhundertvier(self, klient: TestClient) -> None:
        assert klient.delete("/lernen/api/laeufe/job_gibtesnicht").status_code == 404

    def test_zweimal_loeschen_geht_nicht(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        assert klient.delete(f"/lernen/api/laeufe/{lauf['job_id']}").status_code == 200
        assert klient.delete(f"/lernen/api/laeufe/{lauf['job_id']}").status_code == 404


class TestNeueAufnahmen:
    """Wie viele Aufnahmen ein Modell noch nicht kennt.

    Keine Automatik, sondern eine Zahl: Ein Lauf belegt die Karte und friert
    einen Stand des Korpus ein. Von selbst angestoßen wüsste hinterher niemand
    mehr, welche Aufnahmen in welchem Modell stecken.
    """

    def test_ohne_fertigen_lauf_zaehlt_alles_als_neu(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        antwort = klient.get("/lernen/api/laeufe").json()
        assert antwort["aufnahmen_jetzt"] == 6
        assert antwort["aufnahmen_neu"] == 6

    def test_nach_einem_fertigen_lauf_zaehlt_nur_das_danach(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        laeufe.schreibe_json(
            laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"]) / laeufe.ZUSTAND,
            {"status": laeufe.FERTIG, "version": "v1"},
        )
        assert klient.get("/lernen/api/laeufe").json()["aufnahmen_neu"] == 0

        sprich(3)
        antwort = klient.get("/lernen/api/laeufe").json()
        assert antwort["aufnahmen_jetzt"] == 9
        assert antwort["aufnahmen_neu"] == 3

    def test_ein_gescheiterter_lauf_zaehlt_nicht_als_stand(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        # Er sagt nichts darüber, was ein Modell kennt - es gibt keines.
        sprich(6)
        lauf = _beauftrage(klient)
        laeufe.schreibe_json(
            laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"]) / laeufe.ZUSTAND,
            {"status": laeufe.GESCHEITERT, "fehler": "irgendwas"},
        )
        assert klient.get("/lernen/api/laeufe").json()["aufnahmen_neu"] == 6

    def test_geloeschte_aufnahmen_ergeben_keine_negative_zahl(
        self, klient: TestClient, hoeren: TestClient, quelle: str, sprich, datenverzeichnis
    ) -> None:
        kennungen = sprich(6)
        lauf = _beauftrage(klient)
        laeufe.schreibe_json(
            laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"]) / laeufe.ZUSTAND,
            {"status": laeufe.FERTIG, "version": "v1"},
        )
        assert hoeren.delete(f"/api/recordings/{kennungen[0]}").status_code == 204

        antwort = klient.get("/lernen/api/laeufe").json()
        assert antwort["aufnahmen_jetzt"] == 5
        assert antwort["aufnahmen_neu"] == 0
