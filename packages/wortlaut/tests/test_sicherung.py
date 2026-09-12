"""Was eine Sicherung auslässt - und was sie darüber dazuschreibt.

Der Weg über die Apps ist in `apps/hoeren/tests/test_aufsicht.py` geprüft;
hier steht das Archivformat für sich. Vor allem die beiden Fälle, die in
einem laufenden Bestand kaum je zusammenkommen: eine Datenbank, die die
ausgelassene Tabelle noch gar nicht hat, und ein Verzeichnisname, der nur so
anfängt wie ein ausgelassener.
"""

from __future__ import annotations

import sqlite3
import tarfile
from contextlib import closing
from pathlib import Path

import pytest
from wortlaut import sicherung


def _datenbank(pfad: Path, *, mit_tabelle: bool = True) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(pfad)) as verbindung:
        verbindung.execute("CREATE TABLE recordings (id TEXT PRIMARY KEY)")
        verbindung.execute("INSERT INTO recordings VALUES ('rec_1')")
        if mit_tabelle:
            verbindung.execute("CREATE TABLE erkennungen (id TEXT PRIMARY KEY)")
            verbindung.executemany(
                "INSERT INTO erkennungen VALUES (?)", [(f"erk_{n}",) for n in range(50)]
            )
        verbindung.commit()


def _bestand(wurzel: Path, *, mit_tabelle: bool = True) -> None:
    _datenbank(wurzel / "korpus/spr_a/hoeren.sqlite", mit_tabelle=mit_tabelle)
    (wurzel / "korpus/spr_a/audio").mkdir(parents=True, exist_ok=True)
    (wurzel / "korpus/spr_a/audio/rec_1.wav").write_bytes(b"gesprochen")
    (wurzel / "korpus/spr_a/audio/varianten").mkdir(parents=True, exist_ok=True)
    (wurzel / "korpus/spr_a/audio/varianten/rec_1.pegel.wav").write_bytes(b"gerechnet")


AUSGELASSEN = sicherung.Abgeleitetes(
    verzeichnisse=("korpus/spr_a/audio/varianten",),
    tabellen={"hoeren.sqlite": ("erkennungen",)},
)


def _namen(archiv: Path) -> list[str]:
    with tarfile.open(archiv, "r:gz") as geoeffnet:
        return geoeffnet.getnames()


class TestAuslassen:
    def test_ohne_angabe_wandert_alles_mit(self, tmp_path: Path) -> None:
        # Diese Datei entscheidet nicht, was gerechnet und was gesprochen ist.
        _bestand(tmp_path / "data")
        ziel = sicherung.schreibe_archiv(
            tmp_path / "data", ["korpus/spr_a"], tmp_path / "alles.tgz"
        )
        assert any("varianten" in name for name in _namen(ziel))

    def test_genanntes_verzeichnis_bleibt_draussen(self, tmp_path: Path) -> None:
        _bestand(tmp_path / "data")
        ziel = sicherung.schreibe_archiv(
            tmp_path / "data", ["korpus/spr_a"], tmp_path / "s.tgz", ohne=AUSGELASSEN
        )
        namen = _namen(ziel)
        assert not [name for name in namen if "varianten" in name]
        assert "daten/korpus/spr_a/audio/rec_1.wav" in namen

    def test_ein_aehnlicher_name_ist_kein_treffer(self, tmp_path: Path) -> None:
        # `varianten-alt/` ist nicht `varianten/`. Verglichen wird deshalb auf
        # der Grenze zwischen zwei Pfadstücken, nicht auf dem Zeichen davor.
        _bestand(tmp_path / "data")
        (tmp_path / "data/korpus/spr_a/audio/varianten-alt").mkdir()
        (tmp_path / "data/korpus/spr_a/audio/varianten-alt/rec_1.wav").write_bytes(b"ton")

        ziel = sicherung.schreibe_archiv(
            tmp_path / "data", ["korpus/spr_a"], tmp_path / "s.tgz", ohne=AUSGELASSEN
        )
        assert "daten/korpus/spr_a/audio/varianten-alt/rec_1.wav" in _namen(ziel)


class TestGeleerteTabellen:
    def test_die_tabelle_ist_leer_und_die_uebrigen_stehen(self, tmp_path: Path) -> None:
        _bestand(tmp_path / "data")
        archiv = sicherung.schreibe_archiv(
            tmp_path / "data", ["korpus/spr_a"], tmp_path / "s.tgz", ohne=AUSGELASSEN
        )
        sicherung.stelle_wieder_her(archiv, tmp_path / "neu")

        with closing(sqlite3.connect(tmp_path / "neu/korpus/spr_a/hoeren.sqlite")) as verbindung:
            assert verbindung.execute("SELECT count(*) FROM erkennungen").fetchone()[0] == 0
            assert verbindung.execute("SELECT count(*) FROM recordings").fetchone()[0] == 1

    def test_der_bestand_behaelt_seine_zeilen(self, tmp_path: Path) -> None:
        # Geleert wird die Sicherungskopie. Wer sichert, verliert nichts.
        _bestand(tmp_path / "data")
        sicherung.schreibe_archiv(
            tmp_path / "data", ["korpus/spr_a"], tmp_path / "s.tgz", ohne=AUSGELASSEN
        )
        with closing(sqlite3.connect(tmp_path / "data/korpus/spr_a/hoeren.sqlite")) as verbindung:
            assert verbindung.execute("SELECT count(*) FROM erkennungen").fetchone()[0] == 50

    def test_ein_unmoeglicher_name_bricht_ab(self, tmp_path: Path) -> None:
        # Laut statt still: Käme so ein Name durch, hieße es, dass Abgeleitetes
        # unbemerkt doch im Archiv landet.
        _bestand(tmp_path / "data")
        with pytest.raises(ValueError, match="Kein Tabellenname"):
            sicherung.schreibe_archiv(
                tmp_path / "data",
                ["korpus/spr_a"],
                tmp_path / "s.tgz",
                ohne=sicherung.Abgeleitetes(tabellen={"hoeren.sqlite": ("erkennungen; --",)}),
            )

    def test_eine_fehlende_tabelle_ist_kein_fehler(self, tmp_path: Path) -> None:
        # Eine Datenbank, die noch vor der betreffenden Migration steht, hat
        # schlicht nichts wegzulassen.
        _bestand(tmp_path / "data", mit_tabelle=False)
        archiv = sicherung.schreibe_archiv(
            tmp_path / "data", ["korpus/spr_a"], tmp_path / "s.tgz", ohne=AUSGELASSEN
        )
        sicherung.stelle_wieder_her(archiv, tmp_path / "neu")
        with closing(sqlite3.connect(tmp_path / "neu/korpus/spr_a/hoeren.sqlite")) as verbindung:
            assert verbindung.execute("SELECT count(*) FROM recordings").fetchone()[0] == 1


class TestManifest:
    def test_nennt_das_ausgelassene(self, tmp_path: Path) -> None:
        # Wer in einem Jahr auspackt, soll das Fehlende nicht für einen
        # Schaden halten.
        _bestand(tmp_path / "data")
        archiv = sicherung.schreibe_archiv(
            tmp_path / "data", ["korpus/spr_a"], tmp_path / "s.tgz", ohne=AUSGELASSEN
        )
        manifest = sicherung.lies_manifest(archiv)
        assert manifest["ausgelassen"] == {
            "verzeichnisse": ["korpus/spr_a/audio/varianten"],
            "tabellen": {"hoeren.sqlite": ["erkennungen"]},
        }

    def test_die_pruefsumme_gilt_der_gesicherten_datei(self, tmp_path: Path) -> None:
        # Die Datenbank im Archiv ist nicht die auf der Platte - geleert und
        # verdichtet. Die Prüfsumme muss die im Archiv meinen, sonst schlägt
        # jede spätere Kontrolle Alarm.
        _bestand(tmp_path / "data")
        archiv = sicherung.schreibe_archiv(
            tmp_path / "data", ["korpus/spr_a"], tmp_path / "s.tgz", ohne=AUSGELASSEN
        )
        angaben = sicherung.lies_manifest(archiv)["dateien"]
        sicherung.stelle_wieder_her(archiv, tmp_path / "neu")
        datenbank = tmp_path / "neu/korpus/spr_a/hoeren.sqlite"
        assert datenbank.stat().st_size == angaben["daten/korpus/spr_a/hoeren.sqlite"]["bytes"]
