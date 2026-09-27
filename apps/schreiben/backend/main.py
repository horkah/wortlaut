"""App „schreiben" - diktieren, vorlesen lassen, Fehler neu einsprechen.

Start in der Entwicklung (aus dem Repository-Wurzelverzeichnis):

    uv run uvicorn apps.schreiben.backend.main:app --reload --port 8001

Alles hängt am Zugang eines Sprechers (`deps.py`): Das Diktat läuft auf
seinem Modell und fließt in seinen Korpus zurück. Der Zugang kommt über den
persönlichen Link wie bei „hören" - getippt wird nichts.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from wortlaut.web import FrontendDateien

from .api import model, outbox, segments, sessions

# Der Ort unter der gemeinsamen Domain, auch für die API - der Proxy reicht
# den Pfad unverändert durch. Verschieben heißt drei Stellen ändern: `BASIS`,
# `base` in `frontend/vite.config.ts`, den Pfad in `packages/ui/apps.ts`.
BASIS = "/schreiben"

app = FastAPI(title="wortlaut · schreiben", version="0.1.0")

for router in (sessions.router, segments.router, model.router, outbox.router):
    app.include_router(router, prefix=BASIS)


@app.get("/gesundheit", tags=["Betrieb"])
def gesundheit() -> dict[str, str]:
    """Auf der Wurzel, für Proxy und Compose."""
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def wurzel() -> RedirectResponse:
    """Wer den Container ohne Pfad anspricht, landet trotzdem in der App."""
    return RedirectResponse(f"{BASIS}/")


# Das gebaute Frontend unter `BASIS`; die Ansichten stehen im Hash.
_frontend = Path(__file__).parents[1] / "frontend" / "dist"
if _frontend.is_dir():
    app.mount(BASIS, FrontendDateien(directory=_frontend, html=True), name="frontend")
