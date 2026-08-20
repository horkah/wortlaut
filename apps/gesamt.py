"""Beide Apps in einem Prozess — der Betriebsfall auf einem einzelnen Wirt.

Gestartet wird das so:

    uvicorn apps.gesamt:app --host 0.0.0.0 --port 8000

Was sonst der Reverse Proxy tut, tut hier ein Verteiler von zwanzig Zeilen:
`/schreiben/…` geht an „schreiben", alles andere an „hören". Der Pfad bleibt
dabei unverändert — beide Apps hängen ihre Wege schon selbst dorthin, wo sie
liegen sollen (`BASIS` in „schreiben"). Draußen genügt darum eine einzige
Regel, die auf diesen einen Port zeigt.

Die Trennung, die sonst zwei Container leisten, bleibt in der Sache bestehen:
Jede App behält ihre eigene Datenbank, ihre eigene Ablage und ihre eigenen
Zugangsregeln — die `/api`-Wege von „hören" hinter dem Token, „schreiben" ohne
(Grundentscheidung 7). Geteilt wird nur der Prozess.

Der Weg von „schreiben" zurück in den Korpus führt auch hier über die API und
nicht am Modell vorbei (Grundentscheidung 6); er zeigt lediglich auf
`127.0.0.1` statt in ein Containernetz. Verklemmen kann das nicht: Der
Postausgang sendet in einem Arbeitsfaden (`run_in_threadpool`), während der
Ereignisschleife die eingehende Lieferung offensteht.

Wer die Apps getrennt betreiben will — eigene Container, eigene Neustarts —,
nimmt weiterhin die beiden Module `apps/<app>/backend/main.py` einzeln. Dieses
Modul fügt nur zusammen, es ändert an ihnen nichts.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from fastapi import FastAPI

from apps.hoeren.backend.main import app as hoeren
from apps.schreiben.backend.main import BASIS, app as schreiben

Nachricht = dict[str, Any]


def _gehoert_zu_schreiben(pfad: str) -> bool:
    """Der Pfad der App und alles darunter — aber nicht `/schreibendes`."""
    return pfad == BASIS or pfad.startswith(f"{BASIS}/")


async def _lebenszyklus(receive, send) -> None:
    """Start und Ende an beide Apps weitergeben.

    Heute hat keine der beiden einen Handler dafür. Bekäme eine später einen
    und dieser Verteiler reichte ihn nicht durch, bliebe er unbemerkt aus —
    ein Fehler, den niemand sähe, bis etwas fehlt.
    """
    await receive()  # lifespan.startup
    async with AsyncExitStack() as stapel:
        try:
            for teil in (hoeren, schreiben):
                await stapel.enter_async_context(teil.router.lifespan_context(teil))
        except Exception as fehler:  # noqa: BLE001 — der Server will nur den Text
            await send({"type": "lifespan.startup.failed", "message": str(fehler)})
            return
        await send({"type": "lifespan.startup.complete"})
        await receive()  # lifespan.shutdown
    await send({"type": "lifespan.shutdown.complete"})


async def app(scope: Nachricht, receive, send) -> None:
    """Der Verteiler selbst: eine Entscheidung, ein Weiterreichen."""
    if scope["type"] == "lifespan":
        await _lebenszyklus(receive, send)
        return

    ziel: FastAPI = schreiben if _gehoert_zu_schreiben(scope["path"]) else hoeren
    await ziel(scope, receive, send)
