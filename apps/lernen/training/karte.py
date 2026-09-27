"""Ein Training, das auf die Karte wartet, statt an ihr zu scheitern.

**Der Fall.** Am 27. September 2026 scheiterten drei Läufe binnen einer Minute
am ersten Schritt mit `CUDA out of memory`. Die Karte war nicht zu klein für
sie - der Webdienst hielt gut fünf ihrer elf Gigabyte, Erkenner einer
Auswertung, die längst vorbei war. Beim Laden eines Erkenners wartete der
Trainer da schon (`bewerten._hole_karte`); beim Lernen nicht.

**Was hier geschieht.** Scheitert ein Training am Speicher, wird aufgeräumt -
der Arbeitsstand dieser Faltung und was torch noch hält -, gewartet und die
Faltung von vorn begonnen. Derselbe Takt wie beim Laden (`WARTEZEITEN_S`),
aus demselben Grund: Die kurzen Belegungen sind in zehn Minuten vorbei, und
eine Auswertung über Stunden auszusitzen hieße, die Karte zu blockieren statt
zu teilen.

**Wann nicht gewartet wird.** Wenn nach dem Aufräumen niemand sonst etwas auf
der Karte hält. Dann passt das Training nicht, und das wird in zehn Minuten
nicht anders - der Fehler soll sofort dastehen.

Ohne torch geschrieben, damit es sich ohne das Abbild des Trainers prüfen
lässt: Was die Karte angeht, kommt von außen herein (`finetune.py`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

from .bewerten import WARTEZEITEN_S

Ergebnis = TypeVar("Ergebnis")

# Was andere auf der Karte halten müssen, damit sich Warten lohnt. Nicht null:
# Der eigene Prozess hält seinen CUDA-Kontext, ein paar hundert Megabyte, die
# kein Aufräumen zurückgibt und die von außen aussehen wie die eines anderen.
FREMD_AB_MB = 1000.0


def ist_speichermangel(ursache: BaseException) -> bool:
    """Ob ein Fehler heißt: Die Karte ist voll.

    Am Text und nicht an der Klasse: torch wirft `OutOfMemoryError`,
    CTranslate2 beim Laden eines Erkenners in der Tempowahl einen nackten
    `RuntimeError` - beide sagen „out of memory".
    """
    return "out of memory" in str(ursache).lower()


def mit_geduld(
    versuch: Callable[[], Ergebnis],
    bericht: Any,
    *,
    aufraeumen: Callable[[], None],
    fremd_belegt_mb: Callable[[], float],
    wartezeiten: tuple[float, ...] = WARTEZEITEN_S,
    schlafe: Callable[[float], None] = time.sleep,
) -> Ergebnis:
    """`versuch()`, und bei Speichermangel aufräumen, warten und noch einmal.

    Jeder andere Fehler geht sofort durch; ebenso der Speichermangel, wenn die
    Karte nach dem Aufräumen niemand anderem gehört oder die Wartezeit um ist.
    """
    for nummer in range(len(wartezeiten) + 1):
        mangel = ""
        try:
            ergebnis = versuch()
        except Exception as ursache:  # noqa: BLE001 - was immer torch wirft
            if not ist_speichermangel(ursache) or nummer == len(wartezeiten):
                raise
            mangel = str(ursache).splitlines()[0]
        else:
            if nummer:
                bericht.sage(f"  Karte frei nach {nummer} vergeblichen Versuchen.")
            return ergebnis

        # Außerhalb des `except`: Solange die Ausnahme lebt, hält ihr
        # Traceback die Rahmen des Trainings fest - samt Modell und
        # Optimierer auf der Karte. Aufräumen ginge dort ins Leere.
        aufraeumen()
        fremd = fremd_belegt_mb()
        if fremd < FREMD_AB_MB:
            raise RuntimeError(
                f"{mangel} - und außer diesem Training hält niemand etwas auf der "
                "Karte. Es passt nicht darauf; Warten ändert daran nichts."
            )
        bericht.sage(
            f"  Karte belegt ({fremd:.0f} MB bei anderen) - es wird gewartet, "
            "dann beginnt diese Faltung von vorn."
        )
        schlafe(wartezeiten[nummer])
    raise AssertionError("unerreichbar")  # pragma: no cover
