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

# ── Stufe 1: die drei Frontends, jede App für sich ──────────────────────────
#
# Drei Stufen und nicht eine, und das ist keine Ordnungsfrage, sondern eine
# Frage der Abhängigkeit: Innerhalb einer Stufe hängen die Schichten in einer
# Reihe, und was unter einer verworfenen Schicht steht, wird mit verworfen -
# auch wenn es mit ihr nichts zu tun hat. Eine geänderte Zeile in „lernen"
# baute deshalb „schreiben" gleich mit; jetzt baut sie „lernen" und sonst
# nichts (gemessen: 8 s auf 6 s). Als eigene Stufen haben die drei nichts
# miteinander zu tun, und BuildKit nimmt sie sich deshalb gleichzeitig vor -
# das zeigt sich dort, wo wirklich alle drei müssen: Eine Änderung an
# `packages/ui` kostete in Reihe 14 s reine Bauzeit, nebeneinander 6.
#
# Was sie doch teilen, steht in jeder von ihnen noch einmal: `packages/ui` und
# `assets`. Das ist richtig so - ändert sich dort etwas, geht es in alle drei
# Bündel ein, also müssen auch alle drei neu gebaut werden. Es steht nur
# **unter** `npm ci`, damit eine geänderte Svelte-Datei nicht die Installation
# verwirft.
#
# `npm ci` statt `npm install`: baut genau das, was in package-lock.json steht.
# Der Mount darunter ist der Paketspeicher von npm - außerhalb des Abbilds,
# und er erspart den Weg ins Netz, wenn eine Schicht doch neu gebaut wird. Je
# App ein eigener Speicher (`id=`), denn die drei Stufen laufen gleichzeitig,
# und ein gemeinsames Verzeichnis wäre genau das, worüber sie stolpern
# könnten. Der Preis sind ein paar Dutzend Megabyte doppelt - auf einer Platte,
# die ohnehin Gigabyte an Bauspeicher hält.
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

# `.[asr,gpu,vorlesen,ocr]` ist das Projekt samt faster-whisper, den
# CUDA-Bibliotheken, Piper und der Zeichenerkennung (siehe pyproject.toml). Die ersten beiden sind in
# diesem Abbild Pflicht: „schreiben" läuft hier mit, und die Auswertung von
# „hören" ebenso.
#
# Piper ist es nicht - ohne liest der Browser vor wie bisher -, wiegt aber
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

COPY --from=frontend-hoeren /bau/apps/hoeren/frontend/dist ./apps/hoeren/frontend/dist
COPY --from=frontend-lernen /bau/apps/lernen/frontend/dist ./apps/lernen/frontend/dist
COPY --from=frontend-schreiben /bau/apps/schreiben/frontend/dist ./apps/schreiben/frontend/dist

# Wann dieses Abbild entstanden ist.
#
# **Warum hier unten und nicht im Frontend.** Das Baudatum stand bisher allein
# im JavaScript-Bündel (`packages/ui/bau.ts`, gesetzt über `define` in der
# Vite-Konfiguration). Das ist genau so lange richtig, wie sich am Frontend
# etwas ändert: Wird nur das Backend angefasst, sind die Frontend-Stufen
# unverändert, BuildKit nimmt sie aus dem Zwischenspeicher - samt des Datums,
# das beim letzten Frontend-Bau darin festgeschrieben wurde. Der Seitenfuß
# zeigte dann tagelang dieselbe Uhrzeit, während dreimal ausgerollt wurde.
#
# Diese Zeile steht **unter** allen `COPY` dieser Stufe und erbt damit deren
# Zwischenspeicher: Ändert sich irgendetwas am ausgelieferten Stand - Backend,
# Skripte, Frontend -, entsteht sie neu. Ändert sich nichts, bleibt sie stehen,
# und das ist ebenso richtig: Dann läuft auch nichts Neues.
RUN date -u +%Y-%m-%dT%H:%M:%SZ > /srv/wortlaut/STAND

# Die Grundmodelle landen in einem eigenen Ablagepfad und nicht im Abbild;
# ohne diesen Pfad lädt sie jeder Neustart des Containers erneut herunter.
# Getrennt vom Datenverzeichnis, weil sie das Gegenteil der Daten sind: von
# Hugging Face jederzeit neu zu holen und mehrere Gigabyte schwer. Wohin auf
# dem Wirt, entscheidet die compose.yaml.
ENV HF_HOME=/srv/wortlaut/modellcache

EXPOSE 8000
CMD ["uvicorn", "apps.gesamt:app", "--host", "0.0.0.0", "--port", "8000"]
