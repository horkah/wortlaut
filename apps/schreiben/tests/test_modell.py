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

        assert antwort["ref"] == ""
        assert antwort["basismodell"] == "tiny"
        assert antwort["beschriftung"] == "whisper-tiny · unverändert"

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
        assert antwort["beschriftung"] == "whisper-large-v3 · Stand 2026-08-15 · WER 14,6 %"

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

        assert antwort["ref"] == ""
        assert antwort["beschriftung"] == "whisper-tiny · unverändert"

    def test_ein_nicht_freigegebener_stand_zaehlt_nicht(
        self, klient: TestClient, datenverzeichnis: Path
    ) -> None:
        registry.schreibe_stand(datenverzeichnis, {**MANIFEST, "status": "draft"})

        assert klient.get("/schreiben/api/model").json()["ref"] == ""


class TestModellpfad:
    def test_ohne_stand_ist_es_der_blosse_name(self, _umgebung: None, sprecher: str) -> None:
        # faster-whisper lädt dann das unveränderte Whisper-Modell selbst.
        assert modellpfad(einstellungen(), sprecher) == "tiny"

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
