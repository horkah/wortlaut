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
import re

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


def ist_bild(inhalt: bytes) -> bool:
    """Ob sich diese Bytes als Bild öffnen lassen.

    **Gefragt wird den Inhalt, nicht den Dateinamen.** Der Name war einmal das
    Kriterium, und daran ist der Weg aus der Zwischenablage gescheitert: Ein
    Bildschirmfoto kommt als `image.png` an, ein Foto aus der Mediathek des
    iPhones je nach Browser als `image` ohne Endung oder ganz ohne Namen. Beides
    ist dasselbe Bild, und ob es eines ist, steht in seinen ersten Bytes.
    """
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        with Image.open(io.BytesIO(inhalt)) as bild:
            bild.verify()
        return True
    except Exception:
        return False


# Wie Tesseract die Seite aufteilt, in der Reihenfolge, in der es versucht wird.
#
# `3` ist die Vorgabe und die richtige Wahl für eine Seite Fließtext: Sie
# erkennt Spalten und Absätze. Auf einem **Foto** ist sie die falsche - dort
# steht Text in verstreuten Blöcken, quer, gewölbt, verschieden groß, und die
# Seitenanalyse wirft das meiste weg. `11` ist für genau diesen Fall gedacht
# („sparse text"): kein Layout, nur finden, was nach Schrift aussieht.
#
# Nachgemessen am Foto eines Cremedeckels: `3` fand 77 Punkte, `11` fand 115.
# Auf einer gerenderten Seite Fließtext fanden beide dieselben 131 - und dort
# gewinnt `3`, weil es zuerst steht und der Gleichstand für die Vorgabe
# entschieden wird.
SEITENARTEN = (3, 11)


def _punkte(text: str) -> int:
    """Wie viel Schrift hier steht - zum Vergleich zweier Durchgänge.

    Gezählt werden die Zeichen in Wörtern aus mindestens drei Buchstaben. Das
    trennt Gefundenes von Rauschen: Was eine Zeichenerkennung erfindet, sind
    Einzelzeichen und Paare (`&®`, `fi`, `wT`), keine Wörter.
    """
    return sum(len(wort) for wort in re.findall(r"[^\W\d_]{3,}", text, re.UNICODE))


def aus_bild(inhalt: bytes, sprache: str) -> str:
    """Den Text eines Bildes erkennen - in zwei Durchgängen, der bessere gilt.

    Zweimal zu lesen kostet die doppelte Zeit, und sie ist hier gut angelegt:
    Ein Bild ist ein Bild, keine zwanzig Seiten, und ob es ein abfotografiertes
    Etikett oder eine abfotografierte Seite ist, weiß vorher niemand - auch der
    Mensch nicht, der es hochlädt (siehe `SEITENARTEN`).
    """
    if not verfuegbar():
        raise OcrFehler("Auf diesem Server ist keine Zeichenerkennung eingerichtet.")
    import pytesseract

    bild = _oeffne(inhalt)
    lang = kuerzel(sprache)
    try:
        versuche = [
            pytesseract.image_to_string(bild, lang=lang, config=f"--psm {art}")
            for art in SEITENARTEN
        ]
    except Exception as ursache:
        raise OcrFehler(f"Die Zeichenerkennung ist gescheitert: {ursache}") from ursache
    # `max` gibt bei Gleichstand den ersten zurück - und das ist die Vorgabe.
    return max(versuche, key=_punkte)


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
