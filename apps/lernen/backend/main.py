"""App „lernen" - aus den Proben ein eigenes Modell.

Start in der Entwicklung (aus dem Repository-Wurzelverzeichnis):

    uv run uvicorn apps.lernen.backend.main:app --reload --port 8002

Alles unter `/lernen`, nur `/gesundheit` auf der Wurzel. Jeder Weg sonst
verlangt den Sprecherzugang und leitet die Kennung daraus ab.

Gerechnet wird hier nicht: Diese App legt das Laufverzeichnis an
(`wortlaut/laeufe.py`) und liest, was der Trainer hineinschreibt
(`apps/lernen/training/`).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from wortlaut.web import FrontendDateien

from .api import aufteilung, laeufe, modelle

# Derselbe Pfad wie `base` in der Vite-Konfiguration und in `packages/ui/apps.ts`.
BASIS = "/lernen"

app = FastAPI(title="wortlaut · lernen", version="0.1.0")

for router in (aufteilung.router, laeufe.router, modelle.router):
    app.include_router(router)


@app.get("/gesundheit", tags=["Betrieb"])
def gesundheit() -> dict[str, str]:
    """Ohne Token erreichbar, damit Proxy und Compose den Dienst prüfen können."""
    return {"status": "ok"}


_frontend = Path(__file__).parents[1] / "frontend" / "dist"
if _frontend.is_dir():
    app.mount(BASIS, FrontendDateien(directory=_frontend, html=True), name="frontend")
