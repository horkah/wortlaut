"""Aussteuern vor dem Erkennen - eine Hörhilfe, kein Eingriff in den Datensatz.

Der Aufnahmepegel eines Browsers hängt am Gerät, am Abstand und an der Stimme.
Bei leisen Aufnahmen schöpft Whisper den Wertebereich nicht aus, den seine
Merkmalsberechnung erwartet; vor allem die kleineren Modelle hören dann
schlechter. Vor dem Erkennen wird deshalb lauter gerechnet - als Vorgabe und
abschaltbar.

Die Zusage, die dabei am leichtesten bricht und am spätesten auffiele: **Nur
die gehörte Fassung ist ausgesteuert.** Was abgelegt und später als Korrektur
an „hören" gegeben wird, ist die Aufnahme, wie sie gesprochen wurde. Sonst
wäre das, was drüben als „Original" im Korpus landet, schon bearbeitet - und
die Abwandlung `pegel`, die „hören" daraus rechnet, ein Nichts.
"""

from __future__ import annotations

import array
import shutil
import wave
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from wortlaut import audio, augmentierung

if TYPE_CHECKING:  # nur für die Typen - zur Laufzeit kommt der Ersatz als Fixture
    from apps.schreiben.tests.conftest import Testtranskriptor


def _spitze(wav: Path) -> int:
    with wave.open(str(wav), "rb") as datei:
        werte = array.array("h")
        werte.frombytes(datei.readframes(datei.getnframes()))
    return max(max(werte), -min(werte))


# Wohin `pegel` die Spitze legt: knapp unter den Anschlag.
ZIEL = audio.VOLLAUSSCHLAG * 10 ** (augmentierung.ZIEL_SPITZE_DBFS / 20)


@pytest.fixture
def leise_aufnahme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wav_schreiben, _umgebung: None
) -> int:
    """Statt der Vorgabe eine ausgesprochen leise Aufnahme; gibt ihre Spitze zurück."""
    vorlage = wav_schreiben(tmp_path / "leise.wav", sekunden=8.0, amplitude=2000)
    monkeypatch.setattr(audio, "wandle_in_wav", lambda quelle, ziel: shutil.copy(vorlage, ziel))
    return _spitze(vorlage)


class TestVorgabe:
    def test_ist_an(self, klient: TestClient) -> None:
        assert klient.get("/schreiben/api/model").json()["aussteuern"] is True

    def test_whisper_hoert_die_ausgesteuerte_fassung(
        self,
        klient: TestClient,
        sitzung: str,
        aufnahme: dict,
        whisper: Testtranskriptor,
        leise_aufnahme: int,
    ) -> None:
        klient.post(f"/schreiben/api/sessions/{sitzung}/segments", files=aufnahme)

        assert leise_aufnahme < ZIEL / 2  # die Vorlage war wirklich leise
        assert whisper.gehoerte_spitze == pytest.approx(ZIEL, rel=0.02)

    def test_abgelegt_wird_die_aufnahme_wie_gesprochen(
        self,
        klient: TestClient,
        sitzung: str,
        aufnahme: dict,
        audioverzeichnis: Path,
        leise_aufnahme: int,
    ) -> None:
        # Die Zusage, an der alles hängt: Was von hier nach „hören" geht, muss
        # dort ein echtes Original sein.
        klient.post(f"/schreiben/api/sessions/{sitzung}/segments", files=aufnahme)

        abschnitte = sorted(audioverzeichnis.glob("*.wav"))
        assert abschnitte
        for ausschnitt in abschnitte:
            assert _spitze(ausschnitt) <= leise_aufnahme

    def test_auch_beim_neu_einsprechen(
        self,
        klient: TestClient,
        diktat: dict,
        aufnahme: dict,
        whisper: Testtranskriptor,
        audioverzeichnis: Path,
        leise_aufnahme: int,
    ) -> None:
        abschnitt = diktat["abschnitte"][0]["id"]
        antwort = klient.post(f"/schreiben/api/segments/{abschnitt}/neu", files=aufnahme)
        assert antwort.status_code == 200, antwort.text

        assert whisper.gehoerte_spitze == pytest.approx(ZIEL, rel=0.02)
        assert _spitze(audioverzeichnis / f"{abschnitt}.wav") == leise_aufnahme


class TestAbgeschaltet:
    def test_whisper_hoert_dann_die_rohe_aufnahme(
        self,
        klient: TestClient,
        sitzung: str,
        aufnahme: dict,
        whisper: Testtranskriptor,
        leise_aufnahme: int,
    ) -> None:
        assert klient.put("/schreiben/api/model", json={"aussteuern": False}).status_code == 200

        klient.post(f"/schreiben/api/sessions/{sitzung}/segments", files=aufnahme)
        assert whisper.gehoerte_spitze == leise_aufnahme

    def test_die_einstellung_haelt(self, klient: TestClient) -> None:
        klient.put("/schreiben/api/model", json={"aussteuern": False})
        assert klient.get("/schreiben/api/model").json()["aussteuern"] is False

        klient.put("/schreiben/api/model", json={"aussteuern": True})
        assert klient.get("/schreiben/api/model").json()["aussteuern"] is True


class TestZweiStellschrauben:
    """Modell und Aufbereitung stehen nebeneinander und fassen sich nicht an."""

    def test_der_schalter_setzt_die_modellwahl_nicht_zurueck(
        self, klient: TestClient
    ) -> None:
        klient.put("/schreiben/api/model", json={"ref": "medium"})
        antwort = klient.put("/schreiben/api/model", json={"aussteuern": False}).json()

        assert antwort["ref"] == "medium"
        assert antwort["aussteuern"] is False

    def test_die_modellwahl_setzt_den_schalter_nicht_zurueck(
        self, klient: TestClient
    ) -> None:
        klient.put("/schreiben/api/model", json={"aussteuern": False})
        antwort = klient.put("/schreiben/api/model", json={"ref": "medium"}).json()

        assert antwort["aussteuern"] is False
        assert antwort["basismodell"] == "medium"

    def test_zurueck_zur_vorgabe_laesst_den_schalter_stehen(
        self, klient: TestClient
    ) -> None:
        # Ein leeres `ref` heißt „zurück zur Vorgabe" und nicht „alles zurück".
        klient.put("/schreiben/api/model", json={"aussteuern": False, "ref": "medium"})
        antwort = klient.put("/schreiben/api/model", json={"ref": ""}).json()

        assert antwort["gewaehlt"] is False
        assert antwort["aussteuern"] is False
