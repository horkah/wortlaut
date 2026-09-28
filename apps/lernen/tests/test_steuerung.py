"""Wonach ausgewählt wird - Prüfplan und WER der Steuergröße (`training/steuerung.py`).

Ohne Karte und ohne torch: Hier steht, wann geprüft wird und wie die Zahl
entsteht, die über den besten Zwischenstand entscheidet.
"""

from __future__ import annotations

import pytest
from wortlaut import laeufe

from apps.lernen.training import steuerung

REZEPT = {"geduld": 4, "wer_pruefungen_je_durchgang": 3}


class TestPruefplan:
    def test_der_verlust_prueft_je_durchgang(self) -> None:
        plan = steuerung.plane(laeufe.STEUERUNG_VERLUST, True, 30, REZEPT)
        assert (plan.mass, plan.je_durchgang, plan.alle_schritte) == ("loss", 1, None)
        assert plan.metrik == "eval_loss"
        assert not plan.dekodiert

    def test_die_wer_prueft_je_drittel(self) -> None:
        plan = steuerung.plane(laeufe.STEUERUNG_WER, True, 30, REZEPT)
        assert (plan.mass, plan.je_durchgang, plan.alle_schritte) == ("wer", 3, 10)
        assert plan.metrik == "eval_wer"
        assert plan.dekodiert

    def test_ein_rest_rundet_den_abstand_auf(self) -> None:
        # Nie eine vierte Prüfung am Ende eines Durchgangs.
        assert steuerung.plane(laeufe.STEUERUNG_WER, True, 31, REZEPT).alle_schritte == 11

    def test_ein_winziger_korpus_prueft_je_schritt(self) -> None:
        plan = steuerung.plane(laeufe.STEUERUNG_WER, True, 2, REZEPT)
        assert (plan.je_durchgang, plan.alle_schritte) == (2, 1)

    def test_die_geduld_zaehlt_durchgaenge(self) -> None:
        # Viermal geduldig heißt vier Durchgänge, wie oft auch geprüft wird.
        assert steuerung.plane(laeufe.STEUERUNG_VERLUST, True, 30, REZEPT).geduld(REZEPT) == 4
        assert steuerung.plane(laeufe.STEUERUNG_WER, True, 30, REZEPT).geduld(REZEPT) == 12

    def test_ohne_validierung_gibt_es_nichts_zu_dekodieren(self) -> None:
        # Das Endmodell hält nichts zurück.
        plan = steuerung.plane(laeufe.STEUERUNG_WER, False, 30, REZEPT)
        assert not plan.dekodiert

    def test_eine_unbekannte_steuergroesse_faellt_sofort_auf(self) -> None:
        with pytest.raises(RuntimeError, match="Steuergröße"):
            steuerung.plane("bauchgefuehl", True, 30, REZEPT)


class TestMittlereWer:
    def test_je_zeile_gemittelt_wie_die_messung(self) -> None:
        # Ein kurzer falscher Satz zählt so viel wie ein langer richtiger -
        # wie im Mittel über die Zeilen einer Faltung.
        wer = steuerung.mittlere_wer(
            ["ein langer richtiger Satz mit vielen Wörtern", "kurz"],
            ["ein langer richtiger Satz mit vielen Wörtern", "falsch"],
        )
        assert wer == pytest.approx(0.5)

    def test_verglichen_wird_normalisiert(self) -> None:
        assert steuerung.mittlere_wer(["Guten Morgen."], ["guten morgen"]) == 0.0

    def test_ohne_zeilen_null(self) -> None:
        assert steuerung.mittlere_wer([], []) == 0.0
