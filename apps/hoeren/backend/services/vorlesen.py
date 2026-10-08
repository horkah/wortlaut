"""Die vorgelesene Fassung einer Vorlage: anlegen, finden, wegräumen.

Wie ein Satz zu Klang wird, steht in `wortlaut/vorlesen.py`; hier steht, wo
die Dateien im Korpus liegen und wann sie entstehen und verschwinden:

* **Bei Bedarf.** Beim ersten Druck auf den Knopf entsteht die Datei;
  `scripts/vorlesen.py` rechnet auf Wunsch alles vorab.
* **Abgeleitet**, also nicht in der Sicherung (`services/ausleitung.py`).
* **Je Sprecher**, auch wenn dieselbe Vorlage bei zweien steht: Ein
  gemeinsamer Speicher bliebe nach einer Löschung übrig.

Scheitert das Vorlesen, kommt nichts zurück, und die Oberfläche liest stumm
mit der Browserstimme vor (`packages/ui/speak.ts`).
"""

from __future__ import annotations

from pathlib import Path

from wortlaut import corpus, storage
from wortlaut import vorlesen as klangwandel

from ..db.models import Vorlage

# Durchgereicht, damit der Rest der App eine Adresse für diese Begriffe hat.
Stimme = klangwandel.Stimme
VorlesenFehler = klangwandel.VorlesenFehler
bietet = klangwandel.bietet


def relpfad(vorlage: Vorlage, stimme: str) -> str:
    """Der Blob zur vorgelesenen Fassung dieser Vorlage."""
    return corpus.vorlesung_relpfad(vorlage.speaker_id, vorlage.id, stimme)


def stimmen(stimmenverzeichnis: Path, motor: str) -> list[Stimme]:
    """Welche Stimmen dieser Server anbieten kann - leer ist kein Fehler."""
    return klangwandel.stimmen(stimmenverzeichnis, motor)


def stelle_her(
    ablage: storage.Ablage,
    vorlage: Vorlage,
    stimme: str,
    stimmenverzeichnis: Path,
    motor: str,
) -> str | None:
    """Die Vorlesung anlegen, falls sie fehlt; gibt den Blob zurück.

    `None` heißt: Es geht nicht - keine Stimme, kein Piper, ein leerer Satz.
    Der Aufrufer liest dann im Browser vor.

    Eine vorhandene Datei wird nie neu gerechnet; der Dateiname sagt, welche
    Vorlage in welcher Stimme.
    """
    text = str(vorlage.text or "").strip()
    if not text:
        return None

    blob = relpfad(vorlage, stimme)
    if ablage.pfad(blob).is_file():
        return blob

    try:
        motorkopf = klangwandel.motor_fuer(stimmenverzeichnis, motor)
        # Direkt in die Ablage - der Motor schreibt über eine Entwurfsdatei.
        motorkopf.sprich(text, stimme, ablage.pfad(blob))
    except klangwandel.VorlesenFehler:
        return None
    return blob


def stelle_probe_her(
    ablage: storage.Ablage,
    sprecher_id: str,
    text: str,
    stimme: str,
    stimmenverzeichnis: Path,
    motor: str,
) -> str | None:
    """Der feste Probesatz in dieser Stimme - zum Vergleichen vor der Wahl.

    Unter der Kennung `probe` neben den Vorlesungen, nach derselben Regel.
    """
    blob = corpus.vorlesung_relpfad(sprecher_id, "probe", stimme)
    if ablage.pfad(blob).is_file():
        return blob
    try:
        klangwandel.motor_fuer(stimmenverzeichnis, motor).sprich(text, stimme, ablage.pfad(blob))
    except klangwandel.VorlesenFehler:
        return None
    return blob


def loesche(ablage: storage.Ablage, vorlage: Vorlage, stimmen_schluessel: list[str]) -> None:
    """Alle vorgelesenen Fassungen dieser Vorlage entfernen.

    Gerufen, wenn eine Vorlage verschwindet.
    """
    for stimme in stimmen_schluessel:
        ablage.loesche(relpfad(vorlage, stimme))
