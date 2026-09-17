"""Die eine Stelle, an der steht, welche Sprachen dieses System kennt.

Geprüft wird nicht, dass es Deutsch ist - das ist eine Entscheidung und kein
Verhalten. Geprüft wird, dass die Vorgabe wirklich unterstützt wird, dass
Unbekanntes abgewiesen wird und dass dieselbe Sprache nicht in zwei
Schreibweisen in die Datenbank kommt.
"""

from __future__ import annotations

import pytest
from wortlaut import sprachen


class TestBestand:
    def test_die_vorgabe_ist_eine_unterstuetzte_sprache(self) -> None:
        # Sonst legte jedes Profil ohne Angabe eine Sprache an, die es nicht
        # gibt - und das fiele erst beim Vorlesen auf.
        assert sprachen.VORGABE in sprachen.UNTERSTUETZT

    def test_jede_unterstuetzte_sprache_ist_normiert_hinterlegt(self) -> None:
        # `pruefe` gibt die normierte Form zurück; stünde im Bestand `de-DE`,
        # fände sich der Rückgabewert dort nie wieder.
        for kuerzel in sprachen.UNTERSTUETZT:
            assert sprachen.normiere(kuerzel) == kuerzel

    def test_jede_hat_einen_namen(self) -> None:
        assert all(name for name in sprachen.UNTERSTUETZT.values())


class TestNormieren:
    @pytest.mark.parametrize("roh", ["de", "DE", " de ", "de-DE", "de_DE", "De-at"])
    def test_gebiet_und_schreibweise_fallen_weg(self, roh: str) -> None:
        # Nachsichtig beim Lesen: Wer ein Gebiet mitschickt, meint dieselbe
        # Sprache. Whisper unterscheidet sie ohnehin nicht.
        assert sprachen.normiere(roh) == "de"

    def test_normiert_wird_auch_beim_pruefen(self) -> None:
        assert sprachen.pruefe("de-DE") == "de"


class TestPruefen:
    def test_unbekanntes_wird_abgewiesen(self) -> None:
        with pytest.raises(sprachen.UnbekannteSprache):
            sprachen.pruefe("kl")

    def test_der_fehler_nennt_die_wahl(self) -> None:
        # Wer eine Sprache anfragt, die es nicht gibt, soll lesen können,
        # welche es gibt - sonst rät er ein zweites Mal.
        with pytest.raises(sprachen.UnbekannteSprache) as fehler:
            sprachen.pruefe("kl")
        assert sprachen.VORGABE in str(fehler.value)

    def test_leer_ist_keine_sprache(self) -> None:
        with pytest.raises(sprachen.UnbekannteSprache):
            sprachen.pruefe("")


class TestName:
    def test_bekanntes_bekommt_seinen_namen(self) -> None:
        assert sprachen.name(sprachen.VORGABE) == sprachen.UNTERSTUETZT[sprachen.VORGABE]

    def test_unbekanntes_bleibt_das_kuerzel(self) -> None:
        # Hässlich, aber richtig - dieselbe Regel wie bei einer fremden Stimme
        # in `vorlesen.py`: lieber ein Kürzel zeigen als einen Bestand
        # verschweigen.
        assert sprachen.name("kl") == "kl"


class TestEnglisch:
    """Die zweite Sprache - und was mit ihr zusammenhängen muss."""

    def test_englisch_steht_zur_wahl(self) -> None:
        assert sprachen.ENGLISCH in sprachen.UNTERSTUETZT

    def test_das_gebiet_faellt_auch_hier_weg(self) -> None:
        # `en-GB` und `en-US` sind für Whisper dieselbe Sprache.
        assert sprachen.pruefe("en-GB") == sprachen.ENGLISCH
