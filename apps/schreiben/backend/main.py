"""App „schreiben" — diktieren, vorlesen lassen, Fehler neu einsprechen.

Start in der Entwicklung (aus dem Repository-Wurzelverzeichnis):

    uv run uvicorn apps.schreiben.backend.main:app --reload --port 8001

Anders als „hören" hängt hier nichts hinter einem Token: Die Zielperson kann
schlecht lesen und schreiben, ein Anmeldefeld wäre eine unüberwindbare Hürde
(Grundentscheidung 7). Eine Instanz gehört deshalb ins private Netz oder
hinter einen Zugang, den jemand anderes einrichtet — siehe
`docs/datenschutz.md`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import model, outbox, segments, sessions

app = FastAPI(title="wortlaut · schreiben", version="0.1.0")

for router in (sessions.router, segments.router, model.router, outbox.router):
    app.include_router(router)


@app.get("/gesundheit", tags=["Betrieb"])
def gesundheit() -> dict[str, str]:
    """Ohne Umschweife erreichbar, damit Proxy und Compose den Dienst prüfen können."""
    return {"status": "ok"}


# Das gebaute Frontend, falls vorhanden. `html=True` liefert für unbekannte
# Pfade die index.html aus, damit die Routen im Browser direkt aufrufbar sind.
#
# Die Wege beginnen hier bei `/`, obwohl die App im Betrieb unter `/schreiben/`
# liegt: Caddy schneidet das Präfix ab (`handle_path`), und das gebaute
# Frontend sucht seine Dateien über das `base` seiner Vite-Konfiguration
# darunter. Wer diesen Container ohne Proxy direkt anspricht, bekommt deshalb
# die Seite, aber nicht ihre Dateien — das ist kein Betriebsfall.
_frontend = Path(__file__).parents[1] / "frontend" / "dist"
if _frontend.is_dir():
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
