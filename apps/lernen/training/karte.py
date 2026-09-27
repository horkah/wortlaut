"""Ein Training, das die Karte freiräumt und auf sie wartet, statt an ihr zu scheitern.

Die Karte teilt sich der Trainer mit dem Webdienst, dessen Erkenner sie
zeitweise halten. Scheitert ein Training am Speicher, wird aufgeräumt - der
Arbeitsstand der Faltung und was torch hält -, gewartet und die Faltung neu
begonnen, im Takt des Ladens (`bewerten.WARTEZEITEN_S`).

Hält nach dem Aufräumen niemand sonst etwas, passt das Training nicht, und
der Fehler steht sofort da.

**Vor jedem Lauf und jeder Faltung** gibt Ollama seine Modelle ab
(`entlade_ollama`) - das Sprachmodell der Textquelle hält gut fünf Gigabyte,
die es beim nächsten Text in Sekunden wieder lädt. Danach wird gewartet, bis
genug frei ist (`warte_auf_platz`).

Ohne torch, damit es sich ohne das Trainerabbild prüfen lässt; was die Karte
angeht, kommt von außen (`finetune.py`).
"""

from __future__ import annotations

import json
import time
import urllib.request
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


# Wie lange Ollama für eine Antwort bekommt. Es läuft nebenan; wer länger
# braucht, ist nicht da, und das Training wartet nicht darauf.
OLLAMA_ZEITLIMIT_S = 5.0


def _json_anfrage(url: str, nutzlast: dict[str, Any] | None = None) -> dict[str, Any]:
    daten = json.dumps(nutzlast).encode("utf-8") if nutzlast is not None else None
    anfrage = urllib.request.Request(
        url, data=daten, headers={"Content-Type": "application/json"} if daten else {}
    )
    with urllib.request.urlopen(anfrage, timeout=OLLAMA_ZEITLIMIT_S) as antwort:
        return json.loads(antwort.read() or b"{}")


def entlade_ollama(
    basis: str,
    bericht: Any,
    anfrage: Callable[[str, dict[str, Any] | None], dict[str, Any]] = _json_anfrage,
) -> list[str]:
    """Ollama seine geladenen Modelle abgeben lassen; gibt ihre Namen zurück.

    `basis` ist die Adresse von Ollama (`WORTLAUT_OLLAMA_URL`), leer heißt: kein
    Ollama. Ein Modell geht mit `keep_alive: 0` von der Karte (Ollama-API,
    `/api/ps` und `/api/generate`). Ist Ollama nicht erreichbar, steht es im
    Protokoll, und das Training geht weiter - dann hält es auch nichts.
    """
    if not basis:
        return []
    basis = basis.rstrip("/")
    try:
        geladen = [
            str(modell.get("name") or modell.get("model"))
            for modell in anfrage(f"{basis}/api/ps", None).get("models", [])
        ]
        for name in geladen:
            anfrage(f"{basis}/api/generate", {"model": name, "keep_alive": 0})
    except Exception as ursache:  # noqa: BLE001 - Netz, Zeitlimit, kaputte Antwort
        bericht.sage(f"  Ollama nicht erreichbar ({type(ursache).__name__}) - nichts entladen.")
        return []
    if geladen:
        bericht.sage(f"  Ollama entladen: {', '.join(geladen)}")
    return geladen


def warte_auf_platz(
    bedarf_mb: float,
    frei_mb: Callable[[], float],
    bericht: Any,
    *,
    wartezeiten: tuple[float, ...] = WARTEZEITEN_S,
    schlafe: Callable[[float], None] = time.sleep,
) -> float:
    """Warten, bis `bedarf_mb` auf der Karte frei ist; gibt den freien Platz zurück.

    Nach der letzten Wartezeit geht es trotzdem los: Was dann fehlt, meldet
    der Probeschritt als Speichermangel, und `mit_geduld` übernimmt.
    """
    frei = frei_mb()
    for nummer, pause in enumerate(wartezeiten):
        if frei >= bedarf_mb:
            if nummer:
                bericht.sage(f"  Karte frei nach {nummer} Wartezeiten: {frei:.0f} MB")
            return frei
        if nummer == 0:
            bericht.sage(
                f"  Karte belegt: {frei:.0f} MB frei, gebraucht {bedarf_mb:.0f} MB - es wird gewartet."
            )
        schlafe(pause)
        frei = frei_mb()
    return frei
