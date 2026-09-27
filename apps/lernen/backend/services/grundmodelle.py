"""Was ein unverändertes Whisper-Modell ist - der Steckbrief eines Grundmodells.

Ein eigener Stand erzählt seine Geschichte selbst: Auftrag, Manifest,
Protokoll. Ein Grundmodell kommt ohne das aus dem Netz. Was man über es wissen
will, steht an zwei Orten:

* **In der Modellkarte** - was OpenAI veröffentlicht hat: Größe, Aufbau,
  Trainingsdaten, Datum, Lizenz. Das ändert sich nicht und steht deshalb fest
  in `KARTEN`. Quellen: Radford et al., „Robust Speech Recognition via
  Large-Scale Weak Supervision" (2022), Tabelle 1 und Abschnitt 2, und die
  Modellkarten auf Hugging Face (`openai/whisper-*`).
* **Im Modellcache dieser Maschine** - was tatsächlich hier liegt: welche
  Revision, wann geladen, wie groß, wie viele Sprachen und Mel-Kanäle das
  Modell selbst nennt. Das wird gelesen, nicht behauptet (`vor_ort`).

Erkannt wird mit den CTranslate2-Fassungen von Systran (faster-whisper),
trainiert auf den Originalen von OpenAI (transformers) - zwei Einträge im
Cache für dasselbe Modell.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Modellkarte:
    """Was OpenAI über ein Modell veröffentlicht hat."""

    # Ein Satz für den, der nur wissen will, was er vor sich hat.
    erklaerung: str
    parameter_mio: int
    # Je Encoder und Decoder gleich viele.
    schichten: int
    breite: int
    koepfe: int
    # Eingang und Sprachen - der Cache sagt es genauer, wo er es sagt.
    mel_kanaele: int
    sprachen: int
    veroeffentlicht: str  # ISO 8601
    trainingsdaten: str


# 680.000 Stunden: 438.000 englische Erkennung, 126.000 Übersetzung ins
# Englische, 117.000 Erkennung in 96 weiteren Sprachen (Radford et al.,
# Abschnitt 2.3).
_DATEN_2022 = (
    "680.000 Stunden aus dem Netz, schwach beschriftet - davon 117.000 Stunden "
    "Erkennung in 96 Sprachen außer Englisch"
)

KARTEN: dict[str, Modellkarte] = {
    "small": Modellkarte(
        erklaerung=(
            "Das kleinste der drei: schnell, auf der Karte wie auf dem Prozessor "
            "brauchbar."
        ),
        parameter_mio=244,
        schichten=12,
        breite=768,
        koepfe=12,
        mel_kanaele=80,
        sprachen=99,
        veroeffentlicht="2022-09-21",
        trainingsdaten=_DATEN_2022,
    ),
    "medium": Modellkarte(
        erklaerung=(
            "Dreimal so viele Parameter wie small und entsprechend langsamer."
        ),
        parameter_mio=769,
        schichten=24,
        breite=1024,
        koepfe=16,
        mel_kanaele=80,
        sprachen=99,
        veroeffentlicht="2022-09-21",
        trainingsdaten=_DATEN_2022,
    ),
    "large-v3": Modellkarte(
        erklaerung=(
            "Das größte Whisper, mit mehr Daten und feinerem Spektrogramm "
            "nachtrainiert - die stärkste Baseline und die langsamste."
        ),
        parameter_mio=1550,
        schichten=32,
        breite=1280,
        koepfe=20,
        mel_kanaele=128,
        sprachen=100,
        veroeffentlicht="2023-11-06",
        trainingsdaten=(
            "1 Mio. Stunden schwach beschriftet und 4 Mio. Stunden, die whisper-large-v2 "
            "beschriftet hat - zwei Durchgänge"
        ),
    ),
}

def repo_erkennen(name: str) -> str:
    """Die CTranslate2-Fassung, die faster-whisper zu diesem Namen lädt."""
    return f"Systran/faster-whisper-{name}"


def repo_trainieren(name: str) -> str:
    """Die Originalgewichte, auf denen `lernen` trainiert (`WORTLAUT_LERNEN_GRUNDMODELLE`)."""
    return f"openai/whisper-{name}"


# Was für alle gleich ist.
FENSTER_S = 30
AUSGABE_TOKEN = 448
LIZENZ = "MIT (OpenAI; die CTranslate2-Fassung von Systran ebenso)"


@dataclass(frozen=True)
class Cacheeintrag:
    """Ein Modell, wie es im Hugging-Face-Cache dieser Maschine liegt."""

    repo: str
    revision: str
    # Wann die letzte Datei ankam - das Ende des Herunterladens.
    geladen: str
    bytes: int
    # Die größte Datei: die Gewichte.
    gewichte: str
    gewichte_bytes: int
    ordner: Path


def hub() -> Path:
    """Der Hub-Ordner des Caches - im Abbild unter `HF_HOME`, sonst der Vorgabeort."""
    if ort := os.environ.get("HF_HUB_CACHE"):
        return Path(ort)
    wurzel = os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
    return Path(wurzel) / "hub"


def im_cache(repo: str) -> Cacheeintrag | None:
    """Was vom Repository `repo` hier liegt; `None`, wenn es nie geladen wurde."""
    ordner = hub() / f"models--{repo.replace('/', '--')}"
    referenz = ordner / "refs" / "main"
    if not referenz.is_file():
        return None
    revision = referenz.read_text(encoding="utf-8").strip()
    schnappschuss = ordner / "snapshots" / revision
    dateien = [d for d in (ordner / "blobs").iterdir() if d.is_file()] if (ordner / "blobs").is_dir() else []
    if not dateien or not schnappschuss.is_dir():
        return None
    # Die Namen stehen an den Verweisen im Schnappschuss, die Größen an den Blobs.
    groesste = max(
        (eintrag for eintrag in schnappschuss.iterdir() if eintrag.is_file()),
        key=lambda eintrag: eintrag.stat().st_size,
        default=None,
    )
    return Cacheeintrag(
        repo=repo,
        revision=revision,
        geladen=datetime.fromtimestamp(max(d.stat().st_mtime for d in dateien), UTC).isoformat(),
        bytes=sum(d.stat().st_size for d in dateien),
        gewichte=groesste.name if groesste else "",
        gewichte_bytes=groesste.stat().st_size if groesste else 0,
        ordner=schnappschuss,
    )


def _json(pfad: Path) -> dict:
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@dataclass(frozen=True)
class Selbstauskunft:
    """Was die CTranslate2-Fassung über sich selbst sagt."""

    sprachen: int | None
    # `None`: Die Fassung trägt keine Vorverarbeitung, es gilt die Vorgabe
    # von faster-whisper (80).
    mel_kanaele: int | None
    wortschatz: int | None


def selbstauskunft(eintrag: Cacheeintrag) -> Selbstauskunft:
    konfiguration = _json(eintrag.ordner / "config.json")
    vorverarbeitung = _json(eintrag.ordner / "preprocessor_config.json")
    wortschatz = eintrag.ordner / "vocabulary.json"
    try:
        woerter = len(json.loads(wortschatz.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        woerter = None
    return Selbstauskunft(
        sprachen=len(konfiguration["lang_ids"]) if "lang_ids" in konfiguration else None,
        mel_kanaele=int(vorverarbeitung["feature_size"]) if "feature_size" in vorverarbeitung else None,
        wortschatz=woerter,
    )


def groesse(bytes_: int) -> str:
    """`3087284237` → `3,1 GB`."""
    for einheit, teiler in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if bytes_ >= teiler:
            return f"{bytes_ / teiler:.1f} {einheit}".replace(".", ",")
    return f"{bytes_} B"
