"""Warten auf die Karte, statt an ihr zu scheitern (`training/karte.py`).

Ohne Karte und ohne torch: Was belegt ist und was ein Versuch wirft, spielt
der Test selbst.
"""

from __future__ import annotations

import pytest

from apps.lernen.training import karte

MANGEL = "CUDA out of memory. Tried to allocate 18.00 MiB."


class Bericht:
    def __init__(self) -> None:
        self.zeilen: list[str] = []

    def sage(self, text: str) -> None:
        self.zeilen.append(text)


class Versuche:
    """Wirft der Reihe nach, was in `folge` steht; danach gelingt es."""

    def __init__(self, *folge: Exception) -> None:
        self.folge = list(folge)
        self.anzahl = 0

    def __call__(self) -> str:
        self.anzahl += 1
        if self.folge:
            raise self.folge.pop(0)
        return "gewichte"


def _mit_geduld(versuch, *, fremd: float = 5000.0, wartezeiten=(5, 10)):
    geschlafen: list[float] = []
    aufgeraeumt: list[int] = []
    bericht = Bericht()
    ergebnis = karte.mit_geduld(
        versuch,
        bericht,
        aufraeumen=lambda: aufgeraeumt.append(versuch.anzahl),
        fremd_belegt_mb=lambda: fremd,
        wartezeiten=wartezeiten,
        schlafe=geschlafen.append,
    )
    return ergebnis, geschlafen, aufgeraeumt, bericht


class TestWarten:
    def test_ohne_mangel_wird_nicht_gewartet(self) -> None:
        versuch = Versuche()
        ergebnis, geschlafen, aufgeraeumt, _ = _mit_geduld(versuch)
        assert (ergebnis, versuch.anzahl, geschlafen, aufgeraeumt) == ("gewichte", 1, [], [])

    def test_belegte_karte_wird_ausgesessen(self) -> None:
        versuch = Versuche(RuntimeError(MANGEL))
        ergebnis, geschlafen, aufgeraeumt, bericht = _mit_geduld(versuch)
        assert ergebnis == "gewichte"
        assert versuch.anzahl == 2
        # Aufgeräumt nach dem ersten Versuch, und erst dann gewartet.
        assert aufgeraeumt == [1]
        assert geschlafen == [5]
        assert any("Karte frei" in zeile for zeile in bericht.zeilen)

    def test_nach_der_letzten_wartezeit_kommt_der_fehler(self) -> None:
        versuch = Versuche(*(RuntimeError(MANGEL) for _ in range(3)))
        with pytest.raises(RuntimeError, match="out of memory"):
            _mit_geduld(versuch)
        assert versuch.anzahl == 3

    def test_ein_anderer_fehler_geht_sofort_durch(self) -> None:
        versuch = Versuche(ValueError("Rezept kaputt"))
        with pytest.raises(ValueError, match="Rezept kaputt"):
            _mit_geduld(versuch)
        assert versuch.anzahl == 1

    def test_haelt_niemand_sonst_etwas_passt_es_nicht(self) -> None:
        # Dann ändert Warten nichts: Das Training ist zu groß für die Karte.
        versuch = Versuche(RuntimeError(MANGEL))
        with pytest.raises(RuntimeError, match="passt nicht"):
            _mit_geduld(versuch, fremd=300.0)
        assert versuch.anzahl == 1


class TestErkennung:
    @pytest.mark.parametrize(
        "text",
        [MANGEL, "CUDA failed with error out of memory", "Out Of Memory"],
    )
    def test_speichermangel(self, text: str) -> None:
        assert karte.ist_speichermangel(RuntimeError(text))

    def test_anderer_fehler(self) -> None:
        assert not karte.ist_speichermangel(RuntimeError("device-side assert triggered"))
