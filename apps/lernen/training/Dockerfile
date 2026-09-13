# Der Trainings-Container: das, was auf der Karte läuft.
#
# Ein eigenes Abbild und nicht das der Apps, aus einem einzigen Grund: torch
# mit CUDA wiegt gut drei Gigabyte. Der Webdienst braucht davon nichts und soll
# in Sekunden neu starten; dieses Abbild wird einmal gebaut und läuft dann
# monatelang. Verbunden sind beide nur über das Datenverzeichnis - der Läufer
# holt sich Aufträge aus `data/snapshots/` (siehe `wortlaut/laeufe.py`).
#
# Bauen und starten über die compose.yaml des Projekts:
#
#     docker compose --profile training up -d training
#
# Das Profil ist Absicht: Wer keine Karte hat, soll `docker compose up` nicht
# an einem Dienst scheitern sehen, den er nie benutzt.

# Dieselbe Grundlage wie das Abbild der Apps, und das ist eine bewusste Wahl
# gegen das naheliegende `pytorch/pytorch`: Jenes bringt CUDA und torch fertig
# mit, aber mit Python 3.11 - dieses Projekt verlangt 3.12 (`pyproject.toml`).
# Die geteilte Bibliothek `wortlaut` liefe dann hier auf einer anderen Fassung
# als in jedem anderen Container. Ein Unterschied, der lange nichts tut und
# dann etwas Unerklärliches.
#
# CUDA kommt stattdessen aus den torch-Rädern selbst: Sie tragen die nötigen
# Bibliotheken bei sich, und auf dem Wirt genügt der Treiber.
FROM python:3.12-slim

# ffmpeg braucht faster-whisper zum Einlesen der Testaufnahmen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/wortlaut

# torch zuerst und in einer eigenen Schicht: Es ist mit Abstand der größte
# Brocken, und so wird er beim nächsten Bau nicht noch einmal geladen, nur
# weil sich eine Zeile Python geändert hat. `cu121` passt zu Turing (RTX 2080
# Ti, Rechenfähigkeit 7.5) und läuft unter jedem Treiber ab 12.1.
#
# Der Mount ist der Radspeicher von pip - außerhalb des Abbilds, also ohne
# Gewicht darin. Er ist die Versicherung gegen den Tag, an dem diese Schicht
# doch neu gebaut wird: Dann kommen die zweieinhalb Gigabyte von der Platte
# und nicht aus dem Netz. Genau dafür steht hier kein `--no-cache-dir` mehr;
# es hat nie ein Byte im Abbild gespart, sondern nur den Weg ins Netz
# erzwungen.
RUN --mount=type=cache,target=/root/.cache/pip \
        pip install \
        --index-url https://download.pytorch.org/whl/cu121 \
        "torch==2.5.1"

# `transformers` und `peft` für das Training, `faster-whisper` für die
# Bewertung danach, `ctranslate2` für die Umwandlung dazwischen (es kommt mit
# faster-whisper). Die Versionsuntergrenzen sind keine Zier: `transformers`
# hat die Schnittstelle des Trainers mehrfach umgebaut, und
# `Seq2SeqTrainer.compute_loss` bekommt erst ab 4.46 das Argument
# `num_items_in_batch`, auf das der gewichtete Verlust in `finetune.py`
# eingestellt ist.
RUN --mount=type=cache,target=/root/.cache/pip \
        pip install \
        "transformers>=4.46,<5" \
        "peft>=0.13" \
        "accelerate>=1.0" \
        "faster-whisper>=1.1" \
        "pyyaml>=6" \
        "sqlalchemy>=2.0" \
        "pydantic-settings>=2.4"

# Nur, was der Trainer wirklich braucht. Die Apps „hören" und „schreiben"
# liegen nicht in diesem Abbild - es gibt keinen Weg, auf dem dieser Container
# eine ihrer Anfragen beantwortete.
COPY packages ./packages
COPY apps/lernen ./apps/lernen

# Die geteilte Bibliothek und die App über den Suchpfad und nicht über eine
# Installation: `pip install -e .` zöge die Abhängigkeiten der Web-Apps mit
# herein (fastapi, uvicorn, anthropic), die hier nichts zu suchen haben.
ENV PYTHONPATH=/srv/wortlaut:/srv/wortlaut/packages/wortlaut/src

# Die Modelldateien landen in einem eigenen Ablagepfad und nicht im Abbild;
# ohne diesen Pfad lädt sie jeder Neustart des Containers erneut herunter -
# bei whisper-small knapp ein Gigabyte. Derselbe Pfad wie bei „hören", damit
# beide dieselbe Kopie benutzen und nicht jeder seine eigene lädt.
ENV HF_HOME=/srv/wortlaut/modellcache

CMD ["python", "-u", "-m", "apps.lernen.training.laeufer"]
