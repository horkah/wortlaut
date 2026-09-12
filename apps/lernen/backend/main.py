"""App „lernen" - aus den Proben ein eigenes Modell.

Start in der Entwicklung (aus dem Repository-Wurzelverzeichnis):

    uv run uvicorn apps.lernen.backend.main:app --reload --port 8002

Alles unter `/lernen` - dem Ort dieser App unter der gemeinsamen Domain. Nur
`/gesundheit` bleibt auf der Wurzel: Eine Überwachung spricht den Container
unmittelbar an.

Jeder Weg außer `/gesundheit` verlangt den Sprecherzugang aus „hören" und
leitet die Kennung daraus ab - dieselbe Regel wie in den beiden anderen Apps,
aus demselben Grund (die Bindung zieht der Server, nicht der Aufrufer).

**Was diese App nicht tut: rechnen.** Ein Feintuning braucht torch, CUDA und
einige Gigabyte Abbild. Dieser Prozess liefert eine Oberfläche aus und soll in
Sekunden neu starten. Er legt deshalb nur das Verzeichnis an, an dem der
Trainer einen Auftrag erkennt (`wortlaut/laeufe.py`), und liest, was dieser
hineinschreibt. Der Trainer ist ein eigener Dienst mit einer Karte - siehe
`apps/lernen/training/`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from wortlaut.web import FrontendDateien

from .api import aufteilung, laeufe, modelle

# Wo diese App unter der gemeinsamen Domain liegt. Derselbe Wert steht im
# `base` der Vite-Konfiguration und in `packages/ui/apps.ts`; alle drei müssen
# zusammenpassen, sonst führt der Reiter ins Leere.
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
