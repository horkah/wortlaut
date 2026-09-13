"""Aufnehmen, Prüfen, Verwerfen - und was die Warteschlange daraus macht.

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
from wortlaut import audio, augmentierung, corpus

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


class TestGestreuteReihenfolge:
    """`zufall=true`: dieselbe Auswahl, gemischt statt der Reihe nach."""

    def test_ohne_schalter_bleibt_es_bei_der_reihenfolge(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        # Vorgabe ist aus: Wer nichts einstellt, bekommt den Text wie gehabt.
        ausschnitt = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        assert ausschnitt["aktuell"]["text"].startswith("Der Hund")

    def test_streut_ueber_alle_aktiven_quellen(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        klient.post(
            f"/api/sources/upload?sprecher={sprecher}",
            files={"datei": ("zweite.txt", "Ein Satz aus der zweiten Quelle.".encode(), "text/plain")},
        )
        # Über alle Sitzungen hinweg darf nicht immer dieselbe Einheit oben
        # liegen - sonst wäre der Schalter wirkungslos.
        gesehen: set[str] = set()
        for _ in range(12):
            sitzung = klient.post(f"/api/sessions?sprecher={sprecher}").json()["id"]
            gesehen.add(
                klient.get(
                    f"/api/prompts/next?sprecher={sprecher}&session={sitzung}&zufall=true"
                ).json()["aktuell"]["id"]
            )
        assert len(gesehen) > 1

    def test_bleibt_innerhalb_einer_sitzung_stehen(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        # Der wichtigste Teil: Ein Neuladen darf einem den Satz nicht wegreißen.
        sitzung = klient.post(f"/api/sessions?sprecher={sprecher}").json()["id"]
        adresse = f"/api/prompts/next?sprecher={sprecher}&session={sitzung}&zufall=true"
        zuerst = klient.get(adresse).json()["aktuell"]["id"]
        for _ in range(5):
            assert klient.get(adresse).json()["aktuell"]["id"] == zuerst

    def test_rueckt_nach_einer_aufnahme_vor(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        sitzung = klient.post(f"/api/sessions?sprecher={sprecher}").json()["id"]
        adresse = f"/api/prompts/next?sprecher={sprecher}&session={sitzung}&zufall=true"

        vorher = klient.get(adresse).json()
        nimm_auf(klient, sprecher, vorher["aktuell"]["id"], audio_datei, session=sitzung)

        danach = klient.get(adresse).json()
        assert danach["aktuell"]["id"] != vorher["aktuell"]["id"]
        # Das eben Gesprochene steht als Davor - der gemischte Ablauf, nicht
        # der Nachbar im Text.
        assert danach["vorher"]["id"] == vorher["aktuell"]["id"]
        assert danach["erledigt"] == 1

    def test_zaehler_meinen_dieselbe_menge(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        der_reihe_nach = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        gestreut = klient.get(f"/api/prompts/next?sprecher={sprecher}&zufall=true").json()
        assert gestreut["gesamt"] == der_reihe_nach["gesamt"]

    def test_abgestellte_quelle_bleibt_auch_gestreut_draussen(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        klient.patch(f"/api/sources/{quelle}?sprecher={sprecher}", json={"aktiv": False})
        ausschnitt = klient.get(f"/api/prompts/next?sprecher={sprecher}&zufall=true").json()
        assert ausschnitt["aktuell"] is None

    def test_am_ende_bleibt_nichts_offen(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        adresse = f"/api/prompts/next?sprecher={sprecher}&zufall=true"
        while (ausschnitt := klient.get(adresse).json())["aktuell"] is not None:
            nimm_auf(klient, sprecher, ausschnitt["aktuell"]["id"], audio_datei)
        assert ausschnitt["erledigt"] == ausschnitt["gesamt"]


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


class TestFassungenAnhoeren:
    """Nicht nur das Original - auch die abgewandelten Fassungen sind hörbar.

    Die Auswertung stellt neben jede Fassung, was die Modelle aus ihr gemacht
    haben. Die interessanteste Frage dabei ist, ob man selbst noch versteht,
    was ein Modell nicht mehr verstand - und die beantwortet keine Zahl,
    sondern nur das Rauschen selbst.
    """

    def test_das_original_ist_die_vorgabe(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        aufnahme = nimm_auf(klient, sprecher, einheit["id"], audio_datei)

        ohne = klient.get(f"/api/recordings/{aufnahme['id']}/audio")
        mit = klient.get(f"/api/recordings/{aufnahme['id']}/audio?fassung=original")

        assert ohne.status_code == 200
        assert mit.status_code == 200
        assert ohne.content == mit.content

    def test_jede_abwandlung_laesst_sich_hoeren(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        # Die Fassungen entstehen beim Hochladen (`services/augmentierung.py`).
        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        aufnahme = nimm_auf(klient, sprecher, einheit["id"], audio_datei)
        original = klient.get(f"/api/recordings/{aufnahme['id']}/audio").content

        for abwandlung in augmentierung.ABWANDLUNGEN:
            antwort = klient.get(
                f"/api/recordings/{aufnahme['id']}/audio?fassung={abwandlung.name}"
            )
            assert antwort.status_code == 200, abwandlung.name
            # Abgewandelt heißt abgewandelt: Käme hier dasselbe zurück, wäre
            # der Abspieler eine Behauptung.
            assert antwort.content != original, abwandlung.name

    def test_eine_unbekannte_fassung_ist_vierhundertvier(
        self, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        # Der Name landet im Dateipfad - was hier nicht geprüft würde, wäre ein
        # Weg, fremde Dateien auszuliefern.
        einheit = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()["aktuell"]
        aufnahme = nimm_auf(klient, sprecher, einheit["id"], audio_datei)

        for unfug in ("gibtsnicht", "../../etc/passwd"):
            antwort = klient.get(f"/api/recordings/{aufnahme['id']}/audio?fassung={unfug}")
            assert antwort.status_code == 404, unfug


class TestVorlesen:
    """Die Wege zum Vorlesen - und dass sie ohne Stimme still bleiben.

    Ohne abgelegte Stimme gibt es nichts zu sprechen. Beide Wege antworten
    dann mit 404, und das ist keine Störung, sondern die Ansage an die
    Oberfläche: nimm die Browserstimme (`packages/ui/speak.ts`).
    """

    def test_ohne_stimmen_ist_die_liste_leer(self, klient: TestClient) -> None:
        antwort = klient.get("/api/vorlesen/stimmen")
        assert antwort.status_code == 200
        assert antwort.json() == []

    def test_ohne_stimme_gibt_es_keine_vorlesung(
        self, klient: TestClient, sprecher: str, quelle: str
    ) -> None:
        naechste = klient.get(f"/api/prompts/next?sprecher={sprecher}").json()
        vorlage = naechste["aktuell"]["id"]
        antwort = klient.get(
            f"/api/prompts/{vorlage}/vorlesung?stimme=piper/de_DE-thorsten-high"
        )
        assert antwort.status_code == 404

    def test_eine_fremde_vorlage_bleibt_fremd(self, klient: TestClient) -> None:
        antwort = klient.get("/api/prompts/prm_gibtsnicht/vorlesung?stimme=piper/x")
        assert antwort.status_code == 404

    def test_ohne_zugang_kein_vorlesen(self, klient_ohne_token: TestClient) -> None:
        assert klient_ohne_token.get("/api/vorlesen/stimmen").status_code == 401
        assert klient_ohne_token.get("/api/vorlesen/probe?stimme=piper/x").status_code == 401
