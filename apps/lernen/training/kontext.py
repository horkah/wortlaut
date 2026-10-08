"""Der Startprompt - Kontextverstärkung beim Dekodieren (`laeufe.KONTEXT_VOKABULAR`).

Die einzige Maßnahme ohne Training: Whisper beginnt jede Erkennung mit einer
Liste der Wörter, die für diese Person einschlägig sind. faster-whisper kennt
keine flache Fusion mit einem Sprachmodell; der Startprompt (`initial_prompt`)
ist der Weg, der ohne Umbau des Dekodierers geht.

**Welche Wörter.** Die seltenen der Lerntexte: Was Whispers Zerteiler in
viele Stücke zerlegt, hat Whisper selten gesehen - Namen, Fachwörter,
Zusammensetzungen. Häufiges vorn, bis das Budget an Marken erschöpft ist
(`kontext_marken`, `kontext_mindestteile` im Rezept).

**Nur aus den Lerntexten.** Eine Faltung bekommt den Startprompt ihrer
Lernzeilen - sonst stünden die Wörter der gemessenen Sätze vorab da. Das
Endmodell nimmt alle Texte, Selbstbeschriftetes nie.

Der Startprompt liegt als `startprompt.txt` neben den Gewichten und geht mit
in den CTranslate2-Stand (`finetune.wandle_um`); jeder Erkenner, der den Stand
lädt, liest ihn (`wortlaut/whisper/local.py`).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from wortlaut import laeufe
from wortlaut.whisper.local import STARTPROMPT

# Ein Wort beginnt mit einem Buchstaben; Bindestrich und Apostroph gehören dazu.
WORT = re.compile(r"[^\W\d_][\w'-]*", re.UNICODE)
# Kürzeres zerlegt der Zerteiler ohnehin kaum.
MINDESTLAENGE = 4
# Wenn das Rezept nichts sagt: Marken für den ganzen Prompt (Whisper erlaubt
# 223) und Stücke, ab denen ein Wort als selten gilt.
MARKEN = 120
MINDESTTEILE = 3


def texte_fuer(zeilen: Iterable[dict[str, Any]]) -> list[str]:
    """Die Texte der Lernzeilen - ohne Selbstbeschriftetes."""
    return [
        str(zeile.get("text") or "")
        for zeile in zeilen
        if str(zeile.get("quelle")) != laeufe.QUELLE_SELBST
    ]


def vokabular(
    texte: Iterable[str],
    marken_von: Callable[[str], int],
    budget: int = MARKEN,
    mindestteile: int = MINDESTTEILE,
) -> list[str]:
    """Die einschlägigen Wörter, häufigste zuerst, bis `budget` Marken verbraucht sind.

    `marken_von` zählt die Marken eines Wortes mit führendem Leerzeichen, wie
    es im Satz stünde. Groß und klein zählen zusammen; geschrieben wird die
    häufigste Form. Jedes Wort kostet dazu eine Marke für das Komma.
    """
    anzahl: Counter[str] = Counter()
    formen: dict[str, Counter[str]] = defaultdict(Counter)
    for text in texte:
        for wort in WORT.findall(text):
            if len(wort) < MINDESTLAENGE:
                continue
            anzahl[wort.lower()] += 1
            formen[wort.lower()][wort] += 1

    kandidaten = []
    for schluessel, wie_oft in anzahl.items():
        form = formen[schluessel].most_common(1)[0][0]
        teile = marken_von(f" {form}")
        if teile >= mindestteile:
            kandidaten.append((wie_oft, teile, form))
    kandidaten.sort(key=lambda kandidat: (-kandidat[0], -kandidat[1], kandidat[2]))

    gewaehlt: list[str] = []
    verbraucht = 0
    for _wie_oft, teile, form in kandidaten:
        if verbraucht + teile + 1 > budget:
            continue
        gewaehlt.append(form)
        verbraucht += teile + 1
    return gewaehlt


def als_prompt(woerter: list[str]) -> str:
    return ", ".join(woerter)


def schreibe(
    gewichte: Path,
    zeilen: Iterable[dict[str, Any]],
    zerteiler,
    rezept: dict[str, Any],
) -> list[str]:
    """Den Startprompt für diese Lernzeilen neben die Gewichte legen; gibt die Wörter zurück."""
    woerter = vokabular(
        texte_fuer(zeilen),
        lambda wort: len(zerteiler(wort, add_special_tokens=False).input_ids),
        int(rezept.get("kontext_marken", MARKEN)),
        int(rezept.get("kontext_mindestteile", MINDESTTEILE)),
    )
    if woerter:
        (gewichte / STARTPROMPT).write_text(als_prompt(woerter) + "\n", encoding="utf-8")
    return woerter
