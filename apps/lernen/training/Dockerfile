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

# Das amtliche PyTorch-Abbild bringt CUDA, cuDNN und ein dazu passendes torch
# schon mit. Selbst zu installieren hieße, drei Versionsbäume von Hand
# aufeinander abzustimmen - und beim nächsten Update noch einmal.
FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime

# ffmpeg braucht faster-whisper zum Einlesen; das Übrige ist für die
# Umwandlung nach CTranslate2 nötig.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/wortlaut

# Nur, was der Trainer wirklich braucht. Die Apps „hören" und „schreiben"
# liegen nicht in diesem Abbild - es gibt keinen Weg, auf dem dieser Container
# eine ihrer Anfragen beantwortete.
COPY pyproject.toml README.md LICENSE ./
COPY packages ./packages
COPY apps/lernen ./apps/lernen

# `transformers` und `peft` für das Training, `faster-whisper` für die
# Bewertung danach, `ctranslate2` für die Umwandlung dazwischen. Die
# Versionsuntergrenzen sind keine Zier: `transformers` hat die Schnittstelle
# des Trainers mehrfach umgebaut, und `Seq2SeqTrainer.compute_loss` bekommt
# erst ab 4.46 das Argument `num_items_in_batch`, auf das der gewichtete
# Verlust in `finetune.py` eingestellt ist.
RUN pip install --no-cache-dir \
        "transformers>=4.46,<5" \
        "peft>=0.13" \
        "accelerate>=1.0" \
        "faster-whisper>=1.1" \
        "pyyaml>=6" \
        "sqlalchemy>=2.0" \
        "pydantic-settings>=2.4" \
    && pip install --no-cache-dir --no-deps -e .

# Die Modelldateien landen im Volume und nicht im Abbild; ohne diesen Pfad lädt
# sie jeder Neustart des Containers erneut herunter - bei whisper-small knapp
# ein Gigabyte.
ENV HF_HOME=/srv/wortlaut/data/.cache/huggingface
ENV PYTHONPATH=/srv/wortlaut

CMD ["python", "-u", "-m", "apps.lernen.training.laeufer"]
