"""Paare aus Aufnahme und Vorlage in Stücke von 25-30 Sekunden teilen, bevorzugt an Satzenden.

    docker run --rm --gpus all --user "$(id -u):$(id -g)" -e HOME=/tmp \\
      -v "$PWD/data:/daten" -v "$PWD/scripts:/skripte:ro" \\
      -v "$WORTLAUT_TRAININGSABLAGE/modelle:/modelle:ro" \\
      --entrypoint python wortlaut-wortlaut /skripte/paare_teilen.py \\
      "/daten/FEMKE input m4a txt" "/daten/FEMKE split wav txt" \\
      /modelle/<sprecher_id>

Eingang ist ein Verzeichnisbaum mit Paaren `<name>.m4a` + `<name>.txt`: eine
vorgelesene Seite und ihr Text. Für Whisper ist eine solche Seite zu lang -
es hört in Fenstern von 30 Sekunden. Dieses Skript schneidet jedes Paar in
Stücke, die hineinpassen, und legt sie in einem parallelen Baum ab:

    <name>_1.wav          das Audio des Stücks, in Abtastrate und Kanälen der Aufnahme
    <name>_1.txt          der Teil der Vorlage, der dazu gehört
    <name>_1.recogn.txt   was das Modell im Stück allein erkennt - die Gegenprobe

Neben der Aufnahme im Eingangsbaum entstehen:

    <name>.recogn.txt     die Erkennung der ganzen Aufnahme, Stück für Stück gehört
    <name>.recogn.tsv     dieselbe Wort für Wort mit Anfang, Ende und Wahrscheinlichkeit

Paare, deren Text die Erkennung zu weniger als einem Viertel deckt, gehören
nicht zusammen und werden ausgelassen (`--mindeckung`).

**Erst der Text, dann die Zeit, dann der Schnitt.**

1. *Erkennen.* Das Modell hört die ganze Aufnahme und nennt zu jedem Wort,
   wann es fällt. Lücken, in denen gesprochen wird, hört es einzeln nach.
2. *Grob zuordnen.* Die Erkennung wird Buchstabe für Buchstabe gegen die
   Vorlage ausgerichtet; Läufe von mindestens drei gleichen Buchstaben sind
   Anker, die einer Stelle der Vorlage eine Zeit geben. Zwischen den Ankern
   verteilt sich die Zeit nach Silben - diese Sprecherin liest Wort für Wort,
   also bekommt jedes Wort dazu einen festen Anteil für die Pause danach.
3. *Fein zuordnen.* Zwischen je zwei sicher erkannten Wörtern wird der
   **Text der Vorlage** gegen das Audio gelegt (Forced Alignment über die
   Aufmerksamkeit des Modells, wie faster-whisper es für Wortzeiten tut). Das
   Modell muss dazu nichts erkennen, nur zeigen, wo der bekannte Text liegt.
4. *Stücke wählen.* Jede Wortgrenze der Vorlage ist ein möglicher Schnitt;
   geschnitten wird in der Mitte der längsten Stille zwischen den beiden
   Wörtern. Die Wahl über alle Grenzen zugleich hält jedes Stück unter
   29,5 Sekunden, möglichst nah an 27,5, und zieht Satzenden den Kommas und
   diese jeder anderen Wortgrenze vor; eine lange Pause zählt zusätzlich.
5. *Nachhören.* Jedes Stück wird allein erkannt - kürzer als 30 s und in
   Stille geschnitten, hört Whisper es vollständiger als am Stück. Mit dieser
   Erkennung beginnt es wieder bei 2, bis die Schnitte stehen, höchstens
   dreimal.
6. *Gegenprobe.* Wie viele Wörter der Nachbarstücke in der Erkennung eines
   Stücks zu hören sind, steht in `_bericht.tsv` im Zielbaum - neben Länge,
   Art der Grenze und Fehlerrate.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from wortlaut import metriken, rechenwerk

RATE = 16_000
# Stille: Frames von 10 ms, Schwelle bei 30 % zwischen Grundrauschen
# (10. Perzentil) und Sprachpegel (95. Perzentil).
FRAME = RATE // 100
SCHWELLE_ANTEIL = 0.3
STILLE_MIN_S = 0.1
# So weit darf die Stille, in der geschnitten wird, über die Lücke zwischen
# den beiden Wörtern hinausreichen, die das Alignment nennt.
SPIELRAUM_S = 0.25
LUECKENVORSPRUNG_S = 0.3
RAND_S = 0.3

LAENGSTE_S, IDEAL_S = 29.5, 27.5
# Abweichung von 27,5 s: nach unten weich, nach oben steil bis zur Grenze.
STREUUNG_KURZ_S, STREUUNG_LANG_S = 4.0, 1.5
# Was eine Grenze kostet, gemessen an der Längenabweichung (4 s zu kurz = 1).
KOSTEN_TEILSATZ, KOSTEN_WORT = 1.5, 5.0
PAUSENGEWICHT, PAUSE_ZAEHLT_BIS_S = 1.0, 1.0
# Eine Stelle wegzulassen kostet so viel wie viele schlecht gewählte Grenzen.
VERWURF_KOSTEN, VERWURF_WOERTER = 100.0, 12

FENSTER_S = 20.0
MIN_DECKUNG = 0.25
MODELL_ZEILE = "# modell: "
LUECKE_S, LUECKE_LAUT_S = 4.0, 1.0
DAUER_MIN_S = 0.02
RUNDEN = 3

SATZENDE = ".!?…"
TEILSATZ = ",;:–"
ZIERAT = "\"'»«„“”‚‘’)]"
# Gegenprobe: so viele Wörter der Nachbarstücke stehen zum Abgleich daneben.
NACHBARN = 6


def normal(wort: str) -> str:
    return re.sub(r"[\W_]", "", wort.lower())


def silben(wort: str) -> int:
    return max(1, len(re.findall(r"[aeiouyäöü]+", wort.lower())))


def endet_mit(wort: str, zeichen: str) -> bool:
    kern = wort.rstrip(ZIERAT)
    return bool(kern) and kern[-1] in zeichen


# ── Audio ───────────────────────────────────────────────────────────────────


def abtastung(pfad: Path) -> tuple[int, int]:
    """Abtastrate und Kanäle der Aufnahme - so werden die Stücke geschrieben."""
    aus = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=sample_rate,channels", "-of", "json", str(pfad)],
        capture_output=True, check=True, text=True,
    ).stdout
    strom = json.loads(aus)["streams"][0]
    return int(strom["sample_rate"]), int(strom["channels"])


def dekodiere(pfad: Path, rate: int, kanaele: int) -> np.ndarray:
    roh = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(pfad), "-ac", str(kanaele), "-ar", str(rate),
         "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(roh, np.int16).reshape(-1, kanaele)


def schreibe_wav(pfad: Path, proben: np.ndarray, rate: int) -> None:
    with wave.open(str(pfad), "wb") as datei:
        datei.setnchannels(proben.shape[1])
        datei.setsampwidth(2)
        datei.setframerate(rate)
        datei.writeframes(np.ascontiguousarray(proben).tobytes())


@dataclass(frozen=True)
class Stille:
    anfang: float
    ende: float

    @property
    def dauer(self) -> float:
        return self.ende - self.anfang

    @property
    def mitte(self) -> float:
        return (self.anfang + self.ende) / 2


def pegel(proben: np.ndarray) -> np.ndarray:
    frames = proben[: len(proben) // FRAME * FRAME].reshape(-1, FRAME)
    return 20 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-9)


def schwelle(db: np.ndarray) -> float:
    boden, sprache = np.percentile(db, 10), np.percentile(db, 95)
    return float(boden + SCHWELLE_ANTEIL * (sprache - boden))


def stillen(db: np.ndarray) -> list[Stille]:
    still = db < schwelle(db)
    gefunden, anfang = [], None
    for nummer, ist_still in enumerate([*still, False]):
        if ist_still and anfang is None:
            anfang = nummer
        elif not ist_still and anfang is not None:
            if (nummer - anfang) * FRAME >= STILLE_MIN_S * RATE:
                gefunden.append(Stille(anfang * FRAME / RATE, nummer * FRAME / RATE))
            anfang = None
    return gefunden


@dataclass
class Lage:
    anfang: float
    kern_ende: float
    ende: float
    wahrscheinlichkeit: float


def schnittstelle(links: Lage, rechts: Lage, alle: list[Stille], db: np.ndarray) -> tuple[float, float]:
    """Wo zwischen zwei Wörtern geschnitten wird, und wie lang die Stille dort ist.

    Gesucht wird zwischen den Mitten der beiden Wörter: Das Alignment schlägt
    eine Pause gern einem der Nachbarn zu. Die längste Stille dort gewinnt,
    eine an der Lücke, die das Alignment nennt, mit Vorsprung; geschnitten
    wird in ihrer Mitte. Gibt es keine, an der leisesten Stelle der Lücke.
    """
    von = (links.anfang + links.kern_ende) / 2
    bis = max(von, (rechts.anfang + rechts.kern_ende) / 2)
    luecke_von, luecke_bis = min(links.kern_ende, rechts.anfang), max(links.kern_ende, rechts.anfang)

    def wert(s: Stille) -> float:
        dauer = min(s.ende, bis) - max(s.anfang, von)
        an_der_luecke = s.ende > luecke_von - SPIELRAUM_S and s.anfang < luecke_bis + SPIELRAUM_S
        return dauer + (LUECKENVORSPRUNG_S if an_der_luecke else 0.0)

    kandidaten = [s for s in alle if s.ende > von and s.anfang < bis]
    if kandidaten:
        beste = max(kandidaten, key=wert)
        return float(np.clip(beste.mitte, von, bis)), beste.dauer
    a, b = int(luecke_von * 100), max(int(luecke_bis * 100), int(luecke_von * 100) + 1)
    ausschnitt = db[a:b]
    if not len(ausschnitt):
        return (von + bis) / 2, 0.0
    return (a + int(np.argmin(ausschnitt)) + 0.5) / 100, 0.0


# ── Erkennung ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Wort:
    anfang: float
    ende: float
    wahrscheinlichkeit: float
    text: str


def erkenne(modell, audio: np.ndarray, sprache: str) -> tuple[str, list[Wort]]:
    abschnitte, _info = modell.transcribe(audio, language=sprache, word_timestamps=True)
    texte, woerter = [], []
    for abschnitt in abschnitte:
        texte.append(abschnitt.text.strip())
        woerter.extend(Wort(w.start, w.end, w.probability, w.word.strip()) for w in abschnitt.words or [])
    return " ".join(t for t in texte if t), woerter


def nachhoeren(modell, audio: np.ndarray, sprache: str, woerter: list[Wort], db: np.ndarray) -> list[Wort]:
    """Lücken der Erkennung, in denen gesprochen wird, einzeln nachhören.

    Über eine lange Aufnahme springt Whisper gelegentlich ganze Sätze weit -
    bei dieser langsamen Sprecherin eher, als bei anderen. Was dort fehlt,
    fehlt der Zuordnung als Anker. Jede Lücke von mindestens 4 s mit
    mindestens 1 s über der Stille-Schwelle wird für sich erkannt.
    """
    laut = db >= schwelle(db)
    dauer = len(audio) / RATE
    for _runde in range(3):
        grenzen = [0.0, *(x for w in woerter for x in (w.anfang, w.ende)), dauer]
        neu = []
        for von, bis in zip(grenzen[::2], grenzen[1::2]):
            if bis - von < LUECKE_S or laut[int(von * 100) : int(bis * 100)].sum() / 100 < LUECKE_LAUT_S:
                continue
            _text, gehoert = erkenne(modell, audio[int(von * RATE) : int(bis * RATE)], sprache)
            neu += [
                Wort(w.anfang + von, w.ende + von, w.wahrscheinlichkeit, w.text)
                for w in gehoert
                if von <= von + (w.anfang + w.ende) / 2 <= bis
            ]
        if not neu:
            break
        woerter = sorted([*woerter, *neu], key=lambda w: w.anfang)
    return woerter


def lies_erkennung(tsv: Path, modellname: str) -> list[Wort] | None:
    """Die Erkennung eines früheren Laufs, wenn sie vom selben Modell stammt."""
    if not tsv.is_file():
        return None
    zeilen = tsv.read_text(encoding="utf-8").splitlines()
    if not zeilen or zeilen[0] != MODELL_ZEILE + modellname:
        return None
    woerter = []
    for zeile in zeilen[2:]:
        anfang, ende, wahrscheinlichkeit, text = zeile.split("\t", 3)
        woerter.append(Wort(float(anfang), float(ende), float(wahrscheinlichkeit), text))
    return woerter


def schreibe_erkennung(tsv: Path, modellname: str, woerter: list[Wort]) -> None:
    zeilen = [MODELL_ZEILE + modellname, "anfang_s\tende_s\twahrscheinlichkeit\twort"]
    zeilen += [f"{w.anfang:.2f}\t{w.ende:.2f}\t{w.wahrscheinlichkeit:.3f}\t{w.text}" for w in woerter]
    tsv.write_text("\n".join(zeilen) + "\n", encoding="utf-8")


# Was Whisper in Pausen gern erfindet - Abspann von Untertiteln, der Gruß am
# Ende eines Videos. Es steht in keiner Vorlage; für die Ausrichtung fällt es
# weg, die `.recogn.txt` behält es.
ERFUNDEN = re.compile(
    r"untertitel\w*( im auftrag des \w+)?( für funk)?[ ,]*\d*"
    r"|swiss txt( ag)?[ ,]*\d*"
    r"|(vielen )?dank für'?s? (zuschauen|zuhören)|das war'?s für heute|bis zum nächsten mal|tschüss",
    re.IGNORECASE,
)


def ohne_erfundenes(woerter: list[Wort]) -> list[Wort]:
    """Die Erkennung ohne erfundene Floskeln und ohne Wörter, die keine Zeit
    dauern - an denen erkennt man Whispers Schleifen."""
    woerter = [w for w in woerter if w.ende - w.anfang >= DAUER_MIN_S]
    text, stellen = "", []
    for wort in woerter:
        stellen.append(len(text) + (1 if text else 0))
        text = f"{text} {wort.text}" if text else wort.text
    weg = set()
    for treffer in ERFUNDEN.finditer(text):
        weg |= {n for n, s in enumerate(stellen) if treffer.start() <= s < treffer.end()}
    return [w for n, w in enumerate(woerter) if n not in weg]


# ── Ausrichtung ─────────────────────────────────────────────────────────────


def richte_aus(erkannt: str, vorlage: str) -> list[tuple[int | None, int | None]]:
    """Levenshtein über Buchstaben; der Pfad als Paare (Stelle erkannt, Stelle Vorlage)."""
    n, m = len(erkannt), len(vorlage)
    b = np.frombuffer(vorlage.encode("utf-32-le"), np.uint32)
    stufen = np.arange(m + 1, dtype=np.int32)
    kosten = np.empty((n + 1, m + 1), dtype=np.int32)
    kosten[0] = stufen
    for i in range(1, n + 1):
        ungleich = (b != ord(erkannt[i - 1])).astype(np.int32)
        kandidat = np.empty(m + 1, dtype=np.int32)
        kandidat[0] = i
        kandidat[1:] = np.minimum(kosten[i - 1, :-1] + ungleich, kosten[i - 1, 1:] + 1)
        # Einfügen hängt am linken Nachbarn derselben Zeile: laufendes Minimum.
        kosten[i] = np.minimum.accumulate(kandidat - stufen) + stufen
    pfad, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and kosten[i, j] == kosten[i - 1, j - 1] + (erkannt[i - 1] != vorlage[j - 1]):
            pfad.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and kosten[i, j] == kosten[i - 1, j] + 1:
            pfad.append((i - 1, None))
            i -= 1
        else:
            pfad.append((None, j - 1))
            j -= 1
    return pfad[::-1]


def anker(erkannt: str, vorlage: str) -> list[tuple[int, int]]:
    """Paare gleicher Buchstaben in Läufen von mindestens drei - ein einzelnes
    gleiches `e` ist Zufall, drei am Stück sind es kaum noch."""
    gefunden, lauf = [], []
    for i, j in [*richte_aus(erkannt, vorlage), (None, None)]:
        if i is not None and j is not None and erkannt[i] == vorlage[j]:
            lauf.append((i, j))
            continue
        if len(lauf) >= 3:
            gefunden.extend(lauf)
        lauf = []
    return gefunden


def zeile(woerter: list[str]) -> tuple[str, list[int]]:
    """Wörter normalisiert zu einer Zeile, dazu die Stelle, an der jedes beginnt."""
    text, stellen = "", []
    for wort in woerter:
        stellen.append(len(text) + (1 if text else 0))
        text = f"{text} {normal(wort)}" if text else normal(wort)
    return text, stellen


def grob(vorlage: list[str], erkannt: list[Wort], anfang: float, ende: float) -> tuple[np.ndarray, np.ndarray, float]:
    """Wann jedes Wort der Vorlage beginnt, aus der Erkennung geschätzt; dazu das Ende des letzten.

    Als zweites, welche Wörter sicher erkannt sind: mindestens vier
    Buchstaben lang und zu drei Vierteln an Ankern. Ihr Anfang ist gemessen,
    nicht verteilt. Als drittes die Deckung: welcher Anteil der Buchstaben der Vorlage an
    Ankern hängt. Liegt sie nahe null, gehören Aufnahme und Text nicht zusammen.
    """
    # Die Achse, auf der zwischen Ankern verteilt wird: je Wort seine Silben
    # und eine für die Pause danach.
    gewicht = np.array([silben(w) + 1.0 for w in vorlage])
    achse = np.concatenate([[0.0], np.cumsum(gewicht)])
    vtext, vstellen = zeile(vorlage)
    etext, estellen = zeile([w.text for w in erkannt])
    vwort = np.searchsorted(vstellen, np.arange(len(vtext)), side="right") - 1
    ewort = np.searchsorted(estellen, np.arange(len(etext)), side="right") - 1

    punkte_u, punkte_t = [0.0], [anfang]
    gefunden = anker(etext, vtext) if etext else []
    for i, j in gefunden:
        k, e = vwort[j], ewort[i]
        v_laenge = max(1, len(normal(vorlage[k])))
        e_laenge = max(1, len(normal(erkannt[e].text)))
        punkte_u.append(achse[k] + gewicht[k] * (j - vstellen[k]) / v_laenge)
        wort = erkannt[e]
        punkte_t.append(wort.anfang + (wort.ende - wort.anfang) * (i - estellen[e]) / e_laenge)
    punkte_u.append(achse[-1])
    punkte_t.append(ende)
    # Monoton in der Zeit: Ein Anker, der hinter einen späteren zurückfällt, zählt nicht.
    punkte_t = np.clip(np.maximum.accumulate(punkte_t), anfang, ende)
    getroffen = np.bincount([vwort[j] for _i, j in gefunden if vtext[j] != " "], minlength=len(vorlage))
    laengen = np.array([len(normal(w)) for w in vorlage])
    sicher = (laengen >= 4) & (getroffen >= 0.75 * laengen)
    deckung = getroffen.sum() / max(1, laengen.sum())
    return np.interp(achse, punkte_u, punkte_t), sicher, deckung


class Aligner:
    """Den bekannten Text gegen ein Stück Audio legen - Forced Alignment mit
    dem Erkenner selbst, über die Aufmerksamkeit zwischen Text und Ton."""

    def __init__(self, modell, sprache: str) -> None:
        from faster_whisper.tokenizer import Tokenizer

        self.modell = modell
        self.tokenizer = Tokenizer(modell.hf_tokenizer, modell.model.is_multilingual, task="transcribe", language=sprache)

    def lege(self, audio: np.ndarray, woerter: list[str]) -> list[tuple[float, float, float, float]]:
        """Je Wort: Anfang, Ende der Buchstaben, Ende samt Satzzeichen, Wahrscheinlichkeit."""
        from faster_whisper.audio import pad_or_trim

        tokens, grenzen = [], []
        for wort in woerter:
            kern = wort.rstrip(ZIERAT + SATZENDE + TEILSATZ) or wort
            anfang = len(tokens)
            tokens += self.tokenizer.encode(" " + kern)
            mitte = len(tokens)
            if kern != wort:
                tokens += self.tokenizer.encode(wort[len(kern):])
            grenzen.append((anfang, mitte, len(tokens)))
        merkmale = self.modell.feature_extractor(audio)
        kodiert = self.modell.encode(pad_or_trim(merkmale))
        ergebnis = self.modell.model.align(
            kodiert, self.tokenizer.sot_sequence, [tokens], merkmale.shape[-1], median_filter_width=7
        )[0]
        text_i = np.array([p[0] for p in ergebnis.alignments])
        zeit_i = np.array([p[1] for p in ergebnis.alignments])
        spruenge = np.pad(np.diff(text_i), (1, 0), constant_values=1).astype(bool)
        zeiten = zeit_i[spruenge] / self.modell.tokens_per_second
        dauer = len(audio) / RATE
        zeiten = np.concatenate([zeiten, np.full(max(0, len(tokens) + 1 - len(zeiten)), dauer)])
        p = np.asarray(ergebnis.text_token_probs)
        return [
            (float(zeiten[a]), float(zeiten[m]), float(zeiten[e]), float(p[a:m].mean()) if m > a else 0.0)
            for a, m, e in grenzen
        ]


def fein(
    aligner: Aligner, audio: np.ndarray, vorlage: list[str], anfaenge: np.ndarray, sicher: np.ndarray
) -> list[Lage]:
    """Die Vorlage zwischen sicheren Wörtern gegen das Audio gelegt.

    Jedes Fenster beginnt am Anfang eines sicher erkannten Worts und endet am
    Anfang eines anderen: Text und Ton passen an beiden Rändern zusammen, das
    Alignment verteilt nur, was dazwischen liegt. Ein festes Zeitfenster
    dagegen schnitte mitten in Wörter, und über lange Pausen hinweg zöge das
    Alignment den Text an den Fensteranfang. Wo zwei sichere Wörter weiter als
    29,5 s auseinander liegen, bleibt es bei der groben Zuordnung.
    """
    stuetzen = [0, *(k for k in range(1, len(vorlage)) if sicher[k]), len(vorlage)]
    lagen = [Lage(anfaenge[k], anfaenge[k + 1], anfaenge[k + 1], 0.0) for k in range(len(vorlage))]
    a = 0
    while a < len(stuetzen) - 1:
        b = a + 1
        while b + 1 < len(stuetzen) and anfaenge[stuetzen[b + 1]] - anfaenge[stuetzen[a]] <= FENSTER_S:
            b += 1
        k0, k1 = stuetzen[a], stuetzen[b]
        t0, t1 = anfaenge[k0], anfaenge[k1]
        if 0 < t1 - t0 <= LAENGSTE_S:
            lage = aligner.lege(audio[int(t0 * RATE) : int(t1 * RATE)], vorlage[k0:k1])
            for k, (anfang, kern_ende, ende, p) in zip(range(k0, k1), lage):
                lagen[k] = Lage(anfang + t0, kern_ende + t0, ende + t0, p)
        a = b
    # Monoton: Kein Wort beginnt vor seinem Vorgänger.
    for k in range(1, len(lagen)):
        if lagen[k].anfang < lagen[k - 1].anfang:
            lagen[k].anfang = lagen[k - 1].anfang
        if lagen[k - 1].kern_ende > lagen[k].anfang:
            lagen[k - 1].kern_ende = lagen[k].anfang
    return lagen


# ── Stücke ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Grenze:
    wort: int  # so viele zählende Wörter der Vorlage liegen davor
    zeit: float
    pause: float
    art: str  # anfang | satzende | teilsatz | wort | ende
    wahrscheinlichkeit: float
    abweichung: float  # fein gegen grob, in Sekunden


def waehle(grenzen: list[Grenze]) -> list[tuple[Grenze, Grenze, bool]]:
    """Die Stücke als (Grenze davor, Grenze danach, behalten) - kürzester Weg vom Anfang zum Ende.

    Braucht die Sprecherin für wenige Wörter länger als 29,5 s, passt kein
    Stück darum. Dann fällt diese Stelle weg, Audio und Text zusammen - teuer
    genug, dass es nur dort geschieht, wo es anders nicht geht.
    """
    kosten = [0.0] + [float("inf")] * (len(grenzen) - 1)
    vorher = [(-1, True)] * len(grenzen)
    for j in range(1, len(grenzen)):
        g = grenzen[j]
        preis = {"satzende": 0.0, "teilsatz": KOSTEN_TEILSATZ, "wort": KOSTEN_WORT}.get(g.art, 0.0)
        preis -= PAUSENGEWICHT * min(g.pause, PAUSE_ZAEHLT_BIS_S) if g.art != "ende" else 0.0
        for i in range(j - 1, -1, -1):
            if kosten[i] == float("inf"):
                continue
            laenge = g.zeit - grenzen[i].zeit
            if laenge <= LAENGSTE_S:
                streuung = STREUUNG_KURZ_S if laenge < IDEAL_S else STREUUNG_LANG_S
                wert, behalten = kosten[i] + ((laenge - IDEAL_S) / streuung) ** 2 + preis, True
            elif g.wort - grenzen[i].wort <= VERWURF_WOERTER:
                wert, behalten = kosten[i] + VERWURF_KOSTEN + laenge, False
            else:
                break
            if wert < kosten[j]:
                kosten[j], vorher[j] = wert, (i, behalten)
    stuecke, j = [], len(grenzen) - 1
    while j > 0:
        i, behalten = vorher[j]
        stuecke.append((grenzen[i], grenzen[j], behalten))
        j = i
    return stuecke[::-1]


def gegenprobe(erkannt: str, davor: list[str], teil: list[str], danach: list[str]) -> tuple[int, int]:
    """Wie viele Wörter der Nachbarstücke das Stück allein hören lässt - vorn und hinten.

    Ein Wort gilt als gehört, wenn mindestens drei Viertel seiner Buchstaben
    (und mindestens drei) an Ankern hängen.
    """
    worte = [*davor, *teil, *danach]
    vtext, vstellen = zeile(worte)
    etext, _ = zeile([w for w in erkannt.split() if normal(w)])
    if not etext or not vtext:
        return 0, 0
    getroffen = np.zeros(len(worte), int)
    for _i, j in anker(etext, vtext):
        k = int(np.searchsorted(vstellen, j, side="right") - 1)
        getroffen[k] += 1
    gehoert = [getroffen[k] >= max(3, 0.75 * len(normal(w))) for k, w in enumerate(worte)]
    vorn = sum(gehoert[: len(davor)])
    hinten = sum(gehoert[len(davor) + len(teil) :])
    return vorn, hinten


def teilung(
    vorlage: list[str],
    arten: list[str],
    erkannt: list[Wort],
    aligner: Aligner,
    audio: np.ndarray,
    db: np.ndarray,
    alle_stillen: list[Stille],
    von: float,
    bis: float,
) -> tuple[list[tuple[Grenze, Grenze, bool]], float]:
    """Aus einer Erkennung die Stücke - und die Deckung, auf der sie beruhen."""
    anfaenge, sicher, deckung = grob(vorlage, ohne_erfundenes(erkannt), von, bis)
    lagen = fein(aligner, audio, vorlage, anfaenge, sicher)
    grenzen = [Grenze(0, von, 0.0, "anfang", 1.0, 0.0)]
    for b in range(1, len(vorlage)):
        links, rechts = lagen[b - 1], lagen[b]
        zeit, pause = schnittstelle(links, rechts, alle_stillen, db)
        wahrscheinlichkeit = min(links.wahrscheinlichkeit, rechts.wahrscheinlichkeit)
        grenzen.append(Grenze(b, zeit, pause, arten[b], wahrscheinlichkeit, rechts.anfang - anfaenge[b]))
    grenzen.append(Grenze(len(vorlage), bis, 0.0, "ende", 1.0, 0.0))
    # Ein Schnitt, der hinter dem vorigen läge, verwürfe Audio: nur aufsteigende Grenzen.
    grenzen = [g for n, g in enumerate(grenzen) if n == 0 or g.zeit > max(h.zeit for h in grenzen[:n])]
    return waehle(grenzen), deckung


def teile(
    m4a: Path, quelle: Path, ziel: Path, modell, modellname: str, aligner: Aligner, sprache: str, min_deckung: float
) -> list[dict]:
    alle_woerter = m4a.with_suffix(".txt").read_text(encoding="utf-8").split()
    # Wörter nur aus Zeichen („–") zählen nicht; sie hängen am Wort davor.
    zaehlend = [n for n, w in enumerate(alle_woerter) if normal(w)]
    vorlage = [alle_woerter[n] for n in zaehlend]

    def als_wort(b: int) -> int:
        return zaehlend[b] if b < len(zaehlend) else len(alle_woerter)

    def text(links: Grenze, rechts: Grenze) -> str:
        return " ".join(alle_woerter[als_wort(links.wort) if links.wort else 0 : als_wort(rechts.wort)])

    arten = ["anfang"] + [
        "satzende" if endet_mit(w, SATZENDE) else "teilsatz" if endet_mit(w, TEILSATZ) else "wort"
        for w in (alle_woerter[als_wort(b) - 1] for b in range(1, len(vorlage)))
    ]

    ausgabe = ziel / m4a.parent.relative_to(quelle)
    ausgabe.mkdir(parents=True, exist_ok=True)
    rate, kanaele = abtastung(m4a)
    proben = dekodiere(m4a, rate, kanaele)
    audio = dekodiere(m4a, RATE, 1)[:, 0].astype(np.float32) / 32768
    dauer = len(audio) / RATE
    db = pegel(audio)
    alle_stillen = stillen(db)
    # Sprache von der ersten bis zur letzten Stelle, die nicht still ist.
    laut = np.flatnonzero(db >= schwelle(db))
    von = max(0.0, laut[0] / 100 - RAND_S) if len(laut) else 0.0
    bis = min(dauer, (laut[-1] + 1) / 100 + RAND_S) if len(laut) else dauer

    tsv = m4a.with_suffix(".recogn.tsv")
    erkannt = lies_erkennung(tsv, modellname)
    if erkannt is None:
        _text, erkannt = erkenne(modell, audio, sprache)
        erkannt = nachhoeren(modell, audio, sprache, erkannt, db)
        # Schon jetzt abgelegt: Ein ausgelassenes Paar behält so, was darin zu hören ist.
        m4a.with_suffix(".recogn.txt").write_text(" ".join(w.text for w in erkannt) + "\n", encoding="utf-8")
        schreibe_erkennung(tsv, modellname, erkannt)

    # Teilen und die Stücke einzeln erkennen, im Wechsel: Ein Stück unter
    # 30 s, an beiden Enden in Stille, hört Whisper vollständiger als die
    # ganze Aufnahme am Stück - die nächste Teilung hat mehr Anker.
    schnitte, texte = None, {}
    for _runde in range(RUNDEN):
        stuecke, deckung = teilung(vorlage, arten, erkannt, aligner, audio, db, alle_stillen, von, bis)
        if deckung < min_deckung:
            print(f"{m4a.relative_to(quelle)}: ausgelassen - die Erkennung deckt nur {deckung:.0%} der Vorlage", flush=True)
            return []
        if [(links.zeit, rechts.zeit) for links, rechts, _ in stuecke] == schnitte:
            break
        schnitte = [(links.zeit, rechts.zeit) for links, rechts, _ in stuecke]
        erkannt, texte = [], {}
        for links, rechts in schnitte:
            gehoert, woerter = erkenne(modell, audio[round(links * RATE) : round(rechts * RATE)], sprache)
            texte[links] = gehoert
            erkannt += [Wort(w.anfang + links, w.ende + links, w.wahrscheinlichkeit, w.text) for w in woerter]
    m4a.with_suffix(".recogn.txt").write_text(" ".join(texte[links] for links, _ in schnitte) + "\n", encoding="utf-8")
    schreibe_erkennung(tsv, modellname, erkannt)

    verworfen = [
        f"  verworfen {links.zeit:.1f}-{rechts.zeit:.1f} s: {text(links, rechts)}"
        for links, rechts, behalten in stuecke
        if not behalten
    ]
    stuecke = [(links, rechts) for links, rechts, behalten in stuecke if behalten]

    # Stücke eines früheren Laufs, die es bei dieser Teilung nicht mehr gibt.
    muster = re.compile(rf"{re.escape(m4a.stem)}_(\d+)\.(wav|txt|recogn\.txt)")
    for alt in ausgabe.iterdir():
        treffer = muster.fullmatch(alt.name)
        if treffer and int(treffer.group(1)) > len(stuecke):
            alt.unlink()

    zeilen = []
    for nummer, (links, rechts) in enumerate(stuecke, 1):
        teil = text(links, rechts)
        gehoert = texte[links.zeit]
        stamm = ausgabe / f"{m4a.stem}_{nummer}"
        schreibe_wav(Path(f"{stamm}.wav"), proben[round(links.zeit * rate) : round(rechts.zeit * rate)], rate)
        Path(f"{stamm}.txt").write_text(teil + "\n", encoding="utf-8")
        Path(f"{stamm}.recogn.txt").write_text(gehoert + "\n", encoding="utf-8")
        vorn, hinten = gegenprobe(
            gehoert,
            vorlage[max(0, links.wort - NACHBARN) : links.wort],
            vorlage[links.wort : rechts.wort],
            vorlage[rechts.wort : rechts.wort + NACHBARN],
        )
        zeilen.append(
            {
                "datei": str(m4a.relative_to(quelle).with_suffix("")) + f"_{nummer}",
                "von_s": f"{links.zeit:.2f}",
                "bis_s": f"{rechts.zeit:.2f}",
                "dauer_s": f"{rechts.zeit - links.zeit:.2f}",
                "grenze_danach": rechts.art,
                "pause_danach_s": f"{rechts.pause:.2f}" if rechts.art != "ende" else "",
                "wahrscheinlichkeit_grenze": f"{rechts.wahrscheinlichkeit:.2f}" if rechts.art != "ende" else "",
                # Wie weit das Forced Alignment den Anfang des nächsten Worts
                # gegen die Schätzung aus der Erkennung verschiebt - große
                # Abstände lohnen einen Blick.
                "fein_gegen_grob_s": f"{rechts.abweichung:+.2f}" if rechts.art != "ende" else "",
                "fremd_vorn": vorn,
                "fremd_hinten": hinten,
                "wer": f"{metriken.bewerte(teil, gehoert).wer:.3f}",
                "erkannt": gehoert,
                "vorlage": teil,
            }
        )
    print(
        f"{m4a.relative_to(quelle)}: {dauer:.1f} s, Deckung {deckung:.0%}, {len(zeilen)} Stücke "
        f"({', '.join(z['dauer_s'] for z in zeilen)} s; "
        f"{', '.join(z['grenze_danach'] for z in zeilen[:-1]) or '-'})",
        *verworfen,
        sep="\n",
        flush=True,
    )
    return zeilen


def main() -> int:
    argumente = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    argumente.add_argument("quelle", type=Path)
    argumente.add_argument("ziel", type=Path)
    argumente.add_argument(
        "modell",
        type=Path,
        help="das Registry-Verzeichnis eines Sprechers (dann gilt seine Freigabe) oder ein ct2-Verzeichnis",
    )
    argumente.add_argument("--sprache", default="de")
    argumente.add_argument(
        "--mindeckung",
        type=float,
        default=MIN_DECKUNG,
        help="Paare, deren Vorlage die Erkennung zu weniger als diesem Anteil deckt, auslassen",
    )
    argumente.add_argument(
        "--ohne",
        action="append",
        default=[],
        help="ein Paar auslassen, relativ zur Quelle und ohne Endung (mehrfach möglich)",
    )
    wahl = argumente.parse_args()

    from faster_whisper import WhisperModel

    modell, modellname = wahl.modell, str(wahl.modell)
    freigabe = modell / "freigabe.json"
    if freigabe.is_file():
        # Die Freigabe des Sprechers - dasselbe Modell, mit dem „schreiben" ihn hört.
        modellname = str(json.loads(freigabe.read_text(encoding="utf-8"))["ref"])
        modell = modell / modellname.split("/", 1)[1] / "ct2" if "/" in modellname else modellname
        print(f"Freigegeben: {modellname}", flush=True)
    geraet, rechenart = rechenwerk.waehle()
    erkenner = WhisperModel(str(modell), device=geraet, compute_type=rechenart)
    aligner = Aligner(erkenner, wahl.sprache)

    alle, ausgelassen = [], []
    ohne = {Path(name) for name in wahl.ohne}
    paare = sorted(
        p
        for p in wahl.quelle.rglob("*.m4a")
        if p.with_suffix(".txt").is_file() and p.relative_to(wahl.quelle).with_suffix("") not in ohne
    )
    for m4a in paare:
        stuecke = teile(m4a, wahl.quelle, wahl.ziel, erkenner, modellname, aligner, wahl.sprache, wahl.mindeckung)
        if not stuecke:
            ausgelassen.append(m4a.relative_to(wahl.quelle))
        alle.extend(stuecke)

    print(f"{len(paare)} Paare, {len(alle)} Stücke → {wahl.ziel}")
    if alle:
        with (wahl.ziel / "_bericht.tsv").open("w", encoding="utf-8", newline="") as datei:
            schreiber = csv.DictWriter(datei, fieldnames=list(alle[0]), delimiter="\t")
            schreiber.writeheader()
            schreiber.writerows(alle)
        dauern = [float(z["dauer_s"]) for z in alle]
        arten = [z["grenze_danach"] for z in alle if z["grenze_danach"] != "ende"]
        fremd = sum(1 for z in alle if z["fremd_vorn"] or z["fremd_hinten"])
        print(
            f"Länge {min(dauern):.1f}-{max(dauern):.1f} s, Median {np.median(dauern):.1f} s; "
            f"Grenzen: {arten.count('satzende')} Satzende, {arten.count('teilsatz')} Teilsatz, "
            f"{arten.count('wort')} Wort; {fremd} Stücke mit Wörtern der Nachbarn in der Gegenprobe"
        )
    if ausgelassen:
        print("Ausgelassen, Aufnahme und Text passen nicht zusammen:\n  " + "\n  ".join(map(str, ausgelassen)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
