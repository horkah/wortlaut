# Zwei Stufen: Frontend bauen, dann in das Python-Abbild legen.
FROM node:22-slim AS frontend
WORKDIR /bau
COPY apps/hoeren/frontend/package*.json ./apps/hoeren/frontend/
# `npm ci` statt `npm install`: baut genau das, was in package-lock.json steht.
RUN cd apps/hoeren/frontend && npm ci
COPY packages/ui ./packages/ui
# Die Kopfzeile bindet das Zeichen als Quelltext ein
# (packages/ui/Kopfleiste.svelte) — ohne assets/ bricht der Bau ab.
COPY assets ./assets
COPY apps/hoeren/frontend ./apps/hoeren/frontend
RUN cd apps/hoeren/frontend && npm run build

FROM python:3.12-slim
# ffmpeg ist die einzige Systemabhängigkeit: Browser liefern kein WAV.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/wortlaut
COPY pyproject.toml README.md LICENSE ./
COPY packages ./packages
COPY apps/hoeren ./apps/hoeren
RUN pip install --no-cache-dir .

COPY --from=frontend /bau/apps/hoeren/frontend/dist ./apps/hoeren/frontend/dist

EXPOSE 8000
CMD ["uvicorn", "apps.hoeren.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
