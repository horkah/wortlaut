"""Paare aus Aufnahme und Vorlage an Pausen in Stücke von 15-29 Sekunden teilen.

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

    <name>_1.wav          das Audio des Stücks, 16 kHz mono (wie `wortlaut/audio.py`)
    <name>_1.recogn.txt   was das Modell darin erkannt hat
    <name>_1.txt          der Teil der Vorlage, der dazu gehört
    <name>.recogn.txt     alle Erkennungen, mit ` // ` zwischen den Stücken

**Geschnitten wird nur in Pausen.** Zuerst werden alle Pausen gesucht (Pegel
unter einer Schwelle zwischen Grundrauschen und Sprachpegel, mindestens
200 ms), dann wird daraus die Teilmenge gewählt, die jedes Stück auf 15 bis
29 Sekunden bringt, möglichst nah an 22 - und bei der Wahl zählt eine lange
Pause mehr als eine kurze: Die langen liegen am Satzende, die kurzen oft
zwischen zwei Wörtern.

**Der Text folgt dem Audio über die Erkennung.** Wo ein Stück aufhört, weiß
nur das Audio. Die Erkennungen aller Stücke, mit Trennern dazwischen, werden
Wort für Wort gegen die Vorlage ausgerichtet (Zeilenumbrüche der Vorlage
zählen als Leerzeichen); wo die Trenner landen, wird die Vorlage geteilt.
Liegen zwischen dem letzten sicher erkannten Wort des einen Stücks und dem
ersten des nächsten Wörter der Vorlage, die die Erkennung nicht getroffen hat,
fällt die Grenze bevorzugt hinter ein Satzende. `_bericht.tsv` im Zielbaum
nennt je Stück, wie sicher die Grenze ist und wie gut Erkennung und Textteil
zusammenpassen.
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
from wortlaut import metriken

RATE = 16_000
# Pausensuche: Frames von 10 ms, Schwelle bei 30 % zwischen Grundrauschen
# (10. Perzentil) und Sprachpegel (95. Perzentil), mindestens 200 ms still.
FRAME = RATE // 100
SCHWELLE_ANTEIL = 0.3
PAUSE_MIN_S = 0.2

KUERZESTE_S, LAENGSTE_S, IDEAL_S = 15.0, 29.0, 22.0
# Wie viel eine lange Pause wert ist, gemessen an der Abweichung von 22 s:
# Eine Sekunde Pause wiegt so viel wie gut fünf Sekunden daneben.
STREUUNG_S = 3.5
PAUSENGEWICHT = 2.0
PAUSE_ZAEHLT_BIS_S = 1.5

TRENNER = " // "
SATZENDE = ".!?…"
# Wie viele Wörter Abstand ein Satzende (ein Komma) aufwiegt.
SATZBONUS, TEILSATZBONUS = 1.5, 0.5
TEILSATZ = ",;:"
ZIERAT = "\"'»«„“”‚‘’)]"


# ── Audio ───────────────────────────────────────────────────────────────────


def dekodiere(pfad: Path) -> np.ndarray:
    roh = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(pfad), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(roh, np.int16)


@dataclass(frozen=True)
class Pause:
    anfang: float
    ende: float

    @property
    def dauer(self) -> float:
        return self.ende - self.anfang

    @property
    def mitte(self) -> float:
        return (self.anfang + self.ende) / 2


def pausen(proben: np.ndarray) -> list[Pause]:
    """Alle Stellen, an denen es mindestens 200 ms lang still ist - Anfang und Ende ausgenommen."""
    frames = (proben[: len(proben) // FRAME * FRAME].astype(np.float32) / 32768).reshape(-1, FRAME)
    pegel = 20 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-9)
    boden, sprache = np.percentile(pegel, 10), np.percentile(pegel, 95)
    still = pegel < boden + SCHWELLE_ANTEIL * (sprache - boden)

    gefunden, anfang = [], None
    for nummer, ist_still in enumerate([*still, False]):
        if ist_still and anfang is None:
            anfang = nummer
        elif not ist_still and anfang is not None:
            # Stille am Rand ist keine Pause zwischen zwei Stücken.
            if anfang > 0 and nummer < len(still) and (nummer - anfang) * FRAME >= PAUSE_MIN_S * RATE:
                gefunden.append(Pause(anfang * FRAME / RATE, nummer * FRAME / RATE))
            anfang = None
    return gefunden


def schnitte(dauer: float, kandidaten: list[Pause]) -> tuple[list[Pause], bool]:
    """Die Pausen, an denen geschnitten wird; dazu, ob 15-29 s eingehalten werden konnten.

    Kürzester Weg über die Pausen: Jedes Stück kostet seine quadrierte
    Abweichung von 22 s, jede benutzte Pause bringt ihre Länge als Gutschrift.
    Geht es in den Grenzen nicht, werden sie Schritt für Schritt geweitet.
    """
    if dauer <= LAENGSTE_S:
        return [], True
    punkte = [0.0, *(pause.mitte for pause in kandidaten), dauer]
    # Geweitet wird nur nach unten: Über 30 s hört Whisper nicht, ein langes
    # Stück wäre für das Training abgeschnitten.
    for weitung, eingehalten in ((0.0, True), (3.0, False), (6.0, False), (10.0, False)):
        kurz, lang = KUERZESTE_S - weitung, LAENGSTE_S
        kosten = [0.0] + [float("inf")] * (len(punkte) - 1)
        vorher = [-1] * len(punkte)
        for j in range(1, len(punkte)):
            gutschrift = (
                PAUSENGEWICHT * min(kandidaten[j - 1].dauer, PAUSE_ZAEHLT_BIS_S)
                if j < len(punkte) - 1
                else 0.0
            )
            for i in range(j):
                laenge = punkte[j] - punkte[i]
                if kurz <= laenge <= lang and kosten[i] < float("inf"):
                    wert = kosten[i] + ((laenge - IDEAL_S) / STREUUNG_S) ** 2 - gutschrift
                    if wert < kosten[j]:
                        kosten[j], vorher[j] = wert, i
        if kosten[-1] < float("inf"):
            gewaehlt, j = [], vorher[-1]
            while j > 0:
                gewaehlt.append(kandidaten[j - 1])
                j = vorher[j]
            return sorted(gewaehlt, key=lambda p: p.mitte), eingehalten
    raise RuntimeError(f"Keine Teilung möglich ({dauer:.1f} s, {len(kandidaten)} Pausen)")


def _gleich(pfad: Path, proben: np.ndarray) -> bool:
    with wave.open(str(pfad), "rb") as datei:
        return datei.getnframes() == len(proben) and datei.readframes(len(proben)) == proben.tobytes()


def schreibe_wav(pfad: Path, proben: np.ndarray) -> None:
    with wave.open(str(pfad), "wb") as datei:
        datei.setnchannels(1)
        datei.setsampwidth(2)
        datei.setframerate(RATE)
        datei.writeframes(proben.tobytes())


# ── Text ────────────────────────────────────────────────────────────────────
#
# Ausgerichtet wird Buchstabe für Buchstabe und nicht Wort für Wort. Die
# Erkennung trifft bei dieser Sprache wenige Wörter ganz, aber viele halb - und
# schon Zahl und Länge der Wörter sagen, wie weit der Text reicht. Auf der
# Ebene der Buchstaben zählt beides mit; auf der der Wörter wäre ein halb
# getroffenes Wort so viel wert wie ein ganz verfehltes.


def normal(wort: str) -> str:
    return re.sub(r"[\W_]", "", wort.lower())


# Was Whisper in Pausen gern erfindet - Abspann von Untertiteln, der Gruß am
# Ende eines Videos. Es steht in keiner Vorlage und zöge die Grenzen nur um
# seine eigene Länge weiter. Entfernt wird es allein für die Ausrichtung; die
# `.recogn.txt` behält, was das Modell gesagt hat.
ERFUNDEN = re.compile(
    r"untertitel\w*( im auftrag des \w+)?( für funk)?[ ,]*\d*"
    r"|swiss txt( ag)?[ ,]*\d*"
    r"|(vielen )?dank für'?s? zuschauen|das war'?s für heute|bis zum nächsten mal|tschüss",
    re.IGNORECASE,
)


def bereinigt(text: str) -> str:
    """Die Erkennung ohne erfundene Floskeln und ohne gleich wiederholte Sätze."""
    text = ERFUNDEN.sub(" ", text)
    saetze, zuletzt = [], None
    for satz in re.split(r"(?<=[.!?])\s+", text):
        kern = normal(satz)
        if kern and kern != zuletzt:
            saetze.append(satz)
        zuletzt = kern or zuletzt
    # Schleifen innerhalb eines Satzes („zu schlafen, zu schlafen, …"): eine
    # gleich wiederholte Folge von bis zu vier Wörtern bleibt einmal stehen.
    worte = " ".join(saetze).split()
    for laenge in range(1, 5):
        stelle = 0
        while stelle + 2 * laenge <= len(worte):
            folge = [normal(w) for w in worte[stelle : stelle + laenge]]
            if folge == [normal(w) for w in worte[stelle + laenge : stelle + 2 * laenge]]:
                del worte[stelle + laenge : stelle + 2 * laenge]
            else:
                stelle += 1
    return " ".join(worte)


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


@dataclass(frozen=True)
class Grenze:
    wort: int  # so viele Wörter der Vorlage gehören zu den Stücken davor
    art: str  # sicher | satzende | teilsatz | geschaetzt | tempo
    beleg: float  # Anteil der Erkennung um die Grenze, der an Ankern hängt


def endet_mit(wort: str, zeichen: str) -> bool:
    kern = wort.rstrip(ZIERAT)
    return bool(kern) and kern[-1] in zeichen


def grenzen(stuecke: list[str], woerter: list[str], tempo_anteile: list[float]) -> list[Grenze]:
    """Wo in der Vorlage jedes Stück (außer dem letzten) aufhört.

    `tempo_anteile`: je Schnitt, welcher Anteil der Sprechzeit (ohne Pausen)
    vor ihm liegt. Er trägt die Grenze dort, wo die Erkennung zu wenig trifft,
    um sie zu tragen.
    """
    # Die Vorlage als eine Zeile aus normalisierten Wörtern. Wörter nur aus
    # Zeichen („–") zählen nicht mit; sie hängen am Wort davor.
    zaehlend = [nummer for nummer, wort in enumerate(woerter) if normal(wort)]
    wortanfang, teile_ = [], []
    for nummer in zaehlend:
        wortanfang.append(sum(len(t) + 1 for t in teile_))
        teile_.append(normal(woerter[nummer]))
    vorlage = " ".join(teile_)

    erkannt, stueckanfang = "", []
    for text in stuecke:
        stueckanfang.append(len(erkannt) + (1 if erkannt else 0))
        worte = " ".join(normal(w) for w in bereinigt(text).split() if normal(w))
        erkannt = f"{erkannt} {worte}" if erkannt else worte
    # Ein Stück ohne Erkennung beginnt, wo das nächste beginnt.
    stueckanfang = [min(a, len(erkannt)) for a in stueckanfang]

    pfad = richte_aus(erkannt, vorlage)
    # Anker: Buchstaben in Läufen von mindestens drei Treffern. Ein einzelnes
    # gleiches `e` ist Zufall, drei am Stück sind es kaum noch.
    treffer = [i is not None and j is not None and erkannt[i] == vorlage[j] for i, j in pfad]
    anker, lauf = [], []
    for stelle, (paar, ist) in enumerate(zip(pfad, treffer)):
        if ist:
            lauf.append(paar)
        if not ist or stelle == len(pfad) - 1:
            if len(lauf) >= 3:
                anker.extend(lauf)
            lauf = []
    # Wo der Pfad in der Vorlage steht, wenn er eine Stelle der Erkennung erreicht.
    vorlage_bei: dict[int, int] = {}
    stand = 0
    for i, j in pfad:
        if i is not None and i not in vorlage_bei:
            vorlage_bei[i] = stand
        if j is not None:
            stand = j + 1

    def als_wort(index: int) -> int:
        return zaehlend[index] if index < len(zaehlend) else len(woerter)

    def stelle(b: int) -> int:
        """Grenze b (vor dem b-ten zählenden Wort) als Stelle in der Vorlage: das Leerzeichen davor."""
        return wortanfang[b] - 1 if b < len(wortanfang) else len(vorlage)

    def als_grenze(zeichenstelle: float) -> float:
        """Eine Stelle in der Vorlage als (gebrochene) Wortgrenze."""
        return float(np.interp(zeichenstelle, [stelle(b) for b in range(len(zaehlend) + 1)], range(len(zaehlend) + 1)))

    n_woerter = len(zaehlend)
    stueckende = [*stueckanfang[1:], len(erkannt) + 1]
    angekert = {i for i, _ in anker}

    def beleg(nummer: int) -> float:
        """Welcher Anteil der Erkennung in den Stücken um eine Grenze an Ankern hängt."""
        von, bis = stueckanfang[nummer - 1], stueckende[nummer]
        buchstaben = [i for i in range(von, min(bis, len(erkannt))) if erkannt[i] != " "]
        return sum(i in angekert for i in buchstaben) / len(buchstaben) if buchstaben else 0.0

    ziele, belege, sicher = [], [], []
    for nummer in range(1, len(stuecke)):
        start = stueckanfang[nummer]
        lo = max((j for i, j in anker if i < start), default=-1) + 1
        hi = min((j for i, j in anker if i >= start), default=len(vorlage))
        im_bereich = [b for b in range(n_woerter + 1) if lo <= stelle(b) <= hi]
        buchstabenziel = im_bereich[0] if len(im_bereich) == 1 else als_grenze(vorlage_bei.get(start, len(vorlage)))
        # Wie sehr der Buchstabenabgleich zählt: Unter einem Zehntel Ankern
        # ist er Zufall (kurze Wörter wie „der" treffen immer irgendwo), ab
        # knapp der Hälfte trägt er allein - halb getroffene Erkennungen
        # dieser Sprache kommen auf 15-45 %. Dazwischen wird gemischt.
        belegt = beleg(nummer)
        gewicht = float(np.clip((belegt - 0.1) / 0.35, 0.0, 1.0))
        tempoziel = n_woerter * tempo_anteile[nummer - 1]
        ziele.append(gewicht * buchstabenziel + (1 - gewicht) * tempoziel)
        belege.append(belegt)
        sicher.append(len(im_bereich) == 1 and gewicht >= 0.5)

    # Alle Grenzen zusammen: nah an ihrem Ziel, lieber hinter einem Satzende,
    # und - solange die Wörter reichen - jedes Stück mit mindestens einem Wort.
    # Ein Stück, das spricht, hat auch Text.
    k = len(ziele)
    if not k:
        return []
    abstand_min = 1 if n_woerter >= k + 1 else 0

    def kosten(nummer: int, b: int) -> float:
        wert = abs(b - ziele[nummer])
        if sicher[nummer]:
            wert *= 4
        if 0 < b and endet_mit(woerter[als_wort(b - 1)], SATZENDE):
            wert -= SATZBONUS
        elif 0 < b and endet_mit(woerter[als_wort(b - 1)], TEILSATZ):
            wert -= TEILSATZBONUS
        return wert

    unendlich = float("inf")
    tafel = [[unendlich] * (n_woerter + 1) for _ in range(k)]
    zurueck = [[-1] * (n_woerter + 1) for _ in range(k)]
    for b in range(abstand_min, n_woerter + 1):
        tafel[0][b] = kosten(0, b)
    for nummer in range(1, k):
        bestes, bestes_b = unendlich, -1
        for b in range(n_woerter + 1):
            # Das beste b' <= b - abstand_min, laufend mitgeführt.
            kandidat = b - abstand_min
            if kandidat >= 0 and tafel[nummer - 1][kandidat] < bestes:
                bestes, bestes_b = tafel[nummer - 1][kandidat], kandidat
            if bestes < unendlich:
                tafel[nummer][b] = bestes + kosten(nummer, b)
                zurueck[nummer][b] = bestes_b
    obergrenze = n_woerter - abstand_min
    b = min(range(obergrenze + 1), key=lambda x: tafel[k - 1][x]) if k else 0
    gewaehlt = []
    for nummer in range(k - 1, -1, -1):
        gewaehlt.append(b)
        b = zurueck[nummer][b]
    gewaehlt.reverse()

    ergebnis = []
    for nummer, b in enumerate(gewaehlt):
        if sicher[nummer] and b == round(ziele[nummer]):
            art = "sicher"
        elif belege[nummer] < 0.1:
            art = "tempo"
        elif b > 0 and endet_mit(woerter[als_wort(b - 1)], SATZENDE):
            art = "satzende"
        elif b > 0 and endet_mit(woerter[als_wort(b - 1)], TEILSATZ):
            art = "teilsatz"
        else:
            art = "geschaetzt"
        ergebnis.append(Grenze(als_wort(b), art, belege[nummer]))
    return ergebnis


# ── Ablauf ──────────────────────────────────────────────────────────────────


def teile(m4a: Path, quelle: Path, ziel: Path, erkenner, sprache: str) -> list[dict]:
    vorlage_pfad = m4a.with_suffix(".txt")
    woerter = vorlage_pfad.read_text(encoding="utf-8").split()
    ausgabe = ziel / m4a.parent.relative_to(quelle)
    ausgabe.mkdir(parents=True, exist_ok=True)

    proben = dekodiere(m4a)
    dauer = len(proben) / RATE
    kandidaten = pausen(proben)
    gewaehlt, eingehalten = schnitte(dauer, kandidaten)
    punkte = [0.0, *(p.mitte for p in gewaehlt), dauer]
    # Stücke eines früheren Laufs, die es bei dieser Teilung nicht mehr gibt.
    muster = re.compile(rf"{re.escape(m4a.stem)}_(\d+)\.(wav|txt|recogn\.txt)$")
    for alt in ausgabe.iterdir():
        treffer = muster.fullmatch(alt.name)
        if treffer and int(treffer.group(1)) >= len(punkte):
            alt.unlink()

    stuecke = []
    for nummer, (von, bis) in enumerate(zip(punkte, punkte[1:]), 1):
        wav = ausgabe / f"{m4a.stem}_{nummer}.wav"
        erkannt_pfad = wav.with_suffix(".recogn.txt")
        teilproben = proben[round(von * RATE) : round(bis * RATE)]
        # Liegt dasselbe Stück schon da, gilt seine Erkennung weiter - ein
        # zweiter Lauf rechnet nur, was sich geändert hat.
        if erkannt_pfad.is_file() and wav.is_file() and _gleich(wav, teilproben):
            text = erkannt_pfad.read_text(encoding="utf-8").strip()
        else:
            schreibe_wav(wav, teilproben)
            text = erkenner.transkribiere(wav, sprache).text.strip()
            erkannt_pfad.write_text(text + "\n", encoding="utf-8")
        stuecke.append(text)
    (ausgabe / f"{m4a.stem}.recogn.txt").write_text(TRENNER.join(stuecke) + "\n", encoding="utf-8")

    # Sprechzeit vor jedem Schnitt: die Zeit bis dorthin ohne die Pausen darin.
    def sprechzeit(bis: float) -> float:
        return bis - sum(max(0.0, min(p.ende, bis) - p.anfang) for p in kandidaten)

    gesamt = sprechzeit(dauer) or dauer
    teilgrenzen = grenzen(stuecke, woerter, [sprechzeit(p.mitte) / gesamt for p in gewaehlt])
    woerterpunkte = [0, *(g.wort for g in teilgrenzen), len(woerter)]
    zeilen = []
    for nummer in range(len(stuecke)):
        teil = " ".join(woerter[woerterpunkte[nummer] : woerterpunkte[nummer + 1]])
        (ausgabe / f"{m4a.stem}_{nummer + 1}.txt").write_text(teil + "\n", encoding="utf-8")
        zeilen.append(
            {
                "datei": str(m4a.relative_to(quelle).with_suffix("")) + f"_{nummer + 1}",
                "von_s": f"{punkte[nummer]:.2f}",
                "bis_s": f"{punkte[nummer + 1]:.2f}",
                "dauer_s": f"{punkte[nummer + 1] - punkte[nummer]:.2f}",
                "pause_danach_s": f"{gewaehlt[nummer].dauer:.2f}" if nummer < len(gewaehlt) else "",
                "grenze_danach": teilgrenzen[nummer].art if nummer < len(teilgrenzen) else "",
                "beleg": f"{teilgrenzen[nummer].beleg:.2f}" if nummer < len(teilgrenzen) else "",
                "laenge_ok": "ja" if eingehalten else "nein",
                # Wie weit die Grenze von der liegt, die ein gleichmäßiges
                # Sprechtempo ergäbe - eine Gegenprobe, keine Regel: Große
                # Abstände lohnen einen Blick.
                "abstand_tempo_woerter": (
                    str(woerterpunkte[nummer + 1] - round(len(woerter) * punkte[nummer + 1] / dauer))
                    if nummer < len(teilgrenzen)
                    else ""
                ),
                "wer": f"{metriken.bewerte(teil, stuecke[nummer]).wer:.3f}",
                "erkannt": stuecke[nummer],
                "vorlage": teil,
            }
        )
    print(
        f"{m4a.relative_to(quelle)}: {dauer:.1f} s, {len(kandidaten)} Pausen, "
        f"{len(stuecke)} Stücke ({', '.join(z['dauer_s'] for z in zeilen)} s)"
        + ("" if eingehalten else "  ! Grenzen geweitet"),
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
        "--ohne",
        action="append",
        default=[],
        help="ein Paar auslassen, relativ zur Quelle und ohne Endung (mehrfach möglich)",
    )
    wahl = argumente.parse_args()

    from wortlaut.whisper.local import LokalerTranskriptor

    modell = wahl.modell
    freigabe = modell / "freigabe.json"
    if freigabe.is_file():
        # Die Freigabe des Sprechers - dasselbe Modell, mit dem „schreiben" ihn hört.
        ref = str(json.loads(freigabe.read_text(encoding="utf-8"))["ref"])
        modell = modell / ref.split("/", 1)[1] / "ct2" if "/" in ref else ref
        print(f"Freigegeben: {ref}", flush=True)
    erkenner = LokalerTranskriptor(modell)
    alle = []
    ohne = {Path(name) for name in wahl.ohne}
    paare = sorted(
        p
        for p in wahl.quelle.rglob("*.m4a")
        if p.with_suffix(".txt").is_file() and p.relative_to(wahl.quelle).with_suffix("") not in ohne
    )
    for m4a in paare:
        alle.extend(teile(m4a, wahl.quelle, wahl.ziel, erkenner, wahl.sprache))

    with (wahl.ziel / "_bericht.tsv").open("w", encoding="utf-8", newline="") as datei:
        schreiber = csv.DictWriter(datei, fieldnames=list(alle[0]), delimiter="\t")
        schreiber.writeheader()
        schreiber.writerows(alle)
    print(f"{len(paare)} Paare, {len(alle)} Stücke → {wahl.ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
