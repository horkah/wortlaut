"""Kennungen, Datenbank, Blob-Ablage, Korpus-Layout, Modell-Registry.

Alles kleine Bausteine — geprüft wird jeweils nur die Zusage, auf die sich der
Rest des Systems verlässt.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from wortlaut import corpus, db, ids, registry, storage

MIGRATION = """
CREATE TABLE beispiel (id TEXT PRIMARY KEY);
INSERT INTO beispiel (id) VALUES ('eins');
"""


class TestIds:
    def test_traegt_das_praefix(self) -> None:
        assert ids.neue_id("rec").startswith("rec_")

    def test_ist_eindeutig(self) -> None:
        assert len({ids.neue_id("prm") for _ in range(500)}) == 500

    def test_sortiert_sich_grob_zeitlich(self) -> None:
        # Auf die Millisekunde genau, nicht feiner: innerhalb einer Millisekunde
        # entscheidet der Zufallsteil. Verzeichnislisten reicht das.
        folge = []
        for _ in range(5):
            folge.append(ids.neue_id("ses"))
            time.sleep(0.002)
        assert folge == sorted(folge)


class TestDatenbank:
    def test_wendet_migrationen_genau_einmal_an(self, tmp_path: Path) -> None:
        verzeichnis = tmp_path / "migrations"
        verzeichnis.mkdir()
        (verzeichnis / "001_init.sql").write_text(MIGRATION, encoding="utf-8")
        datenbank = tmp_path / "tief" / "test.sqlite"

        assert db.wende_migrationen_an(datenbank, verzeichnis) == ["001_init"]
        # Der zweite Lauf darf die Migration nicht wiederholen — sonst schlüge
        # das INSERT mit einem Schlüsselkonflikt fehl.
        assert db.wende_migrationen_an(datenbank, verzeichnis) == []

    def test_setzt_wal_und_fremdschluessel(self, tmp_path: Path) -> None:
        datenbank = tmp_path / "test.sqlite"
        sqlite3.connect(datenbank).close()
        engine = db.verbinde(datenbank)

        with engine.connect() as verbindung:
            journal = verbindung.exec_driver_sql("PRAGMA journal_mode").scalar()
            fremdschluessel = verbindung.exec_driver_sql("PRAGMA foreign_keys").scalar()

        assert journal == "wal"  # „lernen" liest, während „hören" schreibt
        assert fremdschluessel == 1


class TestAblage:
    def test_verschiebt_und_loescht(self, tmp_path: Path) -> None:
        ablage = storage.oeffne_ablage("local", tmp_path)
        quelle = tmp_path / "temp.wav"
        quelle.write_bytes(b"klang")

        ablage.lege_ab("korpus/spr_1/audio/rec_1.wav", quelle)

        assert ablage.pfad("korpus/spr_1/audio/rec_1.wav").read_bytes() == b"klang"
        assert not quelle.exists()  # verschoben, nicht kopiert

        ablage.loesche("korpus/spr_1/audio/rec_1.wav")
        assert not ablage.pfad("korpus/spr_1/audio/rec_1.wav").exists()
        ablage.loesche("korpus/spr_1/audio/rec_1.wav")  # zweimal löschen ist erlaubt

    def test_meldet_unbekannte_arten(self, tmp_path: Path) -> None:
        with pytest.raises(NotImplementedError):
            storage.oeffne_ablage("s3", tmp_path)
        with pytest.raises(ValueError):
            storage.oeffne_ablage("ftp", tmp_path)


class TestKorpus:
    def test_findet_nur_vollstaendige_korpora(self, tmp_path: Path) -> None:
        (tmp_path / "korpus" / "spr_1").mkdir(parents=True)
        (tmp_path / "korpus" / "spr_1" / corpus.DATENBANKNAME).touch()
        (tmp_path / "korpus" / "spr_2").mkdir()  # Verzeichnis ohne Datenbank

        assert corpus.sprecher_ids(tmp_path) == ["spr_1"]
        assert corpus.sprecher_ids(tmp_path / "leer") == []

    def test_legt_audio_unter_den_sprecher(self) -> None:
        assert corpus.audio_relpfad("spr_1", "rec_2") == "korpus/spr_1/audio/rec_2.wav"


class TestRegistry:
    def test_schreibt_und_liest_einen_modellstand(self, tmp_path: Path) -> None:
        registry.schreibe_stand(tmp_path, {"id": "spr_1/2026-08-15T1420", "status": "draft"})
        registry.schreibe_stand(tmp_path, {"id": "spr_1/2026-08-16T0900", "status": "active"})

        assert registry.lies_stand(tmp_path, "spr_1", "2026-08-15T1420")["status"] == "draft"
        assert len(registry.alle_staende(tmp_path, "spr_1")) == 2
        # „schreiben" wird auf genau einen Stand festgenagelt.
        assert registry.aktiver_stand(tmp_path, "spr_1")["id"] == "spr_1/2026-08-16T0900"

    def test_ohne_modelle_kein_aktiver_stand(self, tmp_path: Path) -> None:
        assert registry.aktiver_stand(tmp_path, "spr_unbekannt") is None
