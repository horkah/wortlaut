"""Worauf gerechnet wird - eine Entscheidung, drei Nutzer.

Geprüft wird die Entscheidung selbst und nicht das Rechnen: Ob eine Karte da
ist, weiß nur die Maschine, auf der dieser Test läuft, und ein Test, der eine
verlangt, liefe nirgends.
"""

from __future__ import annotations

import pytest
from wortlaut import rechenwerk


@pytest.fixture(autouse=True)
def _ohne_gedaechtnis():
    """`karte_da` merkt sich seine Antwort - zwischen zwei Tests darf es das nicht."""
    rechenwerk.karte_da.cache_clear()
    yield
    rechenwerk.karte_da.cache_clear()


class TestWahl:
    def test_mit_karte_wird_die_karte_genommen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rechenwerk, "karte_da", lambda: True)
        assert rechenwerk.waehle() == ("cuda", "int8_float16")

    def test_ohne_karte_der_prozessor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rechenwerk, "karte_da", lambda: False)
        assert rechenwerk.waehle() == ("cpu", "int8")

    def test_ein_ausdruecklicher_wunsch_gilt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Auch der unsinnige: Wer `cuda` erzwingt, wo keine Karte ist, soll den
        # Fehler sehen und nicht stillschweigend auf dem Prozessor landen.
        monkeypatch.setattr(rechenwerk, "karte_da", lambda: False)
        assert rechenwerk.waehle("cuda") == ("cuda", "int8_float16")
        monkeypatch.setattr(rechenwerk, "karte_da", lambda: True)
        assert rechenwerk.waehle("cpu") == ("cpu", "int8")

    def test_die_rechenart_laesst_sich_einzeln_setzen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rechenwerk, "karte_da", lambda: True)
        assert rechenwerk.waehle(rechenart="float16") == ("cuda", "float16")


class TestMarke:
    def test_nennt_geraet_und_rechenart(self) -> None:
        assert rechenwerk.marke("cuda", "int8_float16") == "cuda/int8_float16"

    def test_zwei_rechenwerke_sind_zu_unterscheiden(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Daran hängt, ob zwei Rechenzeiten nebeneinanderstehen dürfen.
        monkeypatch.setattr(rechenwerk, "karte_da", lambda: True)
        auf_karte = rechenwerk.gilt()
        monkeypatch.setattr(rechenwerk, "karte_da", lambda: False)
        assert auf_karte != rechenwerk.gilt()


class TestOhneCTranslate:
    def test_keine_karte_ohne_laufzeit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Eine Installation ohne `[asr]`: Wer nicht erkennt, braucht auch keine
        # Karte - und soll daran nicht scheitern.
        import builtins

        echt = builtins.__import__

        def ohne(name, *rest):
            if name == "ctranslate2":
                raise ModuleNotFoundError(name)
            return echt(name, *rest)

        monkeypatch.setattr(builtins, "__import__", ohne)
        assert rechenwerk.karte_da() is False
