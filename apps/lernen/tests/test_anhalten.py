"""Anhalten und neu starten.

Anhalten geht über das Verzeichnis: Die Oberfläche legt `halt` hin, der
Läufer im Trainer-Container beendet den Prozess. Beide Seiten sind hier
geprüft - die des Läufers mit echten Unterprozessen, denn um deren Ende geht
es. Der Trainer selbst (`finetune.py`) braucht torch und läuft hier nicht.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import laeufe

from apps.lernen.training import laeufer


def _beauftrage(klient: TestClient, **weiteres: str) -> dict:
    antwort = klient.post(
        "/lernen/api/laeufe", json={"methode": "lora", **weiteres}
    )
    assert antwort.status_code == 201, antwort.text
    return antwort.json()


def _verzeichnis(datenverzeichnis: Path, job_id: str) -> Path:
    return laeufe.lauf_verzeichnis(datenverzeichnis, job_id)


def _setze(datenverzeichnis: Path, job_id: str, **zustand: object) -> None:
    laeufe.schreibe_json(_verzeichnis(datenverzeichnis, job_id) / laeufe.ZUSTAND, zustand)


def _in_der_liste(klient: TestClient, job_id: str) -> dict:
    return next(
        lauf for lauf in klient.get("/lernen/api/laeufe").json()["laeufe"]
        if lauf["job_id"] == job_id
    )


class TestAnhalten:
    def test_ein_rechnender_wird_ueber_den_trainer_angehalten(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis: Path
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        _setze(datenverzeichnis, lauf["job_id"], status=laeufe.LAEUFT, stufe="training")

        antwort = klient.post(f"/lernen/api/laeufe/{lauf['job_id']}/abbruch")

        assert antwort.status_code == 200
        # Der Zustand gehört dem rechnenden Prozess; bis der Läufer ihn
        # beendet, sagt er weiter `laeuft` - und die Ansicht, dass er anhält.
        assert antwort.json()["status"] == laeufe.LAEUFT
        assert antwort.json()["wird_angehalten"] is True
        assert laeufe.anhalten_verlangt(_verzeichnis(datenverzeichnis, lauf["job_id"]))

    def test_ein_haengender_ist_sofort_angehalten(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis: Path, monkeypatch
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        _setze(datenverzeichnis, lauf["job_id"], status=laeufe.LAEUFT, schritt=40)
        monkeypatch.setattr(laeufe, "STILLSTAND_S", -1)

        antwort = klient.post(f"/lernen/api/laeufe/{lauf['job_id']}/abbruch").json()

        assert antwort["status"] == laeufe.ABGEBROCHEN
        assert antwort["neu_startbar"] is True
        # Wo er stand, bleibt stehen.
        zustand = laeufe.lies_json(_verzeichnis(datenverzeichnis, lauf["job_id"]) / laeufe.ZUSTAND)
        assert zustand["schritt"] == 40

    def test_ein_fertiger_laesst_sich_nicht_anhalten(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis: Path
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        _setze(datenverzeichnis, lauf["job_id"], status=laeufe.FERTIG)
        assert klient.post(f"/lernen/api/laeufe/{lauf['job_id']}/abbruch").status_code == 409

    def test_angehaltene_und_gescheiterte_bleiben_stehen(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis: Path
    ) -> None:
        sprich(6)
        angehalten = _beauftrage(klient)
        gescheitert = _beauftrage(klient)
        klient.post(f"/lernen/api/laeufe/{angehalten['job_id']}/abbruch")
        _setze(datenverzeichnis, gescheitert["job_id"], status=laeufe.GESCHEITERT, fehler="kaputt")

        # Auch ein neuer Auftrag räumt sie nicht weg.
        _beauftrage(klient)

        assert _in_der_liste(klient, angehalten["job_id"])["status"] == laeufe.ABGEBROCHEN
        assert _in_der_liste(klient, gescheitert["job_id"])["status"] == laeufe.GESCHEITERT
        assert _in_der_liste(klient, angehalten["job_id"])["neu_startbar"] is True
        assert _in_der_liste(klient, gescheitert["job_id"])["neu_startbar"] is True


class TestNeustart:
    def test_der_neue_ersetzt_den_alten(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis: Path
    ) -> None:
        sprich(6)
        alt = _beauftrage(klient, abschluss="beides")
        _setze(datenverzeichnis, alt["job_id"], status=laeufe.GESCHEITERT, fehler="kaputt")
        altes_manifest = (_verzeichnis(datenverzeichnis, alt["job_id"]) / laeufe.MANIFEST).read_text(
            encoding="utf-8"
        )

        antwort = klient.post(f"/lernen/api/laeufe/{alt['job_id']}/neustart")

        assert antwort.status_code == 201, antwort.text
        neu = antwort.json()
        assert neu["job_id"] != alt["job_id"]
        assert neu["status"] == laeufe.WARTET
        # Derselbe Auftrag, derselbe Titel samt Folge - nur diesmal zu Ende.
        assert neu["code"] == alt["code"]
        assert neu["abschluss"] == "beides"
        verzeichnis = _verzeichnis(datenverzeichnis, neu["job_id"])
        assert (verzeichnis / laeufe.MANIFEST).read_text(encoding="utf-8") == altes_manifest
        assert laeufe.lies_json(verzeichnis / laeufe.AUFTRAG)["neu_von"] == alt["job_id"]
        assert not (verzeichnis / laeufe.ZUSTAND).exists()

        # Der alte ist weg, der neue steht in der Warteschlange.
        assert not _verzeichnis(datenverzeichnis, alt["job_id"]).exists()
        offen = laeufe.naechster_offener(datenverzeichnis)
        assert offen is not None and offen.job_id == neu["job_id"]

    def test_ein_angehaltener_ebenso(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis: Path
    ) -> None:
        sprich(6)
        alt = _beauftrage(klient)
        klient.post(f"/lernen/api/laeufe/{alt['job_id']}/abbruch")
        antwort = klient.post(f"/lernen/api/laeufe/{alt['job_id']}/neustart")
        assert antwort.status_code == 201
        # Der Wunsch anzuhalten gehörte dem alten und kommt nicht mit.
        assert not laeufe.anhalten_verlangt(_verzeichnis(datenverzeichnis, antwort.json()["job_id"]))

    def test_die_kernauswahl_kommt_mit(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis: Path
    ) -> None:
        sprich(6)
        alt = _beauftrage(klient)
        # Nachgestellt: ein Kernlauf mit seiner Auswahl.
        verzeichnis = _verzeichnis(datenverzeichnis, alt["job_id"])
        auftrag = laeufe.lies_json(verzeichnis / laeufe.AUFTRAG)
        laeufe.schreibe_json(verzeichnis / laeufe.AUFTRAG, {**auftrag, "auswahl": "kern"})
        laeufe.schreibe_json(verzeichnis / laeufe.KERNAUSWAHL, {"kern": ["rec_a"]})
        _setze(datenverzeichnis, alt["job_id"], status=laeufe.GESCHEITERT)

        neu = klient.post(f"/lernen/api/laeufe/{alt['job_id']}/neustart").json()

        neu_verzeichnis = _verzeichnis(datenverzeichnis, neu["job_id"])
        assert laeufe.kern_aus(
            neu_verzeichnis, laeufe.lies_json(neu_verzeichnis / laeufe.AUFTRAG)
        ) == {"rec_a"}

    @pytest.mark.parametrize("status", [laeufe.WARTET, laeufe.LAEUFT, laeufe.FERTIG])
    def test_nur_gescheiterte_und_angehaltene(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis: Path, status: str
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        _setze(datenverzeichnis, lauf["job_id"], status=status)
        assert klient.post(f"/lernen/api/laeufe/{lauf['job_id']}/neustart").status_code == 409
        assert _verzeichnis(datenverzeichnis, lauf["job_id"]).exists()

    def test_ohne_schluessel_kein_neustart(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis: Path
    ) -> None:
        sprich(6)
        lauf = _beauftrage(klient)
        _setze(datenverzeichnis, lauf["job_id"], status=laeufe.GESCHEITERT)
        antwort = klient.post(
            f"/lernen/api/laeufe/{lauf['job_id']}/neustart", headers={"X-Trainer-Key": ""}
        )
        assert antwort.status_code == 401
        assert _verzeichnis(datenverzeichnis, lauf["job_id"]).exists()


class TestLaeufer:
    """Die Seite im Trainer-Container - mit echten Prozessen."""

    @pytest.fixture
    def lauf(self, klient: TestClient, quelle: str, sprich, datenverzeichnis: Path):
        sprich(6)
        job_id = _beauftrage(klient)["job_id"]
        return laeufe.lies_lauf(datenverzeichnis, job_id)

    @staticmethod
    def _prozess(code: str) -> subprocess.Popen:
        return subprocess.Popen([sys.executable, "-c", code], start_new_session=True)

    def test_ohne_wunsch_laeuft_er_weiter(self, lauf, monkeypatch) -> None:
        monkeypatch.setattr(laeufer, "HALT_TAKT_S", 0.05)
        prozess = self._prozess("import time; time.sleep(0.5)")
        laeufer._wache(lauf, prozess)
        assert prozess.returncode == 0

    def test_der_wunsch_beendet_den_prozess(self, lauf, monkeypatch) -> None:
        monkeypatch.setattr(laeufer, "HALT_TAKT_S", 0.05)
        prozess = self._prozess("import time; time.sleep(60)")
        laeufe.verlange_anhalten(lauf.verzeichnis)
        begonnen = time.monotonic()
        laeufer._wache(lauf, prozess)
        assert prozess.wait(timeout=5) != 0
        assert time.monotonic() - begonnen < 5

    def test_wer_nicht_hoert_faellt_nach_der_frist(self, lauf, monkeypatch) -> None:
        monkeypatch.setattr(laeufer, "HALT_TAKT_S", 0.05)
        monkeypatch.setattr(laeufer, "GNADENFRIST_S", 0.3)
        # Ein Prozess, der SIGTERM übergeht - wie einer, der in einer Rechnung
        # auf der Karte steckt.
        prozess = self._prozess(
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
        )
        time.sleep(0.3)  # bis er das Signal wirklich übergeht
        laeufe.verlange_anhalten(lauf.verzeichnis)
        laeufer._wache(lauf, prozess)
        assert prozess.wait(timeout=5) == -9

    def test_danach_steht_er_als_angehalten(self, lauf) -> None:
        laeufe.schreibe_json(
            lauf.verzeichnis / laeufe.ZUSTAND, {"status": laeufe.LAEUFT, "faltung": 2}
        )
        laeufe.verlange_anhalten(lauf.verzeichnis)
        laeufer._nacharbeit(lauf, -9)
        zustand = laeufe.lies_json(lauf.verzeichnis / laeufe.ZUSTAND)
        assert zustand["status"] == laeufe.ABGEBROCHEN
        assert zustand["faltung"] == 2

    def test_ohne_wunsch_ist_ein_stummes_ende_gescheitert(self, lauf) -> None:
        laeufe.schreibe_json(lauf.verzeichnis / laeufe.ZUSTAND, {"status": laeufe.LAEUFT})
        laeufer._nacharbeit(lauf, -9)
        assert laeufe.lies_json(lauf.verzeichnis / laeufe.ZUSTAND)["status"] == laeufe.GESCHEITERT

    def test_angehalten_bevor_er_anfing(self, lauf, monkeypatch) -> None:
        # Der Wunsch kam, als der Lauf noch wartete - der Läufer startet ihn nicht.
        gestartet = []
        monkeypatch.setattr(laeufer, "_fuehre_aus", lambda lauf: gestartet.append(lauf) or 0)
        laeufe.verlange_anhalten(lauf.verzeichnis)
        assert laeufer.einmal() is True
        assert gestartet == []
        assert laeufe.lies_json(lauf.verzeichnis / laeufe.ZUSTAND)["status"] == laeufe.ABGEBROCHEN
