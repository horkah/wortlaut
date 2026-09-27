"""Freigeben aus der Oberfläche und mit `make release` - eine Stelle (`services/freigabe.py`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from wortlaut import laeufe, registry

from apps.lernen.backend.services import freigabe

SPRECHER = "spr_01FREIGABE000000000000000"
VERSION = "20260927T2000-large-v3-lora-original"
REF = f"{SPRECHER}/{VERSION}"
JOB = "job_01FREIGABE00000000000000"


@pytest.fixture
def stand(_umgebung: None, datenverzeichnis: Path) -> Path:
    verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, JOB)
    verzeichnis.mkdir(parents=True)
    laeufe.schreibe_json(
        verzeichnis / laeufe.AUFTRAG, {"job_id": JOB, "sprecher_id": SPRECHER, "methode": "lora"}
    )
    laeufe.schreibe_json(verzeichnis / laeufe.ZUSTAND, {"status": laeufe.FERTIG, "version": VERSION})
    registry.schreibe_stand(
        datenverzeichnis,
        {"id": REF, "sprecher_id": SPRECHER, "job_id": JOB, "status": "fertig"},
    )
    return datenverzeichnis


class TestAusDemLauf:
    def test_der_stand_des_laufs(self, stand: Path) -> None:
        assert freigabe.stand_aus_lauf(stand, JOB)["id"] == REF

    def test_ein_unbekannter_lauf(self, stand: Path) -> None:
        with pytest.raises(freigabe.NichtFreigebbar, match="Kein Lauf"):
            freigabe.stand_aus_lauf(stand, "job_gibtesnicht")

    def test_ein_lauf_ohne_stand(self, stand: Path) -> None:
        verzeichnis = laeufe.lauf_verzeichnis(stand, "job_ohne")
        verzeichnis.mkdir(parents=True)
        laeufe.schreibe_json(verzeichnis / laeufe.AUFTRAG, {"job_id": "job_ohne", "sprecher_id": SPRECHER})
        with pytest.raises(freigabe.NichtFreigebbar, match="keinen Stand"):
            freigabe.stand_aus_lauf(stand, "job_ohne")


class TestFreigeben:
    def test_danach_gilt_er(self, stand: Path) -> None:
        freigabe.gib_frei(stand, SPRECHER, REF)
        assert registry.freigegeben(stand, SPRECHER) == REF
        assert registry.lies_stand(stand, SPRECHER, VERSION)["status"] == "active"

    def test_ein_grundmodell_geht_auch(self, stand: Path) -> None:
        freigabe.gib_frei(stand, SPRECHER, "medium")
        assert registry.freigegeben(stand, SPRECHER) == "medium"

    def test_was_nicht_zur_wahl_steht_nicht(self, stand: Path) -> None:
        with pytest.raises(freigabe.NichtFreigebbar):
            freigabe.gib_frei(stand, SPRECHER, "spr_fremd/irgendwas")
