"""App „hören" — Sprachproben sammeln.

Start in der Entwicklung (aus dem Repository-Wurzelverzeichnis):

    uv run uvicorn apps.hoeren.backend.main:app --reload

Alle `/api`-Endpunkte hängen hinter der Token-Prüfung; im Browser erreichbar
ist außerdem das gebaute Frontend, sofern es vorliegt. Ein CORS-Regelwerk
braucht es nicht: in der Entwicklung leitet Vite `/api` an dieses Backend
weiter (siehe `frontend/vite.config.ts`), im Betrieb liefert dieser Prozess
beides aus.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import intake, progress, prompts, recordings, sources, speakers
from .deps import Authentifiziert

app = FastAPI(title="wortlaut · hören", version="0.1.0")

for router in (
    speakers.router,
    sources.router,
    prompts.router,
    recordings.router,
    progress.router,
    intake.router,
):
    app.include_router(router, dependencies=[Authentifiziert])


@app.get("/gesundheit", tags=["Betrieb"])
def gesundheit() -> dict[str, str]:
    """Ohne Token erreichbar, damit Proxy und Compose den Dienst prüfen können."""
    return {"status": "ok"}


# Das gebaute Frontend, falls vorhanden. `html=True` liefert für unbekannte
# Pfade die index.html aus, damit die Routen im Browser direkt aufrufbar sind.
_frontend = Path(__file__).parents[1] / "frontend" / "dist"
if _frontend.is_dir():
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
