"""App „hören" — Sprachproben sammeln.

Start in der Entwicklung (aus dem Repository-Wurzelverzeichnis):

    uv run uvicorn apps.hoeren.backend.main:app --reload

Die Wege teilen sich nach dem, was sie brauchen: Sprecherprofile anzulegen und
Zugänge auszugeben ist Sache der Verwaltung (`WORTLAUT_AUTH_TOKEN`), über alle
Korpora hinweg sehen und löschen darf allein die Aufsicht
(`WORTLAUT_ADMIN_TOKEN`, siehe `api/admin.py`), alles Übrige verlangt den
Zugang **eines** Sprechers und leitet dessen Kennung daraus ab (siehe
`deps.py`). Im Browser erreichbar ist außerdem das gebaute Frontend,
sofern es vorliegt. Ein CORS-Regelwerk
braucht es nicht: in der Entwicklung leitet Vite `/api` an dieses Backend
weiter (siehe `frontend/vite.config.ts`), im Betrieb liefert dieser Prozess
beides aus.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from wortlaut.web import FrontendDateien

from .api import admin, intake, progress, prompts, recordings, sources, speakers, zugang
from .deps import Verwaltung

app = FastAPI(title="wortlaut · hören", version="0.1.0")

# Die Verwaltung: Profile anlegen und ansehen. Sie kommt an keine Aufnahme
# heran — dafür braucht auch sie den Zugang des jeweiligen Sprechers.
app.include_router(speakers.router, dependencies=[Verwaltung])

# Die Aufsicht: der eine Zugang, der über alle Korpora sieht — einsehen,
# sichern, umbenennen, löschen. Sie trägt ihren Wächter selbst
# (`WORTLAUT_ADMIN_TOKEN`) und ist ohne gesetzten Token vollständig zu.
app.include_router(admin.router)

# Zugänge ausgeben und zurückziehen; die Auskunft „wer bin ich hier" darin
# hat bewusst keinen Wächter (siehe `api/zugang.py`).
app.include_router(zugang.router)

# Alles, was Daten berührt. Der Wächter steckt in `SprecherId`/`Datenbank`:
# ohne Sprecherzugang gibt es keine Datenbank, die sich öffnen ließe.
for router in (
    sources.router,
    prompts.router,
    recordings.router,
    progress.router,
    intake.router,
):
    app.include_router(router)


@app.get("/gesundheit", tags=["Betrieb"])
def gesundheit() -> dict[str, str]:
    """Ohne Token erreichbar, damit Proxy und Compose den Dienst prüfen können."""
    return {"status": "ok"}


# Das gebaute Frontend, falls vorhanden. `html=True` liefert für unbekannte
# Pfade die index.html aus, damit die Routen im Browser direkt aufrufbar sind.
# `FrontendDateien` setzt dazu die Cache-Regeln — ohne die zeigt ein Browser
# nach dem Ausrollen weiter die alte App (siehe `wortlaut/web.py`).
_frontend = Path(__file__).parents[1] / "frontend" / "dist"
if _frontend.is_dir():
    app.mount("/", FrontendDateien(directory=_frontend, html=True), name="frontend")
