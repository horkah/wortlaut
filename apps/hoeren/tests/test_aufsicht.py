"""Die Aufsicht: einsehen, umbenennen, sichern, löschen.

Zwei Dinge stehen hier im Mittelpunkt, und beide sind Grenzen:

* `TestGrenze` - die Aufsicht ist ohne gesetzten Token zu, und kein anderer
  Zugang kommt an ihre Wege heran.
* `TestNiemalsAlle` - es gibt keinen Weg, der mehr als einen Sprecher löscht,
  und der eine, der einen löscht, verlangt dessen Kennung als Bestätigung.

Der Rest prüft, dass die ausgeleiteten Archive das enthalten, was daraufsteht:
Eine Sicherung, die sich nicht zurückspielen lässt, merkt man sonst erst, wenn
der Server weg ist - und eine, die das Gerechnete mitschleppt, merkt man am
Platz.
"""

from __future__ import annotations

import io
import json
import sqlite3
import tarfile
import zipfile
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import augmentierung, corpus, sicherung

from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.db.models import Aufnahme, Erkennung
from apps.hoeren.backend.deps import engine_fuer
from apps.hoeren.backend.main import app
from apps.hoeren.tests.conftest import TOKEN


@pytest.fixture
def bespielt(
    aufsicht: TestClient, klient: TestClient, sprecher: str, quelle: str, audio_datei: dict
) -> str:
    """Ein Sprecher mit einer Quelle und zwei Aufnahmen. Gibt seine Kennung zurück."""
    for _ in range(2):
        naechste = klient.get("/api/prompts/next").json()["aktuell"]
        antwort = klient.post(
            "/api/recordings",
            files=audio_datei,
            data={"prompt_id": naechste["id"], "modus": "gelesen"},
        )
        assert antwort.status_code == 201
    return sprecher


class TestGrenze:
    def test_ohne_token_kein_zugriff(self, klient_ohne_token: TestClient) -> None:
        assert klient_ohne_token.get("/api/admin/speakers").status_code == 401

    def test_verwalter_ist_keine_aufsicht(self, verwalter: TestClient) -> None:
        # Der Verwaltertoken legt Profile an - er sieht deshalb noch lange
        # nicht in fremde Korpora und löscht erst recht nichts.
        assert verwalter.get("/api/admin/speakers").status_code == 401

    def test_sprecherzugang_ist_keine_aufsicht(self, klient: TestClient, sprecher: str) -> None:
        assert klient.get("/api/admin/speakers").status_code == 401
        loeschen = klient.delete(f"/api/admin/speakers/{sprecher}?bestaetigung={sprecher}")
        assert loeschen.status_code == 401

    def test_ohne_gesetzten_token_ist_die_aufsicht_zu(
        self, _umgebung: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # „Leer" heißt abgeschaltet, wie beim Verwaltertoken. Sonst stünde auf
        # jeder Installation, die den Token vergisst, ein Löschknopf für alle
        # Korpora offen.
        monkeypatch.setenv("WORTLAUT_ADMIN_TOKEN", "")
        einstellungen.cache_clear()
        with TestClient(app) as offen:
            assert offen.get("/api/admin/speakers").status_code == 401
            assert (
                offen.get(
                    "/api/admin/speakers", headers={"Authorization": "Bearer "}
                ).status_code
                == 401
            )

    def test_gleiche_tokens_sind_ein_startfehler(
        self, _umgebung: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Wären beide gleich, würde jeder Verwalter unbemerkt zur Aufsicht -
        # der Server prüft sie zuerst. Nichts schlüge fehl, es ginge bloß
        # plötzlich mehr. Also beim Start abbrechen.
        monkeypatch.setenv("WORTLAUT_ADMIN_TOKEN", TOKEN)
        einstellungen.cache_clear()
        with pytest.raises(ValidationError):
            einstellungen()

    def test_aufsicht_darf_auch_verwalten(self, aufsicht: TestClient) -> None:
        # Wer jeden Korpus löschen darf, hätte an einem zweiten Token für das
        # Anlegen eines Profils nichts gewonnen.
        assert aufsicht.get("/api/speakers").status_code == 200

    def test_aufsicht_kommt_nicht_an_den_sprecherweg(self, aufsicht: TestClient) -> None:
        # Sie sieht über `/api/admin/…`, nicht über die Wege eines Sprechers:
        # Dort bliebe die Kennung eine Behauptung, und genau das soll es
        # nirgends mehr geben.
        assert aufsicht.get("/api/progress").status_code == 401

    def test_auskunft_nennt_die_aufsicht(self, aufsicht: TestClient) -> None:
        assert aufsicht.get("/api/zugang").json()["art"] == "aufsicht"


class TestEinsicht:
    def test_uebersicht_zeigt_alle_sprecher(
        self, aufsicht: TestClient, bespielt: str, verwalter: TestClient
    ) -> None:
        zweiter = verwalter.post(
            "/api/speakers", json={"name": "Andere", "basismodell": "openai/whisper-small"}
        ).json()["id"]

        liste = aufsicht.get("/api/admin/speakers").json()
        assert {person["id"] for person in liste} == {bespielt, zweiter}

        gefunden = next(person for person in liste if person["id"] == bespielt)
        assert gefunden["kennzahlen"]["aufnahmen"] == 2
        assert gefunden["kennzahlen"]["sekunden"] > 0
        assert gefunden["kennzahlen"]["bytes_audio"] > 0

    def test_einsicht_zeigt_die_eintraege_eines_sprechers(
        self, aufsicht: TestClient, bespielt: str
    ) -> None:
        einsicht = aufsicht.get(f"/api/admin/speakers/{bespielt}").json()
        assert einsicht["sprecher"]["name"] == "Testperson"
        assert [quelle["art"] for quelle in einsicht["quellen"]] == ["upload"]
        assert einsicht["quellen"][0]["einheiten"] > 0

    def test_aufnahmen_tragen_ihren_text(self, aufsicht: TestClient, bespielt: str) -> None:
        # Eine Aufnahme ohne den Text, zu dem sie gehört, ist für die Aufsicht
        # nur eine Kennung - sie soll sehen, was gesprochen wurde.
        seite = aufsicht.get(f"/api/admin/speakers/{bespielt}/recordings").json()
        assert seite["gesamt"] == 2
        assert all(eintrag["text"] for eintrag in seite["aufnahmen"])
        assert all(eintrag["audio_vorhanden"] for eintrag in seite["aufnahmen"])

    def test_sitzungen_werden_geseitet(
        self, aufsicht: TestClient, klient: TestClient, bespielt: str
    ) -> None:
        """Auch die leeren: Der Aufsicht sagt gerade der leere Anlauf etwas.

        Die eigene Ansicht lässt sie weg (`test_konto.py`), hier bleiben sie
        stehen - jemand hat die Aufnahmeseite geöffnet und nichts gesprochen.
        """
        for _ in range(3):
            antwort = klient.post(f"/api/sessions?sprecher={bespielt}")
            assert antwort.status_code == 201

        erste_seite = aufsicht.get(f"/api/admin/speakers/{bespielt}/sessions?ab=0&anzahl=2").json()
        assert erste_seite["gesamt"] == 3
        assert erste_seite["ab"] == 0
        assert len(erste_seite["sitzungen"]) == 2

        zweite_seite = aufsicht.get(f"/api/admin/speakers/{bespielt}/sessions?ab=2&anzahl=2").json()
        assert len(zweite_seite["sitzungen"]) == 1

    def test_audio_ist_abhoerbar(self, aufsicht: TestClient, bespielt: str) -> None:
        erste = aufsicht.get(f"/api/admin/speakers/{bespielt}/recordings").json()["aufnahmen"][0]
        antwort = aufsicht.get(
            f"/api/admin/speakers/{bespielt}/recordings/{erste['id']}/audio"
        )
        assert antwort.status_code == 200
        assert antwort.content[:4] == b"RIFF"

    def test_unbekannter_sprecher_ist_ein_404(self, aufsicht: TestClient) -> None:
        assert aufsicht.get("/api/admin/speakers/spr_gibtsnicht").status_code == 404


class TestUmbenennen:
    def test_name_aendert_sich_kennung_nicht(self, aufsicht: TestClient, sprecher: str) -> None:
        antwort = aufsicht.patch(f"/api/admin/speakers/{sprecher}", json={"name": "Neuer Name"})
        assert antwort.status_code == 200
        assert antwort.json() == {**antwort.json(), "id": sprecher, "name": "Neuer Name"}
        assert aufsicht.get(f"/api/speakers/{sprecher}").json()["name"] == "Neuer Name"

    def test_der_zugang_gilt_weiter(
        self, aufsicht: TestClient, klient: TestClient, sprecher: str
    ) -> None:
        # Umbenennen ist eine Beschriftung, kein Eingriff: Wer gerade aufnimmt,
        # soll davon nichts merken.
        aufsicht.patch(f"/api/admin/speakers/{sprecher}", json={"name": "Neuer Name"})
        assert klient.get("/api/zugang").json()["name"] == "Neuer Name"

    def test_leerer_name_wird_abgewiesen(self, aufsicht: TestClient, sprecher: str) -> None:
        # Auch der aus Leerzeichen: Sonst stünde in der Liste eine leere Zeile,
        # und niemand wüsste, wessen Korpus er vor sich hat.
        for leer in ("", "  "):
            antwort = aufsicht.patch(f"/api/admin/speakers/{sprecher}", json={"name": leer})
            assert antwort.status_code == 422
        assert aufsicht.get(f"/api/speakers/{sprecher}").json()["name"] == "Testperson"


class TestSicherung:
    def test_sicherung_eines_sprechers_enthaelt_datenbank_und_audio(
        self, aufsicht: TestClient, bespielt: str, tmp_path: Path
    ) -> None:
        antwort = aufsicht.get(f"/api/admin/speakers/{bespielt}/sicherung")
        assert antwort.status_code == 200

        namen = _namen(antwort.content)
        assert f"daten/korpus/{bespielt}/{corpus.DATENBANKNAME}" in namen
        # Zwei Dateien für zwei Aufnahmen - gesprochen wurde zweimal.
        assert sum(1 for name in namen if name.endswith(".wav")) == 2
        # Die Begleitdateien des WAL-Modus gehören nicht hinein: Ihr Inhalt
        # steckt schon in der gesicherten Datenbank.
        assert not [name for name in namen if name.endswith(("-wal", "-shm"))]

    def test_abgewandelte_fassungen_bleiben_draussen(
        self, aufsicht: TestClient, bespielt: str, tmp_path: Path
    ) -> None:
        # Auf der Platte liegen sie - drei je Aufnahme, gerechnet beim
        # Hochladen (`services/augmentierung.py`).
        varianten = tmp_path / "data" / corpus.varianten_relpfad(bespielt)
        assert len(list(varianten.glob("*.wav"))) == 2 * len(augmentierung.ABWANDLUNGEN)

        # In der Sicherung nicht: Sie sind gerechnet und nicht gesprochen, und
        # sie wären drei Viertel des Archivs.
        namen = _namen(aufsicht.get(f"/api/admin/speakers/{bespielt}/sicherung").content)
        assert not [name for name in namen if corpus.VARIANTENORDNER in name]

    def test_messwerte_der_auswertung_bleiben_draussen(
        self, aufsicht: TestClient, bespielt: str, tmp_path: Path
    ) -> None:
        # Was ein Lauf jederzeit neu rechnet, muss keine Sicherung wegtragen.
        # Der Rest der Datenbank aber schon - sie kommt vollständig mit, nur
        # ohne diese Zeilen.
        _miss(bespielt)
        archiv = tmp_path / "sicherung.tgz"
        archiv.write_bytes(aufsicht.get(f"/api/admin/speakers/{bespielt}/sicherung").content)

        neu = tmp_path / "wiederhergestellt"
        sicherung.stelle_wieder_her(archiv, neu)
        with closing(sqlite3.connect(corpus.datenbank_pfad(neu, bespielt))) as verbindung:
            gezaehlt = dict(
                verbindung.execute(
                    "SELECT 'erkennungen', count(*) FROM erkennungen "
                    "UNION ALL SELECT 'recordings', count(*) FROM recordings "
                    "UNION ALL SELECT 'prompts', count(*) FROM prompts"
                )
            )
        assert gezaehlt["erkennungen"] == 0
        assert gezaehlt["recordings"] == 2
        assert gezaehlt["prompts"] > 0

    def test_der_bestand_selbst_bleibt_unberuehrt(
        self, aufsicht: TestClient, bespielt: str, tmp_path: Path
    ) -> None:
        # Geleert wird die Sicherungskopie, nie die laufende Datenbank. Ein
        # Sichern, das nebenbei Messwerte wegwirft, wäre ein Datenverlust mit
        # Ansage.
        _miss(bespielt)
        assert aufsicht.get(f"/api/admin/speakers/{bespielt}/sicherung").status_code == 200

        with closing(sqlite3.connect(corpus.datenbank_pfad(tmp_path / "data", bespielt))) as db:
            assert db.execute("SELECT count(*) FROM erkennungen").fetchone()[0] == 2
        assert list((tmp_path / "data" / corpus.varianten_relpfad(bespielt)).glob("*.wav"))

    def test_manifest_nennt_den_sprecher(self, aufsicht: TestClient, bespielt: str) -> None:
        manifest = _manifest(aufsicht.get(f"/api/admin/speakers/{bespielt}/sicherung").content)
        assert manifest["umfang"] == "sprecher"
        assert [person["id"] for person in manifest["sprecher"]] == [bespielt]
        assert manifest["dateien"]  # mit Größe und Prüfsumme je Datei
        # Und es schreibt hin, was fehlt - wer in einem Jahr auspackt, soll das
        # nicht für einen Schaden halten.
        assert manifest["ausgelassen"]["verzeichnisse"] == [
            corpus.varianten_relpfad(bespielt),
            corpus.vorlesen_relpfad(bespielt),
        ]
        assert manifest["ausgelassen"]["tabellen"] == {corpus.DATENBANKNAME: ["erkennungen"]}

    def test_gesamtsicherung_enthaelt_alle_sprecher(
        self, aufsicht: TestClient, bespielt: str, verwalter: TestClient
    ) -> None:
        zweiter = verwalter.post(
            "/api/speakers", json={"name": "Andere", "basismodell": "openai/whisper-small"}
        ).json()["id"]

        inhalt = aufsicht.get("/api/admin/sicherung").content
        manifest = _manifest(inhalt)
        assert manifest["umfang"] == "gesamt"
        assert {person["id"] for person in manifest["sprecher"]} == {bespielt, zweiter}

        namen = _namen(inhalt)
        assert f"daten/korpus/{bespielt}/{corpus.DATENBANKNAME}" in namen
        assert f"daten/korpus/{zweiter}/{corpus.DATENBANKNAME}" in namen

    def test_sicherung_laesst_sich_zurueckspielen(
        self, aufsicht: TestClient, bespielt: str, tmp_path: Path
    ) -> None:
        # Der eigentliche Zweck: Der Server ist weg, das Archiv ist da.
        archiv = tmp_path / "sicherung.tgz"
        archiv.write_bytes(aufsicht.get("/api/admin/sicherung").content)

        neu = tmp_path / "wiederhergestellt"
        geschrieben = sicherung.stelle_wieder_her(archiv, neu)

        datenbank = corpus.datenbank_pfad(neu, bespielt)
        assert datenbank.is_file()
        assert len(list((neu / corpus.sprecher_relpfad(bespielt) / "audio").glob("*.wav"))) == 2
        assert geschrieben

    def test_wiederherstellung_ueberschreibt_nicht_von_selbst(
        self, aufsicht: TestClient, bespielt: str, tmp_path: Path
    ) -> None:
        # Eine Wiederherstellung, die einen laufenden Bestand halb
        # überschreibt, wäre schlimmer als gar keine.
        archiv = tmp_path / "sicherung.tgz"
        archiv.write_bytes(aufsicht.get("/api/admin/sicherung").content)

        bestand = einstellungen().data_dir
        with pytest.raises(FileExistsError):
            sicherung.stelle_wieder_her(archiv, bestand)
        sicherung.stelle_wieder_her(archiv, bestand, ueberschreiben=True)


class TestDatensatz:
    def test_zip_paart_text_und_audio(self, aufsicht: TestClient, bespielt: str) -> None:
        antwort = aufsicht.get(f"/api/admin/speakers/{bespielt}/datensatz")
        assert antwort.status_code == 200

        with zipfile.ZipFile(io.BytesIO(antwort.content)) as archiv:
            namen = archiv.namelist()
            wavs = [name for name in namen if name.endswith(".wav")]
            assert len(wavs) == 2
            # Neben jeder Aufnahme ihr Text als eigene Datei - damit ein
            # Werkzeug, das nur ein Verzeichnis sieht, ohne Tabelle auskommt.
            for wav in wavs:
                txt = wav.removesuffix(".wav") + ".txt"
                assert txt in namen
                assert archiv.read(txt).decode("utf-8").strip()

            tabelle = archiv.read(f"{bespielt}/metadaten.csv").decode("utf-8").splitlines()
            assert tabelle[0].startswith("file_name,transcription")
            assert len(tabelle) == 3  # Kopfzeile plus zwei Aufnahmen

            zeilen = [
                json.loads(zeile)
                for zeile in archiv.read(f"{bespielt}/metadaten.jsonl")
                .decode("utf-8")
                .splitlines()
            ]
            assert {zeile["file_name"] for zeile in zeilen} == {
                name.removeprefix(f"{bespielt}/") for name in wavs
            }

    def test_zip_enthaelt_keine_datenbank(self, aufsicht: TestClient, bespielt: str) -> None:
        # Der Datensatz ist ausdrücklich keine Sicherung - wer sichern will,
        # soll nicht die falsche Datei wegtragen.
        with zipfile.ZipFile(
            io.BytesIO(aufsicht.get(f"/api/admin/speakers/{bespielt}/datensatz").content)
        ) as archiv:
            assert not [name for name in archiv.namelist() if name.endswith(".sqlite")]
            assert f"{bespielt}/LIESMICH.txt" in archiv.namelist()


class TestLoeschen:
    def test_einzelne_aufnahme(self, aufsicht: TestClient, bespielt: str, tmp_path: Path) -> None:
        erste = aufsicht.get(f"/api/admin/speakers/{bespielt}/recordings").json()["aufnahmen"][0]
        datei = tmp_path / "data" / corpus.audio_relpfad(bespielt, erste["id"])
        assert datei.is_file()

        antwort = aufsicht.delete(f"/api/admin/speakers/{bespielt}/recordings/{erste['id']}")
        assert antwort.status_code == 204
        assert not datei.exists()
        assert aufsicht.get(f"/api/admin/speakers/{bespielt}/recordings").json()["gesamt"] == 1

    def test_geloeschte_aufnahme_gibt_die_vorlage_frei(
        self, aufsicht: TestClient, klient: TestClient, bespielt: str
    ) -> None:
        # Anders als beim Verwerfen bleibt keine Spur stehen; die Einheit ist
        # danach wieder offen und wird erneut angeboten.
        vorher = klient.get("/api/prompts/next").json()
        erste = aufsicht.get(f"/api/admin/speakers/{bespielt}/recordings").json()["aufnahmen"][0]
        aufsicht.delete(f"/api/admin/speakers/{bespielt}/recordings/{erste['id']}")
        assert klient.get("/api/prompts/next").json()["erledigt"] == vorher["erledigt"] - 1

    def test_alle_aufnahmen_eines_sprechers(
        self, aufsicht: TestClient, klient: TestClient, bespielt: str, tmp_path: Path
    ) -> None:
        antwort = aufsicht.delete(
            f"/api/admin/speakers/{bespielt}/recordings?bestaetigung={bespielt}"
        )
        assert antwort.status_code == 200
        assert antwort.json() == {"geloescht": 2}

        # Das Profil und die Warteschlange stehen noch - das ist „neu
        # anfangen", nicht „Person löschen". Kein Ton bleibt übrig, auch keine
        # abgewandelte Fassung: Gesucht wird deshalb rekursiv. Die leeren
        # Verzeichnisse dürfen stehen bleiben - sie tragen nichts.
        audio = tmp_path / "data" / corpus.sprecher_relpfad(bespielt) / "audio"
        assert not list(audio.rglob("*.wav"))
        assert klient.get("/api/progress").json()["aufnahmen"] == 0
        assert klient.get("/api/prompts/next").json()["gesamt"] > 0

    def test_ganzer_sprecher(self, aufsicht: TestClient, bespielt: str, tmp_path: Path) -> None:
        antwort = aufsicht.delete(f"/api/admin/speakers/{bespielt}?bestaetigung={bespielt}")
        assert antwort.status_code == 200
        assert antwort.json()["geloescht"]
        assert not (tmp_path / "data" / corpus.sprecher_relpfad(bespielt)).exists()
        assert aufsicht.get("/api/admin/speakers").json() == []

    def test_geloeschter_sprecher_kommt_nicht_zurueck(
        self, aufsicht: TestClient, klient: TestClient, bespielt: str, tmp_path: Path
    ) -> None:
        # Eine offene Engine auf die gelöschte Datei legte sie beim nächsten
        # Zugriff wieder an - ein leeres Verzeichnis, das wie ein Sprecher aussieht.
        aufsicht.delete(f"/api/admin/speakers/{bespielt}?bestaetigung={bespielt}")
        assert klient.get("/api/progress").status_code == 401
        assert not corpus.datenbank_pfad(tmp_path / "data", bespielt).exists()


class TestNiemalsAlle:
    """Die harte Grenze: ein Versehen kostet höchstens eine Person."""

    def test_es_gibt_keinen_weg_der_alle_loescht(self, aufsicht: TestClient) -> None:
        # Weder unter der Sammeladresse noch unter der Sicherung.
        assert aufsicht.delete("/api/admin/speakers").status_code == 405
        assert aufsicht.delete("/api/admin/sicherung").status_code == 405

    def test_loeschen_verlangt_die_kennung_als_bestaetigung(
        self, aufsicht: TestClient, bespielt: str, tmp_path: Path
    ) -> None:
        assert aufsicht.delete(f"/api/admin/speakers/{bespielt}").status_code == 422
        assert (
            aufsicht.delete(f"/api/admin/speakers/{bespielt}?bestaetigung=irgendwas").status_code
            == 400
        )
        assert (tmp_path / "data" / corpus.sprecher_relpfad(bespielt)).exists()

    def test_auch_das_leeren_verlangt_die_bestaetigung(
        self, aufsicht: TestClient, bespielt: str
    ) -> None:
        assert (
            aufsicht.delete(
                f"/api/admin/speakers/{bespielt}/recordings?bestaetigung=irgendwas"
            ).status_code
            == 400
        )
        assert aufsicht.get(f"/api/admin/speakers/{bespielt}/recordings").json()["gesamt"] == 2

    def test_loeschen_trifft_nur_den_genannten_sprecher(
        self, aufsicht: TestClient, bespielt: str, verwalter: TestClient, tmp_path: Path
    ) -> None:
        zweiter = verwalter.post(
            "/api/speakers", json={"name": "Andere", "basismodell": "openai/whisper-small"}
        ).json()["id"]

        aufsicht.delete(f"/api/admin/speakers/{bespielt}?bestaetigung={bespielt}")
        assert (tmp_path / "data" / corpus.sprecher_relpfad(zweiter)).exists()
        assert [person["id"] for person in aufsicht.get("/api/admin/speakers").json()] == [zweiter]


def _miss(sprecher_id: str) -> None:
    """Zwei Messwerte in den Korpus legen - ohne Whisper, es geht um die Zeilen."""
    with Session(engine_fuer(sprecher_id)) as sitzung:
        for nummer, aufnahme in enumerate(sitzung.scalars(select(Aufnahme)).all()):
            sitzung.add(
                Erkennung(
                    id=f"erk_{nummer}",
                    recording_id=aufnahme.id,
                    modell="small",
                    variante=augmentierung.ORIGINAL,
                    text="was das Modell gehört hat",
                    wer=0.1,
                    cer=0.1,
                    mer=0.1,
                    wil=0.1,
                    genauigkeit=90.0,
                    rechenzeit_s=1.0,
                    rechenwerk="cpu/int8",
                    erstellt="2026-01-01T00:00:00+00:00",
                )
            )
        sitzung.commit()


def _namen(archiv: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(archiv), mode="r:gz") as geoeffnet:
        return geoeffnet.getnames()


def _manifest(archiv: bytes) -> dict:
    with tarfile.open(fileobj=io.BytesIO(archiv), mode="r:gz") as geoeffnet:
        eintrag = geoeffnet.extractfile(sicherung.MANIFEST)
        assert eintrag is not None
        return json.loads(eintrag.read().decode("utf-8"))


class TestEinProfilEineBeschreibung:
    """Verwaltung und Aufsicht liefern dasselbe Profil - Feld für Feld.

    Es gab dieses Profil zweimal als Pydantic-Modell, einmal je Ansicht. Das
    ist harmlos, solange niemand ein Feld hinzufügt - und im September 2026 kam
    `tempo` dazu, aber nur in einem der beiden. Die Verwaltung zeigte
    „2-fach", die Aufsicht „normal", und beide lasen dieselbe Datenbankzeile.

    Dieser Test prüft nicht `tempo`, sondern die Regel dahinter: Was die eine
    Ansicht über ein Profil sagt, sagt die andere auch. Ein Feld, das jemand
    künftig nur an einer Stelle ergänzt, fällt hier auf.
    """

    def test_dieselben_felder_mit_denselben_werten(
        self, verwalter: TestClient, aufsicht: TestClient, sprecher: str
    ) -> None:
        verwalter.patch(f"/api/speakers/{sprecher}", json={"tempo": 2.0})

        aus_verwaltung = verwalter.get(f"/api/speakers/{sprecher}").json()
        alle = aufsicht.get("/api/admin/speakers").json()
        aus_aufsicht = next(zeile for zeile in alle if zeile["id"] == sprecher)

        # Die Aufsicht bringt Kennzahlen und die PIN-Auskunft zusätzlich mit;
        # alles andere muss sich decken.
        gemeinsam = set(aus_verwaltung) & set(aus_aufsicht)
        assert set(aus_verwaltung) <= set(aus_aufsicht), (
            "Die Verwaltung kennt Felder, die der Aufsicht fehlen: "
            f"{set(aus_verwaltung) - set(aus_aufsicht)}"
        )
        for feld in sorted(gemeinsam):
            assert aus_verwaltung[feld] == aus_aufsicht[feld], f"Feld {feld} weicht ab."
        assert aus_aufsicht["tempo"] == 2.0
