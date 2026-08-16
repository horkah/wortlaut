"""Schneiden und Einlesen von Texten.

Der Chunker ist die Stelle, an der die Sprecheinheit entsteht — und damit die
Einheit, an der später jedes Audio-Text-Paar hängt. Deshalb wird hier genauer
geprüft als anderswo.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from wortlaut.text import chunker, upload

LANGER_SATZ = (
    "Am Zaun blieb der Hund stehen, weil dort eine Katze saß, die ihn schon lange "
    "beobachtet hatte, ohne sich auch nur einen Zentimeter zu bewegen, was ihn "
    "ziemlich beunruhigte."
)


class TestChunker:
    def test_haelt_die_hoechstdauer_ein(self) -> None:
        einheiten = chunker.schneide(LANGER_SATZ * 3)
        assert einheiten
        assert all(e.dauer_geschaetzt_s <= chunker.MAX_SEKUNDEN for e in einheiten)

    def test_verliert_keinen_text(self) -> None:
        text = "Ein kurzer Satz. Noch einer, mit Komma. Und ein dritter!"
        zusammen = " ".join(e.text for e in chunker.schneide(text))
        for wort in ("kurzer", "Komma", "dritter"):
            assert wort in zusammen

    def test_legt_zu_kurze_einheiten_zusammen(self) -> None:
        # Drei Fetzen von je unter drei Sekunden dürfen nicht drei Vorlagen ergeben.
        einheiten = chunker.schneide("Ja. Nein. Vielleicht.")
        assert len(einheiten) == 1

    def test_zerschneidet_abkuerzungen_nicht(self) -> None:
        einheiten = chunker.schneide("Herr Dr. Meier ging spazieren. Es war kalt.")
        assert any("Dr. Meier" in e.text for e in einheiten)

    def test_teilt_lange_saetze_an_teilsatzgrenzen(self) -> None:
        einheiten = chunker.schneide(LANGER_SATZ)
        assert len(einheiten) > 1
        # An Kommagrenzen geschnitten heißt: kein Stück beginnt mit einem Komma.
        assert all(not e.text.startswith(",") for e in einheiten)

    def test_leerer_text_ergibt_nichts(self) -> None:
        assert chunker.schneide("   \n\n  ") == []

    def test_dauer_waechst_mit_der_laenge(self) -> None:
        assert chunker.dauer("kurz") < chunker.dauer("deutlich länger als kurz")


class TestUpload:
    def test_liest_reintext(self) -> None:
        assert upload.lies_text(b"Hallo Welt.", "a.txt") == "Hallo Welt."

    def test_faellt_auf_latin1_zurueck(self) -> None:
        # Ältere deutsche Textdateien sind nicht UTF-8 kodiert.
        assert upload.lies_text("Grüße".encode("latin-1"), "a.txt") == "Grüße"

    def test_entfernt_markdown_zeichen(self) -> None:
        gelesen = upload.lies_text(b"# Titel\n\nEin *kurzer* Satz.", "a.md")
        assert gelesen == "Titel\n\nEin kurzer Satz."

    def test_liest_docx(self) -> None:
        puffer = io.BytesIO()
        raum = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        with zipfile.ZipFile(puffer, "w") as archiv:
            archiv.writestr(
                "word/document.xml",
                f'<w:document xmlns:w="{raum}"><w:body>'
                "<w:p><w:r><w:t>Erster Absatz.</w:t></w:r></w:p>"
                # Word zerlegt Absätze oft in mehrere Läufe.
                "<w:p><w:r><w:t>Zweiter </w:t></w:r><w:r><w:t>Absatz.</w:t></w:r></w:p>"
                "</w:body></w:document>",
            )
        assert upload.lies_text(puffer.getvalue(), "a.docx") == "Erster Absatz.\n\nZweiter Absatz."

    def test_liest_epub_in_lesereihenfolge(self) -> None:
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w") as archiv:
            archiv.writestr(
                "META-INF/container.xml",
                '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<rootfiles><rootfile full-path="OEBPS/buch.opf"/></rootfiles></container>',
            )
            # Manifest absichtlich in falscher Reihenfolge: der Spine entscheidet.
            archiv.writestr(
                "OEBPS/buch.opf",
                '<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
                '<item id="k2" href="zwei.xhtml"/><item id="k1" href="eins.xhtml"/>'
                '</manifest><spine><itemref idref="k1"/><itemref idref="k2"/></spine></package>',
            )
            archiv.writestr(
                "OEBPS/eins.xhtml",
                "<html><body><p>Kapitel eins.</p><style>p{}</style></body></html>",
            )
            archiv.writestr("OEBPS/zwei.xhtml", "<html><body><p>Kapitel zwei.</p></body></html>")

        gelesen = upload.lies_text(puffer.getvalue(), "a.epub")
        assert gelesen == "Kapitel eins.\n\nKapitel zwei."
        assert "p{}" not in gelesen  # Stilangaben sind kein Vorlesetext

    def test_lehnt_unbekanntes_format_ab(self) -> None:
        with pytest.raises(upload.UploadFehler):
            upload.lies_text(b"...", "aufnahme.mp3")
