"""Die Auswertung: Modelle gegen die eigenen Aufnahmen, gemessen und gespeichert.

Whisper kommt hier nicht vor. Was geprüft werden soll, ist der Weg drumherum -
was offen ist, in welcher Reihenfolge gerechnet wird, was ein Fehlschlag
anrichtet und dass ein zweiter Lauf nichts doppelt tut. Der Erkenner selbst ist
darum ein Platzhalter, der liefert, was der Test braucht: Die Güte einer echten
Erkennung ist in `packages/wortlaut/tests/test_metriken.py` geprüft, und ein
Modell zu laden kostete je Test Minuten.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import augmentierung, laeufe, registry
from wortlaut.whisper import Transkript

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.db.models import Erkennung
from apps.hoeren.backend.deps import engine_fuer
from apps.hoeren.backend.services import auswertung

MODELLE = "small,medium"
# Was eine übernommene Faltungszeile sagt - daran ist sie von einer hier
# gerechneten zu unterscheiden.
AUS_DER_FALTUNG = "aus der Faltung"
# Zwei Modelle mal alle Fassungen: So viele Zeilen entstehen je Aufnahme. Die
# Zahl der Fassungen steht in `augmentierung` und nicht hier - sie hat sich
# schon einmal geändert (September 2026, `pegel` und `lauter` verworfen), und
# eine Kopie davon wäre die Stelle, die dann bricht.
FASSUNGEN = len(augmentierung.VARIANTEN)
JE_AUFNAHME = 2 * FASSUNGEN


class PlatzhalterErkenner:
    """Ein Erkenner, der nicht hört, sondern nachschlägt.

    `antworten` bildet den Modellnamen auf das ab, was dabei herauskommen
    soll: entweder ein Text oder eine Ausnahme, die geworfen wird.
    """

    def __init__(self, modell: str, antworten: dict[str, str | Exception]) -> None:
        self.modell = modell
        self.antworten = antworten

    def transkribiere(self, wav: Path, sprache: str) -> Transkript:
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
        # Seit die Auswertung auch trainierte Stände misst, bekommt sie das
        # Datenverzeichnis dazu - dort liegen deren Gewichte.
        lambda modell, geraet, rechenart, datenverzeichnis=None: PlatzhalterErkenner(
            modell, antworten
        ),
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


def _sprecher(klient: TestClient) -> str:
    return klient.get("/api/zugang").json()["sprecher_id"]


def _aufnahmen(klient: TestClient) -> list[str]:
    """Die Kennungen der eigenen Aufnahmen, älteste zuerst."""
    return [
        eintrag["id"]
        for eintrag in klient.get("/api/konto/recordings").json()["aufnahmen"]
    ]


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

        # Zwei Aufnahmen, zwei Modelle, alle Fassungen.
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
        assert namen == list(augmentierung.VARIANTEN)
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
        assert varianten == sorted(
            f"{aufnahme}.{abwandlung.name}.wav"
            for abwandlung in augmentierung.ABWANDLUNGEN
        )
        # Das Original bleibt, wo es war: `audio/` ist unverändert das, was in
        # der Datenbank steht.
        assert [pfad.name for pfad in sorted(korpus.rglob("audio/*.wav"))] == [
            f"{aufnahme}.wav"
        ]

    def test_verworfene_aufnahme_nimmt_ihre_fassungen_mit(
        self, klient: TestClient, quelle: str, sprich, antworten: dict, tmp_path: Path
    ) -> None:
        # Eine abgewandelte Fassung ist dieselbe Stimme, nur
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

    def test_verwerfen_nach_dem_rechnen_laesst_nichts_ueber_hundert_prozent(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        """Gemessen bleibt gemessen - gezählt wird trotzdem nur, was gilt.

        Sonst zählte `gesamt` die verworfene Aufnahme nicht mehr, `erledigt`
        ihre Zeilen aber weiter, und der Balken stünde über 100 %.
        """
        sprich()
        sprich()
        antworten.update({"small": "etwas", "medium": "etwas"})
        assert _laufe_bis_fertig(klient)["erledigt"] == 2 * JE_AUFNAHME

        assert klient.delete(f"/api/recordings/{_erste(klient)}").status_code == 204

        stand = klient.get("/api/auswertung").json()["stand"]
        assert (stand["erledigt"], stand["gesamt"]) == (JE_AUFNAHME, JE_AUFNAHME)

    def test_verwerfen_raeumt_die_erkannten_texte_weg(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        # Der erkannte Text ist dieselbe Äußerung, nur in Schrift. Ihn stehen
        # zu lassen, während das Audio gelöscht wird, wäre die halbe Bewegung.
        sprich()
        antworten.update({"small": "etwas", "medium": "etwas"})
        _laufe_bis_fertig(klient)
        aufnahme = _erste(klient)
        assert klient.get(f"/api/auswertung/{aufnahme}").json()["erkennungen"]

        assert klient.delete(f"/api/recordings/{aufnahme}").status_code == 204

        with Session(engine_fuer(_sprecher(klient))) as db:
            assert db.scalars(select(Erkennung)).all() == []

    def test_ein_scheiterndes_modell_haelt_den_lauf_nicht_auf(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        vorlage = sprich()
        antworten.update({"small": RuntimeError("Modell nicht ladbar"), "medium": vorlage})

        stand = _laufe_bis_fertig(klient)

        # Übersprungen wird fassungsweise: Das Modell scheitert an jeder
        # Fassung, und jede wird einzeln vermerkt statt die Aufnahme als Ganzes.
        assert stand["uebersprungen"] == FASSUNGEN
        assert "Modell nicht ladbar" in (stand["fehler"] or "")
        # Das andere Modell ist trotzdem durchgelaufen, und zwar vollständig.
        werte = klient.get("/api/auswertung").json()["punkte"][0]["werte"]
        assert len(werte["medium"]) == FASSUNGEN
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
        assert len(list(korpus.rglob("varianten/*.wav"))) == len(augmentierung.ABWANDLUNGEN)

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
            (modell, fassung)
            for modell in ("small", "medium")
            for fassung in augmentierung.VARIANTEN
        ]
        # Die erste Zeile des zweiten Modells - das ist die, die trifft.
        assert vergleich["erkennungen"][FASSUNGEN]["text"] == vorlage

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


class TestRechenwerk:
    """Jede Messung sagt, worauf sie entstand - und was anderswo entstand, gilt nicht.

    Die Rechenzeit hängt an der Maschine und nicht am Modell: Zwischen Karte
    und Prozessor liegt beim Erkennen das Zehn- bis Zwanzigfache. Eine Spalte,
    die beides mischt, sagt weniger als keine.
    """

    def _zeilen(self, sprecher: str):
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from apps.hoeren.backend.db.models import Erkennung
        from apps.hoeren.backend.deps import engine_fuer

        with Session(engine_fuer(sprecher)) as db:
            return list(db.scalars(select(Erkennung)))

    def test_jede_zeile_traegt_ihr_rechenwerk(
        self, klient: TestClient, sprecher: str, quelle: str, sprich, antworten: dict
    ) -> None:
        antworten.update({"small": "irgendetwas", "medium": "irgendetwas"})
        sprich()
        _laufe_bis_fertig(klient)

        werke = {zeile.rechenwerk for zeile in self._zeilen(sprecher)}

        # Der Ersatz für Whisper meldet kein eigenes Rechenwerk - dann gilt das
        # des Laufs. Leer wäre der Fehler: Eine solche Zeile gälte bei jedem
        # weiteren Lauf aufs Neue als offen, und der Lauf käme nie zum Ende.
        assert werke and "" not in werke

    def test_was_auf_einem_anderen_rechenwerk_entstand_wird_neu_gerechnet(
        self, klient: TestClient, sprecher: str, quelle: str, sprich, antworten: dict
    ) -> None:
        from sqlalchemy import update
        from sqlalchemy.orm import Session

        from apps.hoeren.backend.db.models import Erkennung
        from apps.hoeren.backend.deps import engine_fuer

        antworten.update({"small": "irgendetwas", "medium": "irgendetwas"})
        sprich()
        vorher = _laufe_bis_fertig(klient)
        assert vorher["erledigt"] == vorher["gesamt"] > 0

        # So sieht der Bestand aus, nachdem jemand von der Karte auf den
        # Prozessor gewechselt ist - oder umgekehrt.
        with Session(engine_fuer(sprecher)) as db:
            db.execute(update(Erkennung).values(rechenwerk="cuda/float16"))
            db.commit()

        offen = klient.get("/api/auswertung").json()["stand"]
        assert offen["erledigt"] == 0
        assert offen["gesamt"] == vorher["gesamt"]

        # Und der nächste Lauf holt sie wirklich zurück, statt sie liegen zu
        # lassen: Sonst stünden zwei Maßstäbe in einer Spalte.
        nachher = _laufe_bis_fertig(klient)
        assert nachher["erledigt"] == nachher["gesamt"]
        assert not [z for z in self._zeilen(sprecher) if z.rechenwerk == "cuda/float16"]


class TestNichtsZuTun:
    """Ein Knopf, der nichts tut, muss sagen, dass er nichts zu tun hatte.

    Der Lauf ist wiederaufnehmbar: Er rechnet, was fehlt. Steht schon alles, ist
    er fertig, bevor er anfängt - und für den Menschen davor sah das aus wie ein
    Knopf, der kaputt ist: Der Fortschritt blieb, wo er war, und sonst geschah
    nichts.
    """

    def test_ein_zweiter_start_meldet_dass_nichts_offen_war(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        antworten.update({"small": "irgendetwas", "medium": "irgendetwas"})
        sprich()
        fertig = _laufe_bis_fertig(klient)
        assert fertig["erledigt"] == fertig["gesamt"] > 0

        nochmal = klient.post("/api/auswertung/start").json()

        # `laeuft` ist die Auskunft, an der die Ansicht das erkennt. Früher
        # stand hier `True`, obwohl die Aufgabe nichts vorfand und sofort
        # zurückkam - eine Angabe, auf die sich niemand verlassen konnte.
        assert nochmal["laeuft"] is False
        assert nochmal["erledigt"] == nochmal["gesamt"] == fertig["gesamt"]

    def test_mit_einer_neuen_aufnahme_laeuft_er_wieder(
        self, klient: TestClient, quelle: str, sprich, antworten: dict
    ) -> None:
        antworten.update({"small": "irgendetwas", "medium": "irgendetwas"})
        sprich()
        _laufe_bis_fertig(klient)

        sprich()
        angestossen = klient.post("/api/auswertung/start").json()

        assert angestossen["laeuft"] is True
        assert _laufe_bis_fertig(klient)["erledigt"] == JE_AUFNAHME * 2

    def test_ohne_aufnahmen_laeuft_ebenfalls_nichts(self, klient: TestClient) -> None:
        angestossen = klient.post("/api/auswertung/start").json()
        assert angestossen["laeuft"] is False
        assert angestossen["gesamt"] == 0


class TestTrainierteStaende:
    """Ein trainierter Stand tritt hier neben die Grundmodelle.

    **Und er wird nicht neu gerechnet, wo es schon eine ehrliche Zahl gibt.**
    Die meisten Aufnahmen dieses Korpus hat er im Training gehört; ihn darauf
    loszulassen ergäbe eine Zahl über sein Gedächtnis. Für genau sie liegt die
    Messung der Kreuzvalidierung vor, und die wird übernommen
    (`014_erkennungen_aus_faltungen.sql`).
    """

    @pytest.fixture
    def lege_stand_an(self, klient: TestClient) -> Callable[..., str]:
        """Einen Stand samt Lauf hinlegen, mit Faltungsmessungen zu diesen Aufnahmen."""

        def hin(*aufnahmen: str, mit_gewichten: bool = True) -> str:
            daten = einstellungen().data_dir
            job = "job_probe"
            sprecher = _sprecher(klient)
            ref = f"{sprecher}/20260912T1420-lora-original"
            verzeichnis = laeufe.lauf_verzeichnis(daten, job)
            verzeichnis.mkdir(parents=True, exist_ok=True)
            for aufnahme_id in aufnahmen:
                for fassung in augmentierung.VARIANTEN:
                    laeufe.haenge_an(
                        verzeichnis / laeufe.BEWERTUNG,
                        {
                            "recording_id": aufnahme_id,
                            "variante": fassung,
                            "text": AUS_DER_FALTUNG,
                            "wer": 0.25,
                            "cer": 0.1,
                            "mer": 0.25,
                            "wil": 0.3,
                            "genauigkeit": 70.0,
                            "rechenzeit_s": 9.0,
                            # Ein anderes Rechenwerk als dieses hier - genau
                            # der Fall, in dem eine gerechnete Zeile als offen
                            # gälte und eine übernommene nicht.
                            "rechenwerk": "cuda/float16",
                        },
                    )
            registry.schreibe_stand(
                daten, {"id": ref, "job_id": job, "methode": "lora", "daten": "original"}
            )
            if mit_gewichten:
                registry.ct2_verzeichnis(daten, ref).mkdir(parents=True, exist_ok=True)
            return ref

        return hin

    def test_der_stand_steht_in_der_modellliste(
        self, klient: TestClient, quelle: str, sprich, lege_stand_an
    ) -> None:
        sprich()
        ref = lege_stand_an()
        assert ref in klient.get("/api/auswertung").json()["modelle"]

    def test_ohne_gewichte_tritt_er_nicht_an(
        self, klient: TestClient, quelle: str, sprich, lege_stand_an
    ) -> None:
        # Er brächte seine Faltungen mit, könnte aber keine neuere Aufnahme
        # hören - und eine Zeile, die nach dem halben Korpus aufhört, lässt
        # sich neben die übrigen nicht stellen.
        sprich()
        ref = lege_stand_an(mit_gewichten=False)
        assert ref not in klient.get("/api/auswertung").json()["modelle"]

    def test_er_bekommt_seine_kurzkennung_als_beschriftung(
        self, klient: TestClient, quelle: str, sprich, lege_stand_an
    ) -> None:
        # `spr_…/20260912T1420-lora-original` trägt keine Achse der Welt, und
        # ein vorangestelltes Wort stünde in jeder Zeile dasselbe da.
        sprich()
        ref = lege_stand_an()
        beschriftungen = klient.get("/api/auswertung").json()["beschriftungen"]
        assert beschriftungen["small"] == "small"
        assert beschriftungen[ref] == registry.kurzkennung(ref.split("/", 1)[1])

    def test_die_faltungen_stehen_da_bevor_jemand_rechnen_laesst(
        self, klient: TestClient, quelle: str, sprich, lege_stand_an
    ) -> None:
        """Gemessen ist gemessen - dafür muss niemand einen Knopf drücken.

        Sonst zeigte die Ansicht bis zum ersten Lauf zu wenige fertige und zu
        viele offene Posten und verlangte eine Rechnung für etwas, das längst
        dasteht.
        """
        sprich()
        aufnahme = _aufnahmen(klient)[0]
        ref = lege_stand_an(aufnahme)

        uebersicht = klient.get("/api/auswertung").json()
        assert uebersicht["punkte"][0]["werte"][ref] != {}
        # Die Faltungen zählen als erledigt; offen sind nur die Grundmodelle.
        assert uebersicht["stand"]["erledigt"] == FASSUNGEN
        assert uebersicht["stand"]["gesamt"] == FASSUNGEN * 3

    def test_faltungen_werden_uebernommen_statt_gerechnet(
        self, klient: TestClient, quelle: str, sprich, antworten: dict, lege_stand_an
    ) -> None:
        sprich()
        antworten.update({"small": "egal", "medium": "egal"})
        aufnahme = _aufnahmen(klient)[0]
        ref = lege_stand_an(aufnahme)

        _laufe_bis_fertig(klient)

        vom_stand = [
            zeile
            for zeile in klient.get(f"/api/auswertung/{aufnahme}").json()["erkennungen"]
            if zeile["modell"] == ref
        ]
        assert len(vom_stand) == FASSUNGEN
        # Aus der Faltung und nicht vom Platzhalter-Erkenner - für den steht in
        # `antworten` unter dieser Kennung nichts, er würde also scheitern.
        assert {zeile["text"] for zeile in vom_stand} == {AUS_DER_FALTUNG}

    def test_spaetere_aufnahmen_rechnet_der_stand_selbst(
        self, klient: TestClient, quelle: str, sprich, antworten: dict, lege_stand_an
    ) -> None:
        """Der eigentliche Punkt: Die Lücke schließt der ausgelieferte Stand.

        Die zweite Aufnahme kam nach dem Training - er hat sie nie gehört, also
        ist sie für ihn dasselbe Prüfstück wie für ein Grundmodell.
        """
        sprich()
        sprich()
        antworten.update({"small": "egal", "medium": "egal"})
        alt, spaeter = _aufnahmen(klient)[:2]
        ref = lege_stand_an(alt)
        antworten[ref] = "frisch gehört"

        _laufe_bis_fertig(klient)

        def texte(aufnahme: str) -> set[str]:
            return {
                zeile["text"]
                for zeile in klient.get(f"/api/auswertung/{aufnahme}").json()["erkennungen"]
                if zeile["modell"] == ref
            }

        assert texte(alt) == {AUS_DER_FALTUNG}
        assert texte(spaeter) == {"frisch gehört"}

    def test_wer_mitten_im_lauf_verschwindet_tritt_nicht_weiter_an(
        self, klient: TestClient, quelle: str, sprich, lege_stand_an
    ) -> None:
        """Ein Lauf hält nicht an einer Liste fest, die beim Anstoßen stimmte.

        Sonst liefe er je Aufnahme und Fassung in denselben Fehler - einige
        hundert Mal, und am Ende stünde eine große Zahl „übersprungen".
        """
        sprich()
        daten = einstellungen().data_dir
        ref = lege_stand_an()
        assert auswertung.noch_da(daten, ["small", ref]) == ["small", ref]

        shutil.rmtree(registry.ct2_verzeichnis(daten, ref))
        assert auswertung.noch_da(daten, ["small", ref]) == ["small"]

    def test_fehlende_gewichte_sagen_das_mit_der_kennung(
        self, klient: TestClient, quelle: str, sprich, lege_stand_an
    ) -> None:
        # Sonst käme die Meldung von faster-whisper - über einen Hub, der hier
        # nichts zu suchen hat - und nennte den ganzen Pfad.
        sprich()
        daten = einstellungen().data_dir
        ref = lege_stand_an()
        shutil.rmtree(registry.ct2_verzeichnis(daten, ref))

        with pytest.raises(FileNotFoundError) as fehler:
            auswertung.gewichte(daten, ref)
        assert registry.kurzkennung(ref.split("/", 1)[1]) in str(fehler.value)
        assert "/" not in str(fehler.value)

    def test_ein_stand_hoert_so_wie_er_gelernt_hat(
        self, klient: TestClient, quelle: str, sprich, lege_stand_an
    ) -> None:
        """Was im Manifest steht, gilt beim Messen - und was fehlt, gilt nicht.

        Ein Stand von vor September 2026 hat ungeschnittene Ausschnitte
        gelernt. Bekäme er hier geschnittene, wäre die Zahl daneben eine über
        eine Lage, die es nie gibt - und niemand sähe es, denn ein Text kommt
        ja heraus.
        """
        sprich()
        daten = einstellungen().data_dir
        ref = lege_stand_an()

        assert auswertung.gehoer_fuer(daten, "small") == (1.0, False)
        assert auswertung.gehoer_fuer(daten, ref) == (1.0, False)

        sprecher, version = ref.split("/", 1)
        manifest = registry.lies_stand(daten, sprecher, version)
        registry.schreibe_stand(daten, {**manifest, "tempo": 2.0, "stille": True})
        assert auswertung.gehoer_fuer(daten, ref) == (2.0, True)

    def test_ein_geloeschter_stand_laesst_nichts_zurueck(
        self, klient: TestClient, quelle: str, sprich, antworten: dict, lege_stand_an
    ) -> None:
        # Wer einen Lauf löscht, löscht alles, was aus ihm hervorging. Seine
        # Messungen stehen aber in der Tabelle von „hören".
        sprich()
        antworten.update({"small": "egal", "medium": "egal"})
        aufnahme = _aufnahmen(klient)[0]
        ref = lege_stand_an(aufnahme)
        _laufe_bis_fertig(klient)
        assert any(
            zeile["modell"] == ref
            for zeile in klient.get(f"/api/auswertung/{aufnahme}").json()["erkennungen"]
        )

        sprecher, version = ref.split("/", 1)
        registry.loesche_stand(einstellungen().data_dir, sprecher, version)
        _laufe_bis_fertig(klient)

        assert not any(
            zeile["modell"] == ref
            for zeile in klient.get(f"/api/auswertung/{aufnahme}").json()["erkennungen"]
        )
