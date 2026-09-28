"""Wo der LoRA-Zusatz sitzt und wie groß er ist (`training/adapter.py`)."""

from __future__ import annotations

import re

import pytest
from wortlaut import laeufe

from apps.lernen.training import adapter

REZEPT = {"lora": {"alpha_je_rang": 2, "ausfall": 0.05}}

# Namen, wie peft sie in whisper sieht.
NAMEN = (
    "model.encoder.layers.0.self_attn.q_proj",
    "model.encoder.layers.11.fc1",
    "model.decoder.layers.3.self_attn.k_proj",
    "model.decoder.layers.3.encoder_attn.out_proj",
    "model.decoder.layers.3.fc2",
    "proj_out",
)


def _getroffen(muster: list[str] | str) -> set[str]:
    """Welche Namen peft mit diesem `target_modules` trifft - seine beiden Regeln."""
    if isinstance(muster, str):
        return {name for name in NAMEN if re.fullmatch(muster, name)}
    return {name for name in NAMEN if any(name == z or name.endswith(f".{z}") for z in muster)}


def _auftrag(**achsen: str) -> dict[str, str]:
    return {"methode": "lora", **achsen}


class TestZiele:
    def test_die_vorgabe_ist_q_und_v(self) -> None:
        zusatz = adapter.adapter_fuer(REZEPT, _auftrag())
        assert _getroffen(zusatz.muster) == {"model.encoder.layers.0.self_attn.q_proj"}

    def test_alle_projektionen_in_beiden_teilen(self) -> None:
        zusatz = adapter.adapter_fuer(REZEPT, _auftrag(lora_ziele=laeufe.ZIELE_ALLE))
        assert _getroffen(zusatz.muster) == set(NAMEN) - {"proj_out"}

    def test_nur_der_encoder(self) -> None:
        zusatz = adapter.adapter_fuer(REZEPT, _auftrag(lora_ziele=laeufe.ZIELE_ENCODER))
        assert _getroffen(zusatz.muster) == {
            "model.encoder.layers.0.self_attn.q_proj",
            "model.encoder.layers.11.fc1",
        }

    def test_nur_der_decoder_samt_kreuzaufmerksamkeit(self) -> None:
        # `encoder_attn` sitzt im Decoder und gehört zu ihm.
        zusatz = adapter.adapter_fuer(REZEPT, _auftrag(lora_ziele=laeufe.ZIELE_DECODER))
        assert _getroffen(zusatz.muster) == {
            "model.decoder.layers.3.self_attn.k_proj",
            "model.decoder.layers.3.encoder_attn.out_proj",
            "model.decoder.layers.3.fc2",
        }


class TestRang:
    @pytest.mark.parametrize(("rang", "alpha"), [("8", 16), ("32", 64), ("64", 128)])
    def test_alpha_waechst_mit(self, rang: str, alpha: int) -> None:
        zusatz = adapter.adapter_fuer(REZEPT, _auftrag(lora_rang=rang))
        assert (zusatz.rang, zusatz.alpha) == (int(rang), alpha)

    def test_ohne_feld_die_vorgabe(self) -> None:
        assert adapter.adapter_fuer(REZEPT, _auftrag()).rang == int(laeufe.RANG_VORGABE)


class TestPruefung:
    def test_nur_mit_lora(self) -> None:
        with pytest.raises(RuntimeError, match="nur mit LoRA"):
            adapter.pruefe({"methode": "full", "lora_rang": "8"})

    def test_volles_training_mit_vorgaben_geht(self) -> None:
        adapter.pruefe({"methode": "full"})

    def test_unbekannte_ziele(self) -> None:
        with pytest.raises(RuntimeError, match="LoRA-Ziele"):
            adapter.pruefe(_auftrag(lora_ziele="ueberall"))
