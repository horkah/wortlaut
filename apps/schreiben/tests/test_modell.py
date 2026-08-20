"""Welcher Modellstand läuft — die Auskunft für die Kopfzeile.

Ein Modellwechsel ist eine Konfigurationsänderung mit Neustart. Wer eine
Ausgabe beurteilt, muss deshalb jederzeit sehen können, welcher Stand sie
erzeugt hat.
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


class TestModellpfad:
    def test_ohne_ref_ist_es_der_blosse_name(self, _umgebung: None) -> None:
        # faster-whisper lädt dann das unveränderte Whisper-Modell selbst.
        assert modellpfad(einstellungen()) == "tiny"

    def test_mit_ref_ist_es_das_ct2_verzeichnis(
        self, _umgebung: None, datenverzeichnis: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WORTLAUT_MODELL_REF", MANIFEST["id"])
        einstellungen.cache_clear()

        pfad = modellpfad(einstellungen())

        assert pfad == datenverzeichnis / "modelle" / "spr_test" / "2026-08-15T1420" / "ct2"
