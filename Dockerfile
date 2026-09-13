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
#
# Je App ein Paar aus COPY und RUN, und nicht drei COPY vor einem RUN. Der
# Unterschied zeigt sich, sobald **eine** Sperrdatei sich ändert: Bei einem
# gemeinsamen RUN hängt der an allen dreien, und ein neues Paket in „hören"
# ließ auch „lernen" und „schreiben" von vorn installieren.
#
# `npm ci` statt `npm install`: baut genau das, was in package-lock.json steht.
# Der Mount darunter ist der Paketspeicher von npm - er liegt außerhalb des
# Abbilds, überlebt den Bau und erspart den Weg ins Netz, wenn eine Schicht
# doch einmal neu gebaut wird.
COPY apps/hoeren/frontend/package*.json ./apps/hoeren/frontend/
RUN --mount=type=cache,target=/root/.npm \
    cd apps/hoeren/frontend && npm ci
COPY apps/lernen/frontend/package*.json ./apps/lernen/frontend/
RUN --mount=type=cache,target=/root/.npm \
    cd apps/lernen/frontend && npm ci
COPY apps/schreiben/frontend/package*.json ./apps/schreiben/frontend/
RUN --mount=type=cache,target=/root/.npm \
    cd apps/schreiben/frontend && npm ci

# Das Geteilte zuerst: Was hier liegt, geht in alle drei Bündel ein, also
# müssen danach auch alle drei neu gebaut werden. Die App-Quellen dahinter,
# je App eine Schicht - eine Änderung in „lernen" baut dann nur „lernen".
COPY packages/ui ./packages/ui
COPY assets ./assets
COPY apps/hoeren/frontend ./apps/hoeren/frontend
RUN cd apps/hoeren/frontend && npm run build
COPY apps/lernen/frontend ./apps/lernen/frontend
RUN cd apps/lernen/frontend && npm run build
COPY apps/schreiben/frontend ./apps/schreiben/frontend
RUN cd apps/schreiben/frontend && npm run build

# ── Stufe 2: Python und Auslieferung ────────────────────────────────────────
FROM python:3.12-slim
# ffmpeg ist die einzige Systemabhängigkeit: Browser liefern kein WAV.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/wortlaut

# Erst das, was die Installation braucht, dann die Installation, dann der Rest.
# Die Reihenfolge ist der Unterschied zwischen zwei Sekunden und vier Minuten:
# `pip install` holt gut anderthalb Gigabyte CUDA-Räder, und jede Zeile davor,
# die sich ändert, lässt ihn von vorn beginnen. Solange die Apps über dem
# Befehl standen, tat das auch eine einzige geänderte Zeile im Frontend - also
# so gut wie jede Änderung an diesem Projekt.
#
# Danach stand die Bibliothek darüber, und das war die zweite Hälfte desselben
# Fehlers: Ein geändertes Wort in `wortlaut/` lud 1,35 GB cuBLAS und cuDNN neu,
# obwohl sich an keiner Abhängigkeit etwas geändert hatte. Gemessen: 234
# Sekunden für eine Zeile.
#
# Deshalb jetzt in zwei Schritten. Zuerst die Abhängigkeiten, und zwar über
# einen **Platzhalter**: hatchling will das Paketverzeichnis sehen, um ein Rad
# zu bauen (siehe `[tool.hatch.build.targets.wheel]` in pyproject.toml), der
# Inhalt ist ihm dabei gleich. Diese Schicht hängt damit allein an
# pyproject.toml - an der Datei, in der die Abhängigkeiten tatsächlich stehen.
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p packages/wortlaut/src/wortlaut \
    && touch packages/wortlaut/src/wortlaut/__init__.py

# `.[asr,gpu]` ist das Projekt samt faster-whisper und den CUDA-Bibliotheken
# (siehe pyproject.toml). Beides ist in diesem Abbild Pflicht: „schreiben"
# läuft hier mit, und die Auswertung von „hören" ebenso.
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
    pip install ".[asr,gpu]"

# Und jetzt die Bibliothek selbst über den Platzhalter. `--no-deps`, weil oben
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

COPY --from=frontend /bau/apps/hoeren/frontend/dist ./apps/hoeren/frontend/dist
COPY --from=frontend /bau/apps/lernen/frontend/dist ./apps/lernen/frontend/dist
COPY --from=frontend /bau/apps/schreiben/frontend/dist ./apps/schreiben/frontend/dist

# Die Grundmodelle landen in einem eigenen Ablagepfad und nicht im Abbild;
# ohne diesen Pfad lädt sie jeder Neustart des Containers erneut herunter.
# Getrennt vom Datenverzeichnis, weil sie das Gegenteil der Daten sind: von
# Hugging Face jederzeit neu zu holen und mehrere Gigabyte schwer. Wohin auf
# dem Wirt, entscheidet die compose.yaml.
ENV HF_HOME=/srv/wortlaut/modellcache

EXPOSE 8000
CMD ["uvicorn", "apps.gesamt:app", "--host", "0.0.0.0", "--port", "8000"]
