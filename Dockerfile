# Ein Abbild für die ganze App: „hören" auf der Wurzel, „lernen" unter /lernen,
# „schreiben" unter /schreiben, alle drei hinter einem uvicorn (siehe
# apps/gesamt.py).
#
# Die Dockerfiles unter apps/ bleiben daneben bestehen - sie sind der Weg, die
# Apps getrennt zu betreiben. Dieses hier ist der Weg für einen einzelnen
# Wirt: ein Abbild, ein Port, eine Regel im Reverse Proxy.
#
# Was hier **nicht** drin ist: torch und alles, was ein Feintuning braucht.
# „lernen" liefert hier nur seine Oberfläche aus und legt Aufträge an;
# trainiert wird im Abbild unter apps/lernen/training/, das eine Karte verlangt.
#
# Was hier **wohl** drin ist, seit dem Umbau auf ein gemeinsames Rechenwerk:
# cuBLAS und cuDNN. Diktieren und die Auswertung nehmen die Karte, wenn eine da
# ist (`wortlaut/rechenwerk.py`) - das ist der Unterschied zwischen vier
# Sekunden und einer Viertelsekunde je Aufnahme. Die beiden Bibliotheken wiegen
# gut zwei Gigabyte im Abbild, ändern aber nichts an der Startzeit: Geladen
# wird erst, wenn zum ersten Mal erkannt wird, und ohne Karte bleiben sie
# unberührt liegen.

# ── Stufe 1: alle drei Frontends bauen ──────────────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /bau
# Erst die Sperrdateien, dann der Rest: So bleibt die Installation im Cache,
# solange sich an den Abhängigkeiten nichts ändert.
COPY apps/hoeren/frontend/package*.json ./apps/hoeren/frontend/
COPY apps/lernen/frontend/package*.json ./apps/lernen/frontend/
COPY apps/schreiben/frontend/package*.json ./apps/schreiben/frontend/
# `npm ci` statt `npm install`: baut genau das, was in package-lock.json steht.
RUN cd apps/hoeren/frontend && npm ci \
    && cd ../../lernen/frontend && npm ci \
    && cd ../../schreiben/frontend && npm ci
COPY packages/ui ./packages/ui
COPY assets ./assets
COPY apps/hoeren/frontend ./apps/hoeren/frontend
COPY apps/lernen/frontend ./apps/lernen/frontend
COPY apps/schreiben/frontend ./apps/schreiben/frontend
RUN cd apps/hoeren/frontend && npm run build \
    && cd ../../lernen/frontend && npm run build \
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
COPY apps/lernen ./apps/lernen
COPY apps/schreiben ./apps/schreiben
COPY scripts ./scripts
# `.[asr,gpu]` ist das Projekt samt faster-whisper und den CUDA-Bibliotheken
# (siehe pyproject.toml). Beides ist in diesem Abbild Pflicht: „schreiben"
# läuft hier mit, und die Auswertung von „hören" ebenso.
RUN pip install --no-cache-dir ".[asr,gpu]"

# Wo CTranslate2 cuBLAS und cuDNN findet. Sie kommen als Python-Räder und
# landen deshalb nicht in /usr/lib, wo der Lader von sich aus sucht - ohne
# diese Zeile meldet die Karte sich als nicht vorhanden, und alles rechnet
# stillschweigend auf dem Prozessor weiter.
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib

COPY --from=frontend /bau/apps/hoeren/frontend/dist ./apps/hoeren/frontend/dist
COPY --from=frontend /bau/apps/lernen/frontend/dist ./apps/lernen/frontend/dist
COPY --from=frontend /bau/apps/schreiben/frontend/dist ./apps/schreiben/frontend/dist

# Das Whisper-Modell landet im Volume und nicht im Abbild; ohne diesen Pfad
# lädt es jeder Neustart des Containers erneut herunter.
ENV HF_HOME=/srv/wortlaut/data/.cache/huggingface

EXPOSE 8000
CMD ["uvicorn", "apps.gesamt:app", "--host", "0.0.0.0", "--port", "8000"]
