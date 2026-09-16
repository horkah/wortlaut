"""Hat es etwas gebracht? - der trainierte Stand gegen die Baseline.

Der Trainer läuft hier nicht, also wird sein Ergebnis nachgestellt: ein
`zustand.json`, eine `bewertung.jsonl` und ein Manifest in der Registry. Genau
das hinterlässt ein fertiger Lauf, und genau daraus baut die Ansicht ihren
Vergleich.

Die Baseline dagegen ist echt: Sie entsteht wie im Betrieb, indem die
Auswertung von „hören" über den Korpus läuft - mit einem Platzhalter statt
Whisper, denn geprüft wird die Verrechnung und nicht das Hören.
"""

from __future__ import annotations

from datetime import datetime

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import augmentierung, laeufe, registry
from wortlaut.whisper import Transkript

from apps.hoeren.backend.services import auswertung


class PlatzhalterErkenner:
    """Ein Erkenner, der immer dasselbe sagt - hier genügt das vollauf."""

    def __init__(self, antwort: str) -> None:
        self.antwort = antwort

    def transkribiere(self, wav: Path, sprache: str) -> Transkript:
        return Transkript(text=self.antwort, abschnitte=[])


@pytest.fixture(autouse=True)
def _baseline_modell(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Dasselbe Modell, auf das „lernen" trainiert - sonst wäre die Baseline
    # keine.
    monkeypatch.setenv("WORTLAUT_AUSWERTUNG_MODELLE", "small")
    monkeypatch.setattr(
        auswertung,
        "transkriptor_fuer",
        lambda modell, geraet, rechenart: PlatzhalterErkenner("völlig daneben gehört"),
    )
    auswertung.vergiss_lauf()
    yield
    auswertung.vergiss_lauf()


@pytest.fixture
def aufnahmen(quelle: str, sprich) -> list[str]:
    """Neun Aufnahmen - genug für ein volles Muster plus Rest."""
    return sprich(9)


@pytest.fixture
def baseline(hoeren: TestClient, aufnahmen: list[str]) -> None:
    """Die Auswertung von „hören" über dieselben Aufnahmen laufen lassen.

    Hängt ausdrücklich an `aufnahmen`: Eine Baseline über einen leeren
    Korpus wäre keine, und die Reihenfolge der Testbausteine ist nichts, auf
    das man sich verlassen sollte, wenn man sie auch hinschreiben kann.
    """
    assert hoeren.post("/api/auswertung/start").status_code == 200
    ende = time.monotonic() + 20.0
    while time.monotonic() < ende:
        if not hoeren.get("/api/auswertung").json()["stand"]["laeuft"]:
            return
    raise AssertionError("Die Baseline wurde nicht fertig.")


def _lauf_fertigstellen(
    datenverzeichnis: Path, job_id: str, sprecher_id: str, *, genauigkeit: float
) -> str:
    """Nachstellen, was ein durchgelaufener Trainer hinterlässt."""
    verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job_id)
    zeilen = [
        json.loads(zeile)
        for zeile in (verzeichnis / laeufe.MANIFEST).read_text(encoding="utf-8").splitlines()
    ]
    # Nachgestellt wird, was die Kreuzvalidierung hinterlässt: zu **jeder**
    # Zeile eine Messung, jeweils aus der Faltung, die sie zurückgehalten hat.
    for zeile in zeilen:
        laeufe.haenge_an(
            verzeichnis / laeufe.BEWERTUNG,
            {
                "recording_id": zeile["recording_id"],
                "variante": zeile["variante"],
                "faltung": zeile["faltung"],
                "text": zeile["text"],
                "wer": 0.1,
                "cer": 0.05,
                "mer": 0.1,
                "wil": 0.15,
                "genauigkeit": genauigkeit,
                "rechenzeit_s": 0.4,
            },
        )

    version = f"20260912T1200-lora-original-{genauigkeit:.0f}"
    registry.schreibe_stand(
        datenverzeichnis,
        {
            "id": f"{sprecher_id}/{version}",
            "sprecher_id": sprecher_id,
            "basismodell": "openai/whisper-small",
            "methode": "lora",
            "daten": "original",
            "job_id": job_id,
            "erstellt": "2026-09-12T12:00:00+00:00",
            "metriken": {"wer": 0.1, "genauigkeit": genauigkeit, "test_einheiten": 8},
            "status": "fertig",
        },
    )
    laeufe.schreibe_json(
        verzeichnis / laeufe.ZUSTAND,
        {"status": laeufe.FERTIG, "beendet": laeufe.jetzt(), "version": version},
    )
    return version


@pytest.fixture
def fertiger_lauf(klient: TestClient, aufnahmen: list[str], datenverzeichnis, sprecher: str):
    lauf = klient.post(
        "/lernen/api/laeufe", json={"methode": "lora", "daten": "original"}
    ).json()
    version = _lauf_fertigstellen(
        datenverzeichnis, lauf["job_id"], sprecher, genauigkeit=88.0
    )
    return lauf["job_id"], version


class TestVergleich:
    def test_stellt_jede_fassung_der_baseline_gegenueber(
        self, klient: TestClient, baseline: None, fertiger_lauf
    ) -> None:
        job_id, _ = fertiger_lauf
        antwort = klient.get(f"/lernen/api/laeufe/{job_id}").json()

        assert set(antwort["vergleich"]) == set(augmentierung.VARIANTEN)
        genauigkeit = next(
            eintrag
            for eintrag in antwort["vergleich"]["original"]
            if eintrag["mass"] == "genauigkeit"
        )
        # Der Platzhalter hört Unsinn, der nachgestellte Stand trifft fast -
        # also hat sich etwas verbessert.
        assert genauigkeit["trainiert"] == pytest.approx(88.0)
        assert genauigkeit["baseline"] < genauigkeit["trainiert"]
        assert genauigkeit["besser"] is True

    def test_bei_den_fehlerraten_ist_kleiner_besser(
        self, klient: TestClient, baseline: None, fertiger_lauf
    ) -> None:
        job_id, _ = fertiger_lauf
        antwort = klient.get(f"/lernen/api/laeufe/{job_id}").json()
        wer = next(e for e in antwort["vergleich"]["original"] if e["mass"] == "wer")
        assert wer["trainiert"] < wer["baseline"]
        assert wer["besser"] is True

    def test_ohne_baseline_gibt_es_nichts_zu_vergleichen(
        self, klient: TestClient, fertiger_lauf
    ) -> None:
        # Die Auswertung in „hören" ist hier nie gelaufen. Dann steht der
        # trainierte Stand allein da - und die Ansicht behauptet keine
        # Verbesserung gegen eine Zahl, die es nicht gibt.
        job_id, _ = fertiger_lauf
        assert klient.get(f"/lernen/api/laeufe/{job_id}").json()["vergleich"] == {}

    def test_verglichen_wird_nur_was_beide_gemessen_haben(
        self, klient: TestClient, baseline: None, fertiger_lauf
    ) -> None:
        job_id, _ = fertiger_lauf
        antwort = klient.get(f"/lernen/api/laeufe/{job_id}").json()
        anzahlen = {
            eintrag["anzahl"]
            for eintraege in antwort["vergleich"].values()
            for eintrag in eintraege
        }
        # Je Fassung dieselbe Zahl auf beiden Seiten - sonst stünde ein Mittel
        # über zwanzig gegen eines über achtzehn.
        assert anzahlen and 0 not in anzahlen


class TestModelluebersicht:
    """Die eine Ansicht, auf der alles zusammenkommt.

    Grundmodelle und eigene Stände in einer Tabelle, an denselben
    Testaufnahmen gemessen - und ein Knopf, der eines davon freigibt.
    """

    def test_ein_fertiger_lauf_steht_neben_den_grundmodellen(
        self, klient: TestClient, fertiger_lauf
    ) -> None:
        _, version = fertiger_lauf
        antwort = klient.get("/lernen/api/modelle").json()

        arten = {modell["art"] for modell in antwort["modelle"]}
        assert arten == {"grundmodell", "trainiert"}

        eigene = [modell for modell in antwort["modelle"] if modell["art"] == "trainiert"]
        assert [modell["version"] for modell in eigene] == [version]
        # Die Zeile nennt beide unterscheidenden Angaben - vier Stände vom
        # selben Tag wären sonst nicht auseinanderzuhalten.
        assert "LoRA" in eigene[0]["name"]
        assert "Nur Originale" in eigene[0]["name"]

    def test_gemessen_wird_auf_denselben_aufnahmen(
        self, klient: TestClient, baseline: None, fertiger_lauf
    ) -> None:
        antwort = klient.get("/lernen/api/modelle").json()

        assert antwort["vergleichbar"] is True
        assert antwort["gemeinsame_einheiten"] > 0
        # Jede Zeile, die überhaupt gemessen hat, rechnet über genau diese
        # Einheiten - sonst stünde ein Mittel über zwanzig gegen eines über
        # achtzehn, und der Unterschied läge an der Auswahl statt am Modell.
        gezaehlt = {
            modell["einheiten"]["alle"]
            for modell in antwort["modelle"]
            if modell["werte"]
        }
        assert gezaehlt == {antwort["gemeinsame_einheiten"]}

    def test_der_nachgestellte_stand_schlaegt_den_platzhalter(
        self, klient: TestClient, baseline: None, fertiger_lauf
    ) -> None:
        # Der Platzhalter-Erkenner hört Unsinn, der nachgestellte Stand trifft
        # fast - in der Tabelle muss das zu sehen sein.
        modelle = klient.get("/lernen/api/modelle").json()["modelle"]
        eigen = next(modell for modell in modelle if modell["art"] == "trainiert")
        grund = next(modell for modell in modelle if modell["ref"] == "small")

        assert eigen["werte"]["alle"]["genauigkeit"] == pytest.approx(88.0)
        assert grund["werte"]["alle"]["genauigkeit"] < eigen["werte"]["alle"]["genauigkeit"]

    def test_ohne_auswertung_steht_es_dort(self, klient: TestClient, fertiger_lauf) -> None:
        # Die Auswertung in „hören" ist hier nie gelaufen: Dann hat kein
        # Grundmodell eine Zahl, und die Tabelle behauptet keinen Vergleich.
        antwort = klient.get("/lernen/api/modelle").json()

        assert antwort["vergleichbar"] is False
        assert "Auswertung" in antwort["hinweis"]
        assert not next(
            modell for modell in antwort["modelle"] if modell["ref"] == "small"
        )["werte"]
        # Die eigene Zahl steht trotzdem da - eine leere Tabelle verschwiege,
        # dass der Lauf gemessen hat.
        assert next(
            modell for modell in antwort["modelle"] if modell["art"] == "trainiert"
        )["werte"]

    def test_fertig_heisst_noch_nicht_freigegeben(
        self, klient: TestClient, fertiger_lauf
    ) -> None:
        # Zwischen „hat gerechnet" und „damit diktiere ich" liegt der Blick auf
        # die Zahlen.
        antwort = klient.get("/lernen/api/modelle").json()
        assert antwort["freigegeben"] == ""
        assert not [modell for modell in antwort["modelle"] if modell["freigegeben"]]

    def test_freigeben_zieht_jeden_anderen_zurueck(
        self, klient: TestClient, fertiger_lauf, datenverzeichnis, sprecher: str
    ) -> None:
        _, erste = fertiger_lauf
        zweiter = klient.post(
            "/lernen/api/laeufe", json={"methode": "full", "daten": "augmentiert"}
        ).json()
        zweite = _lauf_fertigstellen(
            datenverzeichnis, zweiter["job_id"], sprecher, genauigkeit=91.0
        )

        assert klient.post(
            "/lernen/api/modelle/freigabe", json={"ref": f"{sprecher}/{erste}"}
        ).status_code == 200
        antwort = klient.post(
            "/lernen/api/modelle/freigabe", json={"ref": f"{sprecher}/{zweite}"}
        ).json()

        frei = [modell["version"] for modell in antwort["modelle"] if modell["freigegeben"]]
        assert frei == [zweite]
        # Und die Registry sagt dasselbe - sie ist die Wahrheit, aus der auch
        # „schreiben" liest.
        assert registry.freigegeben(datenverzeichnis, sprecher) == f"{sprecher}/{zweite}"

    def test_auch_ein_grundmodell_laesst_sich_freigeben(
        self, klient: TestClient, fertiger_lauf, datenverzeichnis, sprecher: str
    ) -> None:
        # „Mein eigenes ist noch nicht besser als das Grundmodell" ist eine
        # Antwort, und sie soll sich hier geben lassen - früher ging das nur
        # drüben in „schreiben".
        antwort = klient.post(
            "/lernen/api/modelle/freigabe", json={"ref": "small"}
        ).json()

        assert antwort["freigegeben"] == "small"
        assert registry.freigegeben(datenverzeichnis, sprecher) == "small"

    def test_leere_kennung_nimmt_die_freigabe_zurueck(
        self, klient: TestClient, fertiger_lauf, datenverzeichnis, sprecher: str
    ) -> None:
        klient.post("/lernen/api/modelle/freigabe", json={"ref": "small"})
        antwort = klient.post("/lernen/api/modelle/freigabe", json={"ref": ""}).json()

        assert antwort["freigegeben"] == ""
        assert registry.freigegeben(datenverzeichnis, sprecher) == ""

    def test_unbekanntes_modell_ist_vierhundertvier(self, klient: TestClient) -> None:
        # Ein beliebiger Pfad im Feld wäre ein Weg, fremde Verzeichnisse laden
        # zu lassen - und der Stand eines anderen Sprechers ist fremde Stimme.
        assert klient.post(
            "/lernen/api/modelle/freigabe", json={"ref": "gibtesnicht"}
        ).status_code == 404
        assert klient.post(
            "/lernen/api/modelle/freigabe", json={"ref": "spr_fremd/egal"}
        ).status_code == 404


class TestFreigabe:
    """Was gilt, hat ein Mensch gewählt - und nichts sonst.

    Der Anlass steht in `api/modelle.py`: Zwei Stände, die sich nur im
    Abschluss unterschieden, trugen denselben Titel. Freigegeben wurde
    daraufhin der falsche, und der Verdacht lag zunächst auf der Freigabe
    selbst. Sie war es nicht - aber geprüft gehört beides.
    """

    def _stand(self, datenverzeichnis, sprecher: str, version: str, **felder) -> str:
        kennung = f"{sprecher}/{version}"
        registry.schreibe_stand(
            datenverzeichnis,
            {
                "id": kennung,
                "sprecher_id": sprecher,
                "basismodell": "openai/whisper-small",
                "methode": "lora",
                "daten": "augmentiert",
                "erstellt": "2026-09-14T14:47:00+00:00",
                "daten_umfang": {},
                "metriken": {},
                "laufzeit": "faster-whisper>=1.1",
                "status": "fertig",
                **felder,
            },
        )
        return kennung

    def test_ein_neuer_stand_gibt_sich_nicht_selbst_frei(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis, sprecher: str
    ) -> None:
        sprich(6)
        erster = self._stand(
            datenverzeichnis, sprecher, "20260914T1447-lora-augmentiert", abschluss="bester"
        )
        assert (
            klient.post("/lernen/api/modelle/freigabe", json={"ref": erster}).status_code == 200
        )

        # Und nun der zweite, so wie der Trainer ihn einträgt: alles gleich bis
        # auf den Abschluss, Status `fertig`.
        zweiter = self._stand(
            datenverzeichnis,
            sprecher,
            "20260914T1448-lora-augmentiert-beides",
            abschluss="beides",
            erstellt="2026-09-14T14:48:00+00:00",
        )

        uebersicht = klient.get("/lernen/api/modelle").json()
        nach_ref = {m["ref"]: m for m in uebersicht["modelle"]}
        assert uebersicht["freigegeben"] == erster
        assert nach_ref[erster]["freigegeben"] is True
        assert nach_ref[zweiter]["freigegeben"] is False
        assert sum(1 for m in uebersicht["modelle"] if m["freigegeben"]) == 1

    def test_zwei_staende_heissen_nie_gleich(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis, sprecher: str
    ) -> None:
        # Die eigentliche Ursache. In einer Liste mit einem Knopf „freigeben"
        # je Zeile ist ein doppelter Titel die Falle, in die man tritt.
        sprich(6)
        self._stand(
            datenverzeichnis, sprecher, "20260914T1447-lora-augmentiert", abschluss="bester"
        )
        self._stand(
            datenverzeichnis,
            sprecher,
            "20260914T1448-lora-augmentiert-beides",
            abschluss="beides",
            erstellt="2026-09-14T14:48:00+00:00",
        )
        namen = [m["name"] for m in klient.get("/lernen/api/modelle").json()["modelle"]]
        assert len(namen) == len(set(namen)), namen

    def test_zwei_aktive_manifeste_geben_keines_frei(
        self, klient: TestClient, quelle: str, sprich, datenverzeichnis, sprecher: str
    ) -> None:
        # Ohne Freigabedatei zählen die Manifeste - aber nur, wenn sie sich
        # einig sind. „Das neuere von beiden" wäre eine Entscheidung, und die
        # trifft hier kein Programm.
        sprich(6)
        self._stand(
            datenverzeichnis, sprecher, "20260914T1447-lora-augmentiert", status="active"
        )
        self._stand(
            datenverzeichnis,
            sprecher,
            "20260914T1448-lora-augmentiert-beides",
            abschluss="beides",
            status="active",
        )
        assert registry.freigegeben(datenverzeichnis, sprecher) == ""
        uebersicht = klient.get("/lernen/api/modelle").json()
        assert uebersicht["freigegeben"] == ""
        assert not any(m["freigegeben"] for m in uebersicht["modelle"])


class TestVertrauensbereiche:
    """Die Zugabe muss eine Zugabe bleiben.

    Dieser Teil der App ist Forschung: Was die Tabelle heute zeigt, wird mit
    dem verglichen, was sie vor Monaten zeigte. Eine Erweiterung, die dabei
    auch nur eine Stelle verschiebt, macht jeden solchen Vergleich zunichte -
    und niemand sähe es, denn beide Zahlen wären richtig.
    """

    def test_ohne_parameter_bleibt_alles_wie_es_war(
        self, klient: TestClient, baseline, fertiger_lauf
    ) -> None:
        antwort = klient.get("/lernen/api/modelle").json()

        assert antwort["intervall"] == "aus"
        assert antwort["streuung_marke"] == ""
        assert all(not modell["intervalle"] for modell in antwort["modelle"])
        assert all(not modell["unterschied"] for modell in antwort["modelle"])

    def test_bereiche_aendern_die_zahlen_nicht(
        self, klient: TestClient, baseline, fertiger_lauf
    ) -> None:
        ohne = klient.get("/lernen/api/modelle").json()
        mit = klient.get("/lernen/api/modelle?intervall=aufnahme").json()

        assert [modell["werte"] for modell in mit["modelle"]] == [
            modell["werte"] for modell in ohne["modelle"]
        ]
        # Und der Mittelwert im Bereich ist derselbe wie der in der Tabelle.
        for modell in mit["modelle"]:
            for fassung, masse in modell["intervalle"].items():
                for mass, bereich in masse.items():
                    assert bereich["mittel"] == modell["werte"][fassung][mass]
                    assert bereich["unten"] <= bereich["mittel"] <= bereich["oben"]

    def test_gepaart_gegen_ein_genanntes_modell(
        self, klient: TestClient, baseline, fertiger_lauf
    ) -> None:
        antwort = klient.get(
            "/lernen/api/modelle?intervall=aufnahme&vergleich_mit=small"
        ).json()

        assert antwort["vergleich_mit"] == "small"
        eigene = [m for m in antwort["modelle"] if m["art"] == "trainiert"]
        assert eigene and eigene[0]["unterschied"]
        # Gegen sich selbst wird nicht verglichen - das ergäbe eine Spalte Nullen.
        assert not next(m for m in antwort["modelle"] if m["ref"] == "small")["unterschied"]

    def test_unbekannte_blockart_ist_vierhundert(self, klient: TestClient) -> None:
        assert klient.get("/lernen/api/modelle?intervall=quatsch").status_code == 400

    def test_beim_einzelnen_lauf_dasselbe(
        self, klient: TestClient, baseline, fertiger_lauf
    ) -> None:
        job_id = klient.get("/lernen/api/laeufe").json()["laeufe"][0]["job_id"]
        ohne = klient.get(f"/lernen/api/laeufe/{job_id}").json()
        mit = klient.get(f"/lernen/api/laeufe/{job_id}?intervall=aufnahme").json()

        assert ohne["intervall"] == "aus"
        assert all(
            eintrag["unterschied"] is None
            for eintraege in ohne["vergleich"].values()
            for eintrag in eintraege
        )
        for fassung, eintraege in mit["vergleich"].items():
            for stelle, eintrag in enumerate(eintraege):
                vorher = ohne["vergleich"][fassung][stelle]
                assert eintrag["baseline"] == vorher["baseline"]
                assert eintrag["trainiert"] == vorher["trainiert"]
                assert eintrag["besser"] == vorher["besser"]


class TestFremdesTempo:
    """Ein Stand mit abweichender Geschwindigkeit zählt ganz normal mit.

    Er stand eine Weile außerhalb des Vergleichs, grau und ohne gemeinsamen
    Boden - aus Sorge, seine Zahlen seien mit den übrigen nicht zu halten. Die
    Sorge war unbegründet: Ein Stand **bringt sein Tempo mit**, „schreiben"
    liest es aus seinem Manifest und spult beim Diktieren genauso vor. Damit
    ist das Vorspulen kein Teil der Prüfbedingungen, sondern ein Teil des
    Modells, und jede Zeile der Tafel beantwortet dieselbe Frage.
    """

    def test_er_bleibt_in_der_tafel_und_im_vergleich(
        self, klient: TestClient, verwalter: TestClient, sprecher: str, baseline, fertiger_lauf
    ) -> None:
        from sqlalchemy.orm import Session

        from apps.hoeren.backend.db.models import Sprecher
        from apps.hoeren.backend.deps import engine_fuer

        vorher = klient.get("/lernen/api/modelle").json()
        assert vorher["modelle"]

        with Session(engine_fuer(sprecher)) as db:
            db.get(Sprecher, sprecher).tempo = 2.0
            db.commit()

        nachher = klient.get("/lernen/api/modelle").json()
        assert len(nachher["modelle"]) == len(vorher["modelle"])
        # Kein Vorbehalt mehr an der Zeile - weder als Feld noch als Zustand.
        assert all("gilt" not in zeile for zeile in nachher["modelle"])


class TestSteckbrief:
    """Jede Achse benannt - auch die auf Vorgabe, auch bei alten Läufen."""

    def test_jede_achse_steht_da(self, klient: TestClient, fertiger_lauf) -> None:
        job_id, _version = fertiger_lauf
        antwort = klient.get(f"/lernen/api/laeufe/{job_id}").json()
        felder = {zeile["begriff"]: zeile["wert"] for zeile in antwort["steckbrief"]}

        # Vollständig heißt vollständig: Wer wissen will, womit gerechnet
        # wurde, soll für keine Einstellung „steht nicht da" lesen.
        for begriff in ("Grundmodell", "Methode", "Datensatz", "Augmentierung",
                        "Vorspulen", "Abschluss"):
            assert begriff in felder, f"„{begriff}“ fehlt im Steckbrief."

        # Die Vorgaben stehen ausgeschrieben und nicht als Lücke - und der
        # Abschluss sagt, was **geschah**, nicht wie die Wahl hieß.
        assert felder["Abschluss"] == "bester Durchgang"
        assert felder["Vorspulen"] == "1×"
        # Kein Etikett doppelt: Ein Hinweis trägt eine Angabe oder fehlt.
        hinweise = {z["begriff"]: z["hinweis"] for z in antwort["steckbrief"]}
        assert not hinweise["Grundmodell"]

    def test_zeitstempel_gehen_roh_hinaus(self, klient: TestClient, fertiger_lauf) -> None:
        """Der Server formatiert keine Uhrzeit - er kennt die Zeitzone nicht.

        Er schrieb sie einmal mit `strftime` und damit in UTC. Derselbe
        Augenblick stand in der Trainingsliste (im Browser gerechnet) als
        14:38 und im Steckbrief als 12:38. Wer die App aus Zürich öffnet,
        bekäme sonst die Uhrzeit des Rechenzentrums.
        """
        job_id, _version = fertiger_lauf
        zeilen = klient.get(f"/lernen/api/laeufe/{job_id}").json()["steckbrief"]
        zeiten = [z for z in zeilen if z["art"] == "zeit"]
        assert zeiten, "Kein Zeitstempel im Steckbrief."
        for zeile in zeiten:
            # ISO-8601, wie der Server ihn ablegt - kein „14.09.2026, 12:38".
            assert "T" in zeile["wert"], f"{zeile['begriff']} ist vorformatiert: {zeile['wert']}"
            datetime.fromisoformat(zeile["wert"])

    def test_ein_lauf_von_vor_den_achsen_wird_rekonstruiert(
        self, klient: TestClient, aufnahmen: list[str], datenverzeichnis
    ) -> None:
        # Ein Auftrag, wie ihn der Code von früher geschrieben hat: ohne
        # `abschluss`, `augmentierung`, `dauer`, `tempo`, `tempowahl`. Was
        # fehlt, ist keine Unbekannte - es galt die Vorgabe, weil es nichts
        # anderes gab, das hätte gelten können.
        from wortlaut import laeufe as l

        lauf = klient.post(
            "/lernen/api/laeufe", json={"methode": "lora", "daten": "original"}
        ).json()
        pfad = l.lauf_verzeichnis(datenverzeichnis, lauf["job_id"]) / l.AUFTRAG
        alt = l.lies_json(pfad)
        for weg in ("abschluss", "augmentierung", "dauer", "tempo", "tempowahl"):
            alt.pop(weg, None)
        l.schreibe_json(pfad, alt)

        felder = {
            zeile["begriff"]: zeile["wert"]
            for zeile in klient.get(f"/lernen/api/laeufe/{lauf['job_id']}").json()["steckbrief"]
        }
        assert felder["Abschluss"] == "bester Durchgang", "Fehlt er, galt „bester“."
        assert felder["Augmentierung"] == "keine"
        assert felder["Vorspulen"] == "1×"


class TestGemeinsamerBoden:
    """Die Zahl eines Modells hängt daran, welche anderen es gibt - und das muss dastehen.

    Die Tafel rechnet jede Zahl über die Einheiten, die **alle** Modelle
    gemessen haben. Das ist der Sinn der Sache: Zwei Wortfehlerraten über
    verschiedene Aufnahmen sind kein Vergleich. Die Folge erwartet nur niemand:
    Verschwindet eine Zeile, wächst der Boden, und jede andere Zahl ändert
    sich. An einem echten Korpus waren das 0,15 WER auf einen Schlag.
    """

    def _reihe(self, einheiten: int) -> object:
        from apps.lernen.backend.services.messwerte import Messreihe

        reihe = Messreihe()
        for nummer in range(einheiten):
            reihe.werte[(f"rec_{nummer:03d}", "original")] = {"wer": 0.5}
        reihe.werke.add("cuda/int8_float16")
        return reihe

    def test_eine_schmale_zeile_begrenzt_und_wird_benannt(self) -> None:
        from apps.lernen.backend.api.modelle import bodenbegrenzer

        reihen = {"small": self._reihe(100), "spr/gross": self._reihe(100),
                  "spr/schmal": self._reihe(20)}
        begrenzer, jetzt, ohne = bodenbegrenzer(reihen)
        assert begrenzer == "spr/schmal"
        assert (jetzt, ohne) == (20, 100)

    def test_ohne_begrenzer_schweigt_die_auskunft(self) -> None:
        # Gleich breite Zeilen: Löschen ändert nichts, also wird nichts gesagt.
        # Eine Warnung, die immer angeht, liest bald niemand mehr.
        from apps.lernen.backend.api.modelle import bodenbegrenzer

        reihen = {"small": self._reihe(100), "spr/a": self._reihe(100), "spr/b": self._reihe(100)}
        assert bodenbegrenzer(reihen) == ("", 100, 100)

    def test_kleine_unterschiede_loesen_nichts_aus(self) -> None:
        # 100 gegen 95 ist kein „andere Zahlen", sondern ein Rundungsrest.
        from apps.lernen.backend.api.modelle import bodenbegrenzer

        reihen = {"small": self._reihe(100), "spr/fast": self._reihe(95)}
        assert bodenbegrenzer(reihen)[0] == ""

    def test_die_tafel_sagt_es_vorher(self, klient: TestClient, baseline, fertiger_lauf) -> None:
        from apps.lernen.backend.api.modelle import _hinweis
        from apps.lernen.backend.services.messwerte import Messreihe

        reihen = {"small": self._reihe(100), "spr/gross": self._reihe(100),
                  "spr/schmal": self._reihe(20)}
        text = _hinweis({"rec_000"}, reihen, ["small"], [{"id": "spr/schmal", "methode": "lora"}])
        assert "20" in text and "100" in text
        assert "Löschen" in text, "Der Satz muss sagen, dass es auch beim Löschen gilt."
