"""Transkription über einen OpenAI-kompatiblen Endpunkt.

Ein Adapter deckt damit mehrere Anbieter ab. Achtung: Wer diesen Schalter
umlegt, schickt Stimmdaten an Dritte — siehe `docs/datenschutz.md`.
"""

from __future__ import annotations

from pathlib import Path

from . import Abschnitt, Transkript


class EntfernterTranskriptor:
    def __init__(self, endpunkt: str, api_schluessel: str, modell: str = "whisper-1") -> None:
        self.endpunkt = endpunkt.rstrip("/")
        self.api_schluessel = api_schluessel
        self.modell = modell

    def transkribiere(self, wav: Path, sprache: str = "de") -> Transkript:
        import httpx

        with wav.open("rb") as datei:
            antwort = httpx.post(
                f"{self.endpunkt}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_schluessel}"},
                files={"file": (wav.name, datei, "audio/wav")},
                data={
                    "model": self.modell,
                    "language": sprache,
                    # Ohne Segmentgrenzen wäre die Abschnittskorrektur in
                    # „schreiben" nicht möglich.
                    "response_format": "verbose_json",
                },
                timeout=300,
            )
        antwort.raise_for_status()
        nutzlast = antwort.json()

        abschnitte = [
            Abschnitt(start_s=a["start"], ende_s=a["end"], text=a["text"].strip())
            for a in nutzlast.get("segments", [])
        ]
        return Transkript(text=nutzlast.get("text", "").strip(), abschnitte=abschnitte)
