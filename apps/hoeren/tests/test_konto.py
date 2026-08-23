"""Ein Sprecher sieht sich selbst - dieselben Zahlen wie die Aufsicht, aber nur die eigenen.

`/api/konto/…` nennt keine Kennung in der Adresse: Sie kommt aus dem
vorgelegten Zugang, genau wie bei jedem anderen Weg dieser App. Ein zweiter
Sprecher, der denselben Weg mit seinem eigenen Zugang ruft, sieht darum
zwangsläufig nur seine eigenen Daten - das prüft `test_sieht_nur_die_eigenen_aufnahmen`.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient


def _sitzung_mit_aufnahme(klient: TestClient, audio_datei: dict) -> str:
    """Eine Sitzung, in der auch gesprochen wurde; gibt deren Kennung zurück."""
    sitzung = klient.post("/api/sessions").json()["id"]
    naechste = klient.get(f"/api/prompts/next?session={sitzung}").json()["aktuell"]
    antwort = klient.post(
        "/api/recordings",
        files=audio_datei,
        data={"prompt_id": naechste["id"], "modus": "gelesen", "session": sitzung},
    )
    assert antwort.status_code == 201, antwort.text
    return sitzung


class TestZugriff:
    def test_ohne_zugang_kein_zugriff(self, klient_ohne_token: TestClient) -> None:
        assert klient_ohne_token.get("/api/konto").status_code == 401

    def test_verwaltung_kommt_nicht_heran(self, verwalter: TestClient) -> None:
        # Die Verwaltung führt keinen eigenen Sprecher - sie legt Profile an.
        assert verwalter.get("/api/konto").status_code == 401

    def test_aufsicht_kommt_nicht_heran(self, aufsicht: TestClient) -> None:
        # Die Aufsicht hat ebenfalls keinen eigenen Sprecher; sie sieht über
        # `/api/admin/…`, nicht über den eigenen Weg eines Sprechers.
        assert aufsicht.get("/api/konto").status_code == 401


class TestEigeneDaten:
    def test_zeigt_profil_und_quellen(self, klient: TestClient, quelle: str) -> None:
        konto = klient.get("/api/konto").json()
        assert konto["sprecher"]["name"] == "Testperson"
        assert [q["art"] for q in konto["quellen"]] == ["upload"]

    def test_sieht_nur_die_eigenen_aufnahmen(
        self,
        klient_fuer: Callable[[str], TestClient],
        verwalter: TestClient,
        klient: TestClient,
        quelle: str,
        audio_datei: dict,
    ) -> None:
        naechste = klient.get("/api/prompts/next").json()["aktuell"]
        antwort = klient.post(
            "/api/recordings",
            files=audio_datei,
            data={"prompt_id": naechste["id"], "modus": "gelesen"},
        )
        assert antwort.status_code == 201

        zweiter = verwalter.post(
            "/api/speakers", json={"name": "Andere", "basismodell": "openai/whisper-small"}
        ).json()["id"]
        with klient_fuer(zweiter) as andere:
            seite = andere.get("/api/konto/recordings").json()
            assert seite["gesamt"] == 0

        eigene = klient.get("/api/konto/recordings").json()
        assert eigene["gesamt"] == 1
        assert eigene["aufnahmen"][0]["text"]

    def test_sitzungen_werden_geseitet(
        self, klient: TestClient, quelle: str, audio_datei: dict
    ) -> None:
        for _ in range(3):
            _sitzung_mit_aufnahme(klient, audio_datei)

        erste_seite = klient.get("/api/konto/sessions?ab=0&anzahl=2").json()
        assert erste_seite["gesamt"] == 3
        assert len(erste_seite["sitzungen"]) == 2

        zweite_seite = klient.get("/api/konto/sessions?ab=2&anzahl=2").json()
        assert len(zweite_seite["sitzungen"]) == 1

    def test_sitzungen_ohne_aufnahme_bleiben_draussen(
        self, klient: TestClient, quelle: str, audio_datei: dict
    ) -> None:
        """Wer die Aufnahmeseite nur geöffnet hat, hat hier nichts erlebt.

        Eine Sitzung entsteht schon beim Öffnen des Reiters
        (`Aufnahme.svelte: beginne`). In den eigenen Daten stünde sie dann
        zwischen den Sitzungen, in denen wirklich gesprochen wurde - der
        Aufsicht bleibt sie erhalten, siehe
        `test_aufsicht.py::test_sitzungen_werden_geseitet`.
        """
        gesprochen = _sitzung_mit_aufnahme(klient, audio_datei)
        leer = klient.post("/api/sessions").json()["id"]

        seite = klient.get("/api/konto/sessions").json()
        assert seite["gesamt"] == 1
        assert [eintrag["id"] for eintrag in seite["sitzungen"]] == [gesprochen]
        assert leer not in [eintrag["id"] for eintrag in seite["sitzungen"]]

    def test_kennzahl_sitzungen_zaehlt_wie_die_liste(
        self, klient: TestClient, quelle: str, audio_datei: dict
    ) -> None:
        # Sonst nennte die Kachel eine Zahl, die sich darunter nicht
        # wiederfinden lässt - und das liest sich wie ein Fehler.
        _sitzung_mit_aufnahme(klient, audio_datei)
        klient.post("/api/sessions")

        assert klient.get("/api/konto").json()["sprecher"]["kennzahlen"]["sitzungen"] == 1
        assert klient.get("/api/konto/sessions").json()["gesamt"] == 1

    def test_anhoeren_und_verwerfen_bleiben_bei_recordings(
        self, klient: TestClient, quelle: str, audio_datei: dict
    ) -> None:
        # Kein eigener Weg unter `/api/konto/…` dafür - die bestehenden,
        # ebenfalls sprecherbezogenen Wege genügen (siehe `konto.py`).
        naechste = klient.get("/api/prompts/next").json()["aktuell"]
        aufnahme = klient.post(
            "/api/recordings",
            files=audio_datei,
            data={"prompt_id": naechste["id"], "modus": "gelesen"},
        ).json()

        eigene = klient.get("/api/konto/recordings").json()["aufnahmen"][0]
        assert eigene["id"] == aufnahme["id"]
        assert klient.get(f"/api/recordings/{aufnahme['id']}/audio").status_code == 200

        assert klient.delete(f"/api/recordings/{aufnahme['id']}").status_code == 204
        nach_dem_verwerfen = klient.get("/api/konto/recordings").json()["aufnahmen"][0]
        assert nach_dem_verwerfen["status"] == "verworfen"


class TestPin:
    def test_ohne_pin_ist_offen(self, klient: TestClient) -> None:
        assert klient.get("/api/konto/pin").json() == {"gesetzt": False}
        assert klient.get("/api/konto").status_code == 200

    def test_gesetzte_pin_sperrt_die_lesenden_wege(self, klient: TestClient) -> None:
        assert klient.patch("/api/konto/pin", json={"pin": "1234"}).json() == {"gesetzt": True}
        assert klient.get("/api/konto/pin").json() == {"gesetzt": True}

        assert klient.get("/api/konto").status_code == 401
        assert klient.get("/api/konto/sessions").status_code == 401
        assert klient.get("/api/konto/recordings").status_code == 401

        assert klient.get("/api/konto", headers={"X-Pin": "0000"}).status_code == 401
        assert klient.get("/api/konto", headers={"X-Pin": "1234"}).status_code == 200

    def test_pin_wieder_entfernen(self, klient: TestClient) -> None:
        klient.patch("/api/konto/pin", json={"pin": "1234"})
        assert klient.patch("/api/konto/pin", json={"pin": None}).json() == {"gesetzt": False}
        assert klient.get("/api/konto").status_code == 200

    def test_pin_muss_vier_ziffern_haben(self, klient: TestClient) -> None:
        for ungueltig in ("123", "12345", "abcd", ""):
            antwort = klient.patch("/api/konto/pin", json={"pin": ungueltig})
            assert antwort.status_code == 422

    def test_setzen_und_entfernen_verlangt_die_alte_pin_nicht(self, klient: TestClient) -> None:
        # Bewusst so: Die eigene PIN zu ändern ist nicht das Versehen, gegen
        # das sie schützt (siehe `services/pin.py`).
        klient.patch("/api/konto/pin", json={"pin": "1234"})
        assert klient.patch("/api/konto/pin", json={"pin": "5678"}).json() == {"gesetzt": True}
        assert klient.get("/api/konto", headers={"X-Pin": "5678"}).status_code == 200

    def test_aufsicht_setzt_und_entfernt_ohne_die_alte_zu_kennen(
        self, aufsicht: TestClient, klient: TestClient, sprecher: str
    ) -> None:
        klient.patch("/api/konto/pin", json={"pin": "1234"})

        antwort = aufsicht.patch(f"/api/admin/speakers/{sprecher}/pin", json={"pin": "5678"})
        assert antwort.json() == {"gesetzt": True}
        assert klient.get("/api/konto", headers={"X-Pin": "5678"}).status_code == 200
        assert klient.get("/api/konto", headers={"X-Pin": "1234"}).status_code == 401

        aufsicht.patch(f"/api/admin/speakers/{sprecher}/pin", json={"pin": None})
        assert klient.get("/api/konto").status_code == 200

    def test_pin_gesetzt_steht_im_profil(self, aufsicht: TestClient, klient: TestClient) -> None:
        klient.patch("/api/konto/pin", json={"pin": "1234"})
        einsicht = aufsicht.get("/api/admin/speakers").json()
        assert einsicht[0]["pin_gesetzt"] is True


class TestSelbstVerwalten:
    """Umbenennen und Ausleiten kann jeder über die eigenen Daten.

    Der Unterschied zur Aufsicht ist nicht, *was* geht, sondern *wessen* Daten
    es trifft: Hier steht keine Kennung in der Adresse (siehe `api/konto.py`).
    Was der eigenen Ansicht fehlt, sind allein die beiden Löschstufen „alle
    Aufnahmen" und „diesen Sprecher vollständig".
    """

    def test_umbenennen_aendert_nur_den_namen(self, klient: TestClient, sprecher: str) -> None:
        antwort = klient.patch("/api/konto", json={"name": "Neuer Name"})
        assert antwort.status_code == 200
        assert antwort.json()["name"] == "Neuer Name"
        # Die Kennung bleibt, was sie ist - sie steckt im ausgegebenen Zugang.
        assert antwort.json()["id"] == sprecher
        assert klient.get("/api/konto").json()["sprecher"]["name"] == "Neuer Name"

    def test_leerer_name_wird_abgewiesen(self, klient: TestClient) -> None:
        for ungueltig in ("", "   "):
            assert klient.patch("/api/konto", json={"name": ungueltig}).status_code == 422

    def test_sicherung_und_datensatz_kommen_als_archiv(
        self, klient: TestClient, quelle: str, audio_datei: dict
    ) -> None:
        naechste = klient.get("/api/prompts/next").json()["aktuell"]
        klient.post(
            "/api/recordings",
            files=audio_datei,
            data={"prompt_id": naechste["id"], "modus": "gelesen"},
        )

        sicherung = klient.get("/api/konto/sicherung")
        assert sicherung.status_code == 200
        assert sicherung.headers["content-type"] == "application/gzip"
        assert sicherung.content[:2] == b"\x1f\x8b"  # gzip

        datensatz = klient.get("/api/konto/datensatz")
        assert datensatz.status_code == 200
        assert datensatz.content[:2] == b"PK"  # zip

    def test_loeschstufen_der_aufsicht_gibt_es_hier_nicht(self, klient: TestClient) -> None:
        # Weder alle Aufnahmen noch sich selbst - dafür gibt es unter
        # `/api/konto/…` gar keinen Weg.
        assert klient.delete("/api/konto/recordings").status_code == 405
        assert klient.delete("/api/konto").status_code == 405

    def test_die_pin_sperrt_auch_umbenennen_und_ausleiten(self, klient: TestClient) -> None:
        klient.patch("/api/konto/pin", json={"pin": "2468"})

        assert klient.patch("/api/konto", json={"name": "Fremd"}).status_code == 401
        assert klient.get("/api/konto/sicherung").status_code == 401
        assert klient.get("/api/konto/datensatz").status_code == 401

        mit = {"X-Pin": "2468"}
        assert klient.patch("/api/konto", json={"name": "Ich"}, headers=mit).status_code == 200
        assert klient.get("/api/konto/sicherung", headers=mit).status_code == 200
