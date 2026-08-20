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
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import model, outbox, segments, sessions

# Der Ort dieser App unter der gemeinsamen Domain. Alles hängt darunter, auch
# die API: So genügt vor den Containern eine Regel, die den Pfad unverändert
# durchreicht (`/schreiben/` → dieser Dienst). Ein Proxy, der das Präfix
# abschneidet, ist damit nicht mehr nötig — dass genau das einmal vergessen
# wurde, hat die App unerreichbar gemacht.
#
# Wer die App verschiebt, ändert drei Stellen zusammen: dieses `BASIS`, das
# `base` in `frontend/vite.config.ts` und den Pfad in `packages/ui/apps.ts`.
BASIS = "/schreiben"

app = FastAPI(title="wortlaut · schreiben", version="0.1.0")

for router in (sessions.router, segments.router, model.router, outbox.router):
    app.include_router(router, prefix=BASIS)


@app.get("/gesundheit", tags=["Betrieb"])
def gesundheit() -> dict[str, str]:
    """Ohne Umschweife erreichbar, damit Proxy und Compose den Dienst prüfen können.

    Bleibt auf der Wurzel: Eine Überwachung spricht den Container unmittelbar
    an und muss von der Pfadverteilung nichts wissen.
    """
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def wurzel() -> RedirectResponse:
    """Wer den Container ohne Pfad anspricht, landet trotzdem in der App."""
    return RedirectResponse(f"{BASIS}/")


# Das gebaute Frontend, falls vorhanden. Es hängt unter demselben `BASIS` wie
# die API — dort sucht auch das gebaute HTML seine Dateien (`base` in der
# Vite-Konfiguration). `html=True` liefert für `/schreiben/` die index.html;
# die Ansichten dieser App stehen im Hash und brauchen nichts weiter.
_frontend = Path(__file__).parents[1] / "frontend" / "dist"
if _frontend.is_dir():
    app.mount(BASIS, StaticFiles(directory=_frontend, html=True), name="frontend")
