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


class TestFormate:
    def test_heic_ist_dabei(self) -> None:
        # iPhones fotografieren so, und Safari wandelt nicht immer um.
        assert ".heic" in ocr.UNTERSTUETZT

    def test_alle_formate_sind_endungen_mit_punkt(self) -> None:
        # Die Oberfläche reicht die Liste unverändert an `accept` weiter.
        assert all(f.startswith(".") and f.islower() for f in ocr.UNTERSTUETZT)
