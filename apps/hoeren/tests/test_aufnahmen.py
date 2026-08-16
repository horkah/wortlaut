"""Aufnehmen, Prüfen, Verwerfen — und was die Warteschlange daraus macht.

Das ist der Kern der App: Die Position in der Warteschlange wird nirgends
gespeichert, sondern aus den vorhandenen Aufnahmen abgeleitet. Genau das wird
hier von allen Seiten geprüft.
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import audio, corpus

# Beim Einlesen dieser Datei gemerkt, also bevor conftest.py die Umwandlung für
# die übrigen Tests durch eine Kopie ersetzt.
ECHTE_UMWANDLUNG = audio.wandle_in_wav


def nimm_auf(
    klient: TestClient, sprecher: str, prompt_id: str, audio_datei: dict, **felder: str
) -> dict:
    antwort = klient.post(
        f"/api/recordings?sprecher={sprecher}",
        files=audio_datei,
        data={"prompt_id": prompt_id, "modus": "gelesen", **felder},
    )
    assert antwort.status_code == 201, antwort.text
    return antwort.json()


class TestWarteschlange:
    def test_beginnt_bei_der_ersten_einheit(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        ausschnitt = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        assert ausschnitt["vorher"] is None  # ganz am Anfang gibt es kein Davor
        assert ausschnitt["aktuell"]["text"].startswith("Der Hund")
        assert ausschnitt["nachher"] is not None
        assert ausschnitt["erledigt"] == 0

    def test_rueckt_nach_einer_aufnahme_vor(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        vorher = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        nimm_auf(klient, sprecher, vorher["aktuell"]["id"], audio_datei)

        danach = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        assert danach["aktuell"]["id"] != vorher["aktuell"]["id"]
        assert danach["vorher"]["id"] == vorher["aktuell"]["id"]  # Kontext stimmt
        assert danach["erledigt"] == 1

    def test_am_ende_bleibt_nichts_offen(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        while (ausschnitt := klient.get(f"/api/prompts/next?sprecher={sprecher}").json())[
            "aktuell"
        ]:
            nimm_auf(klient, sprecher, ausschnitt["aktuell"]["id"], audio_datei)

        assert ausschnitt["aktuell"] is None
        assert ausschnitt["erledigt"] == ausschnitt["gesamt"]

    def test_sitzung_haelt_die_stelle(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        sitzung = klient.post(f"/api/sessions?sprecher={sprecher}").json()["id"]
        erste = klient.get(f"/api/prompts/next?sprecher={sprecher}&session={sitzung}").json()
        nimm_auf(klient, sprecher, erste["aktuell"]["id"], audio_datei, session=sitzung)

        # Eine neue Sitzung setzt dort fort, wo die alte aufgehört hat.
        zweite_sitzung = klient.post(f"/api/sessions?sprecher={sprecher}").json()["id"]
        weiter = klient.get(
            f"/api/prompts/next?sprecher={sprecher}&session={zweite_sitzung}"
        ).json()
        assert weiter["erledigt"] == 1
        assert weiter["aktuell"]["id"] != erste["aktuell"]["id"]

    def test_unbekannte_sitzung_ist_ein_404(self, klient: TestClient, sprecher: str) -> None:
        antwort = klient.get(f"/api/prompts/next?sprecher={sprecher}&session=ses_gibtsnicht")
        assert antwort.status_code == 404


class TestAufnehmen:
    def test_speichert_messwerte_und_datei(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        aufnahme = nimm_auf(klient, sprecher, einheit["id"], audio_datei)

        assert aufnahme["dauer_s"] > 0
        assert aufnahme["pegel_dbfs"] < 0  # dBFS ist eine Dämpfung
        assert aufnahme["status"] == "ok"
        blob = tmp_path / "data" / corpus.audio_relpfad(sprecher, aufnahme["id"])
        assert blob.is_file()

    def test_gibt_hinweise_statt_abzulehnen(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        # Die Testaufnahme ist vier Sekunden lang; für eine lange Vorlage ist
        # das auffällig kurz. Auffällig heißt: Hinweis, nicht Ablehnung.
        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        aufnahme = nimm_auf(klient, sprecher, einheit["id"], audio_datei)

        assert aufnahme["status"] == "ok"
        if einheit["dauer_geschaetzt_s"] > 10:
            assert aufnahme["hinweise"]

    def test_merkt_sich_den_modus(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        aufnahme = nimm_auf(klient, sprecher, einheit["id"], audio_datei, modus="nachgesprochen")

        assert aufnahme["modus"] == "nachgesprochen"
        fortschritt = klient.get(f"/api/progress?sprecher={sprecher}").json()
        assert fortschritt["nach_modus"] == {"nachgesprochen": 1}

    def test_lehnt_unbekannten_modus_ab(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        antwort = klient.post(
            f"/api/recordings?sprecher={sprecher}",
            files=audio_datei,
            data={"prompt_id": einheit["id"], "modus": "gesungen"},
        )
        assert antwort.status_code == 400

    def test_lehnt_unbekannte_vorlage_ab(
        self, klient: TestClient, sprecher: str, audio_datei: dict
    ) -> None:
        antwort = klient.post(
            f"/api/recordings?sprecher={sprecher}",
            files=audio_datei,
            data={"prompt_id": "prm_gibtsnicht", "modus": "gelesen"},
        )
        assert antwort.status_code == 404

    def test_lehnt_leere_aufnahme_ab(self, klient: TestClient, sprecher: str, quelle: str) -> None:
        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        antwort = klient.post(
            f"/api/recordings?sprecher={sprecher}",
            files={"audio": ("leer.webm", b"", "audio/webm")},
            data={"prompt_id": einheit["id"], "modus": "gelesen"},
        )
        assert antwort.status_code == 400


class TestEchterWeg:
    """Einmal ohne Ersatz: vom Browser-Format bis zur Datei im Korpus."""

    @pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fehlt")
    def test_nimmt_opus_an_und_legt_16khz_mono_ab(
        self,
        klient: TestClient,
        sprecher: str,
        quelle: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        wav_schreiben,
    ) -> None:
        monkeypatch.setattr(audio, "wandle_in_wav", ECHTE_UMWANDLUNG)

        # So etwas liefert `MediaRecorder` im Browser: Opus in WebM, 48 kHz.
        quell_wav = wav_schreiben(tmp_path / "quelle.wav", abtastrate=48_000, sekunden=3.0)
        webm = tmp_path / "aufnahme.webm"
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(quell_wav),
                "-c:a",
                "libopus",
                str(webm),
            ],
            check=True,
        )

        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        aufnahme = nimm_auf(
            klient,
            sprecher,
            einheit["id"],
            {"audio": ("aufnahme.webm", webm.read_bytes(), "audio/webm")},
        )

        assert aufnahme["dauer_s"] == pytest.approx(3.0, abs=0.2)
        abgelegt = tmp_path / "data" / corpus.audio_relpfad(sprecher, aufnahme["id"])
        with wave.open(str(abgelegt), "rb") as datei:
            assert datei.getframerate() == audio.ABTASTRATE
            assert datei.getnchannels() == 1
            assert datei.getsampwidth() == 2


class TestVerwerfen:
    def test_loescht_das_audio_und_gibt_die_vorlage_frei(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        aufnahme = nimm_auf(klient, sprecher, einheit["id"], audio_datei)
        blob = tmp_path / "data" / corpus.audio_relpfad(sprecher, aufnahme["id"])

        assert (
            klient.delete(f"/api/recordings/{aufnahme['id']}?sprecher={sprecher}").status_code
            == 204
        )

        # Stimmaufnahmen sind Gesundheitsdaten: verworfen heißt wirklich weg.
        assert not blob.exists()
        danach = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        assert danach["aktuell"]["id"] == einheit["id"]
        assert danach["erledigt"] == 0
        assert klient.get(f"/api/progress?sprecher={sprecher}").json()["aufnahmen"] == 0

    def test_zweimal_verwerfen_ist_kein_fehler(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        aufnahme = nimm_auf(klient, sprecher, einheit["id"], audio_datei)

        for _ in range(2):
            antwort = klient.delete(f"/api/recordings/{aufnahme['id']}?sprecher={sprecher}")
            assert antwort.status_code == 204


class TestFortschritt:
    def test_zaehlt_sekunden_und_offene_einheiten(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        vorher = klient.get(f"/api/progress?sprecher={sprecher}").json()
        assert vorher["sekunden"] == 0
        assert vorher["offene_einheiten"] > 0

        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        nimm_auf(klient, sprecher, einheit["id"], audio_datei)

        danach = klient.get(f"/api/progress?sprecher={sprecher}").json()
        assert danach["sekunden"] > 0
        assert danach["aufnahmen"] == 1
        assert danach["offene_einheiten"] == vorher["offene_einheiten"] - 1

    def test_nennt_die_marken(self, klient: TestClient, sprecher: str) -> None:
        marken = klient.get(f"/api/progress?sprecher={sprecher}").json()
        assert marken["marke_brauchbar_s"] == 1.5 * 3600
        assert marken["marke_gut_s"] == 20 * 3600
