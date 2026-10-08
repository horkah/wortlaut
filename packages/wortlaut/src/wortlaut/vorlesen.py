"""Einen Satz vorlesen lassen - auf dem Server, einmal, und dann als Datei.

Die Sätze stehen als Vorlagen im Korpus, bevor sie jemand hört. Einmal
gesprochen und abgelegt, klingen sie auf jedem Gerät gleich; die
Browserstimmen dagegen wählt das Betriebssystem.

Die Schnittstelle stellt einem Motor genau zwei Fragen - *welche Stimmen hast
du* und *sprich diesen Satz*. Heute ist es Piper: auf dem Prozessor, wenige
Dutzend Megabyte je Stimme, MIT. Ein zweiter Motor kommt daneben.

Wo die Dateien liegen und wann sie entstehen, steht in
`apps/hoeren/backend/services/vorlesen.py`; hier steht nur, wie ein Satz zu
Klang wird.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import sprachen

# Zwischen Motor und Stimme: `piper/de_DE-thorsten-high`.
TRENNER = "/"


class VorlesenFehler(RuntimeError):
    """Vorlesen ist fehlgeschlagen; der Aufrufer fällt auf die Browserstimme
    zurück (`packages/ui/speak.ts`)."""


@dataclass(frozen=True)
class Stimme:
    """Eine Stimme, wie die Oberfläche sie anbietet."""

    # `<motor>/<stimme>`, z. B. `piper/de_DE-thorsten-high`.
    schluessel: str
    name: str
    erklaerung: str
    sprache: str = sprachen.VORGABE

    @property
    def motor(self) -> str:
        return self.schluessel.split(TRENNER, 1)[0]


class Motor(Protocol):
    """Was ein Motor können muss - zwei Fragen, mehr nicht."""

    name: str

    def stimmen(self) -> list[Stimme]:
        """Welche Stimmen dieser Motor jetzt sprechen kann - ohne, was erst
        heruntergeladen werden müsste."""
        ...

    def sprich(self, text: str, stimme: str, ziel: Path) -> None:
        """Den Text sprechen und als WAV nach `ziel` schreiben."""
        ...


# ── Piper ───────────────────────────────────────────────────────────────────


# ── Die Meldung „Missing phoneme from id map: ̧" ist kein Fehler ─────────────
#
# espeak-ng liefert das ç zerlegt (`c` plus U+0327), und die kleineren
# deutschen Modelle (Kerstin, Pavoque, Ramona, Karlsson, Eva) führen das
# Häkchen nicht - Piper meldet das bei jedem ich-Laut. Setzt man das `ç`
# wieder zusammen, verschwindet die Meldung, und der Klang wird schlechter;
# durch Whisper zurückgelesen:
#
#     Vorlage          Ich möchte nicht, dass mich niemand versteht.
#     mit `ç`          Ihr Mütte näht, dass mir niemand versteht.
#     ohne (Piper)     Ich möchte nicht, dass mich niemand versteht.
#
# Vermutlich sind diese Modelle durch dieselbe verlustbehaftete Stelle
# trainiert worden: Für sie ist `c` allein der ich-Laut. Thorsten führt das
# Häkchen und meldet nichts. Die Meldung bleibt also stehen.


@dataclass
class PiperMotor:
    """Piper: neuronale Sprachsynthese auf dem Prozessor.

    Die Stimmen sind ONNX-Dateien mit einer JSON-Beschreibung daneben, im
    Modellspeicher statt im Abbild. Angeboten wird, was im Verzeichnis liegt.
    """

    verzeichnis: Path
    name: str = "piper"

    # Beschriftungen, deutsch wie die Oberfläche; die Stimme spricht die Sprache
    # ihres Schlüssels. Eine unbekannte Stimme heißt nach ihrer Datei.
    BESCHREIBUNG = {  # noqa: RUF012 - Beschriftung, keine Zustandsdaten
        "de_DE-thorsten-high": (
            "Thorsten, hohe Auflösung",
            "Klar und ruhig. Die kräftigste der freien deutschen Stimmen.",
        ),
        "de_DE-thorsten-medium": (
            "Thorsten",
            "Dasselbe eine Stufe kleiner - schneller gerechnet, etwas rauer.",
        ),
        "de_DE-kerstin-low": (
            "Kerstin",
            "Eine weibliche Stimme, hell und nah am Mikrofon.",
        ),
        "de_DE-pavoque-low": (
            "Pavoque",
            "Eine männliche Stimme, ruhiger und tiefer als Thorsten.",
        ),
        "de_DE-ramona-low": ("Ramona", "Eine weibliche Stimme."),
        "de_DE-karlsson-low": ("Karlsson", "Eine männliche Stimme."),
        "de_DE-eva_k-x_low": ("Eva", "Eine weibliche Stimme, sehr genügsam."),
        "en_US-lessac-high": (
            "Lessac, hohe Auflösung",
            "Eine weibliche Stimme, amerikanisch. Aus einem Studiokorpus.",
        ),
        "en_US-ryan-high": (
            "Ryan, hohe Auflösung",
            "Eine männliche Stimme, amerikanisch.",
        ),
        "en_GB-cori-high": ("Cori, hohe Auflösung", "Eine weibliche Stimme, britisch."),
    }

    def stimmen(self) -> list[Stimme]:
        if not self.verzeichnis.is_dir():
            return []
        gefunden = []
        for modell in sorted(self.verzeichnis.glob("*.onnx")):
            if not modell.with_suffix(".onnx.json").is_file():
                # Ohne Beschreibung nicht ladbar - halb heruntergeladen.
                continue
            kennung = modell.stem
            name, erklaerung = self.BESCHREIBUNG.get(
                kennung, (kennung, "Eine abgelegte Piper-Stimme.")
            )
            gefunden.append(
                Stimme(
                    schluessel=f"{self.name}{TRENNER}{kennung}",
                    name=name,
                    erklaerung=erklaerung,
                    sprache=(
                        kennung.split("_", 1)[0] if "_" in kennung else sprachen.VORGABE
                    ),
                )
            )
        return gefunden

    def sprich(self, text: str, stimme: str, ziel: Path) -> None:
        kennung = stimme.split(TRENNER, 1)[-1]
        modell = self.verzeichnis / f"{kennung}.onnx"
        if not modell.is_file():
            raise VorlesenFehler(f"Diese Stimme liegt nicht vor: {kennung}")

        try:
            from piper import PiperVoice
        except ImportError as ursache:  # pragma: no cover - hängt am Abbild
            raise VorlesenFehler(
                "Piper ist in diesem Abbild nicht installiert."
            ) from ursache

        ziel.parent.mkdir(parents=True, exist_ok=True)
        # Erst daneben, dann an die Stelle: Der Abspieler sieht nie die Hälfte.
        entwurf = ziel.with_suffix(".wav.neu")
        try:
            sprecher = PiperVoice.load(str(modell))
            with wave.open(str(entwurf), "wb") as datei:
                # `synthesize_wav` schreibt die ganze Datei samt Kopf.
                sprecher.synthesize_wav(text, datei)
        except Exception as ursache:  # was immer onnx wirft
            entwurf.unlink(missing_ok=True)
            raise VorlesenFehler(f"Piper konnte nicht sprechen: {ursache}") from ursache
        entwurf.replace(ziel)


# ── Die Auswahl ─────────────────────────────────────────────────────────────


def motor_fuer(stimmenverzeichnis: Path, motorname: str = "piper") -> Motor:
    """Der Motor zu seinem Namen - hier kommt ein weiterer dazu."""
    if motorname == "piper":
        return PiperMotor(verzeichnis=stimmenverzeichnis)
    raise VorlesenFehler(f"Unbekannter Vorlesemotor: {motorname}")


def stimmen(stimmenverzeichnis: Path, motorname: str = "piper") -> list[Stimme]:
    """Alle Stimmen, die jetzt sprechen können - leer, wenn keine da ist.

    Leer ist der Normalfall einer frischen Installation; dann liest der
    Browser vor (`scripts/vorlesen.py` holt Stimmen).
    """
    try:
        return motor_fuer(stimmenverzeichnis, motorname).stimmen()
    except VorlesenFehler:
        return []


def bietet(stimmenverzeichnis: Path, motorname: str, stimme: str) -> bool:
    """Ob diese Stimme hier zur Wahl steht - die Prüfung vor jedem Vorlesen."""
    return stimme in {eintrag.schluessel for eintrag in stimmen(stimmenverzeichnis, motorname)}
