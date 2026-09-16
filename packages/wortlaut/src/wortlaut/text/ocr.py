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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import sprachen

# Ein Hüllskript, das Tesseract mit einem einzigen Rechenfaden startet (siehe
# `Dockerfile`). Steht es da, werden die Durchgänge nebeneinander gerechnet;
# fehlt es, nacheinander.
#
# **Beides ist nötig, und zwar zusammen.** Vier Durchgänge auf einem Foto
# dauerten nacheinander 5,7 Sekunden. Nebeneinander, aber mit Tesseracts
# eigener Parallelität, dauerten sie **8,3** - die vier Ausführungen nahmen
# einander die Kerne weg. Nebeneinander mit je einem Faden: **1,6 Sekunden**,
# bei Zeichen für Zeichen demselben Ergebnis.
#
# Ohne das Skript wird deshalb nicht parallelisiert: Es wäre langsamer, nicht
# schneller.
EINFAEDIG = Path("/usr/local/bin/tesseract-einfaedig")

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
#
# `6` kam später dazu: „ein zusammenhängender Block Text" - die Lage bei einer
# Karte oder einem Aufsteller, auf dem ein Absatz und eine Liste stehen und
# sonst nichts. Für die Seitenanalyse von `3` ist das zu wenig Seite, für die
# verstreute Suche von `11` zu viel Zusammenhang. Gemessen an vier Vorlagen
# holt sie auf einer glänzenden Werbekarte eine Zeile mehr heraus und ändert
# an den übrigen dreien nichts.
#
# Der Preis ist ein halber Durchgang mehr je Fassung, und der kostet fast
# nichts: Die sechs laufen nebeneinander auf acht Kernen (siehe `EINFAEDIG`).
SEITENARTEN = (3, 6, 11)


# Wie groß ein Bild höchstens in die Erkennung geht - die lange Seite in Pixeln.
#
# **Mehr Pixel kaufen nichts.** Nachgemessen am Foto eines Cremedeckels, in der
# besten von vier Lesarten:
#
#     1200 px    96 Punkte     2,2 s
#     1600 px   103 Punkte     3,5 s
#     2000 px   118 Punkte     4,9 s
#     2576 px   119 Punkte     4,8 s   (die Aufnahme selbst)
#     3200 px   114 Punkte    10,4 s
#
# Oberhalb von etwa 2000 steht die Trefferquote still und fällt dann wieder,
# während die Zeit davonläuft: Tesseract rechnet intern ohnehin auf eine
# Zeilenhöhe herunter, und ein weicher, großer Buchstabe ist schlechter zu
# lesen als ein kleiner scharfer. Ein Foto vom iPhone hat 4032 Pixel; ohne
# diese Grenze dauerten vier Durchgänge 22 Sekunden statt 7, bei gleichem
# Ergebnis.
MAX_KANTE = 2400


# Wie groß die Lageprobe rechnet und wie deutlich sie sein muss.
#
# 1200 Pixel genügen, um die vier Lagen sicher zu trennen, und kosten zusammen
# gut zwei Sekunden. Der Faktor sagt, wie viel besser eine Drehung sein muss,
# damit gedreht wird: Bei einem Bild ohne Text stehen vier zufällige Zahlen
# nebeneinander, und die soll keine das Bild verdrehen lassen. Gemessen am
# Foto eines Cremedeckels lag die richtige Lage um das Vierfache vorn.
PROBE_KANTE = 1200
PROBE_VORSPRUNG = 1.5

_LAGEN = (0, 90, 180, 270)


def _zuversicht(bild, lang: str) -> float:
    """Wie sicher Tesseract ist, hier Wörter zu sehen - Zuversicht mal Wortlänge.

    **Warum hier nicht `_punkte` zählt.** Um Seitenart und Entrauschen zu
    wählen, genügt die Menge: Mehr gefundene Zeichen sind mehr gefundener Text.
    Bei der Lage versagt das. Kopfüber gestellte Schrift sieht immer noch wie
    Schrift aus - Tesseract findet dort ähnlich viele Zeichen, sie ergeben nur
    keine Wörter. Nachgemessen: nach Länge lagen aufrecht und kopfüber bei 41
    zu 42 Punkten, also Gleichstand; nach Zuversicht bei 8324 zu 2075.
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

    **Zwei Wege, und der zweite wird gebraucht.** Ein Foto trägt seine Lage
    gewöhnlich als EXIF-Marke bei sich, und `exif_transpose` richtet es danach
    auf - das kostet nichts und ist immer richtig, wenn die Marke da ist.

    Aus der **Zwischenablage** ist sie es oft nicht: Wer ein Foto in der
    Mediathek des iPhones kopiert, bekommt die Bildpunkte in der Lage des
    Sensors und die Marke bleibt unterwegs liegen. Das Bild sieht in der
    Mediathek aufrecht aus und kommt hier quer an. Erkannt wurde daraus
    „3 jgegolor-oig SWSIDYOS EUOYV" - Buchstabenformen ohne Sprache.

    Tesseracts eigene Lageerkennung (OSD) hilft hier nicht: Sie braucht eine
    Seite Text und scheitert an einem Etikett mit acht Wörtern - nachgemessen,
    sie meldete auf allen vier Lagen einen Fehler. Also wird geprobt: viermal
    klein lesen, und die Lage mit der größten Zuversicht gewinnt.

    **Auch die Probe spricht die Sprache des Profils.** Hier stand einmal ein
    festes `deu`, und das war dieselbe Hartkodierung, die aus dem übrigen
    Quelltext längst verschwunden ist: Die Zuversicht misst, ob Tesseract hier
    *Wörter* sieht - und was ein Wort ist, hängt an der Sprache. Mit dem
    falschen Wörterbuch wären alle vier Lagen gleich unsicher, und die Probe
    entschiede nach Zufall.
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
        # Kein deutlicher Vorsprung: stehen lassen. Ein Bild ohne Text liefert
        # vier zufällige Zahlen, und die sollen es nicht verdrehen.
        return bild
    return bild.rotate(-beste, expand=True)


def _vorbereitet(bild):
    """Auf ein vernünftiges Maß bringen - und eine entrauschte Fassung daneben.

    **Der Medianfilter ist nicht Kosmetik, sondern der Unterschied zwischen
    lesbar und gar nichts.** Wer einen Bildschirm abfotografiert, bekommt das
    Gitter der Bildpunkte als feines Muster ins Bild (Moiré), und Tesseract
    liest darin Schrift, wo keine ist - oder gar nichts mehr. Nachgemessen an
    einem nachgestellten Bildschirmfoto: **0 Punkte** im Rohbild, **131** nach
    einem 3×3-Median. Auf dem gewöhnlichen Foto schadet er nicht, er half dort
    sogar leicht (115 → 119).

    Zurück kommen beide Fassungen, denn welche gewinnt, entscheidet erst der
    Vergleich: Ein Filter, der einem scharfen Bild kleine Schrift weichzeichnet,
    soll sich nicht durchsetzen, nur weil er angewandt wurde.
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

    **Vorsichtig, nicht gründlich.** Eine Zeichenerkennung findet auf einem Foto
    auch dort Schrift, wo Muster sind - der Wirbel auf einem Cremedeckel wird zu
    `| x`, `Ye`, `v,`, `ae`. Solche Zeilen bestehen aus Ein- und
    Zweizeichen-Brocken; alles, was ein Mensch geschrieben hat, enthält
    irgendwo drei Zeichen am Stück.

    Die Grenze liegt deshalb bei drei und nicht höher, und sie zählt Ziffern
    mit: `48h` wäre sonst weg, und `10/2024` auch.

    **Und mindestens die Hälfte der Brocken muss ein Wort sein.** Ein einzelnes
    genügte anfangs, und damit blieb `k Be #2 I CFrAN` stehen - eine Zeile aus
    fünf Bruchstücken, von denen eines zufällig fünf Zeichen lang war. Die
    Mehrheitsregel nimmt sie und lässt alles stehen, was wirklich dasteht:
    `Bio-Jojobaöl &` hat zwei Brocken und ein Wort, `ZERTIFIZIERT || VEGAN`
    drei und zwei, `48h` einen und einen.

    Das ist die richtige Richtung: Was hier stehen bleibt, streicht ein Mensch
    im nächsten Schritt weg - was hier verschwindet, sieht er nie wieder.
    Gegen Zeilen, die durchweg wie Wörter aussehen und trotzdem keine sind -
    ein Unterstrich unter einer Überschrift -, hilft das nicht; dagegen steht
    `MINDESTZUVERSICHT`.

    Angewandt wird das **nur auf Erkanntes**. Ein gelesener Text steht so da,
    wie ihn jemand geschrieben hat, und daran wird nicht gefiltert.
    """
    behalten = [z.rstrip() for z in text.splitlines() if not z.strip() or _traegt_text(z)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(behalten)).strip()


def _traegt_text(zeile: str) -> bool:
    """Ob in dieser Zeile mehrheitlich Wörter stehen und nicht Bruchstücke."""
    brocken = zeile.split()
    worthaft = sum(1 for brocken_stueck in brocken if _WORTHAFT.search(brocken_stueck))
    return worthaft * 2 >= len(brocken)


# Wie sicher Tesseract bei einer Zeile mindestens sein muss, damit sie bleibt.
#
# **Wogegen das hilft.** Ein Unterstrich unter einer Überschrift ist ein
# Balken, kein Buchstabe - aber Tesseract muss etwas zurückgeben und liest ihn
# als Wort. So entstand unter „Birchermüsli zum Frühstück?" die Zeile
# „a nee heneibneeneschebeißsi": lang genug für den Längenfilter, Unsinn für
# jeden Menschen. Was fehlt, ist nicht die Länge, sondern die Sicherheit - und
# die sagt Tesseract selbst, wenn man sie erfragt.
#
# **Warum 15 und nicht mehr.** Gemessen an zwei Vorlagen:
#
#     Plakat, sauber      Rauschzeile  6,5  ·  echter Text ab 75
#     Cremedeckel, schwer              ---  ·  echter Text ab 28
#
# Die Grenze muss unter das schwächste Echte und über das stärkste Rauschen.
# 15 liegt in dieser Lücke, mit Abstand nach beiden Seiten: Auf dem schweren
# Foto wäre `OKO-TEST` (28) und `BIO-JOJOBAÖL` (40) sonst mit weggefallen, und
# das sind Wörter, die wirklich dastehen.
MINDESTZUVERSICHT = 15.0

# Dieselbe Frage noch einmal, für **kurze** Zeilen - und dort viel strenger.
#
# **Warum zwei Grenzen.** Ein Foto einer Stofffläche oder einer genarbten
# Kunststoffschale liefert Dreibuchstabenwörter am laufenden Band: `Res`,
# `RER`, `ber`, `Ser`, `ale`, `STE`. Sie sind lang genug für den Längenfilter
# und sicher genug für die Grenze oben - gemessen an einem Akku auf einer
# Hose kamen sie auf bis zu 43.
#
# Anheben ließ sich die eine Grenze aber nicht: `OKO-TEST` steht wirklich auf
# dem Cremedeckel und kommt dort auf 28, `BIO-JOJOBAÖL` auf 40.
#
# Was beide trennt, ist nicht die Sicherheit allein, sondern sie **zusammen
# mit der Länge**. Ein Klassifikator, der acht Formen hintereinander zu einem
# Wort zusammensetzt, hat etwas gesehen, auch wenn er zögert; drei zufällig
# passende Formen findet man in jeder Struktur. Gemessen an vier Vorlagen:
#
#     kurz (bis 5 Zeichen)   Rauschen bis 43   ·   echt ab 74
#     lang (ab 6 Zeichen)    Rauschen bis  6   ·   echt ab  2
#
# Die 60 liegen in der Lücke der oberen Zeile. Echt und kurz waren `BOSCH`
# (96), `ERT` (90) und `sehr gut 5` (74) - alle drei bleiben.
MINDESTZUVERSICHT_KURZ = 60.0

# Bis hierhin gilt eine Zeile als kurz - gemessen am längsten Wort darin, nicht
# an der ganzen Zeile: `sehr gut 5` ist kurz, `OKO-TEST` ist lang.
KURZE_ZEILE = 5


def _gelesen(bild, lang: str, seitenart: int) -> str:
    """Eine Fassung lesen - zeilenweise, und nur was sicher genug ist.

    Gelesen wird über `image_to_data` statt `image_to_string`, weil nur das die
    Zuversicht je Wort mitliefert. Es ist derselbe Durchgang, nur eine andere
    Ausgabe; teurer wird es nicht.

    Zusammengesetzt wird entlang der Struktur, die Tesseract selbst meldet:
    Wörter zu Zeilen, Absätze durch Leerzeilen getrennt - denn genau daran
    schneidet `text/chunker.py` später die Sprecheinheiten.
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
    # `max` gibt bei Gleichstand den ersten zurück - und das ist das Rohbild in
    # der Vorgabe-Seitenart, also der zurückhaltendste der vier Wege.
    return entrausche(max(versuche, key=_punkte))


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

    **Hier wird einmal gelesen und nicht viermal, anders als bei einem Bild.**
    Das ist das Maß, das zum Format gehört: Ein Scan ist eine Seite Fließtext,
    flach ausgeleuchtet und hoch im Kontrast - genau der Fall, für den
    Tesseracts Vorgabe gemacht ist, und einer ohne Moiré. Ein Bild ist eines;
    ein PDF sind bis zu zwanzig, und vier Durchgänge je Seite wären achtzig.
    Wessen Scan schlecht liest, fotografiert die Seite - dann greift der andere
    Weg mit allem, was er hat.
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
        # Auch die Seiten eines PDFs nebeneinander - hier zahlt es sich am
        # meisten aus, denn es sind bis zu zwanzig.
        bilder = [
            dokument[nummer].render(scale=RASTER).to_pil()
            for nummer in range(min(len(dokument), MAX_SEITEN))
        ]
        seiten = _alle([lambda b=b: _gelesen(b, lang, SEITENARTEN[0]) for b in bilder])
    except Exception as ursache:
        raise OcrFehler(f"Die Zeichenerkennung ist gescheitert: {ursache}") from ursache
    return entrausche("\n\n".join(seiten))
