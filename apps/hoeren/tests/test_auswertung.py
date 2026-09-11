"""Die Auswertung: Modelle gegen die eigenen Aufnahmen, gemessen und gespeichert.

Whisper kommt hier nicht vor. Was geprüft werden soll, ist der Weg drumherum -
was offen ist, in welcher Reihenfolge gerechnet wird, was ein Fehlschlag
anrichtet und dass ein zweiter Lauf nichts doppelt tut. Der Erkenner selbst ist
darum ein Platzhalter, der liefert, was der Test braucht: Die Güte einer echten
Erkennung ist in `packages/wortlaut/tests/test_metriken.py` geprüft, und ein
Modell zu laden kostete je Test Minuten.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut.whisper import Transkript

from apps.hoeren.backend.services import auswertung

MODELLE = "small,medium"
# Zwei Modelle mal vier Fassungen: So viele Zeilen entstehen je Aufnahme.
JE_AUFNAHME = 2 * 4


class PlatzhalterErkenner:
    """Ein Erkenner, der nicht hört, sondern nachschlägt.

    `antworten` bildet den Modellnamen auf das ab, was dabei herauskommen
    soll: entweder ein Text oder eine Ausnahme, die geworfen wird.
    """

    def __init__(self, modell: str, antworten: dict[str, str | Exception]) -> None:
        self.modell = modell
        self.antworten = antworten

    def transkribiere(self, wav: Path, sprache: str = "de") -> Transkript:
        antwort = self.antworten[self.modell]
        if isinstance(antwort, Exception):
            raise antwort
        return Transkript(text=antwort, abschnitte=[])


@pytest.fixture
def antworten() -> dict[str, str | Exception]:
    """Was die Modelle „hören". Ein Test schreibt hier hinein, was er braucht."""
    return {}


@pytest.fixture(autouse=True)
def _erkenner(
    antworten: dict[str, str | Exception], monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    monkeypatch.setenv("WORTLAUT_AUSWERTUNG_MODELLE", MODELLE)
    monkeypatch.setattr(
        auswertung,
        "transkriptor_fuer",
        lambda modell, geraet, rechenart: PlatzhalterErkenner(modell, antworten),
    )
    auswertung.vergiss_lauf()
    yield
    auswertung.vergiss_lauf()


@pytest.fixture
def sprich(klient: TestClient, audio_datei: dict) -> Callable[[], str]:
    """Eine Aufnahme machen; gibt die Vorlage zurück, die dabei vorgelesen wurde."""

    def einmal() -> str:
        naechste = klient.get("/api/prompts/next").json()["aktuell"]
        antwort = klient.post(
            "/api/recordings",
            files=audio_datei,
            data={"prompt_id": naechste["id"], "modus": "gelesen"},
        )
        assert antwort.status_code == 201, antwort.text
        return naechste["text"]

    return einmal


def _laufe_bis_fertig(klient: TestClient, hoechstens: float = 10.0) -> dict:
    """Starten und warten, bis der Hintergrundlauf nichts mehr zu tun hat.

    Abgefragt wird über denselben Weg, den auch die Seite benutzt - damit ist
    zugleich geprüft, dass der Fortschritt während des Laufs abrufbar bleibt
    und der Server nicht blockiert.
    """
    assert klient.post("/api/auswertung/start").status_code == 200
    ende = time.monotonic() + hoechstens
    while time.monotonic() < ende:
        stand = klient.get("/api/auswertung").json()["stand"]
        if not stand["laeuft"]:
            return stand
    raise AssertionError("Der Lauf wurde nicht fertig.")


class TestZugriff:
    def test_ohne_zugang_kein_zugriff(self, klient_ohne_token: TestClient) -> None:
        assert klient_ohne_token.get("/api/auswertung").status_code == 401

    def test_aufsicht_hat_hier_keinen_eigenen_sprecher(self, aufsicht: TestClient) -> None:
        # Wie gut ein Modell hört, hängt an der Stimme - gemessen wird immer
        # ein bestimmter Korpus, und den wählt der Zugang.
        assert aufsicht.get("/api/auswertung").status_code == 401


class TestOhneAufnahmen:
    def test_leerer_korpus_hat_nichts_zu_rechnen(self, klient: TestClient, quelle: str) -> None:
        antwort = klient.get("/api/auswertung").json()
        assert antwort["punkte"] == []
        assert antwort["stand"]["gesamt"] == 0
        assert antwort["modelle"] == ["small", "medium"]

    def test_die_masse_kommen_vom_server(self, klient: TestClient) -> None:
        schluessel = [m["schluessel"] for m in klient.get("/api/auswertung").json()["metriken"]]
        assert schluessel[0] == "genauigkeit"
        assert {"wer", "cer", "mer", "wil"} <= set(schluessel)


class TestLauf:
    def test_rechnet_jede_fassung_jeder_aufnahme_durch_jedes_modell(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        vorlage = sprich()
        sprich()
        antworten.update({"small": "völlig daneben", "medium": vorlage})

        stand = _laufe_bis_fertig(klient)

        # Zwei Aufnahmen, zwei Modelle, vier Fassungen.
        assert stand["gesamt"] == 2 * JE_AUFNAHME
        assert stand["erledigt"] == 2 * JE_AUFNAHME
        assert stand["fehler"] is None

    def test_misst_jede_fassung_einzeln(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        sprich()
        antworten.update({"small": "etwas", "medium": "etwas"})
        _laufe_bis_fertig(klient)

        antwort = klient.get("/api/auswertung").json()
        gemessen = antwort["punkte"][0]["werte"]
        assert set(gemessen) == {"small", "medium"}
        # Die Fassungen kommen vom Server, samt Namen und Erklärung - die
        # Oberfläche führt keine eigene Liste.
        namen = [eintrag["schluessel"] for eintrag in antwort["varianten"]]
        assert namen == ["original", "pegel", "lauter", "rauschen"]
        assert set(gemessen["small"]) == set(namen)

    def test_die_abgewandelten_fassungen_liegen_geordnet_im_korpus(
        self, klient: TestClient, quelle: str, sprich, antworten: dict, tmp_path: Path
    ) -> None:
        # Jede Fassung trägt erst die Aufnahme, dann ihren Namen, und sie liegt
        # nicht bei den Aufnahmen, sondern darunter. Damit kann keine Datei mit
        # einer Aufnahme verwechselt werden, und ein sortiertes Verzeichnis
        # liegt nach Aufnahmen geordnet da.
        sprich()
        aufnahme = _erste(klient)
        antworten.update({"small": "etwas", "medium": "etwas"})
        _laufe_bis_fertig(klient)

        korpus = tmp_path / "data" / "korpus"
        varianten = sorted(pfad.name for pfad in korpus.rglob("varianten/*.wav"))
        assert varianten == [
            f"{aufnahme}.lauter.wav",
            f"{aufnahme}.pegel.wav",
            f"{aufnahme}.rauschen.wav",
        ]
        # Das Original bleibt, wo es war: `audio/` ist unverändert das, was in
        # der Datenbank steht.
        assert [pfad.name for pfad in sorted(korpus.rglob("audio/*.wav"))] == [
            f"{aufnahme}.wav"
        ]

    def test_verworfene_aufnahme_nimmt_ihre_fassungen_mit(
        self, klient: TestClient, quelle: str, sprich, antworten: dict, tmp_path: Path
    ) -> None:
        # Eine abgewandelte Fassung ist dieselbe Stimme, nur lauter oder
        # verrauscht - wer die Aufnahme wegwirft, hat nicht drei Kopien gemeint.
        sprich()
        antworten.update({"small": "etwas", "medium": "etwas"})
        _laufe_bis_fertig(klient)
        korpus = tmp_path / "data" / "korpus"
        assert list(korpus.rglob("varianten/*.wav"))

        assert klient.delete(f"/api/recordings/{_erste(klient)}").status_code == 204
        assert not list(korpus.rglob("*.wav"))

    def test_nummeriert_luecklos_von_eins_an(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        for _ in range(3):
            sprich()
        antworten.update({"small": "etwas", "medium": "etwas"})
        _laufe_bis_fertig(klient)

        punkte = klient.get("/api/auswertung").json()["punkte"]
        assert [p["nummer"] for p in punkte] == [1, 2, 3]

    def test_gute_erkennung_bekommt_die_bessere_note(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        vorlage = sprich()
        antworten.update({"small": "ein ganz anderer satz", "medium": vorlage})
        _laufe_bis_fertig(klient)

        werte = klient.get("/api/auswertung").json()["punkte"][0]["werte"]
        assert werte["medium"]["original"]["genauigkeit"] == pytest.approx(100.0)
        assert werte["medium"]["original"]["wer"] == 0
        assert (
            werte["small"]["original"]["genauigkeit"]
            < werte["medium"]["original"]["genauigkeit"]
        )

    def test_zweiter_lauf_rechnet_nichts_doppelt(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        sprich()
        antworten.update({"small": "etwas", "medium": "etwas"})
        _laufe_bis_fertig(klient)

        # Ein zweiter Lauf über denselben Stand: Es gibt nichts mehr zu tun,
        # und vor allem kommt nichts hinzu.
        stand = _laufe_bis_fertig(klient)
        assert stand["erledigt"] == JE_AUFNAHME
        erkennungen = klient.get(f"/api/auswertung/{_erste(klient)}").json()["erkennungen"]
        assert len(erkennungen) == JE_AUFNAHME

    def test_neue_aufnahme_wird_beim_naechsten_lauf_nachgeholt(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        sprich()
        antworten.update({"small": "etwas", "medium": "etwas"})
        _laufe_bis_fertig(klient)

        sprich()
        assert klient.get("/api/auswertung").json()["stand"]["erledigt"] == JE_AUFNAHME
        stand = _laufe_bis_fertig(klient)
        assert (stand["erledigt"], stand["gesamt"]) == (2 * JE_AUFNAHME, 2 * JE_AUFNAHME)

    def test_verworfene_aufnahme_zaehlt_nicht_mit(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        # Was der Sprecher selbst verworfen hat, ist kein Prüfstück - es ginge
        # sonst als schlechte Note eines Modells durch.
        sprich()
        verworfen = _erste(klient)
        assert klient.delete(f"/api/recordings/{verworfen}").status_code == 204

        antworten.update({"small": "etwas", "medium": "etwas"})
        stand = _laufe_bis_fertig(klient)
        assert stand["gesamt"] == 0
        assert klient.get("/api/auswertung").json()["punkte"] == []

    def test_ein_scheiterndes_modell_haelt_den_lauf_nicht_auf(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        vorlage = sprich()
        antworten.update({"small": RuntimeError("Modell nicht ladbar"), "medium": vorlage})

        stand = _laufe_bis_fertig(klient)

        # Übersprungen wird fassungsweise: Das Modell scheitert an jeder der
        # vier, und jede wird einzeln vermerkt statt die Aufnahme als Ganzes.
        assert stand["uebersprungen"] == 4
        assert "Modell nicht ladbar" in (stand["fehler"] or "")
        # Das andere Modell ist trotzdem durchgelaufen, und zwar vollständig.
        werte = klient.get("/api/auswertung").json()["punkte"][0]["werte"]
        assert len(werte["medium"]) == 4
        assert "small" not in werte


class TestNachtraeglich:
    """Aufnahmen, die vor der Einführung der Fassungen im Korpus lagen.

    Nachgestellt, indem die Dateien wieder verschwinden - für den Server ist
    das derselbe Fall wie ein Korpus, in dem es sie nie gab.
    """

    def test_der_lauf_holt_fehlende_fassungen_nach(
        self, klient: TestClient, quelle: str, sprich, antworten: dict, tmp_path: Path
    ) -> None:
        sprich()
        korpus = tmp_path / "data" / "korpus"
        for pfad in korpus.rglob("varianten/*.wav"):
            pfad.unlink()

        antworten.update({"small": "etwas", "medium": "etwas"})
        stand = _laufe_bis_fertig(klient)

        assert stand["erledigt"] == JE_AUFNAHME
        assert len(list(korpus.rglob("varianten/*.wav"))) == 3

    def test_das_skript_holt_sie_fuer_alle_korpora_nach(
        self, klient: TestClient, quelle: str, sprich, tmp_path: Path
    ) -> None:
        # `scripts/augmentieren.py` ist der Weg, das vor einem Lauf und für
        # alle Sprecher auf einmal zu tun.
        from scripts import augmentieren

        sprich()
        korpus = tmp_path / "data" / "korpus"
        vorher = {pfad.name: pfad.read_bytes() for pfad in korpus.rglob("varianten/*.wav")}
        for pfad in korpus.rglob("varianten/*.wav"):
            pfad.unlink()

        assert augmentieren.main() == 0

        nachher = {pfad.name: pfad.read_bytes() for pfad in korpus.rglob("varianten/*.wav")}
        # Byte für Byte dieselben Dateien: Das Rauschen hängt an der Kennung
        # der Aufnahme und nicht am Zufall des Tages. Ohne das wäre eine
        # wiederholte Messung keine Wiederholung.
        assert nachher == vorher

    def test_ein_zweiter_lauf_des_skripts_rechnet_nichts_neu(
        self, klient: TestClient, quelle: str, sprich
    ) -> None:
        from scripts import augmentieren

        sprich()
        assert augmentieren.main() == 0
        assert augmentieren.main() == 0


class TestVergleich:
    def test_zeigt_vorlage_und_jede_fassung(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        vorlage = sprich()
        antworten.update({"small": "so ungefähr", "medium": vorlage})
        _laufe_bis_fertig(klient)

        vergleich = klient.get(f"/api/auswertung/{_erste(klient)}").json()
        assert vergleich["nummer"] == 1
        assert vergleich["referenz"] == vorlage
        # In der Reihenfolge der Konfiguration, nicht in der der Datenbank -
        # und Fassung innen, Modell außen.
        assert [(e["modell"], e["variante"]) for e in vergleich["erkennungen"]] == [
            ("small", "original"),
            ("small", "pegel"),
            ("small", "lauter"),
            ("small", "rauschen"),
            ("medium", "original"),
            ("medium", "pegel"),
            ("medium", "lauter"),
            ("medium", "rauschen"),
        ]
        assert vergleich["erkennungen"][4]["text"] == vorlage

    def test_unbekannte_aufnahme_ist_vierhundertvier(self, klient: TestClient) -> None:
        assert klient.get("/api/auswertung/rec_gibtesnicht").status_code == 404

    def test_fremde_aufnahme_ist_nicht_zu_sehen(
        self,
        klient: TestClient,
        quelle: str,
        sprich,
        antworten: dict,
        klient_fuer: Callable[[str], TestClient],
        verwalter: TestClient,
    ) -> None:
        sprich()
        meine = _erste(klient)

        zweiter = verwalter.post("/api/speakers", json={"name": "Zweite"}).json()["id"]
        with klient_fuer(zweiter) as fremder:
            # Die Kennung ist echt, nur eben aus einem anderen Korpus. Der
            # Zugang öffnet nur den eigenen - hier ist sie schlicht unbekannt.
            assert fremder.get(f"/api/auswertung/{meine}").status_code == 404


def _erste(klient: TestClient) -> str:
    """Die Kennung der ersten (ältesten) brauchbaren Aufnahme."""
    return klient.get("/api/konto/recordings").json()["aufnahmen"][-1]["id"]
