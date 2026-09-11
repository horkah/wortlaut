"""Fehlerraten und die Zahl darüber - gerechnet an Fällen, die man nachzählen kann.

Die Vorlagen sind absichtlich kurz: Bei sechs Wörtern lässt sich jede Zahl im
Kopf prüfen, und genau das ist der Zweck dieser Tests. Was hier schiefginge,
fiele in einer Kurve über hundert Aufnahmen nie auf.
"""

from __future__ import annotations

import pytest
from wortlaut.metriken import Schritte, bewerte, genauigkeit, normalisiere, schritte

VORLAGE = "Am Montag gehe ich zum Markt."


class TestNormalisieren:
    def test_satzzeichen_und_grossschreibung_fallen_weg(self) -> None:
        assert normalisiere(VORLAGE) == "am montag gehe ich zum markt"

    def test_umlaute_und_ss_bleiben_wortbestandteil(self) -> None:
        assert normalisiere("Große Häuser, weiß!") == "große häuser weiß"

    def test_zerlegtes_und_zusammengesetztes_a_umlaut_sind_dasselbe(self) -> None:
        # Ein „ä" kann als ein Zeichen oder als a + Trema ankommen. Ohne
        # Angleichung zählte der Zeichenvergleich denselben Buchstaben einmal
        # als eins und einmal als zwei.
        assert normalisiere("Häuser") == normalisiere("Häuser")

    def test_typografie_wird_zu_einfachen_zeichen(self) -> None:
        assert normalisiere("„Ja“ - er kam …") == "ja er kam"

    def test_mehrfache_leerzeichen_werden_eins(self) -> None:
        assert normalisiere("  a \n\t b  ") == "a b"


class TestSchritte:
    def test_gleiche_folgen_sind_lauter_treffer(self) -> None:
        assert schritte(["a", "b"], ["a", "b"]) == Schritte(2, 0, 0, 0)

    def test_ein_vertauschtes_wort_ist_eine_ersetzung(self) -> None:
        # Und nicht Löschung plus Einfügung: bei gleichen Kosten gewinnt das
        # Ersetzen, weil ein vertauschtes Wort als ein Fehler verständlicher ist.
        assert schritte(["a", "b"], ["a", "x"]) == Schritte(1, 1, 0, 0)

    def test_fehlendes_wort_ist_eine_loeschung(self) -> None:
        assert schritte(["a", "b"], ["a"]) == Schritte(1, 0, 1, 0)

    def test_zusaetzliches_wort_ist_eine_einfuegung(self) -> None:
        assert schritte(["a"], ["a", "b"]) == Schritte(1, 0, 0, 1)

    def test_leere_hypothese_loescht_alles(self) -> None:
        assert schritte(["a", "b", "c"], []) == Schritte(0, 0, 3, 0)

    def test_leere_referenz_fuegt_alles_ein(self) -> None:
        assert schritte([], ["a", "b"]) == Schritte(0, 0, 0, 2)


class TestBewerten:
    def test_wortgleich_ist_fehlerfrei(self) -> None:
        guete = bewerte(VORLAGE, "am montag gehe ich zum markt")
        assert guete.wer == 0
        assert guete.cer == 0
        assert guete.genauigkeit == pytest.approx(100.0)

    def test_ein_wort_von_sechs_daneben(self) -> None:
        guete = bewerte(VORLAGE, "Am Dienstag gehe ich zum Markt.")
        assert guete.wer == pytest.approx(1 / 6)
        assert guete.mer == pytest.approx(1 / 6)
        # WIP = 5²/(6·6), also WIL = 1 - 25/36.
        assert guete.wil == pytest.approx(1 - 25 / 36)

    def test_leere_hypothese_ist_null(self) -> None:
        guete = bewerte(VORLAGE, "")
        assert guete.wer == 1
        assert guete.mer == 1
        assert guete.wil == 1
        assert guete.genauigkeit == 0

    def test_kein_einziges_wort_getroffen_ist_null(self) -> None:
        # Auch wenn CER über 1 liegt: Der Boden kommt von MER und WIL, und
        # „nichts davon war richtig" ist genau die 0.
        guete = bewerte(VORLAGE, "Völlig anderer Satz hier ohne Bezug")
        assert guete.genauigkeit == 0

    def test_dreifach_geliefert_ist_nicht_dasselbe_wie_stille(self) -> None:
        """Der Grund gegen einen Deckel bei 1 (siehe `genauigkeit`).

        Wiederholt ein Modell den Satz dreimal, ist jedes Wort richtig erkannt
        und nur zu viel geliefert. Ein gekappter WER machte das von völliger
        Stille ununterscheidbar.
        """
        satz = "Der Hund bellt."
        dreifach = bewerte(satz, f"{satz} {satz} {satz}")
        stille = bewerte(satz, "")

        assert dreifach.wer > 1
        assert dreifach.genauigkeit > 25
        assert stille.genauigkeit == 0

    def test_zeichenmass_ist_feiner_als_das_wortmass(self) -> None:
        knapp = bewerte(VORLAGE, "Am Montag gehe ich zum Mark")
        grob = bewerte(VORLAGE, "Am Dienstag gehe ich zum Markt.")

        assert knapp.wer == grob.wer  # beide: ein Wort von sechs
        assert knapp.cer < grob.cer  # aber ein Zeichen gegen drei
        assert knapp.genauigkeit > grob.genauigkeit


class TestGenauigkeit:
    def test_fehlerfrei_sind_hundert(self) -> None:
        assert genauigkeit(0, 0, 0, 0) == pytest.approx(100.0)

    def test_ein_durchgefallenes_mass_zieht_alles_mit(self) -> None:
        """Der Grund für das geometrische Mittel.

        Zeichen fast richtig, aber kein Wort getroffen: Das arithmetische
        Mittel gäbe hier eine mittlere Note, das geometrische die 0.
        """
        assert genauigkeit(wer=0.1, cer=0.05, mer=1.0, wil=1.0) == 0

    def test_faellt_monoton_mit_dem_fehler(self) -> None:
        vorher = 101.0
        for fehler in (0.0, 0.1, 0.25, 0.5, 0.75, 1.0):
            wert = genauigkeit(fehler, fehler, fehler, fehler)
            assert wert < vorher
            vorher = wert

    def test_bleibt_zwischen_null_und_hundert(self) -> None:
        for fehler in (0.0, 0.5, 1.0, 2.0, 17.0):
            assert 0 <= genauigkeit(fehler, fehler, min(fehler, 1), min(fehler, 1)) <= 100
