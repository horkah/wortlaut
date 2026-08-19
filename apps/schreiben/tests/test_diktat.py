"""Sprechen und nachbessern.

Geprüft wird der Kern dieser App: Aus einer Aufnahme werden Abschnitte mit je
eigenem Audio, und ein einzelner Abschnitt lässt sich ersetzen, ohne die
anderen anzufassen.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from wortlaut.whisper import Abschnitt

if TYPE_CHECKING:  # nur für Editoren; zur Laufzeit reicht pytest die Fixtures durch
    from apps.schreiben.tests.conftest import Testtranskriptor


def audiodateien(verzeichnis: Path) -> list[Path]:
    return sorted(verzeichnis.glob("*.wav"))


class TestDiktieren:
    def test_zerlegt_die_aufnahme_in_abschnitte(self, diktat: dict) -> None:
        assert [a["text"] for a in diktat["abschnitte"]] == [
            "Ich möchte einen Kaffee.",
            "Mit wenig Milch.",
            "Und ein Stück Kuchen.",
        ]
        assert [a["position"] for a in diktat["abschnitte"]] == [1, 2, 3]
        assert all(a["herkunft"] == "initial" for a in diktat["abschnitte"])

    def test_legt_je_abschnitt_eine_wav_datei_an(
        self, diktat: dict, audioverzeichnis: Path
    ) -> None:
        # Jeder Abschnitt geht später einzeln als Korrekturpaar an „hören" —
        # ohne eigene Datei ginge das nicht.
        dateien = audiodateien(audioverzeichnis)
        assert len(dateien) == 3
        assert {datei.stem for datei in dateien} == {a["id"] for a in diktat["abschnitte"]}
        assert all(datei.stat().st_size > 0 for datei in dateien)

    def test_liefert_den_abschnitt_zum_anhoeren(self, klient: TestClient, diktat: dict) -> None:
        kennung = diktat["abschnitte"][0]["id"]
        antwort = klient.get(f"/api/segments/{kennung}/audio")
        assert antwort.status_code == 200
        assert antwort.content.startswith(b"RIFF")

    def test_weiteres_diktat_haengt_hinten_an(
        self, klient: TestClient, sitzung: str, diktat: dict, aufnahme: dict
    ) -> None:
        antwort = klient.post(f"/api/sessions/{sitzung}/segments", files=aufnahme)
        assert antwort.status_code == 201
        assert [a["position"] for a in antwort.json()["abschnitte"]] == [1, 2, 3, 4, 5, 6]

    def test_lehnt_leere_aufnahme_ab(self, klient: TestClient, sitzung: str) -> None:
        antwort = klient.post(
            f"/api/sessions/{sitzung}/segments",
            files={"audio": ("leer.webm", b"", "audio/webm")},
        )
        assert antwort.status_code == 400

    def test_meldet_wenn_nichts_verstanden_wurde(
        self, klient: TestClient, sitzung: str, aufnahme: dict, whisper: Testtranskriptor
    ) -> None:
        whisper.abschnitte = []
        antwort = klient.post(f"/api/sessions/{sitzung}/segments", files=aufnahme)
        assert antwort.status_code == 422

    def test_kennt_die_sitzung_nach_dem_neuladen(
        self, klient: TestClient, sitzung: str, diktat: dict
    ) -> None:
        antwort = klient.get(f"/api/sessions/{sitzung}")
        assert antwort.status_code == 200
        assert antwort.json() == diktat


class TestNeuEinsprechen:
    def test_ersetzt_nur_diesen_abschnitt(
        self, klient: TestClient, diktat: dict, aufnahme: dict, whisper: Testtranskriptor
    ) -> None:
        kennung = diktat["abschnitte"][1]["id"]
        whisper.abschnitte = [Abschnitt(start_s=0.0, ende_s=1.5, text="Mit viel Milch.")]

        antwort = klient.post(f"/api/segments/{kennung}/neu", files=aufnahme)

        assert antwort.status_code == 200
        abschnitte = antwort.json()["abschnitte"]
        assert [a["text"] for a in abschnitte] == [
            "Ich möchte einen Kaffee.",
            "Mit viel Milch.",
            "Und ein Stück Kuchen.",
        ]
        # Der neu gesprochene Abschnitt bleibt als solcher erkennbar.
        assert [a["herkunft"] for a in abschnitte] == ["initial", "neu", "initial"]

    def test_behaelt_die_zahl_der_audiodateien(
        self,
        klient: TestClient,
        diktat: dict,
        aufnahme: dict,
        audioverzeichnis: Path,
    ) -> None:
        kennung = diktat["abschnitte"][0]["id"]
        klient.post(f"/api/segments/{kennung}/neu", files=aufnahme)
        # Dieselbe Kennung, dieselbe Datei: die alte Aufnahme wird überschrieben.
        assert len(audiodateien(audioverzeichnis)) == 3

    def test_fasst_mehrere_segmente_zu_einem_abschnitt_zusammen(
        self, klient: TestClient, diktat: dict, aufnahme: dict, whisper: Testtranskriptor
    ) -> None:
        # Was der Mensch für einen Abschnitt gesprochen hat, ist der Abschnitt —
        # auch wenn Whisper darin zwei Segmente sieht.
        kennung = diktat["abschnitte"][0]["id"]
        whisper.abschnitte = [
            Abschnitt(start_s=0.0, ende_s=1.0, text="Ich hätte gern"),
            Abschnitt(start_s=1.0, ende_s=2.0, text="einen Tee."),
        ]

        antwort = klient.post(f"/api/segments/{kennung}/neu", files=aufnahme)

        assert antwort.json()["abschnitte"][0]["text"] == "Ich hätte gern einen Tee."

    def test_kennt_den_abschnitt_nicht(self, klient: TestClient, aufnahme: dict) -> None:
        antwort = klient.post("/api/segments/seg_gibtsnicht/neu", files=aufnahme)
        assert antwort.status_code == 404
