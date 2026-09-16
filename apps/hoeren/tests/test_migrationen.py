"""Bestehende Korpora und ein neues Schema.

Der Test, der gefehlt hat. Alle anderen Tests legen ihren Sprecher über
`POST /api/speakers` an - und dort laufen die Migrationen mit. Damit prüft
jeder von ihnen dasselbe: eine Datenbank, die genau zum Schema dieses Standes
passt. Die Datenbank, die ein Update wirklich vorfindet, kam in keinem vor.

Genau daran ging es schief: Die PIN brachte `speakers.pin_hash` mit
(`004_pin.sql`), bestehende Korpora bekamen die Spalte nie, und danach
scheiterte jedes `SELECT` auf `speakers` - die Liste der Aufsicht ebenso wie
die Zugangsprüfung, mit der sich jeder Sprecher anmeldet. Die Testsammlung
blieb grün, weil sie den Fall nicht kannte.

Deshalb steht hier ein Korpus im ältesten Zustand, den es gibt: nur
`001_init.sql`. Der Test bleibt damit auch für die nächste Spalte gültig, ohne
dass jemand ihn anfassen muss - er nennt keine einzelne Migration beim Namen.

Eine Ausnahme steht unten: `006_ohne_tiny.sql` schreibt kein Schema fort,
sondern räumt Daten weg. Was löscht, wird namentlich geprüft.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import corpus, db

from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.db.models import jetzt

ALTBESTAND = "spr_altbestand"
MIT_TINY = "spr_mit_tiny"
# Die Migration, die `tiny` ausräumt - siehe `TestTinyWirdAusgeraeumt`.
OHNE_TINY = "006_ohne_tiny"


@pytest.fixture
def altkorpus(_umgebung: None, tmp_path: Path) -> str:
    """Ein Sprecher, dessen Datenbank auf dem Stand von `001_init` stehen blieb.

    Angelegt wird er an der API vorbei - über die API ginge es nicht, denn
    `POST /api/speakers` bringt gerade die Migrationen mit, um die es hier
    geht. Eingefügt wird mit rohem SQL und nur mit den Spalten aus `001_init`:
    Die Modelle aus `db/models.py` kennen bereits die neuen und wären in dieser
    Datenbank selbst das, was der Test prüfen soll.
    """
    konfiguration = einstellungen()

    nur_erste = tmp_path / "migrationen_001"
    nur_erste.mkdir()
    erste = sorted(konfiguration.migrationsverzeichnis.glob("*.sql"))[0]
    (nur_erste / erste.name).write_text(erste.read_text(encoding="utf-8"), encoding="utf-8")

    pfad = corpus.datenbank_pfad(konfiguration.data_dir, ALTBESTAND)
    assert db.wende_migrationen_an(pfad, nur_erste) == [erste.stem]

    with sqlite3.connect(pfad) as verbindung:
        verbindung.execute(
            "INSERT INTO speakers (id, name, sprache, basismodell, erstellt) VALUES (?, ?, ?, ?, ?)",
            (ALTBESTAND, "Altbestand", "de", "openai/whisper-small", jetzt()),
        )
    return ALTBESTAND


def _offene_migrationen(sprecher_id: str) -> set[str]:
    konfiguration = einstellungen()
    alle = {datei.stem for datei in konfiguration.migrationsverzeichnis.glob("*.sql")}
    pfad = corpus.datenbank_pfad(konfiguration.data_dir, sprecher_id)
    with sqlite3.connect(pfad) as verbindung:
        gelaufen = {
            zeile[0] for zeile in verbindung.execute("SELECT version FROM schema_migrations")
        }
    return alle - gelaufen


class TestAltbestandWirdEingeholt:
    def test_aufsicht_sieht_den_alten_sprecher(
        self, aufsicht: TestClient, altkorpus: str
    ) -> None:
        """Der gemeldete Fehler: in der Aufsicht war niemand mehr zu sehen."""
        antwort = aufsicht.get("/api/admin/speakers")
        assert antwort.status_code == 200
        assert [eintrag["id"] for eintrag in antwort.json()] == [altkorpus]

    def test_verwaltung_sieht_ihn_auch(self, verwalter: TestClient, altkorpus: str) -> None:
        antwort = verwalter.get("/api/speakers")
        assert antwort.status_code == 200
        assert [eintrag["id"] for eintrag in antwort.json()] == [altkorpus]

    def test_der_sprecher_kommt_wieder_herein(
        self, klient_fuer: Callable[[str], TestClient], altkorpus: str
    ) -> None:
        """Ein Zugang für einen alten Korpus - ausgeben, vorlegen, hereinkommen.

        Das ist der Weg, der bei einer fehlenden Spalte ebenfalls bricht: Die
        Zugangsprüfung liest den Sprecher, bevor sie irgendetwas anderes tut.
        """
        with klient_fuer(altkorpus) as klient:
            assert klient.get("/api/konto").status_code == 200

    def test_die_neuen_wege_stehen_offen(
        self, klient_fuer: Callable[[str], TestClient], altkorpus: str
    ) -> None:
        """Was die jüngste Migration mitbrachte, gilt auch für alte Korpora."""
        with klient_fuer(altkorpus) as klient:
            assert klient.get("/api/konto/pin").json() == {"gesetzt": False}
            assert klient.patch("/api/konto/pin", json={"pin": "1234"}).status_code == 200
            assert klient.get("/api/konto", headers={"X-Pin": "1234"}).status_code == 200

    def test_danach_ist_nichts_mehr_offen(self, aufsicht: TestClient, altkorpus: str) -> None:
        assert _offene_migrationen(altkorpus)  # vor dem ersten Zugriff
        assert aufsicht.get("/api/admin/speakers").status_code == 200
        assert _offene_migrationen(altkorpus) == set()

    def test_die_alten_daten_bleiben(self, aufsicht: TestClient, altkorpus: str) -> None:
        """Migrieren heißt fortschreiben, nicht neu anlegen."""
        antwort = aufsicht.get(f"/api/admin/speakers/{altkorpus}")
        assert antwort.status_code == 200
        assert antwort.json()["sprecher"]["name"] == "Altbestand"


class TestKeinKorpusAusVersehen:
    def test_unbekannte_kennung_legt_nichts_an(
        self, aufsicht: TestClient, _umgebung: None
    ) -> None:
        """Migrieren darf die Datei nicht anlegen - sonst wäre ein Tippfehler ein Korpus.

        `wende_migrationen_an` legt eine fehlende Datenbank an. In `engine_fuer`
        steht die Prüfung auf die Datei deshalb davor und muss dort bleiben.
        """
        assert aufsicht.get("/api/admin/speakers/spr_gibtesnicht").status_code == 404
        pfad = corpus.datenbank_pfad(einstellungen().data_dir, "spr_gibtesnicht")
        assert not pfad.exists()
        assert not pfad.parent.exists()


class TestTinyWirdAusgeraeumt:
    """`006_ohne_tiny.sql`: das kleinste Modell verschwindet samt Ergebnissen.

    Die einzige Migration, die diese Sammlung beim Namen nennt - weil sie als
    einzige nicht Schema fortschreibt, sondern Daten wegnimmt. Was etwas
    löscht, soll auch geprüft werden: dass es das Richtige trifft und, ebenso
    wichtig, nur das.
    """

    @pytest.fixture
    def korpus_mit_tiny(self, _umgebung: None, tmp_path: Path) -> Path:
        """Ein Korpus auf dem Stand davor, mit einer Erkennung je Modell."""
        konfiguration = einstellungen()

        davor = tmp_path / "migrationen_vor_006"
        davor.mkdir()
        for datei in sorted(konfiguration.migrationsverzeichnis.glob("*.sql")):
            if datei.stem >= OHNE_TINY:
                break
            (davor / datei.name).write_text(datei.read_text(encoding="utf-8"), encoding="utf-8")

        pfad = corpus.datenbank_pfad(konfiguration.data_dir, MIT_TINY)
        db.wende_migrationen_an(pfad, davor)

        with sqlite3.connect(pfad) as verbindung:
            verbindung.execute(
                "INSERT INTO speakers (id, name, sprache, basismodell, erstellt)"
                " VALUES (?, ?, 'de', 'openai/whisper-tiny', ?)",
                (MIT_TINY, "Mit tiny", jetzt()),
            )
            verbindung.execute(
                "INSERT INTO text_sources (id, speaker_id, art, titel, erstellt)"
                " VALUES ('src_1', ?, 'upload', 'Vorlage', ?)",
                (MIT_TINY, jetzt()),
            )
            verbindung.execute(
                "INSERT INTO prompts"
                " (id, source_id, speaker_id, position, text, dauer_geschaetzt_s, erstellt)"
                " VALUES ('prm_1', 'src_1', ?, 1, 'Ein Satz.', 1.5, ?)",
                (MIT_TINY, jetzt()),
            )
            verbindung.execute(
                "INSERT INTO recordings"
                " (id, prompt_id, speaker_id, blob, dauer_s, pegel_dbfs, spitze_dbfs,"
                "  clipping_anteil, stille_vorn_s, stille_hinten_s, modus, status, erstellt)"
                " VALUES ('rec_1', 'prm_1', ?, 'a.wav', 1.5, -20, -3, 0, 0, 0,"
                "  'gelesen', 'ok', ?)",
                (MIT_TINY, jetzt()),
            )
            for kennung, modell in (("erk_1", "tiny"), ("erk_2", "small")):
                verbindung.execute(
                    "INSERT INTO erkennungen"
                    " (id, recording_id, modell, text, wer, cer, mer, wil, genauigkeit,"
                    "  rechenzeit_s, erstellt)"
                    " VALUES (?, 'rec_1', ?, 'ein satz', 0.1, 0.1, 0.1, 0.1, 90, 1.0, ?)",
                    (kennung, modell, jetzt()),
                )
        return pfad

    def _modelle(self, pfad: Path) -> list[str]:
        with sqlite3.connect(pfad) as verbindung:
            return [
                zeile[0]
                for zeile in verbindung.execute("SELECT modell FROM erkennungen ORDER BY modell")
            ]

    def test_die_gerechneten_zeilen_fallen_weg(self, korpus_mit_tiny: Path) -> None:
        assert self._modelle(korpus_mit_tiny) == ["small", "tiny"]

        db.wende_migrationen_an(korpus_mit_tiny, einstellungen().migrationsverzeichnis)

        assert self._modelle(korpus_mit_tiny) == ["small"]

    # Dass ein Profil von `whisper-tiny` auf `whisper-small` rückt, stand hier
    # einmal als eigener Test. Sein Gegenstand ist weg: `013` entfernt die
    # Spalte, weil sie nie etwas entschieden hat, und ein Test, der alle
    # Migrationen anwendet, kann danach nicht mehr in sie hineinsehen. Der
    # Umzug bleibt trotzdem richtig - er hat die Daten in Ordnung gehalten,
    # solange es die Spalte gab.

    def test_die_aufnahme_selbst_bleibt(self, korpus_mit_tiny: Path) -> None:
        """Gelöscht wird Abgeleitetes, nie das, was ein Mensch gesprochen hat."""
        db.wende_migrationen_an(korpus_mit_tiny, einstellungen().migrationsverzeichnis)

        with sqlite3.connect(korpus_mit_tiny) as verbindung:
            assert verbindung.execute("SELECT count(*) FROM recordings").fetchone()[0] == 1
