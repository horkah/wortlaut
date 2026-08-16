"""Korrekturen von „schreiben" annehmen.

Zwei Zusagen an die dortige Outbox: Wiederholungen legen nichts doppelt an, und
Korrekturen bleiben als schwächere Daten erkennbar.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def liefere_ein(
    klient: TestClient, sprecher: str, audio_datei: dict, *, text: str, externe_id: str
) -> dict:
    antwort = klient.post(
        f"/api/korpus/intake?sprecher={sprecher}",
        files=audio_datei,
        data={"text": text, "externe_id": externe_id},
    )
    assert antwort.status_code == 201, antwort.text
    return antwort.json()


class TestIntake:
    def test_legt_eine_korrektur_an(
        self, klient: TestClient, sprecher: str, audio_datei: dict
    ) -> None:
        ergebnis = liefere_ein(
            klient, sprecher, audio_datei, text="Ich möchte einen Kaffee.", externe_id="seg_1"
        )

        assert ergebnis["neu"] is True
        quellen = klient.get(f"/api/sources?sprecher={sprecher}").json()
        assert [quelle["art"] for quelle in quellen] == ["korrektur"]

    def test_wiederholung_legt_nichts_doppelt_an(
        self, klient: TestClient, sprecher: str, audio_datei: dict
    ) -> None:
        erst = liefere_ein(klient, sprecher, audio_datei, text="Zweimal.", externe_id="seg_1")
        nochmal = liefere_ein(klient, sprecher, audio_datei, text="Zweimal.", externe_id="seg_1")

        assert nochmal["neu"] is False
        assert nochmal["aufnahme_id"] == erst["aufnahme_id"]
        assert klient.get(f"/api/progress?sprecher={sprecher}").json()["aufnahmen"] == 1

    def test_sammelt_alle_korrekturen_in_einer_quelle(
        self, klient: TestClient, sprecher: str, audio_datei: dict
    ) -> None:
        liefere_ein(klient, sprecher, audio_datei, text="Erster Abschnitt.", externe_id="seg_1")
        liefere_ein(klient, sprecher, audio_datei, text="Zweiter Abschnitt.", externe_id="seg_2")

        quellen = klient.get(f"/api/sources?sprecher={sprecher}").json()
        assert len(quellen) == 1
        assert quellen[0]["einheiten"] == 2

    def test_bleibt_im_fortschritt_unterscheidbar(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        # Korrekturen sind schwächere Daten und bekommen im Rezept ein
        # niedrigeres Gewicht — dafür müssen sie zählbar getrennt bleiben.
        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        klient.post(
            f"/api/recordings?sprecher={sprecher}",
            files=audio_datei,
            data={"prompt_id": einheit["id"], "modus": "gelesen"},
        )
        liefere_ein(klient, sprecher, audio_datei, text="Eine Korrektur.", externe_id="seg_9")

        fortschritt = klient.get(f"/api/progress?sprecher={sprecher}").json()
        assert fortschritt["nach_quelle"] == {"upload": 1, "korrektur": 1}
        assert fortschritt["nach_modus"] == {"gelesen": 1, "frei": 1}

    def test_lehnt_leeren_text_ab(
        self, klient: TestClient, sprecher: str, audio_datei: dict
    ) -> None:
        antwort = klient.post(
            f"/api/korpus/intake?sprecher={sprecher}",
            files=audio_datei,
            data={"text": "   ", "externe_id": "seg_leer"},
        )
        assert antwort.status_code == 400
