"""Welcher Modellstand läuft - die Auskunft für die Kopfzeile.

Ein Modell gehört zu genau einem Sprecher (Grundentscheidung 3). Geprüft wird
deshalb beides: dass die Auskunft den freigegebenen Stand **dieses** Sprechers
nennt, und dass der Stand eines anderen hier nichts zu suchen hat.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import registry

from apps.schreiben.backend.config import einstellungen
from apps.schreiben.backend.deps import modellpfad

MANIFEST = {
    "id": "spr_test/2026-08-15T1420",
    "sprecher_id": "spr_test",
    "basismodell": "openai/whisper-large-v3",
    "methode": "full",
    "erstellt": "2026-08-15T14:20:03Z",
    "metriken": {"wer": 0.146, "cer": 0.061},
    "status": "active",
}


class TestModellauskunft:
    def test_meldet_das_grundmodell_ohne_registry(self, klient: TestClient) -> None:
        # Der Normalfall, solange es „lernen" nicht gibt.
        antwort = klient.get("/schreiben/api/model").json()

        # `ref` nennt immer, was geladen ist - hier das Grundmodell, mit dem
        # eine Installation anfängt.
        assert antwort["ref"] == "small"
        assert antwort["gewaehlt"] is False
        assert antwort["basismodell"] == "small"
        assert antwort["beschriftung"] == "whisper-small · unverändert"

    def test_meldet_den_stand_aus_der_registry(
        self,
        klient: TestClient,
        datenverzeichnis: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        registry.schreibe_stand(datenverzeichnis, MANIFEST)
        monkeypatch.setenv("WORTLAUT_MODELL_REF", MANIFEST["id"])
        einstellungen.cache_clear()

        antwort = klient.get("/schreiben/api/model").json()

        assert antwort["basismodell"] == "openai/whisper-large-v3"
        assert antwort["methode"] == "full"
        # Die Methode steht mit in der Zeile: Seit „lernen" je Sprecher vier
        # Stände liefert, wären zwei vom selben Tag sonst nicht zu unterscheiden.
        assert antwort["beschriftung"] == (
            "whisper-large-v3 · voll · Stand 2026-08-15 · WER 14,6 %"
        )

    def test_sagt_es_wenn_der_stand_fehlt(
        self, klient: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Falsch gesetzte Umgebung soll man sehen, nicht raten müssen.
        monkeypatch.setenv("WORTLAUT_MODELL_REF", "spr_test/gibtsnicht")
        einstellungen.cache_clear()

        assert "nicht gefunden" in klient.get("/schreiben/api/model").json()["beschriftung"]


class TestEigenesModell:
    """Jeder Sprecher läuft auf dem Stand, den „lernen" für ihn freigegeben hat."""

    def test_nimmt_den_freigegebenen_stand_dieses_sprechers(
        self, klient: TestClient, datenverzeichnis: Path, sprecher: str
    ) -> None:
        # Ohne WORTLAUT_MODELL_REF - der Betriebsfall, sobald es „lernen" gibt.
        registry.schreibe_stand(datenverzeichnis, MANIFEST)

        antwort = klient.get("/schreiben/api/model").json()

        assert antwort["sprecher_id"] == sprecher
        assert antwort["ref"] == MANIFEST["id"]
        assert antwort["basismodell"] == "openai/whisper-large-v3"

    def test_der_stand_eines_anderen_sprechers_gilt_hier_nicht(
        self, klient: TestClient, datenverzeichnis: Path
    ) -> None:
        # Sonst spräche jemand auf der Stimme eines Fremden - und das Ergebnis
        # sähe aus wie ein schlechtes Modell statt wie ein Fehlgriff.
        registry.schreibe_stand(datenverzeichnis, {**MANIFEST, "id": "spr_fremd/2026-08-15T1420"})

        antwort = klient.get("/schreiben/api/model").json()

        assert antwort["ref"] == "small"
        assert antwort["beschriftung"] == "whisper-small · unverändert"

    def test_ein_nicht_freigegebener_stand_zaehlt_nicht(
        self, klient: TestClient, datenverzeichnis: Path
    ) -> None:
        registry.schreibe_stand(datenverzeichnis, {**MANIFEST, "status": "draft"})

        assert klient.get("/schreiben/api/model").json()["ref"] == "small"


class TestModellpfad:
    def test_ohne_stand_ist_es_der_blosse_name(self, _umgebung: None, sprecher: str) -> None:
        # faster-whisper lädt dann das unveränderte Whisper-Modell selbst.
        assert modellpfad(einstellungen(), sprecher) == "small"

    def test_mit_stand_ist_es_das_ct2_verzeichnis(
        self, _umgebung: None, datenverzeichnis: Path, sprecher: str
    ) -> None:
        registry.schreibe_stand(datenverzeichnis, MANIFEST)

        pfad = modellpfad(einstellungen(), sprecher)

        assert pfad == datenverzeichnis / "modelle" / "spr_test" / "2026-08-15T1420" / "ct2"

    def test_die_vorgabe_aus_der_umgebung_schlaegt_alles(
        self, _umgebung: None, datenverzeichnis: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Zum Erproben eines Standes gedacht; im Betrieb bleibt die Variable leer.
        monkeypatch.setenv("WORTLAUT_MODELL_REF", MANIFEST["id"])
        einstellungen.cache_clear()

        assert modellpfad(einstellungen(), "spr_jemand_anderes") == (
            datenverzeichnis / "modelle" / "spr_test" / "2026-08-15T1420" / "ct2"
        )


class TestModellwahl:
    """Jedes Grundmodell und jeder trainierte Stand lässt sich hier auswählen.

    Vier trainierte Stände je Sprecher (zwei Methoden mal zwei Datensätze) und
    daneben die unveränderten Grundmodelle: Welcher dieser Person am besten
    zuhört, beantwortet sich beim Diktieren und nicht an einer Kennzahl.
    """

    def test_die_grundmodelle_stehen_immer_zur_wahl(self, klient: TestClient) -> None:
        auswahl = klient.get("/schreiben/api/model").json()["auswahl"]
        namen = [wahl["ref"] for wahl in auswahl if wahl["art"] == "grundmodell"]
        # Dieselbe Reihe, gegen die in „hören" gemessen wird.
        assert namen == ["base", "small", "medium", "large-v3"]

    def test_trainierte_staende_stehen_daneben(
        self, klient: TestClient, datenverzeichnis: Path, sprecher: str
    ) -> None:
        registry.schreibe_stand(
            datenverzeichnis,
            {**MANIFEST, "id": f"{sprecher}/2026-09-12T1200", "daten": "augmentiert"},
        )
        auswahl = klient.get("/schreiben/api/model").json()["auswahl"]
        trainiert = [wahl for wahl in auswahl if wahl["art"] == "trainiert"]

        assert len(trainiert) == 1
        # Methode und Datensatz stehen in der Zeile - vier Stände vom selben
        # Tag wären sonst nicht auseinanderzuhalten.
        assert "voll" in trainiert[0]["beschriftung"]
        assert "mit Abwandlungen" in trainiert[0]["beschriftung"]

    def test_fremde_staende_stehen_nicht_zur_wahl(
        self, klient: TestClient, datenverzeichnis: Path
    ) -> None:
        # Ein Stand eines anderen Sprechers ist fremde Stimme.
        registry.schreibe_stand(datenverzeichnis, {**MANIFEST, "id": "spr_fremd/2026-09-12T1200"})
        auswahl = klient.get("/schreiben/api/model").json()["auswahl"]
        assert not [wahl for wahl in auswahl if wahl["art"] == "trainiert"]

    def test_ein_grundmodell_laesst_sich_waehlen(self, klient: TestClient) -> None:
        antwort = klient.put("/schreiben/api/model", json={"ref": "medium"})
        assert antwort.status_code == 200
        assert antwort.json()["beschriftung"] == "whisper-medium · unverändert"
        # Und die Wahl hält über die nächste Anfrage hinaus.
        assert klient.get("/schreiben/api/model").json()["basismodell"] == "medium"

    def test_die_wahl_schlaegt_den_freigegebenen_stand(
        self, klient: TestClient, datenverzeichnis: Path, sprecher: str
    ) -> None:
        # Ohne Wahl gilt, was „lernen" freigegeben hat; mit Wahl gilt die Wahl.
        registry.schreibe_stand(datenverzeichnis, {**MANIFEST, "id": f"{sprecher}/2026-09-12T1200"})
        assert klient.get("/schreiben/api/model").json()["ref"].endswith("2026-09-12T1200")

        klient.put("/schreiben/api/model", json={"ref": "base"})
        antwort = klient.get("/schreiben/api/model").json()
        assert antwort["ref"] == "base"
        assert antwort["basismodell"] == "base"
        assert antwort["gewaehlt"] is True

    def test_ein_trainierter_stand_laesst_sich_waehlen(
        self, klient: TestClient, datenverzeichnis: Path, sprecher: str
    ) -> None:
        kennung = f"{sprecher}/2026-09-12T1200"
        registry.schreibe_stand(datenverzeichnis, {**MANIFEST, "id": kennung, "status": "fertig"})

        # Ausdrücklich ein Stand, den „lernen" **nicht** freigegeben hat: Genau
        # dafür gibt es die Wahl - vier Stände nebeneinander auszuprobieren.
        antwort = klient.put("/schreiben/api/model", json={"ref": kennung}).json()
        assert antwort["ref"] == kennung
        assert antwort["basismodell"] == "openai/whisper-large-v3"

    def test_leere_wahl_setzt_auf_die_vorgabe_zurueck(
        self, klient: TestClient, datenverzeichnis: Path, sprecher: str
    ) -> None:
        registry.schreibe_stand(datenverzeichnis, {**MANIFEST, "id": f"{sprecher}/2026-09-12T1200"})
        klient.put("/schreiben/api/model", json={"ref": "base"})

        antwort = klient.put("/schreiben/api/model", json={"ref": ""}).json()
        assert antwort["gewaehlt"] is False
        assert antwort["ref"].endswith("2026-09-12T1200")

    def test_was_nicht_zur_wahl_steht_wird_abgewiesen(self, klient: TestClient) -> None:
        # Ein beliebiger Pfad im Feld wäre ein Weg, fremde Verzeichnisse laden
        # zu lassen.
        assert klient.put("/schreiben/api/model", json={"ref": "spr_fremd/egal"}).status_code == 404
        assert klient.put("/schreiben/api/model", json={"ref": "../../etc"}).status_code == 404

    def test_der_erkenner_folgt_der_wahl(
        self, klient: TestClient, sprecher: str
    ) -> None:
        from apps.schreiben.backend.deps import modellpfad

        klient.put("/schreiben/api/model", json={"ref": "medium"})
        # Ohne das bekäme ein Wechsel weiter das alte Modell - ein Fehler, den
        # niemand als Fehler erkennte, weil einfach der gewohnte Text herauskäme.
        assert modellpfad(einstellungen(), sprecher, "medium") == "medium"
