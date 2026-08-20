# Zwei Stufen: Frontend bauen, dann in das Python-Abbild legen.
FROM node:22-slim AS frontend
WORKDIR /bau
COPY apps/schreiben/frontend/package*.json ./apps/schreiben/frontend/
# `npm ci` statt `npm install`: baut genau das, was in package-lock.json steht.
RUN cd apps/schreiben/frontend && npm ci
COPY packages/ui ./packages/ui
# Die Kopfzeile bindet das Zeichen als Quelltext ein
# (packages/ui/Kopfleiste.svelte) — ohne assets/ bricht der Bau ab.
COPY assets ./assets
COPY apps/schreiben/frontend ./apps/schreiben/frontend
RUN cd apps/schreiben/frontend && npm run build

FROM python:3.12-slim
# ffmpeg ist die einzige Systemabhängigkeit: Browser liefern kein WAV.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/wortlaut
COPY pyproject.toml README.md LICENSE ./
COPY packages ./packages
COPY apps/schreiben ./apps/schreiben
# `.[asr]` ist das Projekt samt faster-whisper (siehe pyproject.toml). Es
# steht dort nicht bei den Grundabhängigkeiten, weil es CTranslate2 und
# Modelldateien nachzieht und allein von dieser App gebraucht wird.
RUN pip install --no-cache-dir ".[asr]"

COPY --from=frontend /bau/apps/schreiben/frontend/dist ./apps/schreiben/frontend/dist

# Das Modell landet im Abbild-Cache von huggingface; ohne diesen Pfad lädt es
# jeder Neustart erneut herunter.
ENV HF_HOME=/srv/wortlaut/data/.cache/huggingface

EXPOSE 8000
CMD ["uvicorn", "apps.schreiben.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
