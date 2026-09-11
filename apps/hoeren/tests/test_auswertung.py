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
    def test_rechnet_jede_aufnahme_durch_jedes_modell(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        vorlage = sprich()
        sprich()
        antworten.update({"small": "völlig daneben", "medium": vorlage})

        stand = _laufe_bis_fertig(klient)

        assert stand["gesamt"] == 4  # zwei Aufnahmen, zwei Modelle
        assert stand["erledigt"] == 4
        assert stand["fehler"] is None

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
        assert werte["medium"]["genauigkeit"] == pytest.approx(100.0)
        assert werte["medium"]["wer"] == 0
        assert werte["small"]["genauigkeit"] < werte["medium"]["genauigkeit"]

    def test_zweiter_lauf_rechnet_nichts_doppelt(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        sprich()
        antworten.update({"small": "etwas", "medium": "etwas"})
        _laufe_bis_fertig(klient)

        # Ein zweiter Lauf über denselben Stand: Es gibt nichts mehr zu tun,
        # und vor allem kommt nichts hinzu.
        stand = _laufe_bis_fertig(klient)
        assert stand["erledigt"] == 2
        assert len(klient.get(f"/api/auswertung/{_erste(klient)}").json()["erkennungen"]) == 2

    def test_neue_aufnahme_wird_beim_naechsten_lauf_nachgeholt(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        sprich()
        antworten.update({"small": "etwas", "medium": "etwas"})
        _laufe_bis_fertig(klient)

        sprich()
        assert klient.get("/api/auswertung").json()["stand"]["erledigt"] == 2
        stand = _laufe_bis_fertig(klient)
        assert (stand["erledigt"], stand["gesamt"]) == (4, 4)

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

        assert stand["uebersprungen"] == 1
        assert "Modell nicht ladbar" in (stand["fehler"] or "")
        # Das andere Modell ist trotzdem durchgelaufen.
        werte = klient.get("/api/auswertung").json()["punkte"][0]["werte"]
        assert "medium" in werte
        assert "small" not in werte


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
        # In der Reihenfolge der Konfiguration, nicht in der der Datenbank.
        assert [e["modell"] for e in vergleich["erkennungen"]] == ["small", "medium"]
        assert vergleich["erkennungen"][1]["text"] == vorlage

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
