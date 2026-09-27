"""Der Zuschnitt auf die Karte - ohne Karte geprüft (`wortlaut/kartenplan.py`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from wortlaut import kartenplan, laeufe

A100 = kartenplan.Karte(name="NVIDIA A100-SXM4-80GB", speicher_mb=85_000.0, rechenfaehigkeit=(8, 0), anzahl=8)
V100 = kartenplan.Karte(name="Tesla V100-SXM2-32GB", speicher_mb=34_000.0, rechenfaehigkeit=(7, 0))


class TestMethoden:
    """Was auf welche Karte passt - die Regel, nach der „lernen" anbietet."""

    @pytest.mark.parametrize(
        ("modell", "erwartet"),
        [
            ("openai/whisper-small", ("full", "lora")),
            ("openai/whisper-medium", ("lora",)),
            ("openai/whisper-large-v3", ("lora",)),
        ],
    )
    def test_auf_der_2080_ti(self, modell: str, erwartet: tuple[str, ...]) -> None:
        assert laeufe.methoden_fuer(modell) == erwartet

    def test_auf_80_gb_auch_large_v3_voll(self) -> None:
        assert laeufe.methoden_fuer("openai/whisper-large-v3", A100) == ("full", "lora")

    def test_die_reserve_zaehlt_mit(self) -> None:
        # Wer den Erkennern die halbe Karte lässt, bekommt `small` nicht mehr voll.
        assert laeufe.methoden_fuer("openai/whisper-small", kartenplan.VORGABE, 7000) == ("lora",)

    def test_ohne_karte_entscheidet_der_versuch(self) -> None:
        assert laeufe.methoden_fuer("openai/whisper-large-v3", None) == ("full", "lora")

    def test_ein_unbekanntes_modell_gilt_als_gross(self) -> None:
        assert laeufe.methoden_fuer("openai/whisper-riesig") == ("lora",)


class TestGenauigkeit:
    def test_turing_rechnet_fp16(self) -> None:
        assert kartenplan.genauigkeit(kartenplan.VORGABE) == "fp16"
        assert kartenplan.genauigkeit(V100) == "fp16"

    def test_ab_ampere_bf16(self) -> None:
        assert kartenplan.genauigkeit(A100) == "bf16"

    def test_ohne_karte_fp32(self) -> None:
        assert kartenplan.genauigkeit(None) == "fp32"


class TestStapel:
    def test_erst_schnell_dann_sparsam_dann_kleiner(self) -> None:
        assert kartenplan.kandidaten(8) == [(8, False), (8, True), (4, True), (2, True), (1, True)]

    def test_nur_teiler_des_wirksamen_stapels(self) -> None:
        assert [stapel for stapel, _ in kartenplan.kandidaten(6)] == [6, 6, 3, 2, 1]

    def test_die_akkumulation_holt_den_wirksamen_stapel_zurueck(self) -> None:
        plan = kartenplan.plan(kartenplan.VORGABE, "lora", 8, 2, True)
        assert (plan.stapel, plan.akkumulation, plan.wirksam) == (2, 4, 8)
        assert plan.halbe_grundgewichte
        assert plan.aufmerksamkeit == "sdpa"

    def test_voll_bleiben_die_gewichte_ganz(self) -> None:
        assert not kartenplan.plan(A100, "full", 8, 8, False).halbe_grundgewichte

    def test_ein_kandidat_passt_neben_anderen_und_der_reserve(self) -> None:
        # 11 539 MB, 1 000 bei anderen, 2 000 Reserve: 8 539 bleiben.
        assert kartenplan.passt(8000, 500, 11539, 1000, 2000)
        assert not kartenplan.passt(8000, 600, 11539, 1000, 2000)

    def test_der_optimierer_zaehlt_acht_byte_je_gewicht(self) -> None:
        assert kartenplan.optimierer_mb(10_000_000) == pytest.approx(80.0)


class TestKartendatei:
    def test_hin_und_zurueck(self, tmp_path: Path) -> None:
        kartenplan.schreibe_karte(tmp_path, A100)
        assert kartenplan.lies_karte(tmp_path) == A100

    def test_fehlt_sie_gibt_es_keine(self, tmp_path: Path) -> None:
        assert kartenplan.lies_karte(tmp_path) is None

    def test_eine_kaputte_ist_keine(self, tmp_path: Path) -> None:
        (tmp_path / kartenplan.KARTE).write_text("{halb", encoding="utf-8")
        assert kartenplan.lies_karte(tmp_path) is None
