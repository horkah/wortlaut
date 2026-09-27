"""Ein Training, das auf die Karte wartet, statt an ihr zu scheitern.

Die Karte teilt sich der Trainer mit dem Webdienst, dessen Erkenner sie
zeitweise halten. Scheitert ein Training am Speicher, wird aufgeräumt - der
Arbeitsstand der Faltung und was torch hält -, gewartet und die Faltung neu
begonnen, im Takt des Ladens (`bewerten.WARTEZEITEN_S`).

Hält nach dem Aufräumen niemand sonst etwas, passt das Training nicht, und
der Fehler steht sofort da.

Ohne torch, damit es sich ohne das Trainerabbild prüfen lässt; was die Karte
angeht, kommt von außen (`finetune.py`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

from .bewerten import WARTEZEITEN_S

Ergebnis = TypeVar("Ergebnis")

# Ab wann Warten lohnt. Nicht null: Der eigene CUDA-Kontext hält ein paar
# hundert Megabyte, die von außen wie fremde aussehen.
FREMD_AB_MB = 1000.0


def ist_speichermangel(ursache: BaseException) -> bool:
    """Ob ein Fehler heißt: Die Karte ist voll.

    Am Text: torch wirft `OutOfMemoryError`, CTranslate2 einen `RuntimeError`.
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

        # Außerhalb des `except`: Der Traceback hielte Modell und Optimierer fest.
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
