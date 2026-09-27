"""Bilder und eingescannte PDFs → Text, auf diesem Rechner.

Eine Vorlage darf ein Foto sein - der Weg ohne Tastatur (Grundentscheidung 7).
Was hier herauskommt, wird angezeigt und berichtigt, bevor es Vorlage wird
(`api/sources.py`): Ein Erkennungsfehler wanderte sonst über die Aufnahme ins
Training.

Tesseract statt eines Dienstes, weil nichts die Maschine verlässt - ein
fotografierter Brief ist womöglich das Persönlichste, was die App sieht
(`docs/datenschutz.md`). Fehlt Tesseract, fehlt nur dieser Weg, und die App
sagt es.
"""

from __future__ import annotations

import functools
import io
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import sprachen

# Ein Hüllskript, das Tesseract mit einem Rechenfaden startet (`Dockerfile`).
# Nur damit laufen die Durchgänge nebeneinander: Vier dauerten nacheinander
# 5,7 s, nebeneinander mit Tesseracts eigener Parallelität 8,3 s, nebeneinander
# mit je einem Faden 1,6 s - bei gleichem Ergebnis.
EINFAEDIG = Path("/usr/local/bin/tesseract-einfaedig")

# `heic`, weil iPhones so fotografieren und Safari nicht immer umwandelt.
UNTERSTUETZT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif")

# Tesseract nennt Sprachen nach ISO 639-2. Unbekanntes bekommt `eng`, die
# einzige überall mitgelieferte Sprache.
_KUERZEL = {"de": "deu", "en": "eng"}
_RUECKFALL = "eng"


class OcrFehler(RuntimeError):
    """Erkennen ist nicht möglich oder fehlgeschlagen."""


def kuerzel(sprache: str) -> str:
    """`de` → `deu`. Unbekanntes bekommt Tesseracts Vorgabe."""
    return _KUERZEL.get(sprachen.normiere(sprache), _RUECKFALL)


@functools.cache
def _nebeneinander() -> bool:
    """Ob mehrere Durchgänge zugleich gerechnet werden dürfen.

    Nur mit dem Hüllskript: Sonst ist nebeneinander langsamer als nacheinander
    (siehe `EINFAEDIG`). Wo es steht, wird es auch als Tesseract eingesetzt.
    """
    if not EINFAEDIG.is_file():
        return False
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = str(EINFAEDIG)
    return True


def _alle(arbeiten: list) -> list:
    """Eine Liste von Aufrufen abarbeiten - zugleich, wo es sich lohnt."""
    if not _nebeneinander() or len(arbeiten) < 2:
        return [tun() for tun in arbeiten]
    with ThreadPoolExecutor(max_workers=len(arbeiten)) as gespann:
        return list(gespann.map(lambda tun: tun(), arbeiten))


@functools.cache
def verfuegbar() -> bool:
    """Ob auf diesem Rechner erkannt werden kann.

    Gemerkt, weil sich die Antwort zur Laufzeit nicht ändert.
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
    """Ob sich diese Bytes als Bild öffnen lassen - am Inhalt, nicht am Namen:
    Aus der Zwischenablage kommt ein Bild oft als `image` ohne Endung."""
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


# Wie Tesseract die Seite aufteilt, in dieser Reihenfolge versucht:
#
#   3   die Vorgabe, für eine Seite Fließtext mit Spalten und Absätzen
#   6   ein zusammenhängender Block - eine Karte, ein Aufsteller
#   11  verstreuter Text ohne Layout - das typische Foto
#
# Am Foto eines Cremedeckels fand `3` 77 Punkte, `11` 115; auf einer Seite
# Fließtext beide 131, und bei Gleichstand gewinnt die Vorgabe. `6` holt auf
# einer glänzenden Werbekarte eine Zeile mehr. Nebeneinander kostet das kaum
# Zeit (`EINFAEDIG`).
SEITENARTEN = (3, 6, 11)


# Die längste Seite, mit der ein Bild in die Erkennung geht. Mehr Pixel lesen
# nicht besser, nur langsamer (Cremedeckel: 1200 px 96 Punkte, 2000 px 118,
# 2576 px 119, 3200 px 114 bei doppelter Zeit) - ein weicher großer Buchstabe
# liest sich schlechter als ein kleiner scharfer.
MAX_KANTE = 2400


# Die Lageprobe: 1200 px trennen die vier Lagen sicher. Gedreht wird nur mit
# deutlichem Vorsprung - bei einem Bild ohne Text stehen vier Zufallszahlen
# nebeneinander. Am Cremedeckel lag die richtige Lage vierfach vorn.
PROBE_KANTE = 1200
PROBE_VORSPRUNG = 1.5

_LAGEN = (0, 90, 180, 270)


def _zuversicht(bild, lang: str) -> float:
    """Wie sicher Tesseract ist, hier Wörter zu sehen - Zuversicht mal Wortlänge.

    Nicht `_punkte`: Kopfüber findet Tesseract ähnlich viele Zeichen, nur
    keine Wörter - nach Länge 41 zu 42, nach Zuversicht 8324 zu 2075.
    """
    import pytesseract
    from pytesseract import Output

    daten = pytesseract.image_to_data(
        bild, lang=lang, config="--psm 11", output_type=Output.DICT
    )
    summe = 0.0
    for wort, konfidenz in zip(daten["text"], daten["conf"], strict=False):
        if len(wort.strip()) >= 3 and float(konfidenz) > 0:
            summe += float(konfidenz) * len(wort.strip())
    return summe


def _aufgerichtet(bild, lang: str):
    """Das Bild so drehen, dass die Schrift oben ist.

    Zuerst nach der EXIF-Marke. Aus der Zwischenablage fehlt sie oft - ein
    kopiertes iPhone-Foto kommt in der Lage des Sensors an. Tesseracts eigene
    Lageerkennung braucht eine Seite Text und scheitert an einem Etikett.
    Also wird geprobt: viermal klein lesen, die größte Zuversicht gewinnt -
    mit dem Wörterbuch des Profils, denn was ein Wort ist, hängt an der
    Sprache.
    """
    from PIL import Image, ImageOps

    bild = ImageOps.exif_transpose(bild) or bild

    klein = bild.copy()
    klein.thumbnail((PROBE_KANTE, PROBE_KANTE), Image.LANCZOS)
    gedrehte = [klein.rotate(-lage, expand=True) for lage in _LAGEN]
    gemessen = _alle([lambda g=g: _zuversicht(g, lang) for g in gedrehte])
    werte = dict(zip(_LAGEN, gemessen, strict=True))

    beste = max(_LAGEN, key=lambda lage: werte[lage])
    if beste == 0 or werte[beste] < werte[0] * PROBE_VORSPRUNG:
        # Kein deutlicher Vorsprung: stehen lassen.
        return bild
    return bild.rotate(-beste, expand=True)


def _vorbereitet(bild):
    """Auf ein vernünftiges Maß bringen - und eine entrauschte Fassung daneben.

    Der 3×3-Median entfernt das Moiré abfotografierter Bildschirme: 0 Punkte
    im Rohbild, 131 danach; auf gewöhnlichen Fotos schadet er nicht. Welche
    Fassung gilt, entscheidet der Vergleich.
    """
    from PIL import Image, ImageFilter

    if max(bild.size) > MAX_KANTE:
        faktor = MAX_KANTE / max(bild.size)
        bild = bild.resize(
            (round(bild.width * faktor), round(bild.height * faktor)), Image.LANCZOS
        )
    return (bild, bild.filter(ImageFilter.MedianFilter(3)))


# Was als Wort durchgeht: drei Zeichen am Stück, Buchstaben oder Ziffern.
# Absichtlich großzügig - `48h` und `10/2024` sollen bleiben.
_WORTHAFT = re.compile(r"[^\W_]{3,}", re.UNICODE)


def entrausche(text: str) -> str:
    """Zeilen wegnehmen, in denen kein einziges Wort steht.

    Muster auf einem Foto werden zu Brocken wie `| x`, `Ye`, `v,`. Eine Zeile
    bleibt, wenn mindestens die Hälfte ihrer Brocken drei Zeichen am Stück
    hat - Ziffern zählen mit, damit `48h` bleibt. `k Be #2 I CFrAN` fällt,
    `Bio-Jojobaöl &` bleibt. Vorsichtig, denn was stehen bleibt, streicht ein
    Mensch; was verschwindet, sieht er nie. Nur für Erkanntes.
    """
    behalten = [z.rstrip() for z in text.splitlines() if not z.strip() or _traegt_text(z)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(behalten)).strip()


def _traegt_text(zeile: str) -> bool:
    """Ob in dieser Zeile mehrheitlich Wörter stehen und nicht Bruchstücke."""
    brocken = zeile.split()
    worthaft = sum(1 for brocken_stueck in brocken if _WORTHAFT.search(brocken_stueck))
    return worthaft * 2 >= len(brocken)


# Die mittlere Zuversicht, die eine Zeile mindestens braucht. Gegen Zeilen,
# die wie Wörter aussehen und keine sind - ein Unterstrich, gelesen als
# „a nee heneibneeneschebeißsi" (6,5). Echter Text lag ab 28 (`OKO-TEST` auf
# einem schweren Foto), auf einem sauberen Plakat ab 75.
MINDESTZUVERSICHT = 15.0

# Strenger für kurze Zeilen: Stoff oder genarbter Kunststoff liefern
# Dreibuchstabenwörter (`Res`, `RER`, `Ser`) mit Zuversicht bis 43. Drei
# passende Formen findet man in jeder Struktur, acht hintereinander nicht:
#
#     kurz (bis 5 Zeichen)   Rauschen bis 43   ·   echt ab 74
#     lang (ab 6 Zeichen)    Rauschen bis  6   ·   echt ab  2
MINDESTZUVERSICHT_KURZ = 60.0

# Bis hierhin gilt eine Zeile als kurz - gemessen am längsten Wort darin, nicht
# an der ganzen Zeile: `sehr gut 5` ist kurz, `OKO-TEST` ist lang.
KURZE_ZEILE = 5


def _gelesen(bild, lang: str, seitenart: int) -> str:
    """Eine Fassung lesen - zeilenweise, und nur was sicher genug ist.

    `image_to_data` liefert die Zuversicht je Wort. Wörter werden zu Zeilen,
    Absätze durch Leerzeilen getrennt - daran schneidet `text/chunker.py`.
    """
    import pytesseract
    from pytesseract import Output

    daten = pytesseract.image_to_data(
        bild, lang=lang, config=f"--psm {seitenart}", output_type=Output.DICT
    )

    zeilen: dict[tuple[int, int, int], list[tuple[str, float]]] = {}
    for stelle, wort in enumerate(daten["text"]):
        geputzt = wort.strip()
        if not geputzt:
            continue
        konfidenz = float(daten["conf"][stelle])
        if konfidenz < 0:  # -1 steht für „kein Wort", nicht für „unsicher"
            continue
        schluessel = (
            daten["block_num"][stelle],
            daten["par_num"][stelle],
            daten["line_num"][stelle],
        )
        zeilen.setdefault(schluessel, []).append((geputzt, konfidenz))

    ausgabe: list[str] = []
    vorheriger_absatz: tuple[int, int] | None = None
    for (block, absatz, _), woerter in zeilen.items():
        mittel = sum(k for _, k in woerter) / len(woerter)
        laengstes = max(len(wort) for wort, _ in woerter)
        grenze = MINDESTZUVERSICHT_KURZ if laengstes <= KURZE_ZEILE else MINDESTZUVERSICHT
        if mittel < grenze:
            continue
        if vorheriger_absatz is not None and (block, absatz) != vorheriger_absatz:
            ausgabe.append("")
        ausgabe.append(" ".join(wort for wort, _ in woerter))
        vorheriger_absatz = (block, absatz)
    return "\n".join(ausgabe)


def _punkte(text: str) -> int:
    """Wie viel Schrift hier steht - zum Vergleich zweier Durchgänge.

    Die Zeichen in Wörtern ab drei Buchstaben - Erfundenes sind Einzelzeichen
    und Paare.
    """
    return sum(len(wort) for wort in re.findall(r"[^\W\d_]{3,}", text, re.UNICODE))


def aus_bild(inhalt: bytes, sprache: str) -> str:
    """Den Text eines Bildes erkennen: zwei Fassungen mal drei Seitenarten,
    der Durchgang mit den meisten `_punkte` gilt."""
    if not verfuegbar():
        raise OcrFehler("Auf diesem Server ist keine Zeichenerkennung eingerichtet.")

    lang = kuerzel(sprache)
    try:
        versuche = _alle(
            [
                lambda f=fassung, a=art: _gelesen(f, lang, a)
                for fassung in _vorbereitet(_aufgerichtet(_oeffne(inhalt), lang))
                for art in SEITENARTEN
            ]
        )
    except OcrFehler:
        raise
    except Exception as ursache:
        raise OcrFehler(f"Die Zeichenerkennung ist gescheitert: {ursache}") from ursache
    # Bei Gleichstand der erste: das Rohbild in der Vorgabe-Seitenart.
    return entrausche(max(versuche, key=_punkte))


# Rasterfaktor auf 72 dpi, also 180 dpi - darunter geht kleine Schrift
# verloren, darüber wächst nur die Rechenzeit.
RASTER = 2.5

# Wer mehr braucht, lädt Text hoch.
MAX_SEITEN = 20


def aus_pdf(inhalt: bytes, sprache: str) -> str:
    """Ein PDF ohne Textebene seitenweise erkennen.

    Einmal je Seite in der Vorgabe-Seitenart: Ein Scan ist flach
    ausgeleuchteter Fließtext ohne Moiré. Wer schlecht liest, fotografiert die
    Seite.
    """
    if not verfuegbar():
        raise OcrFehler("Auf diesem Server ist keine Zeichenerkennung eingerichtet.")
    try:
        import pypdfium2
    except ImportError as ursache:
        raise OcrFehler("Für gescannte PDFs fehlt pypdfium2.") from ursache

    lang = kuerzel(sprache)
    try:
        dokument = pypdfium2.PdfDocument(inhalt)
        # Die Seiten nebeneinander.
        bilder = [
            dokument[nummer].render(scale=RASTER).to_pil()
            for nummer in range(min(len(dokument), MAX_SEITEN))
        ]
        seiten = _alle([lambda b=b: _gelesen(b, lang, SEITENARTEN[0]) for b in bilder])
    except Exception as ursache:
        raise OcrFehler(f"Die Zeichenerkennung ist gescheitert: {ursache}") from ursache
    return entrausche("\n\n".join(seiten))
