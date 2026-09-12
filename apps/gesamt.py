"""Alle drei Apps in einem Prozess - der Betriebsfall auf einem einzelnen Wirt.

Gestartet wird das so:

    uvicorn apps.gesamt:app --host 0.0.0.0 --port 8000

Was sonst der Reverse Proxy tut, tut hier ein Verteiler von dreißig Zeilen:
`/schreiben/…` geht an „schreiben", `/lernen/…` an „lernen", alles andere an
„hören". Der Pfad bleibt dabei unverändert - jede App hängt ihre Wege schon
selbst dorthin, wo sie liegen sollen (`BASIS` in „schreiben" und „lernen").
Draußen genügt darum eine einzige Regel, die auf diesen einen Port zeigt.

Die Trennung, die sonst drei Container leisten, bleibt in der Sache bestehen:
Jede App behält ihre eigene Datenbank und ihre eigene Ablage. Die Zugangsregeln
sind dieselben - alle drei hängen hinter dem Zugang **eines** Sprechers und
leiten seine Kennung daraus ab; es ist derselbe Zugang, weil es derselbe Mensch
ist. Geteilt wird nur der Prozess.

**Was hier nicht mitläuft: der Trainer.** „lernen" liefert eine Oberfläche aus
und legt Aufträge an; gerechnet wird in einem eigenen Container mit einer
Karte (`apps/lernen/training/`). Er hängt an keinem dieser Wege, sondern am
geteilten Datenverzeichnis - deshalb kann dieser Prozess neu starten, während
ein Training läuft.

Der Weg von „schreiben" zurück in den Korpus führt auch hier über die API und
nicht am Modell vorbei (Grundentscheidung 6); er zeigt lediglich auf
`127.0.0.1` statt in ein Containernetz. Verklemmen kann das nicht: Der
Postausgang sendet in einem Arbeitsfaden (`run_in_threadpool`), während der
Ereignisschleife die eingehende Lieferung offensteht.

Wer die Apps getrennt betreiben will - eigene Container, eigene Neustarts -,
nimmt weiterhin die Module `apps/<app>/backend/main.py` einzeln. Dieses Modul
fügt nur zusammen, es ändert an ihnen nichts.
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

    Die Gleichheit steht mit Absicht daneben: Ohne sie träfe `/schreibendes`
    dieselbe App wie `/schreiben/…`, und ein Tippfehler landete in einer
    fremden Oberfläche statt in einem 404.
    """
    for basis, app_teil in UNTERAPPS:
        if pfad == basis or pfad.startswith(f"{basis}/"):
            return app_teil
    return hoeren


async def _lebenszyklus(receive, send) -> None:
    """Start und Ende an beide Apps weitergeben.

    Heute hat keine der drei einen Handler dafür. Bekäme eine später einen
    und dieser Verteiler reichte ihn nicht durch, bliebe er unbemerkt aus -
    ein Fehler, den niemand sähe, bis etwas fehlt.
    """
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
