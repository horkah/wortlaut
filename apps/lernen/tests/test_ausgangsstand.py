"""Auf einem trainierten Stand aufsetzen: die Wahl, der Auftrag - und das Zurückrechnen.

Ob die zurückgerechneten Gewichte wirklich die des Standes sind, lässt sich
nur mit torch und CTranslate2 prüfen, und die gibt es nur im Abbild des
Trainers. Hier geprüft wird alles davor: das Dateiformat, die Zuordnung der
Namen, und dass die API den Stand anbietet und richtig in den Auftrag
schreibt.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wortlaut import laeufe, registry

from apps.lernen.backend.config import einstellungen
from apps.lernen.training import ausgangsstand

FREMD = "spr_01FREMDERSPRECHER0000000000"
VERSION = "20260926T0458-medium-lora-augmentiert-beides-voll-geduldig"
REF = f"{FREMD}/{VERSION}"


def _lege_stand_an(datenverzeichnis: Path, ref: str = REF) -> None:
    sprecher_id = ref.split("/", 1)[0]
    registry.schreibe_stand(
        datenverzeichnis,
        {
            "id": ref,
            "sprecher_id": sprecher_id,
            "basismodell": "openai/whisper-medium",
            "methode": "lora",
            "daten": "augmentiert",
            "folge": "43d",
        },
    )
    registry.ct2_verzeichnis(datenverzeichnis, ref).mkdir(parents=True)


@pytest.fixture
def mit_staenden(monkeypatch: pytest.MonkeyPatch, datenverzeichnis: Path, klient: TestClient):
    _lege_stand_an(datenverzeichnis)
    monkeypatch.setenv("WORTLAUT_LERNEN_AUSGANGSSTAENDE", f"{REF}, {FREMD}/gibt-es-nicht")
    einstellungen.cache_clear()
    yield
    einstellungen.cache_clear()


class TestWahl:
    def test_der_stand_steht_mit_seiner_kennung_zur_wahl(
        self, mit_staenden, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        wahlen = {g["schluessel"]: g for g in klient.get("/lernen/api/laeufe").json()["grundmodelle"]}
        stand = wahlen[REF]
        assert stand["name"] == "C6G67"
        assert stand["code"] == "C6G67"
        # Auf `medium` gewachsen - und darum wie `medium` nur mit LoRA.
        assert stand["methoden"] == ["lora"]

    def test_ein_fehlender_stand_steht_nicht_zur_wahl(
        self, mit_staenden, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        schluessel = [g["schluessel"] for g in klient.get("/lernen/api/laeufe").json()["grundmodelle"]]
        assert f"{FREMD}/gibt-es-nicht" not in schluessel

    def test_ohne_konfiguration_kein_stand(
        self, klient: TestClient, datenverzeichnis: Path, quelle: str, sprich
    ) -> None:
        # Auch wenn es ihn gibt: Einen fremden Stand bietet nur an, wer ihn nennt.
        _lege_stand_an(datenverzeichnis)
        sprich(6)
        schluessel = [g["schluessel"] for g in klient.get("/lernen/api/laeufe").json()["grundmodelle"]]
        assert REF not in schluessel
        antwort = klient.post(
            "/lernen/api/laeufe", json={"methode": "lora", "daten": "original", "grundmodell": REF}
        )
        assert antwort.status_code == 400


class TestAuftrag:
    def test_der_auftrag_nennt_stand_und_grundmodell(
        self, mit_staenden, klient: TestClient, datenverzeichnis: Path, quelle: str, sprich
    ) -> None:
        sprich(6)
        antwort = klient.post(
            "/lernen/api/laeufe", json={"methode": "lora", "daten": "original", "grundmodell": REF}
        )
        assert antwort.status_code == 201, antwort.text
        lauf = antwort.json()
        assert lauf["grundmodell"] == REF
        assert lauf["basismodell"] == "openai/whisper-medium"
        assert lauf["code"].startswith("C6G67-L")

        verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"])
        auftrag = json.loads((verzeichnis / laeufe.AUFTRAG).read_text(encoding="utf-8"))
        assert auftrag["basismodell"] == "openai/whisper-medium"
        assert auftrag["ausgangsstand"] == REF

    def test_ohne_stand_kein_feld(
        self, mit_staenden, klient: TestClient, datenverzeichnis: Path, quelle: str, sprich
    ) -> None:
        # Ein Auftrag auf einem Grundmodell ist derselbe wie vor dieser Achse.
        sprich(6)
        lauf = klient.post("/lernen/api/laeufe", json={"methode": "lora", "daten": "original"}).json()
        verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"])
        auftrag = json.loads((verzeichnis / laeufe.AUFTRAG).read_text(encoding="utf-8"))
        assert "ausgangsstand" not in auftrag
        assert lauf["grundmodell"] == auftrag["basismodell"]

    def test_volles_training_geht_auf_einem_medium_stand_nicht(
        self, mit_staenden, klient: TestClient, quelle: str, sprich
    ) -> None:
        sprich(6)
        antwort = klient.post(
            "/lernen/api/laeufe", json={"methode": "full", "daten": "original", "grundmodell": REF}
        )
        assert antwort.status_code == 400


# ── Das Dateiformat ─────────────────────────────────────────────────────────


def _schreibe_model_bin(pfad: Path, spezifikation: str = "WhisperSpec") -> None:
    """Eine `model.bin` wie aus `model_spec._serialize`, mit einer Schicht je Seite.

    Die Zahlen sind gleichgültig; es geht um Namen, Formen und Lage.
    """
    breite, innen, woerter = 4, 8, 6

    def text(zeichen: str) -> bytes:
        return struct.pack("H", len(zeichen) + 1) + zeichen.encode() + b"\0"

    groessen: list[tuple[str, tuple[int, ...]]] = []

    def linear(name: str, zeilen: int, spalten: int) -> None:
        groessen.extend([(f"{name}/weight", (zeilen, spalten)), (f"{name}/bias", (zeilen,))])

    def norm(name: str) -> None:
        groessen.extend([(f"{name}/gamma", (breite,)), (f"{name}/beta", (breite,))])

    for seite, positionen in (("encoder", 15), ("decoder", 7)):
        groessen.append((f"{seite}/position_encodings/encodings", (positionen, breite)))
        norm(f"{seite}/layer_norm")
        schicht = f"{seite}/layer_0"
        linear(f"{schicht}/self_attention/linear_0", 3 * breite, breite)
        linear(f"{schicht}/self_attention/linear_1", breite, breite)
        norm(f"{schicht}/self_attention/layer_norm")
        linear(f"{schicht}/ffn/linear_0", innen, breite)
        linear(f"{schicht}/ffn/linear_1", breite, innen)
        norm(f"{schicht}/ffn/layer_norm")
        if seite == "decoder":
            linear(f"{schicht}/attention/linear_0", breite, breite)
            linear(f"{schicht}/attention/linear_1", 2 * breite, breite)
            linear(f"{schicht}/attention/linear_2", breite, breite)
            norm(f"{schicht}/attention/layer_norm")
    groessen.extend(
        [
            ("encoder/conv1/weight", (breite, 80, 3)),
            ("encoder/conv1/bias", (breite,)),
            ("encoder/conv2/weight", (breite, breite, 3)),
            ("encoder/conv2/bias", (breite,)),
            ("decoder/embeddings/weight", (woerter, breite)),
        ]
    )

    daten = struct.pack("I", 6) + text(spezifikation) + struct.pack("I", 3)
    # Dazu eine Größe ohne Form, wie die Einstellungen, die CTranslate2 als
    # Variablen führt - sie gehört zu keinem Gewicht.
    daten += struct.pack("I", len(groessen) + 1)
    daten += text("decoder/num_heads") + struct.pack("B", 0) + struct.pack("B", 3)
    daten += struct.pack("I", 4) + struct.pack("i", 1)
    for name, form in groessen:
        anzahl = 1
        for achse in form:
            anzahl *= achse
        daten += text(name) + struct.pack("B", len(form))
        daten += b"".join(struct.pack("I", achse) for achse in form)
        daten += struct.pack("B", 4) + struct.pack("I", 2 * anzahl) + b"\0\0" * anzahl
    daten += struct.pack("I", 1) + text("decoder/projection/weight") + text("decoder/embeddings/weight")
    pfad.write_bytes(daten)


class TestZurueckrechnen:
    def test_das_verzeichnis_nennt_jede_groesse_mit_form(self, tmp_path: Path) -> None:
        pfad = tmp_path / "model.bin"
        _schreibe_model_bin(pfad)
        variablen, verweise = ausgangsstand.lies_verzeichnis(pfad)
        assert variablen["encoder/layer_0/self_attention/linear_0/weight"].form == (12, 4)
        assert variablen["encoder/conv1/weight"].art == "float16"
        assert verweise == {"decoder/projection/weight": "decoder/embeddings/weight"}

    def test_die_lage_stimmt(self, tmp_path: Path) -> None:
        # Die letzte Größe endet dort, wo die Verweise beginnen - sonst wäre
        # beim Lesen irgendwo ein Byte verrutscht.
        pfad = tmp_path / "model.bin"
        _schreibe_model_bin(pfad)
        variablen, _ = ausgangsstand.lies_verzeichnis(pfad)
        letzte = max(variablen.values(), key=lambda v: v.anfang)
        rest = pfad.read_bytes()[letzte.anfang + letzte.laenge :]
        assert rest.startswith(struct.pack("I", 1))

    def test_jedes_gewicht_hat_eine_quelle_und_jede_quelle_ein_gewicht(
        self, tmp_path: Path
    ) -> None:
        pfad = tmp_path / "model.bin"
        _schreibe_model_bin(pfad)
        variablen, verweise = ausgangsstand.lies_verzeichnis(pfad)
        karte = ausgangsstand.zuordnung(variablen)
        # So viele Gewichte hat `WhisperForConditionalGeneration` mit einer
        # Schicht je Seite: 22 im Encoder, 28 im Decoder und `proj_out`.
        assert len(karte) == 51
        for ausschnitt in karte.values():
            assert verweise.get(ausschnitt.name, ausschnitt.name) in variablen
        assert ausgangsstand.uebrig(variablen, verweise, karte) == set()

    def test_q_k_v_sind_die_drei_drittel(self, tmp_path: Path) -> None:
        pfad = tmp_path / "model.bin"
        _schreibe_model_bin(pfad)
        karte = ausgangsstand.zuordnung(ausgangsstand.lies_verzeichnis(pfad)[0])
        selbst = "model.decoder.layers.0.self_attn"
        assert (karte[f"{selbst}.q_proj.weight"].von, karte[f"{selbst}.q_proj.weight"].bis) == (0, 4)
        assert (karte[f"{selbst}.k_proj.weight"].von, karte[f"{selbst}.k_proj.weight"].bis) == (4, 8)
        assert (karte[f"{selbst}.v_proj.bias"].von, karte[f"{selbst}.v_proj.bias"].bis) == (8, 12)
        # `k_proj` hat keinen Bias - an seiner Stelle stehen Nullen.
        assert f"{selbst}.k_proj.bias" not in karte
        quer = "model.decoder.layers.0.encoder_attn"
        assert karte[f"{quer}.k_proj.weight"].name.endswith("attention/linear_1/weight")
        assert (karte[f"{quer}.v_proj.weight"].von, karte[f"{quer}.v_proj.weight"].bis) == (4, 8)

    def test_ein_fremdes_format_wird_abgewiesen(self, tmp_path: Path) -> None:
        pfad = tmp_path / "model.bin"
        _schreibe_model_bin(pfad, spezifikation="TransformerSpec")
        with pytest.raises(RuntimeError, match="WhisperSpec"):
            ausgangsstand.lies_verzeichnis(pfad)

    def test_ohne_stand_bleibt_es_das_grundmodell(self, tmp_path: Path) -> None:
        auftrag = {"basismodell": "openai/whisper-small"}
        assert ausgangsstand.quelle(tmp_path, tmp_path, auftrag, None) == "openai/whisper-small"
        assert ausgangsstand.erkenner(tmp_path, auftrag) == "small"

    def test_mit_stand_erkennt_der_stand(self, tmp_path: Path) -> None:
        auftrag = {"basismodell": "openai/whisper-medium", "ausgangsstand": REF}
        assert ausgangsstand.erkenner(tmp_path, auftrag) == str(
            registry.ct2_verzeichnis(tmp_path, REF)
        )
