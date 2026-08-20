# Ein Abbild für die ganze App: „hören" auf der Wurzel, „schreiben" unter
# /schreiben, beide hinter einem uvicorn (siehe apps/gesamt.py).
#
# Die beiden Dockerfiles unter apps/ bleiben daneben bestehen — sie sind der
# Weg, die Apps getrennt zu betreiben. Dieses hier ist der Weg für einen
# einzelnen Wirt: ein Abbild, ein Port, eine Regel im Reverse Proxy.

# ── Stufe 1: beide Frontends bauen ──────────────────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /bau
# Erst die Sperrdateien, dann der Rest: So bleibt die Installation im Cache,
# solange sich an den Abhängigkeiten nichts ändert.
COPY apps/hoeren/frontend/package*.json ./apps/hoeren/frontend/
COPY apps/schreiben/frontend/package*.json ./apps/schreiben/frontend/
# `npm ci` statt `npm install`: baut genau das, was in package-lock.json steht.
RUN cd apps/hoeren/frontend && npm ci \
    && cd ../../schreiben/frontend && npm ci
COPY packages/ui ./packages/ui
COPY assets ./assets
COPY apps/hoeren/frontend ./apps/hoeren/frontend
COPY apps/schreiben/frontend ./apps/schreiben/frontend
RUN cd apps/hoeren/frontend && npm run build \
    && cd ../../schreiben/frontend && npm run build

# ── Stufe 2: Python und Auslieferung ────────────────────────────────────────
FROM python:3.12-slim
# ffmpeg ist die einzige Systemabhängigkeit: Browser liefern kein WAV.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/wortlaut
COPY pyproject.toml README.md LICENSE ./
COPY packages ./packages
COPY apps/gesamt.py ./apps/gesamt.py
COPY apps/hoeren ./apps/hoeren
COPY apps/schreiben ./apps/schreiben
COPY scripts ./scripts
# `.[asr]` ist das Projekt samt faster-whisper (siehe pyproject.toml). In
# diesem Abbild ist es Pflicht: „schreiben" läuft hier mit.
RUN pip install --no-cache-dir ".[asr]"

COPY --from=frontend /bau/apps/hoeren/frontend/dist ./apps/hoeren/frontend/dist
COPY --from=frontend /bau/apps/schreiben/frontend/dist ./apps/schreiben/frontend/dist

# Das Whisper-Modell landet im Volume und nicht im Abbild; ohne diesen Pfad
# lädt es jeder Neustart des Containers erneut herunter.
ENV HF_HOME=/srv/wortlaut/data/.cache/huggingface

EXPOSE 8000
CMD ["uvicorn", "apps.gesamt:app", "--host", "0.0.0.0", "--port", "8000"]
