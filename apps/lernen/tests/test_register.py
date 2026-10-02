"""Das Register der Läufe - es überdauert das Löschen von Lauf und Modell.

Der Trainer läuft hier nicht; was er hinterlässt, stellt `_lauf_fertigstellen`
nach (wie in `test_vergleich.py`). Geprüft wird, was danach im Register steht
und dass es dort bleibt.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import corpus, laeufe, registry

from apps.hoeren.backend.services import loeschung
from apps.lernen.backend.services import register
from apps.lernen.tests.test_vergleich import _lauf_fertigstellen


def _zeilen(datenverzeichnis: Path, sprecher: str, sql: str, *werte) -> list[tuple]:
    with closing(sqlite3.connect(register.pfad(datenverzeichnis, sprecher))) as verbindung:
        return verbindung.execute(sql, werte).fetchall()


@pytest.fixture
def fertig(klient: TestClient, quelle: str, sprich, datenverzeichnis, sprecher: str):
    """Ein durchgelaufener Lauf samt Modell: `(job_id, modell)`."""
    sprich(9)
    lauf = klient.post("/lernen/api/laeufe", json={"methode": "lora", "daten": "original"}).json()
    version = _lauf_fertigstellen(datenverzeichnis, lauf["job_id"], sprecher, genauigkeit=88.0)
    return lauf["job_id"], f"{sprecher}/{version}"


class TestEintragen:
    def test_steht_vollstaendig_darin(self, fertig, datenverzeichnis, sprecher: str) -> None:
        job_id, modell = fertig
        assert register.trage_ein(datenverzeichnis, job_id)

        verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job_id)
        manifest = laeufe.lies_zeilen(verzeichnis / laeufe.MANIFEST)
        bewertung = laeufe.lies_zeilen(verzeichnis / laeufe.BEWERTUNG)
        ((status, eingetragen_modell, kennung, entfernt),) = _zeilen(
            datenverzeichnis,
            sprecher,
            "SELECT status, modell, kennung, entfernt FROM laeufe WHERE job_id = ?",
            job_id,
        )
        assert (status, eingetragen_modell, entfernt) == (laeufe.FERTIG, modell, None)
        assert kennung == registry.beschriftung(modell)

        daten = _zeilen(
            datenverzeichnis, sprecher, "SELECT recording_id, text, audio_sha256 FROM daten"
        )
        assert len(daten) == len(manifest) > 0
        assert all(sha and len(sha) == 64 for _, _, sha in daten)
        assert {(zeile["recording_id"], zeile["text"]) for zeile in manifest} == {
            (kennung, text) for kennung, text, _ in daten
        }
        assert _zeilen(datenverzeichnis, sprecher, "SELECT count(*) FROM messungen") == [
            (len(bewertung),)
        ]

    def test_nur_mit_kennung_nicht_mit_namen(
        self, fertig, datenverzeichnis, sprecher: str
    ) -> None:
        # Der Name steht im Profil von „hören", im Register nur die Kennung.
        job_id, _ = fertig
        register.trage_ein(datenverzeichnis, job_id)
        assert b"Testperson" not in register.pfad(datenverzeichnis, sprecher).read_bytes()
        assert _zeilen(datenverzeichnis, sprecher, "SELECT sprecher_id FROM laeufe") == [
            (sprecher,)
        ]

    def test_der_fingerabdruck_bleibt_der_erste(
        self, fertig, datenverzeichnis, sprecher: str
    ) -> None:
        # Wer danach nachschneidet, ändert nicht, worauf gelernt wurde.
        job_id, _ = fertig
        register.trage_ein(datenverzeichnis, job_id)
        ((audio, vorher),) = _zeilen(
            datenverzeichnis, sprecher, "SELECT audio, audio_sha256 FROM daten WHERE zeile = 0"
        )
        (datenverzeichnis / corpus.sprecher_relpfad(sprecher) / audio).write_bytes(b"anders")

        register.trage_ein(datenverzeichnis, job_id)
        assert _zeilen(
            datenverzeichnis, sprecher, "SELECT audio_sha256 FROM daten WHERE zeile = 0"
        ) == [(vorher,)]
        assert _zeilen(datenverzeichnis, sprecher, "SELECT count(*) FROM laeufe") == [(1,)]

    def test_die_umgebung_bleibt_beim_nachtragen(
        self, fertig, datenverzeichnis, sprecher: str
    ) -> None:
        job_id, _ = fertig
        lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
        assert lauf is not None
        umgebung = register.umgebung(datenverzeichnis, lauf.auftrag)
        assert len(umgebung["quellstand"]) == 64
        register.trage_ein(datenverzeichnis, job_id, umgebung)
        register.trage_ein(datenverzeichnis, job_id)
        ((gespeichert,),) = _zeilen(datenverzeichnis, sprecher, "SELECT umgebung FROM laeufe")
        assert umgebung["quellstand"] in gespeichert


class TestDatensatz:
    def test_gleiche_daten_gleicher_fingerabdruck(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis, sprecher: str
    ) -> None:
        # Gleiche Daten, andere Option - genau das Paar, das eine Option misst.
        sprich(9)
        gleich = [
            klient.post("/lernen/api/laeufe", json={"methode": methode, "daten": "original"})
            .json()["job_id"]
            for methode in ("lora", "full")
        ]
        sprich(3)
        mehr = klient.post(
            "/lernen/api/laeufe", json={"methode": "lora", "daten": "original"}
        ).json()["job_id"]
        for job_id in (*gleich, mehr):
            register.trage_ein(datenverzeichnis, job_id)

        fingerabdruck = dict(
            _zeilen(datenverzeichnis, sprecher, "SELECT job_id, datensatz FROM uebersicht")
        )
        assert fingerabdruck[gleich[0]] == fingerabdruck[gleich[1]]
        assert fingerabdruck[mehr] != fingerabdruck[gleich[0]]
        assert len(fingerabdruck[mehr]) == 64


class TestLoeschen:
    def test_das_register_ueberdauert_lauf_und_modell(
        self, klient: TestClient, fertig, datenverzeichnis, sprecher: str
    ) -> None:
        job_id, modell = fertig
        assert klient.delete(f"/lernen/api/laeufe/{job_id}").status_code == 200

        assert not laeufe.lauf_verzeichnis(datenverzeichnis, job_id).exists()
        assert registry.stand_zu_lauf(datenverzeichnis, sprecher, job_id) is None
        ((eingetragen, entfernt, stand),) = _zeilen(
            datenverzeichnis, sprecher, "SELECT modell, entfernt, stand FROM laeufe"
        )
        assert eingetragen == modell
        assert entfernt
        assert '"genauigkeit": 88.0' in stand

    def test_was_hoeren_mit_dem_modell_mass_kommt_mit(
        self, klient: TestClient, fertig, datenverzeichnis, sprecher: str
    ) -> None:
        # Ohne Modell räumt die Auswertung diese Zeilen weg - neu rechnen ließe
        # sich keine.
        job_id, modell = fertig
        verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job_id)
        aufnahme = laeufe.lies_zeilen(verzeichnis / laeufe.MANIFEST)[0]["recording_id"]
        with closing(sqlite3.connect(corpus.datenbank_pfad(datenverzeichnis, sprecher))) as korpus:
            korpus.execute(
                "INSERT INTO erkennungen (id, recording_id, modell, variante, text, wer, cer,"
                " mer, wil, genauigkeit, rechenzeit_s, rechenwerk, tempo, herkunft, erstellt)"
                " VALUES ('erk_1', ?, ?, 'original', 'neu gehört', 0.2, 0.1, 0.2, 0.3, 80.0,"
                " 0.5, 'cpu/int8', 1.0, 'gemessen', '2026-10-02T00:00:00+00:00')",
                (aufnahme, modell),
            )
            korpus.commit()

        assert klient.delete(f"/lernen/api/laeufe/{job_id}").status_code == 200
        assert _zeilen(
            datenverzeichnis,
            sprecher,
            "SELECT recording_id, text, genauigkeit FROM messungen WHERE herkunft = ?",
            register.ENDMODELL,
        ) == [(aufnahme, "neu gehört", 80.0)]

    def test_scheitert_das_register_bleibt_der_lauf(
        self, klient: TestClient, fertig, datenverzeichnis, monkeypatch
    ) -> None:
        job_id, _ = fertig

        def kaputt(*_argumente) -> None:
            raise sqlite3.OperationalError("Platte voll")

        monkeypatch.setattr(register, "trage_vor_dem_loeschen_ein", kaputt)
        with pytest.raises(sqlite3.OperationalError):
            klient.delete(f"/lernen/api/laeufe/{job_id}")
        assert laeufe.lauf_verzeichnis(datenverzeichnis, job_id).is_dir()

    def test_geht_mit_dem_sprecher(self, fertig, datenverzeichnis, sprecher: str) -> None:
        # Das Recht auf Löschung umfasst das Register (`loeschung.ziele`).
        job_id, _ = fertig
        register.trage_ein(datenverzeichnis, job_id)
        assert register.pfad(datenverzeichnis, sprecher).parent in loeschung.ziele(
            datenverzeichnis, sprecher
        )
