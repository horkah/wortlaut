"""Hochgeladene Dateien → Reintext.

txt, md, docx und epub kommen mit der Standardbibliothek aus: docx und epub
sind ZIP-Archive mit XML bzw. HTML darin. Nur für PDF gibt es keine Lösung
ohne Fremdpaket, dafür ist `pypdf` da.

Der Rückgabewert ist immer Fließtext mit Leerzeile zwischen Absätzen — genau
das, was `chunker.schneide()` erwartet.
"""

from __future__ import annotations

import re
import zipfile
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
from typing import ClassVar
from xml.etree import ElementTree

UNTERSTUETZT = (".txt", ".md", ".pdf", ".epub", ".docx")

_MARKDOWN = re.compile(r"^#{1,6}\s+|^[-*+]\s+|^>\s+|[*_`]{1,3}", re.MULTILINE)
_MEHRFACHE_LEERZEILEN = re.compile(r"\n{3,}")


class UploadFehler(ValueError):
    """Format nicht unterstützt oder Datei nicht lesbar."""


def lies_text(inhalt: bytes, dateiname: str) -> str:
    """Wählt anhand der Endung den passenden Leser."""
    endung = PurePosixPath(dateiname).suffix.lower()
    leser = {
        ".txt": _reintext,
        ".md": _markdown,
        ".pdf": _pdf,
        ".epub": _epub,
        ".docx": _docx,
    }.get(endung)
    if leser is None:
        raise UploadFehler(f"Nicht unterstütztes Format: {endung or dateiname!r}")
    return _aufraeumen(leser(inhalt))


def _aufraeumen(text: str) -> str:
    zeilen = [zeile.strip() for zeile in text.replace("\r\n", "\n").split("\n")]
    return _MEHRFACHE_LEERZEILEN.sub("\n\n", "\n".join(zeilen)).strip()


def _reintext(inhalt: bytes) -> str:
    # Fast alles ist heute UTF-8; ältere deutsche Textdateien sind Latin-1.
    try:
        return inhalt.decode("utf-8")
    except UnicodeDecodeError:
        return inhalt.decode("latin-1")


def _markdown(inhalt: bytes) -> str:
    return _MARKDOWN.sub("", _reintext(inhalt))


def _pdf(inhalt: bytes) -> str:
    from pypdf import PdfReader

    leser = PdfReader(BytesIO(inhalt))
    return "\n\n".join(seite.extract_text() or "" for seite in leser.pages)


def _docx(inhalt: bytes) -> str:
    """Ein docx ist ein ZIP; der Fließtext steht in `word/document.xml`."""
    raum = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(BytesIO(inhalt)) as archiv:
        baum = ElementTree.fromstring(archiv.read("word/document.xml"))
    absaetze = [
        "".join(knoten.text or "" for knoten in absatz.iter(f"{raum}t"))
        for absatz in baum.iter(f"{raum}p")
    ]
    return "\n\n".join(absatz for absatz in absaetze if absatz.strip())


def _epub(inhalt: bytes) -> str:
    """Ein epub ist ein ZIP; die Lesereihenfolge steht im Spine der OPF-Datei."""
    with zipfile.ZipFile(BytesIO(inhalt)) as archiv:
        return "\n\n".join(_html_zu_text(archiv.read(name)) for name in _epub_kapitel(archiv))


def _epub_kapitel(archiv: zipfile.ZipFile) -> list[str]:
    """Kapiteldateien in Lesereihenfolge; fällt auf Namenssortierung zurück."""
    try:
        container = ElementTree.fromstring(archiv.read("META-INF/container.xml"))
        opf_pfad = container.find(".//{*}rootfile").attrib["full-path"]
        opf = ElementTree.fromstring(archiv.read(opf_pfad))
        wurzel = PurePosixPath(opf_pfad).parent

        nach_id = {
            eintrag.attrib["id"]: str(wurzel / eintrag.attrib["href"])
            for eintrag in opf.iter("{*}item")
        }
        kapitel = [
            nach_id[verweis.attrib["idref"]]
            for verweis in opf.iter("{*}itemref")
            if verweis.attrib.get("idref") in nach_id
        ]
        if kapitel:
            return kapitel
    except (KeyError, AttributeError, ElementTree.ParseError):
        pass  # kaputtes oder ungewöhnliches epub — unten weiter

    return sorted(
        name for name in archiv.namelist() if name.lower().endswith((".xhtml", ".html", ".htm"))
    )


class _TextSammler(HTMLParser):
    """Nimmt den sichtbaren Text auf und macht aus Absätzen Leerzeilen."""

    BLOCK: ClassVar[set[str]] = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li"}

    def __init__(self) -> None:
        super().__init__()
        self.teile: list[str] = []
        self._ueberspringen = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._ueberspringen = True
        elif tag in self.BLOCK:
            self.teile.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._ueberspringen = False

    def handle_data(self, daten: str) -> None:
        if not self._ueberspringen:
            self.teile.append(daten)


def _html_zu_text(inhalt: bytes) -> str:
    sammler = _TextSammler()
    sammler.feed(_reintext(inhalt))
    return "".join(sammler.teile)
