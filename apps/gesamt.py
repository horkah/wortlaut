"""Alle drei Apps in einem Prozess - der Betriebsfall auf einem einzelnen Wirt.

Gestartet wird das so:

    uvicorn apps.gesamt:app --host 0.0.0.0 --port 8000

`/schreiben/…` geht an „schreiben", `/lernen/…` an „lernen", alles andere an
„hören" - unverändert, denn jede App hängt ihre Wege selbst unter ihren Pfad
(`BASIS`). Draußen genügt eine Regel auf diesen Port. Geteilt wird nur der
Prozess; Datenbanken, Ablagen und Zugangsregeln bleiben je App.

Der Trainer läuft nicht mit: Er hängt am Datenverzeichnis, dieser Prozess darf
also neu starten, während trainiert wird. Die Korrekturen von „schreiben"
gehen auch hier über die API (Grundentscheidung 6), an `127.0.0.1`; der
Postausgang sendet im Arbeitsfaden, verklemmen kann das nicht.

Getrennt betrieben werden die Apps über `apps/<app>/backend/main.py`.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from fastapi import FastAPI

from apps.hoeren.backend.main import app as hoeren
from apps.lernen.backend.main import BASIS as LERNEN, app as lernen
from apps.schreiben.backend.main import BASIS as SCHREIBEN, app as schreiben

Nachricht = dict[str, Any]

# Welche App unter welchem Pfad liegt. „hören" steht nicht darin: Es ist der
# Einstieg und bekommt alles Übrige.
UNTERAPPS = ((SCHREIBEN, schreiben), (LERNEN, lernen))


def _zustaendig(pfad: str) -> FastAPI:
    """Wer diesen Pfad bedient - der Pfad der App und alles darunter.

    Nicht bloß das Präfix: `/schreibendes` gehört nicht zu `/schreiben`.
    """
    for basis, app_teil in UNTERAPPS:
        if pfad == basis or pfad.startswith(f"{basis}/"):
            return app_teil
    return hoeren


async def _lebenszyklus(receive, send) -> None:
    """Start und Ende an alle drei Apps weitergeben, damit ein Handler dafür
    nicht unbemerkt ausfällt."""
    await receive()  # lifespan.startup
    async with AsyncExitStack() as stapel:
        try:
            for teil in (hoeren, lernen, schreiben):
                await stapel.enter_async_context(teil.router.lifespan_context(teil))
        except Exception as fehler:  # noqa: BLE001 - der Server will nur den Text
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

    await _zustaendig(scope["path"])(scope, receive, send)
