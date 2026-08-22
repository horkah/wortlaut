"""Korrekturen von „schreiben" annehmen.

Zwei Zusagen an die dortige Outbox: Wiederholungen legen nichts doppelt an, und
Korrekturen bleiben als schwächere Daten erkennbar. Dazu die dritte, die aus
dem Zugang folgt: In welchen Korpus geschrieben wird, entscheidet der Zugang
und nicht die Adresse.
"""

from __future__ import annotations

from collections.abc import Callable

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


class TestFalschKonfiguriert:
    """„schreiben" mit dem Zugang des einen und der Kennung des anderen.

    Das ist der Weg, auf dem Gesundheitsdaten früher still in einen fremden
    Korpus gewandert wären: „schreiben" nennt seinen `WORTLAUT_SPRECHER_ID`,
    und „hören" schrieb dorthin. Jetzt hält „hören" die Behauptung gegen den
    Zugang aus `WORTLAUT_INTAKE_TOKEN`.
    """

    def test_fremde_kennung_wird_abgewiesen(
        self,
        verwalter: TestClient,
        klient: TestClient,
        klient_fuer: Callable[[str], TestClient],
        audio_datei: dict,
    ) -> None:
        fremd = verwalter.post(
            "/api/speakers", json={"name": "Andere", "basismodell": "openai/whisper-small"}
        ).json()["id"]

        antwort = klient.post(
            f"/api/korpus/intake?sprecher={fremd}",
            files=audio_datei,
            data={"text": "Gehört woandershin.", "externe_id": "seg_1"},
        )

        # 403 heißt für den Postausgang: Eintrag bleibt offen, Grund steht in
        # der Zeile. Nichts geht verloren, und nichts landet falsch.
        assert antwort.status_code == 403
        assert klient_fuer(fremd).get("/api/progress").json()["aufnahmen"] == 0
