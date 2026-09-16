"""Zeichenerkennung - die Mechanik, nicht die Treffsicherheit.

Geprüft wird, was ohne Tesseract gilt: dass es sich sauber abmelden lässt,
statt mitten im Aufruf zu scheitern. Das ist die Zusage, an der die Oberfläche
hängt - sie bietet den Weg gar nicht erst an, wenn es ihn nicht gibt.

Dass Tesseract wirklich liest, prüft kein Test hier: Das verlangt ein
Systempaket, das in der Entwicklungsumgebung nicht steht. Gemessen wurde es von
Hand im Abbild - ein gerendertes Bild mit „Am Montag gehe ich zum Markt und
kaufe frisches Brot. Die Straße war größtenteils leer." kam Zeichen für
Zeichen zurück, samt Umlauten und ß, und dasselbe über eine gerasterte
PDF-Seite.
"""

from __future__ import annotations

import pytest
from wortlaut import sprachen
from wortlaut.text import ocr


class TestSprachkuerzel:
    def test_zwei_buchstaben_werden_drei(self) -> None:
        # Dieses Projekt führt `de` (`wortlaut/sprachen.py`), Tesseract `deu`.
        assert ocr.kuerzel("de") == "deu"

    def test_das_gebiet_stoert_nicht(self) -> None:
        assert ocr.kuerzel("de-DE") == ocr.kuerzel("de")

    def test_die_vorgabe_des_projekts_ist_bekannt(self) -> None:
        # Sonst liefe die einzige Sprache, die es gibt, in den Rückfall.
        assert ocr.kuerzel(sprachen.VORGABE) != "eng" or sprachen.VORGABE == "en"

    def test_unbekanntes_bekommt_tesseracts_vorgabe(self) -> None:
        # Nichts wird geraten: `eng` ist die einzige Sprachdatei, die überall
        # mitgeliefert wird.
        assert ocr.kuerzel("kl") == "eng"


class TestOhneTesseract:
    """Fehlt das Programm, ist das kein Fehler, sondern ein Weg weniger."""

    @pytest.fixture(autouse=True)
    def ohne(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ocr.verfuegbar.cache_clear()
        monkeypatch.setattr(ocr, "verfuegbar", lambda: False)

    def test_ein_bild_meldet_sich_ab(self) -> None:
        with pytest.raises(ocr.OcrFehler):
            ocr.aus_bild(b"nicht wirklich ein Bild", "de")

    def test_ein_pdf_meldet_sich_ab(self) -> None:
        with pytest.raises(ocr.OcrFehler):
            ocr.aus_pdf(b"%PDF-1.4", "de")

    def test_der_fehler_sagt_woran_es_liegt(self) -> None:
        # Die Oberfläche zeigt diesen Satz; „Fehler 500" hülfe niemandem.
        with pytest.raises(ocr.OcrFehler, match="Zeichenerkennung"):
            ocr.aus_bild(b"x", "de")


class TestEntrauschen:
    """Vorsichtig, nicht gründlich - der Mensch sieht danach ohnehin hin."""

    def test_zeilen_ohne_wort_fallen_weg(self) -> None:
        # Der Wirbel auf einem Cremedeckel wird zu solchen Zeilen.
        roh = "NATURKOSMETIK\n| x\nYe\nv,\nVEGAN"
        assert ocr.entrausche(roh) == "NATURKOSMETIK\nVEGAN"

    def test_ziffern_zaehlen_als_wort(self) -> None:
        # `48h` und `10/2024` stehen wirklich auf der Vorlage - ein Filter, der
        # nur Buchstaben zählte, hätte sie weggeworfen.
        assert ocr.entrausche("48h") == "48h"
        assert ocr.entrausche("Magazin 10/2024") == "Magazin 10/2024"

    def test_drei_zeichen_genuegen(self) -> None:
        # Die Grenze liegt bei drei und nicht höher: Lieber ein Brocken zu viel
        # als ein echtes Wort zu wenig.
        assert ocr.entrausche("ZER") == "ZER"
        assert ocr.entrausche("Ye") == ""

    def test_absaetze_bleiben_absaetze(self) -> None:
        # Der Schnitt danach arbeitet an Leerzeilen (`text/chunker.py`).
        assert ocr.entrausche("Erster Satz.\n\nZweiter Satz.") == "Erster Satz.\n\nZweiter Satz."

    def test_leerzeilen_haeufen_sich_nicht(self) -> None:
        # Nach dem Wegnehmen stünden sonst Lücken, wo Rauschen war.
        assert ocr.entrausche("Erster Satz.\nYe\n| x\n\nZweiter Satz.") == (
            "Erster Satz.\n\nZweiter Satz."
        )


class TestBruchstueckzeilen:
    """Zeilen, die mehrheitlich aus Bruchstücken bestehen."""

    def test_ein_langer_brocken_rettet_die_zeile_nicht(self) -> None:
        # Vom Wirbel auf einem Cremedeckel: fünf Bruchstücke, davon eines
        # zufällig fünf Zeichen lang. Ein einzelnes Wort genügte einmal, und
        # damit blieb diese Zeile stehen.
        assert ocr.entrausche("k Be #2 I CFrAN") == ""

    def test_die_haelfte_genuegt(self) -> None:
        # `Bio-Jojobaöl &` ist ein Wort auf zwei Brocken - und steht wirklich da.
        assert ocr.entrausche("Bio-Jojobaöl &") == "Bio-Jojobaöl &"
        assert ocr.entrausche("ZERTIFIZIERT || VEGAN") == "ZERTIFIZIERT || VEGAN"

    def test_ein_satz_bleibt_ein_satz(self) -> None:
        satz = "Dann unbedingt vor dem Zubettgehen beim NTH-"
        assert ocr.entrausche(satz) == satz


class TestZuversicht:
    """Gegen Zeilen, die wie Wörter aussehen und keine sind."""

    def test_die_grenze_liegt_in_der_gemessenen_luecke(self) -> None:
        # Gemessen: Rauschen aus einem Unterstrich kam auf 6,5, das schwächste
        # echte Wort auf dem schweren Foto auf 28. Dazwischen muss sie liegen,
        # mit Abstand nach beiden Seiten (die Zahlen stehen in `ocr.py`).
        assert 10 <= ocr.MINDESTZUVERSICHT <= 20

    def test_laenge_allein_faengt_das_nicht(self) -> None:
        # Der Unterstrich unter „Birchermüsli zum Frühstück?" wurde zu dieser
        # Zeile. Sie besteht aus Wörtern - nur aus keiner Sprache. Dagegen hilft
        # nur, Tesseract nach seiner Sicherheit zu fragen.
        assert ocr.entrausche("a nee heneibneeneschebeißsi") != ""


class TestMass:
    """Was je Format aufgewendet wird - die Zahlen stehen in `ocr.py`."""

    def test_die_kante_bleibt_im_gemessenen_plateau(self) -> None:
        # Unter 2000 fällt die Trefferquote, über 2600 fällt sie auch - und die
        # Zeit läuft davon (die Messreihe steht bei `MAX_KANTE`).
        assert 2000 <= ocr.MAX_KANTE <= 2600

    def test_die_vorgabe_wird_zuerst_versucht(self) -> None:
        # Bei Gleichstand gewinnt der erste - und das soll der zurückhaltendste
        # Weg sein, nicht der findigste.
        assert ocr.SEITENARTEN[0] == 3


class TestFormate:
    def test_heic_ist_dabei(self) -> None:
        # iPhones fotografieren so, und Safari wandelt nicht immer um.
        assert ".heic" in ocr.UNTERSTUETZT

    def test_alle_formate_sind_endungen_mit_punkt(self) -> None:
        # Die Oberfläche reicht die Liste unverändert an `accept` weiter.
        assert all(f.startswith(".") and f.islower() for f in ocr.UNTERSTUETZT)
