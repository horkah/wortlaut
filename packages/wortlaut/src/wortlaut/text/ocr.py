"""Bilder und eingescannte PDFs → Text, auf diesem Rechner.

**Wofür.** Eine Vorlage muss nicht getippt sein. Wer einen Zeitungsausschnitt,
eine Buchseite oder einen Brief vorlesen will, fotografiert ihn - und genau das
ist der Weg, der ohne Tastatur auskommt (Grundentscheidung 7). Was hier
herauskommt, geht **nicht** unmittelbar in den Korpus: Es wird angezeigt,
berichtigt und erst dann übernommen (`api/sources.py`). Eine Zeichenerkennung
irrt, und ein Fehler in der Vorlage wandert sonst in die Aufnahme und von dort
ins Training.

**Warum Tesseract und kein Dienst.** Aus demselben Grund, aus dem Whisper hier
läuft und nicht anderswo: Es verlässt die Maschine nichts
(`docs/datenschutz.md`). Ein fotografierter Brief ist kein Thema, das man
verschickt - er ist womöglich das Persönlichste, was diese App je zu sehen
bekommt.

**Warum es fehlen darf.** Tesseract ist eine Systemabhängigkeit. Im Abbild
dieses Projekts ist es drin; wer die App anders betreibt, hat es vielleicht
nicht. Dann fehlt genau dieser Weg, und die App sagt das, statt mit einem
Serverfehler abzubrechen - wie beim Vorlesen, wo eine fehlende Stimme ebenfalls
kein Fehler ist, sondern ein Weg weniger (`wortlaut/vorlesen.py`).
"""

from __future__ import annotations

import functools
import io

from .. import sprachen

# Was an Bildern hereinkommen darf. `heic` steht dabei nicht aus Vollständigkeit
# in der Liste, sondern weil iPhones so fotografieren: Safari wandelt beim
# Hochladen meistens in JPEG, aber eben nicht immer, und ein Foto, das der
# Server nicht öffnen kann, ist für den Menschen davor kein Formatproblem,
# sondern ein Knopf, der nicht tut.
UNTERSTUETZT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif")

# Wie Tesseract die Sprachen nennt: drei Buchstaben nach ISO 639-2, während
# dieses Projekt zwei führt (`wortlaut/sprachen.py`). Fehlt eine, wird nichts
# geraten - `eng` ist Tesseracts eigene Vorgabe und die einzige, die überall
# mitgeliefert wird.
_KUERZEL = {"de": "deu", "en": "eng"}
_RUECKFALL = "eng"


class OcrFehler(RuntimeError):
    """Erkennen ist nicht möglich oder fehlgeschlagen."""


def kuerzel(sprache: str) -> str:
    """`de` → `deu`. Unbekanntes bekommt Tesseracts Vorgabe."""
    return _KUERZEL.get(sprachen.normiere(sprache), _RUECKFALL)


@functools.cache
def verfuegbar() -> bool:
    """Ob auf diesem Rechner erkannt werden kann.

    Zwischengespeichert, weil die Antwort sich zur Laufzeit nicht ändert und
    die Oberfläche sie bei jedem Aufruf der Textquellen erfragt: Der Aufruf von
    `tesseract --version` kostet einen Prozess, und zwanzig davon je Seite
    wären zwanzig zu viel.
    """
    try:
        import pytesseract
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    try:
        pytesseract.get_tesseract_version()
    except Exception:  # was immer pytesseract wirft, wenn das Programm fehlt
        return False
    return True


def _oeffne(inhalt: bytes):
    from PIL import Image

    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        pass  # dann eben ohne HEIC; die übrigen Formate kennt Pillow selbst

    try:
        return Image.open(io.BytesIO(inhalt))
    except Exception as ursache:
        raise OcrFehler("Dieses Bild ließ sich nicht öffnen.") from ursache


def aus_bild(inhalt: bytes, sprache: str) -> str:
    """Den Text eines Bildes erkennen."""
    if not verfuegbar():
        raise OcrFehler("Auf diesem Server ist keine Zeichenerkennung eingerichtet.")
    import pytesseract

    try:
        return pytesseract.image_to_string(_oeffne(inhalt), lang=kuerzel(sprache))
    except OcrFehler:
        raise
    except Exception as ursache:
        raise OcrFehler(f"Die Zeichenerkennung ist gescheitert: {ursache}") from ursache


# Wie fein eine PDF-Seite gerastert wird, bevor Tesseract sie liest. Das Maß
# ist der Faktor auf die 72 dpi, in denen ein PDF seine Seite beschreibt - 2,5
# sind also 180 dpi. Darunter verliert Tesseract kleine Schrift, darüber wächst
# die Rechenzeit schneller als die Trefferquote.
RASTER = 2.5

# Wie viele Seiten höchstens gelesen werden. Ein gescanntes Buch soll nicht
# zwanzig Minuten binden: Wer so viel Vorlage braucht, lädt sie als Text hoch.
MAX_SEITEN = 20


def aus_pdf(inhalt: bytes, sprache: str) -> str:
    """Ein PDF ohne Textebene seitenweise erkennen.

    Jede Seite wird gerastert und einzeln gelesen; die Seiten werden mit
    Leerzeile getrennt, weil der Schnitt danach an Absätzen arbeitet
    (`text/chunker.py`).
    """
    if not verfuegbar():
        raise OcrFehler("Auf diesem Server ist keine Zeichenerkennung eingerichtet.")
    try:
        import pypdfium2
    except ImportError as ursache:
        raise OcrFehler("Für gescannte PDFs fehlt pypdfium2.") from ursache
    import pytesseract

    lang = kuerzel(sprache)
    try:
        dokument = pypdfium2.PdfDocument(inhalt)
        seiten = [
            pytesseract.image_to_string(
                dokument[nummer].render(scale=RASTER).to_pil(), lang=lang
            )
            for nummer in range(min(len(dokument), MAX_SEITEN))
        ]
    except Exception as ursache:
        raise OcrFehler(f"Die Zeichenerkennung ist gescheitert: {ursache}") from ursache
    return "\n\n".join(seiten)
