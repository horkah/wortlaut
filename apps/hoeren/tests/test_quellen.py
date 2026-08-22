"""Textquellen: Upload, LLM-Schalter, Reihenfolge der entstehenden Vorlagen."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class TestUpload:
    def test_erzeugt_sprecheinheiten(self, klient: TestClient, sprecher: str, quelle: str) -> None:
        liste = klient.get(f"/api/sources?sprecher={sprecher}").json()
        assert len(liste) == 1
        assert liste[0]["art"] == "upload"
        assert liste[0]["einheiten"] > 1

    def test_zweite_quelle_haengt_hinten_an(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        vorher = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()

        klient.post(
            f"/api/sources/upload?sprecher={sprecher}",
            files={"datei": ("mehr.txt", b"Ein ganz neuer Satz kommt hinzu.", "text/plain")},
        )

        # Die Warteschlange arbeitet weiter vorne ab, statt vorzuspringen.
        danach = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        assert danach["aktuell"]["id"] == vorher["aktuell"]["id"]
        assert danach["gesamt"] > vorher["gesamt"]

    def test_lehnt_unbekanntes_format_ab(self, klient: TestClient, sprecher: str) -> None:
        antwort = klient.post(
            f"/api/sources/upload?sprecher={sprecher}",
            files={"datei": ("lied.mp3", b"...", "audio/mpeg")},
        )
        assert antwort.status_code == 400

    def test_lehnt_leeren_text_ab(self, klient: TestClient, sprecher: str) -> None:
        antwort = klient.post(
            f"/api/sources/upload?sprecher={sprecher}",
            files={"datei": ("leer.txt", b"   \n  ", "text/plain")},
        )
        assert antwort.status_code == 400


class TestLLM:
    def test_ohne_anbieter_klare_ansage(self, klient: TestClient, sprecher: str) -> None:
        # WORTLAUT_LLM_PROVIDER ist im Test leer: die Quelle ist abgeschaltet.
        antwort = klient.post(
            f"/api/sources/llm?sprecher={sprecher}",
            json={"thema": "Einkaufen", "altersspanne": "Erwachsene", "umfang": 200},
        )
        assert antwort.status_code == 400
        assert "WORTLAUT_LLM_PROVIDER" in antwort.json()["detail"]

    def test_erzeugt_vorlagen_aus_dem_gelieferten_text(
        self, klient: TestClient, sprecher: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Der Anbieter selbst wird nicht angerufen: geprüft wird der Weg vom
        # gelieferten Text zu den Vorlagen.
        from apps.hoeren.backend.api import sources

        monkeypatch.setattr(
            sources.llm,
            "erzeuge_text",
            lambda *_, **__: "Auf dem Markt gibt es Obst. Der Stand nebenan verkauft Blumen.",
        )

        antwort = klient.post(
            f"/api/sources/llm?sprecher={sprecher}",
            json={"thema": "Wochenmarkt", "altersspanne": "8-12", "umfang": 120},
        )

        assert antwort.status_code == 201
        assert antwort.json()["art"] == "llm"
        assert antwort.json()["titel"] == "Wochenmarkt"
        assert antwort.json()["einheiten"] >= 1


class TestTextAnsehen:
    def test_liefert_die_einheiten_der_reihe_nach(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        # Nicht das Original, sondern das Geschnittene — genau das wird
        # vorgesprochen.
        antwort = klient.get(f"/api/sources/{quelle}/text?sprecher={sprecher}")
        assert antwort.status_code == 200
        assert antwort.headers["content-type"].startswith("text/plain")

        vorlagen = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        assert vorlagen["aktuell"]["text"] in antwort.text

    def test_fremde_quelle_ist_unbekannt(self, klient: TestClient, sprecher: str) -> None:
        assert klient.get(f"/api/sources/src_gibtsnicht/text?sprecher={sprecher}").status_code == 404


class TestAbstellen:
    def test_neue_quelle_ist_aktiv(self, klient: TestClient, sprecher: str, quelle: str) -> None:
        assert klient.get(f"/api/sources?sprecher={sprecher}").json()[0]["aktiv"] is True

    def test_abgestellte_quelle_verlaesst_die_warteschlange(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        vorher = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        assert vorher["aktuell"] is not None

        antwort = klient.patch(f"/api/sources/{quelle}?sprecher={sprecher}", json={"aktiv": False})
        assert antwort.status_code == 200
        assert antwort.json()["aktiv"] is False

        # Die einzige Quelle ist abgestellt: nichts mehr vorzusprechen, und der
        # Zähler behauptet auch nichts anderes.
        danach = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        assert danach["aktuell"] is None
        assert danach["gesamt"] == 0

    def test_wieder_aufnehmen_stellt_die_einheiten_zurueck(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        vorher = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        klient.patch(f"/api/sources/{quelle}?sprecher={sprecher}", json={"aktiv": False})
        klient.patch(f"/api/sources/{quelle}?sprecher={sprecher}", json={"aktiv": True})

        danach = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        assert danach["aktuell"]["id"] == vorher["aktuell"]["id"]
        assert danach["gesamt"] == vorher["gesamt"]

    def test_offene_einheiten_zaehlen_die_abgestellte_nicht_mit(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        klient.patch(f"/api/sources/{quelle}?sprecher={sprecher}", json={"aktiv": False})
        fortschritt = klient.get(f"/api/progress?sprecher={sprecher}").json()
        assert fortschritt["offene_einheiten"] == 0


class TestLoeschen:
    def test_entfernt_quelle_und_einheiten(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        assert klient.delete(f"/api/sources/{quelle}?sprecher={sprecher}").status_code == 204
        assert klient.get(f"/api/sources?sprecher={sprecher}").json() == []

        # Mit der Quelle gehen ihre Einheiten; die Warteschlange ist leer.
        danach = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        assert danach["aktuell"] is None
        assert danach["gesamt"] == 0

    def test_mit_aufnahme_wird_nicht_geloescht(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        # Das Audio ist der Ertrag der Arbeit — es darf nicht an einer
        # Aufräumaktion hängen.
        vorlage = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]["id"]
        klient.post(
            f"/api/recordings?sprecher={sprecher}",
            files=audio_datei,
            data={"prompt_id": vorlage, "modus": "gelesen"},
        )

        antwort = klient.delete(f"/api/sources/{quelle}?sprecher={sprecher}")
        assert antwort.status_code == 409
        # Die Meldung muss den Ausweg nennen, nicht nur das Nein.
        assert "stattdessen ab" in antwort.json()["detail"]
        assert len(klient.get(f"/api/sources?sprecher={sprecher}").json()) == 1

    def test_verworfene_aufnahme_steht_nicht_im_weg(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        # Ihr Audio ist bereits gelöscht; die Zeile ist nur noch ein Vermerk.
        vorlage = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]["id"]
        aufnahme = klient.post(
            f"/api/recordings?sprecher={sprecher}",
            files=audio_datei,
            data={"prompt_id": vorlage, "modus": "gelesen"},
        ).json()["id"]
        klient.delete(f"/api/recordings/{aufnahme}?sprecher={sprecher}")

        assert klient.delete(f"/api/sources/{quelle}?sprecher={sprecher}").status_code == 204

    def test_unbekannte_quelle(self, klient: TestClient, sprecher: str) -> None:
        assert klient.delete(f"/api/sources/src_gibtsnicht?sprecher={sprecher}").status_code == 404
