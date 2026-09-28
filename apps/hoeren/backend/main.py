"""App „hören" - Sprachproben sammeln.

Start in der Entwicklung (aus dem Repository-Wurzelverzeichnis):

    uv run uvicorn apps.hoeren.backend.main:app --reload

Profile und Zugänge gehören der Verwaltung (`WORTLAUT_AUTH_TOKEN`), der Blick
über alle Korpora der Aufsicht (`WORTLAUT_ADMIN_TOKEN`, `api/admin.py`), alles
Übrige verlangt den Zugang eines Sprechers und leitet dessen Kennung daraus ab
(`deps.py`). CORS braucht es nicht: In der Entwicklung leitet Vite `/api`
hierher, im Betrieb liefert dieser Prozess auch das Frontend aus.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from wortlaut import web
from wortlaut.web import FrontendDateien

from .api import (
    admin,
    auswertung,
    fehlerlog,
    intake,
    konto,
    progress,
    prompts,
    recordings,
    sources,
    speakers,
    sprachen,
    system,
    zugang,
    zuschnitt,
)
from .deps import Verwaltung

app = FastAPI(title="wortlaut · hören", version="0.1.0")

# Die Verwaltung: Profile anlegen und ansehen, keine Aufnahme.
app.include_router(speakers.router, dependencies=[Verwaltung])

# Die Aufsicht trägt ihren Wächter selbst und ist ohne Token zu.
app.include_router(admin.router)

# Zugänge ausgeben und zurückziehen, dazu „wer bin ich hier".
app.include_router(zugang.router)

app.include_router(sprachen.router)
app.include_router(system.router)
# Der Wächter steckt im Weg selbst: Verwaltung, Aufsicht oder Trainerschlüssel.
app.include_router(fehlerlog.router)

# Alles, was Daten berührt. Der Wächter steckt in `SprecherId`/`Datenbank`.
for router in (
    sources.router,
    prompts.router,
    recordings.router,
    progress.router,
    intake.router,
    konto.router,
    auswertung.router,
    # Dazu `WORTLAUT_EDITOR_KEY`.
    zuschnitt.router,
):
    app.include_router(router)


@app.get("/gesundheit", tags=["Betrieb"])
def gesundheit() -> dict[str, str]:
    """Ohne Token, für Proxy und Healthcheck. `stand` nennt, wann das laufende
    Abbild gebaut wurde - vom Prozess und nicht aus dem Frontend-Bündel, dessen
    Schicht aus dem Bauspeicher kommen kann."""
    return {"status": "ok", "stand": web.stand()}


# Das gebaute Frontend, falls vorhanden, mit Cache-Regeln (`wortlaut/web.py`).
_frontend = Path(__file__).parents[1] / "frontend" / "dist"
if _frontend.is_dir():
    app.mount("/", FrontendDateien(directory=_frontend, html=True), name="frontend")
