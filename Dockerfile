# Ein Abbild für die ganze App: „hören" auf der Wurzel, „lernen" unter /lernen,
# „schreiben" unter /schreiben, alle drei hinter einem uvicorn (siehe
# apps/gesamt.py).
#
# Die Dockerfiles unter apps/ sind der Weg, die Apps getrennt zu betreiben.
# Dieses hier ist der Weg für einen einzelnen Wirt: ein Abbild, ein Port, eine
# Regel im Reverse Proxy.
#
# Was hier **nicht** drin ist: torch und alles, was ein Feintuning braucht.
# „lernen" liefert hier nur seine Oberfläche aus und legt Aufträge an;
# trainiert wird im Abbild unter apps/lernen/training/, das eine Karte verlangt.
#
# Was hier **wohl** drin ist: cuBLAS und cuDNN. Diktieren und Auswertung
# nehmen die Karte, wenn eine da ist (`wortlaut/rechenwerk.py`) - vier Sekunden
# gegen eine Viertelsekunde je Aufnahme. Gut zwei Gigabyte im Abbild, geladen
# erst beim ersten Erkennen.

# ── Stufe 1: die drei Frontends, jede App für sich ──────────────────────────
#
# Je App eine Stufe: Eine Änderung in einer App baut nur sie, und BuildKit
# baut die Stufen gleichzeitig. `packages/ui` und `assets` stehen in jeder -
# sie gehen in alle Bündel ein -, aber **unter** `npm ci`, damit eine
# geänderte Svelte-Datei die Installation nicht verwirft.
#
# `npm ci` statt `npm install`: baut genau das, was in package-lock.json steht.
# Der Mount ist der Paketspeicher von npm, außerhalb des Abbilds; je App ein
# eigener (`id=`), weil die Stufen gleichzeitig laufen.
FROM node:22-slim AS frontendgrund
WORKDIR /bau

FROM frontendgrund AS frontend-hoeren
COPY apps/hoeren/frontend/package*.json ./apps/hoeren/frontend/
RUN --mount=type=cache,target=/root/.npm,id=npm-hoeren \
    cd apps/hoeren/frontend && npm ci
COPY packages/ui ./packages/ui
COPY assets ./assets
COPY apps/hoeren/frontend ./apps/hoeren/frontend
RUN cd apps/hoeren/frontend && npm run build

FROM frontendgrund AS frontend-lernen
COPY apps/lernen/frontend/package*.json ./apps/lernen/frontend/
RUN --mount=type=cache,target=/root/.npm,id=npm-lernen \
    cd apps/lernen/frontend && npm ci
COPY packages/ui ./packages/ui
COPY assets ./assets
COPY apps/lernen/frontend ./apps/lernen/frontend
RUN cd apps/lernen/frontend && npm run build

FROM frontendgrund AS frontend-schreiben
COPY apps/schreiben/frontend/package*.json ./apps/schreiben/frontend/
RUN --mount=type=cache,target=/root/.npm,id=npm-schreiben \
    cd apps/schreiben/frontend && npm ci
COPY packages/ui ./packages/ui
COPY assets ./assets
COPY apps/schreiben/frontend ./apps/schreiben/frontend
RUN cd apps/schreiben/frontend && npm run build

# ── Stufe 2: Python und Auslieferung ────────────────────────────────────────
FROM python:3.12-slim
# Zwei Systemabhängigkeiten, und beide aus demselben Grund: Was der Mensch
# hereingibt, ist kein Text.
#
# `ffmpeg`, weil Browser kein WAV liefern.
#
# `tesseract-ocr`, weil eine Vorlage auch ein Foto sein darf - ein
# Zeitungsausschnitt, eine Buchseite, ein Brief (`wortlaut/text/ocr.py`). Das
# ist der Weg, der ohne Tastatur auskommt, und er läuft hier und nicht bei
# einem Dienst: Ein fotografierter Brief ist womöglich das Persönlichste, was
# diese App je zu sehen bekommt (`docs/datenschutz.md`).
#
# Die Sprachdateien einzeln, nicht `tesseract-ocr-all`: Zwei wiegen wenige
# Megabyte, alle zusammen über ein Gigabyte. Wer eine dritte Sprache führt,
# trägt sie hier nach - dieselbe Liste wie in `sprachen.UNTERSTUETZT`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Tesseract mit **einem** Rechenfaden - und warum das schneller ist.
#
# Ein Bild wird mehrfach gelesen, je Fassung und Seitenart einmal
# (`wortlaut/text/ocr.py`). Nebeneinander gelesen ist das ohne Grenze langsamer
# als nacheinander - gemessen an vier Durchgängen 8,3 gegen 5,7 Sekunden -,
# denn jede Ausführung greift über OpenMP nach allen Kernen, und sie nehmen
# sie einander weg. Mit `OMP_THREAD_LIMIT=1` je Ausführung: **1,6 Sekunden**,
# bei Zeichen für Zeichen demselben Ergebnis.
#
# Warum ein Hüllskript und keine Umgebungsvariable des Containers: Die Grenze
# gilt für OpenMP überhaupt, und in diesem Abbild rechnet auch Whisper. Ob ihm
# das schadet, ließ sich auf einem Wirt, der nebenher trainiert, nicht sauber
# messen (14 bis 22 Sekunden für dieselbe Aufnahme). Eine Grenze, die man nicht
# freisprechen kann, gehört nicht in die Umgebung aller, sondern an den einen
# Aufruf, um den es geht.
RUN printf '#!/bin/sh\n# Siehe Dockerfile: ein Faden je Aufruf, dafür mehrere Aufrufe zugleich.\nOMP_THREAD_LIMIT=1 exec /usr/bin/tesseract "$@"\n' \
      > /usr/local/bin/tesseract-einfaedig \
    && chmod +x /usr/local/bin/tesseract-einfaedig

WORKDIR /srv/wortlaut

# Erst die Abhängigkeiten, dann der Code - der Unterschied zwischen zwei
# Sekunden und vier Minuten: `pip install` holt gut anderthalb Gigabyte
# CUDA-Räder, und jede Zeile davor, die sich ändert, lässt ihn von vorn
# beginnen - ein geändertes Wort in Frontend oder `wortlaut/` ebenso.
#
# Die Abhängigkeiten deshalb über einen **Platzhalter**: hatchling will das
# Paketverzeichnis sehen, um ein Rad zu bauen (siehe
# `[tool.hatch.build.targets.wheel]` in pyproject.toml), der Inhalt ist ihm
# dabei gleich. Diese Schicht hängt damit allein an pyproject.toml - an der
# Datei, in der die Abhängigkeiten tatsächlich stehen.
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p packages/wortlaut/src/wortlaut \
    && touch packages/wortlaut/src/wortlaut/__init__.py

# `.[asr,gpu,vorlesen,ocr]` ist das Projekt samt faster-whisper, den
# CUDA-Bibliotheken, Piper und der Zeichenerkennung (siehe pyproject.toml).
# Die ersten beiden sind in diesem Abbild Pflicht: „schreiben" läuft hier mit,
# und die Auswertung von „hören" ebenso.
#
# Piper ist es nicht - ohne liest der Browser vor -, wiegt aber
# wenige Megabyte und teilt sich onnxruntime mit faster-whisper. Die Stimmen
# liegen ohnehin außerhalb des Abbilds (`scripts/vorlesen.py`).
#
# Der Mount ist der Radspeicher von pip. Er liegt außerhalb des Abbilds - er
# macht es also kein Byte größer, anders als ein `--no-cache-dir`, das es nur
# scheinbar täte: Die Schicht entsteht ohnehin erst nach dem Aufräumen. Was er
# ändert, ist der Weg bei einer **neuen** Abhängigkeit: Die anderthalb
# Gigabyte kommen dann von der Platte statt aus dem Netz.
#
# Und er braucht dafür **keine** `# syntax=`-Zeile am Dateianfang, auch wenn
# jede Anleitung das behauptet: Der eingebaute Dockerfile-Übersetzer von
# BuildKit kennt `--mount=type=cache` längst (geprüft mit Docker 29.8 / buildx
# 0.37). Die Zeile nachzutragen hieße, bei jedem Bau ein Frontend-Abbild aus
# dem Netz zu holen - ein Grund, sie gerade nicht zu setzen.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ".[asr,gpu,vorlesen,ocr]"

# Dann die Bibliothek selbst über den Platzhalter. `--no-deps`, weil oben
# schon alles steht; `--force-reinstall`, weil die Fassung dieselbe ist (0.1.0)
# und pip sonst „ist schon da" sagt und den Platzhalter stehen ließe.
#
# Nur `packages/wortlaut` und nicht `packages/`: Daneben liegt `packages/ui`,
# und das ist Frontend. Es hat in der Python-Installation nichts zu suchen -
# und eine geänderte Svelte-Datei darin hat erst recht keinen Grund, hier eine
# Schicht zu verwerfen.
COPY packages/wortlaut ./packages/wortlaut
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps --force-reinstall .

# Wo CTranslate2 cuBLAS und cuDNN findet. Sie kommen als Python-Räder und
# landen deshalb nicht in /usr/lib, wo der Lader von sich aus sucht - ohne
# diese Zeile meldet die Karte sich als nicht vorhanden, und alles rechnet
# stillschweigend auf dem Prozessor weiter.
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib

COPY apps/gesamt.py ./apps/gesamt.py
COPY apps/hoeren ./apps/hoeren
COPY apps/lernen ./apps/lernen
COPY apps/schreiben ./apps/schreiben
COPY scripts ./scripts

COPY --from=frontend-hoeren /bau/apps/hoeren/frontend/dist ./apps/hoeren/frontend/dist
COPY --from=frontend-lernen /bau/apps/lernen/frontend/dist ./apps/lernen/frontend/dist
COPY --from=frontend-schreiben /bau/apps/schreiben/frontend/dist ./apps/schreiben/frontend/dist

# Wann dieses Abbild entstanden ist.
#
# Hier unten und nicht nur im Bündel (`packages/ui/bau.ts`): Bei einer reinen
# Backend-Änderung kämen die Frontend-Stufen samt altem Datum aus dem
# Zwischenspeicher. Unter allen `COPY` entsteht die Zeile neu, sobald sich am
# ausgelieferten Stand irgendetwas ändert.
RUN date -u +%Y-%m-%dT%H:%M:%SZ > /srv/wortlaut/STAND

# Die Grundmodelle landen in einem eigenen Ablagepfad und nicht im Abbild;
# ohne diesen Pfad lädt sie jeder Neustart des Containers erneut herunter.
# Getrennt vom Datenverzeichnis, weil sie das Gegenteil der Daten sind: von
# Hugging Face jederzeit neu zu holen und mehrere Gigabyte schwer. Wohin auf
# dem Wirt, entscheidet die compose.yaml.
ENV HF_HOME=/srv/wortlaut/modellcache

EXPOSE 8000
CMD ["uvicorn", "apps.gesamt:app", "--host", "0.0.0.0", "--port", "8000"]
