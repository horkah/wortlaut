"""Welches Modell läuft - die Auskunft für die Zeile unter dem Aufnahmeknopf.

Gewählt wird hier nichts: Welches Modell gilt, entscheidet die Freigabe in
„lernen" (`wortlaut/registry.py`), und diese App liest sie. Geprüft wird
deshalb beides - dass die Auskunft das freigegebene Modell **dieses**
Sprechers nennt, und dass die Freigabe eines anderen hier nichts bewirkt.
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
        # Der Normalfall, solange nichts freigegeben ist.
        antwort = klient.get("/schreiben/api/model").json()

        # `ref` nennt immer, was geladen ist - hier das Grundmodell, mit dem
        # eine Installation anfängt.
        assert antwort["ref"] == "small"
        assert antwort["trainiert"] is False
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
        assert antwort["beschriftung"] == "whisper-large-v3 · voll · Stand 2026-08-15"

    def test_die_beschriftung_traegt_keine_kennzahl(
        self, klient: TestClient, datenverzeichnis: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Sie sagt, **welches** Modell arbeitet, und nicht, wie gut. Die
        # Wortfehlerrate aus dem Manifest stand hier einmal und widersprach der
        # Zahl in der Modellübersicht von „lernen" - beide richtig, über
        # verschiedene Einheiten gemittelt, und nebeneinander ein Rätsel.
        registry.schreibe_stand(datenverzeichnis, MANIFEST)
        monkeypatch.setenv("WORTLAUT_MODELL_REF", MANIFEST["id"])
        einstellungen.cache_clear()

        antwort = klient.get("/schreiben/api/model").json()

        assert "WER" not in antwort["beschriftung"]
        # Die Auskunft des Manifests bleibt trotzdem abrufbar - nur eben als
        # Feld und nicht als Satz.
        assert antwort["wer"] == pytest.approx(0.146)

    def test_sagt_es_wenn_der_stand_fehlt(
        self, klient: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Falsch gesetzte Umgebung soll man sehen, nicht raten müssen.
        monkeypatch.setenv("WORTLAUT_MODELL_REF", "spr_test/gibtsnicht")
        einstellungen.cache_clear()

        assert "nicht gefunden" in klient.get("/schreiben/api/model").json()["beschriftung"]


class TestEigenesModell:
    """Jeder Sprecher läuft auf dem Modell, das für ihn freigegeben ist."""

    def test_nimmt_den_freigegebenen_stand_dieses_sprechers(
        self, klient: TestClient, datenverzeichnis: Path, sprecher: str
    ) -> None:
        # Ohne WORTLAUT_MODELL_REF - der Betriebsfall, sobald es „lernen" gibt.
        registry.schreibe_stand(datenverzeichnis, MANIFEST)
        registry.gib_frei(datenverzeichnis, sprecher, MANIFEST["id"])

        antwort = klient.get("/schreiben/api/model").json()

        assert antwort["sprecher_id"] == sprecher
        assert antwort["ref"] == MANIFEST["id"]
        assert antwort["trainiert"] is True
        assert antwort["basismodell"] == "openai/whisper-large-v3"

    def test_ein_freigegebenes_grundmodell_gilt_genauso(
        self, klient: TestClient, datenverzeichnis: Path, sprecher: str
    ) -> None:
        # Seit die Modellübersicht beide Sorten in einer Tabelle zeigt, kann
        # auch ein unverändertes Whisper-Modell freigegeben sein - „mein
        # eigenes ist noch nicht besser als medium" ist eine Antwort.
        registry.gib_frei(datenverzeichnis, sprecher, "medium")

        antwort = klient.get("/schreiben/api/model").json()

        assert antwort["ref"] == "medium"
        assert antwort["trainiert"] is False
        assert antwort["beschriftung"] == "whisper-medium · unverändert"
        assert modellpfad(einstellungen(), sprecher) == "medium"

    def test_der_stand_eines_anderen_sprechers_gilt_hier_nicht(
        self, klient: TestClient, datenverzeichnis: Path
    ) -> None:
        # Sonst spräche jemand auf der Stimme eines Fremden - und das Ergebnis
        # sähe aus wie ein schlechtes Modell statt wie ein Fehlgriff.
        registry.schreibe_stand(datenverzeichnis, {**MANIFEST, "id": "spr_fremd/2026-08-15T1420"})
        registry.gib_frei(datenverzeichnis, "spr_fremd", "spr_fremd/2026-08-15T1420")

        antwort = klient.get("/schreiben/api/model").json()

        assert antwort["ref"] == "small"
        assert antwort["beschriftung"] == "whisper-small · unverändert"

    def test_ein_nicht_freigegebener_stand_zaehlt_nicht(
        self, klient: TestClient, datenverzeichnis: Path
    ) -> None:
        # Zwischen „hat gerechnet" und „damit diktiere ich" liegt die Freigabe.
        registry.schreibe_stand(datenverzeichnis, {**MANIFEST, "status": "fertig"})

        assert klient.get("/schreiben/api/model").json()["ref"] == "small"

    def test_eine_zurueckgenommene_freigabe_faellt_auf_die_vorgabe(
        self, klient: TestClient, datenverzeichnis: Path, sprecher: str
    ) -> None:
        registry.schreibe_stand(datenverzeichnis, MANIFEST)
        registry.gib_frei(datenverzeichnis, sprecher, MANIFEST["id"])
        registry.gib_frei(datenverzeichnis, sprecher, "")

        assert klient.get("/schreiben/api/model").json()["ref"] == "small"


class TestModellpfad:
    def test_ohne_stand_ist_es_der_blosse_name(self, _umgebung: None, sprecher: str) -> None:
        # faster-whisper lädt dann das unveränderte Whisper-Modell selbst.
        assert modellpfad(einstellungen(), sprecher) == "small"

    def test_mit_stand_ist_es_das_ct2_verzeichnis(
        self, _umgebung: None, datenverzeichnis: Path, sprecher: str
    ) -> None:
        registry.schreibe_stand(datenverzeichnis, MANIFEST)
        registry.gib_frei(datenverzeichnis, sprecher, MANIFEST["id"])

        pfad = modellpfad(einstellungen(), sprecher)

        assert pfad == datenverzeichnis / "modelle" / "spr_test" / "2026-08-15T1420" / "ct2"

    def test_ein_altes_manifest_ohne_freigabedatei_gilt_weiter(
        self, _umgebung: None, datenverzeichnis: Path, sprecher: str
    ) -> None:
        # Eine Installation, die vor der Freigabedatei schon einen Stand
        # freigegeben hatte, soll nach dem Aufspielen nicht stumm auf das
        # Grundmodell zurückfallen: Dann zählt der `status` im Manifest.
        registry.schreibe_stand(datenverzeichnis, MANIFEST)

        assert modellpfad(einstellungen(), sprecher) == (
            datenverzeichnis / "modelle" / "spr_test" / "2026-08-15T1420" / "ct2"
        )

    def test_die_vorgabe_aus_der_umgebung_schlaegt_alles(
        self, _umgebung: None, datenverzeichnis: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Zum Erproben eines Standes gedacht; im Betrieb bleibt die Variable leer.
        monkeypatch.setenv("WORTLAUT_MODELL_REF", MANIFEST["id"])
        einstellungen.cache_clear()

        assert modellpfad(einstellungen(), "spr_jemand_anderes") == (
            datenverzeichnis / "modelle" / "spr_test" / "2026-08-15T1420" / "ct2"
        )


class TestVerschwundenerStand:
    """Was „lernen" löscht, darf hier nicht als Sackgasse zurückbleiben."""

    def test_ein_geloeschtes_modell_bleibt_sichtbar(
        self, klient: TestClient, datenverzeichnis: Path, sprecher: str
    ) -> None:
        # Anders als eine stille Rückkehr zum Grundmodell: Wer in „lernen"
        # einen Lauf samt Modell löscht, nimmt dort auch die Freigabe mit.
        # Bleibt hier trotzdem eine stehen, ist das ein Zustand, den man sehen
        # soll - die Zeile unter dem Aufnahmeknopf sagt ihn.
        import shutil

        kennung = f"{sprecher}/2026-09-12T1200"
        registry.schreibe_stand(datenverzeichnis, {**MANIFEST, "id": kennung, "status": "fertig"})
        registry.gib_frei(datenverzeichnis, sprecher, kennung)
        shutil.rmtree(registry.stand_verzeichnis(datenverzeichnis, sprecher, "2026-09-12T1200"))

        antwort = klient.get("/schreiben/api/model").json()

        assert antwort["ref"] == kennung
        assert "nicht gefunden" in antwort["beschriftung"]

    def test_eine_falsch_gesetzte_umgebung_bleibt_sichtbar(
        self, klient: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WORTLAUT_MODELL_REF", "spr_test/gibtsnicht")
        einstellungen.cache_clear()
        assert "nicht gefunden" in klient.get("/schreiben/api/model").json()["beschriftung"]


class TestGeschwindigkeit:
    """Ein Stand bringt sein Tempo mit - und „schreiben" richtet sich danach.

    Das ist die Bedingung dafür, dass ein Modell mit abweichender
    Geschwindigkeit überhaupt benutzbar ist: Es hat nie ungespulte Sprache
    gehört. Bekäme es sie hier, träfe ein Modell für schnelle Sprache auf einen
    langsamen Sprecher, und das Ergebnis wäre schlechter als ganz ohne
    Training - ohne dass irgendwo ein Fehler stünde.
    """

    def _stand_mit(self, datenverzeichnis, sprecher: str, tempo: float) -> dict:
        manifest = {
            **MANIFEST,
            "id": f"{sprecher}/2026-09-14T0852-lora-{tempo:g}x",
            "sprecher_id": sprecher,
            "tempo": tempo,
        }
        registry.schreibe_stand(datenverzeichnis, manifest)
        registry.gib_frei(datenverzeichnis, sprecher, manifest["id"])
        return manifest

    def test_der_faktor_des_standes_gilt(
        self, klient: TestClient, datenverzeichnis, sprecher: str
    ) -> None:
        from apps.schreiben.backend.deps import tempo_fuer, zwischenspeicher_leeren

        for faktor in (1.0, 2.0, 2.25, 3.0):
            self._stand_mit(datenverzeichnis, sprecher, faktor)
            einstellungen.cache_clear()
            zwischenspeicher_leeren()
            assert tempo_fuer(einstellungen(), sprecher) == faktor

    def test_ein_stand_mit_fremdem_tempo_bleibt_waehlbar(
        self, klient: TestClient, datenverzeichnis, sprecher: str
    ) -> None:
        # Freigeben, benutzen, und die Auskunft nennt ihn - ohne Vorbehalt.
        # Ein Modell, das sein Tempo mitbringt, ist kein Sonderfall.
        from apps.schreiben.backend.deps import zwischenspeicher_leeren

        manifest = self._stand_mit(datenverzeichnis, sprecher, 2.25)
        einstellungen.cache_clear()
        zwischenspeicher_leeren()

        antwort = klient.get("/schreiben/api/model").json()
        assert antwort["ref"] == manifest["id"]
        assert antwort["trainiert"] is True
        assert antwort["kennung"] == registry.kurzkennung(manifest["id"].split("/", 1)[-1])

    def test_ein_grundmodell_folgt_dem_profil(
        self, klient: TestClient, datenverzeichnis, sprecher: str
    ) -> None:
        # Ohne Stand rechnet ein unverändertes Grundmodell, und für das gilt,
        # was die Auswertung in „hören" gerade misst - sonst diktierte man
        # unter anderen Bedingungen, als man vergleicht.
        from apps.schreiben.backend.deps import tempo_fuer, zwischenspeicher_leeren

        einstellungen.cache_clear()
        zwischenspeicher_leeren()
        assert tempo_fuer(einstellungen(), sprecher) == 1.0
