"""Einen Satz vorlesen lassen - auf dem Server, einmal, und dann als Datei.

**Warum überhaupt hier und nicht im Browser.** Vorgelesen wurde bisher über die
Web Speech API: keine Infrastruktur, keine Latenz, und der Preis ist, dass das
Betriebssystem entscheidet, wie es klingt. Dieselbe Seite klingt auf einem
iPhone erträglich und unter Linux mit espeak-ng blechern. Von der App aus ist
das nicht zu ändern - nur hinzunehmen.

Es muss aber gar nicht im Browser passieren. Die Sätze, die vorgelesen werden,
sind keine Eingabe: Sie stehen als Vorlagen im Korpus, bevor sie jemand hört.
Ein Satz, der einmal gesprochen und als Datei abgelegt wird, klingt danach auf
**jedem** Gerät gleich - und die Qualität hängt nicht mehr daran, wie schnell
ein Modell ist, sondern nur daran, wie gut es ist.

**Warum ein Motor und nicht ein Aufruf.** Welche Stimme die beste ist, ist eine
offene Frage: lokal gerechnet (kostenlos, aber begrenzt) oder über einen Dienst
(deutlich natürlicher, dafür extern). Sie soll sich beantworten lassen, ohne
alles darüber anzufassen. Deshalb steht hier eine Schnittstelle mit genau zwei
Fragen - *welche Stimmen hast du* und *sprich diesen Satz* - und darunter ein
Motor. Heute ist es Piper; ein zweiter kommt daneben, nicht an seine Stelle.

**Warum Piper zuerst.** Es läuft auf dem Prozessor, braucht keine Karte, wiegt
je Stimme wenige Dutzend Megabyte und ist frei (MIT). Es schlägt die
Linux-Vorgabe um Längen. Ob es die Stimmen eines Dienstes schlägt, ist damit
nicht behauptet - aber die Mechanik steht, und der Wechsel ist dann eine Zeile
Konfiguration.

**Was hier nicht passiert: Echtzeit.** Diese Datei rechnet, wenn ein Satz
gebraucht wird, und legt das Ergebnis ab. Beim zweiten Mal wird nichts mehr
gerechnet. Wo die Dateien liegen und wann sie entstehen, steht in
`apps/hoeren/backend/services/vorlesen.py`; hier steht nur, wie ein Satz zu
Klang wird.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import sprachen

# Womit dieses Projekt arbeitet - dieselbe Abtastrate wie überall sonst
# (`audio.py`). Was ein Motor anders liefert, wird umgerechnet, bevor es
# abgelegt wird: Eine Vorlesung ist eine WAV-Datei wie jede andere, sonst
# müsste jeder Abspieler ihren Sonderfall kennen.
RATE = 16_000

# Der Trenner zwischen Motor und Stimme in einem Schlüssel:
# `piper/de_DE-thorsten-high`. Ein Motorname enthält keinen Schrägstrich,
# daran allein sind beide zu trennen.
TRENNER = "/"


class VorlesenFehler(RuntimeError):
    """Vorlesen ist fehlgeschlagen - und der Aufrufer soll weiterkommen.

    Immer eine eigene Klasse und nie ein nackter Fehler: Vorlesen ist eine
    Hilfe und keine Bedingung. Wer sie ruft, fällt auf die Browserstimme
    zurück (siehe `packages/ui/speak.ts`), und das soll er an einem Fehler
    erkennen können, den er erwartet hat.
    """


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
        """Welche Stimmen dieser Motor **jetzt** sprechen kann.

        Jetzt heißt jetzt: Ein Piper-Modell, das noch nicht heruntergeladen
        ist, gehört nicht dazu. Eine Stimme anzubieten, die beim ersten Klick
        scheitert, ist schlechter als eine Stimme weniger.
        """
        ...

    def sprich(self, text: str, stimme: str, ziel: Path) -> None:
        """Den Text sprechen und als WAV nach `ziel` schreiben."""
        ...


# ── Piper ───────────────────────────────────────────────────────────────────


# ── Warum hier nichts repariert wird ────────────────────────────────────────
#
# Piper geht in zwei Schritten vor: espeak-ng macht aus dem Text Lautschrift,
# dann schlägt das Modell jedes Zeichen in seiner eigenen Tabelle nach. Beim
# ç sind sich beide Seiten uneins. Das heutige espeak-ng liefert es zerlegt -
# ein `c` und ein freistehendes Häkchen (U+0327) -, und die kleineren
# deutschen Modelle (Kerstin, Pavoque, Ramona, Karlsson, Eva) führen das
# Häkchen nicht. Piper meldet das bei jedem ich-Laut:
#
#     Missing phoneme from id map: ̧
#
# **Diese Meldung sieht nach einem Fehler aus und ist keiner.** Hier stand
# einmal ein Eingriff, der `c` und Häkchen wieder zum fertigen `ç`
# zusammensetzte - das steht in der Tabelle, und die Meldung verschwand. Der
# Klang wurde davon schlechter, nicht besser.
#
# Nachgemessen, indem der gesprochene Satz durch Whisper zurückgelesen wurde:
#
#     Vorlage          Ich möchte nicht, dass mich niemand versteht.
#     mit `ç`          Ihr Mütte näht, dass mir niemand versteht.
#     ohne (Piper)     Ich möchte nicht, dass mich niemand versteht.
#
# Bei Pavoque dasselbe, über drei Sätze hinweg. Der Grund ist naheliegend,
# wenn auch nicht bewiesen: Diese Modelle sind durch dieselbe verlustbehaftete
# Stelle **trainiert** worden. Was das Häkchen verliert, hat schon beim
# Training keines gehabt, und `c` allein ist für sie der ich-Laut. Training
# und Vorlesen sind sich also einig - die Meldung beschreibt einen Verlust,
# der im Modell längst eingebacken ist.
#
# Thorsten braucht ohnehin nichts: Seine größere Tabelle führt das Häkchen,
# er bekommt beide Zeichen und meldet nichts.
#
# Wer diese Meldung das nächste Mal sieht, lasse sie stehen. Sie zu beheben
# heißt, die Stimmen zu verschlechtern - und zwar lautlos, denn hörbar ist es
# nur, wenn jemand hinhört oder den Satz zurücklesen lässt.


@dataclass
class PiperMotor:
    """Piper: neuronale Sprachsynthese auf dem Prozessor.

    Die Stimmen sind ONNX-Dateien mit einer JSON-Beschreibung daneben. Sie
    liegen **nicht** im Abbild, sondern in einem Ablagepfad wie die
    Whisper-Modelle: Je Stimme sind es einige Dutzend Megabyte, und welche
    jemand haben will, entscheidet er und nicht der Bau.

    Angeboten wird nur, was wirklich daliegt. Das ist der Grund, warum diese
    Klasse das Verzeichnis liest und keine Liste mitbringt: Eine Stimme, die es
    zu laden gäbe, ist keine Stimme, die spricht.
    """

    verzeichnis: Path
    name: str = "piper"

    # Was die mitgelieferten deutschen Stimmen sind - für die Beschriftung.
    # Fehlt ein Name hier, steht der Dateiname da; das ist hässlich, aber
    # richtig, und es hält niemanden davon ab, eine eigene Stimme abzulegen.
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
    }

    def stimmen(self) -> list[Stimme]:
        if not self.verzeichnis.is_dir():
            return []
        gefunden = []
        for modell in sorted(self.verzeichnis.glob("*.onnx")):
            if not modell.with_suffix(".onnx.json").is_file():
                # Ohne die Beschreibung daneben lässt sich das Modell nicht
                # laden. Halb heruntergeladen ist nicht vorhanden.
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
        # Erst daneben, dann an die Stelle: Ein Leser sieht nie die Hälfte -
        # dieselbe Regel wie bei `laeufe.schreibe_json`, und hier zählt sie
        # doppelt, weil der Leser ein Abspieler im Browser ist.
        entwurf = ziel.with_suffix(".wav.neu")
        try:
            sprecher = PiperVoice.load(str(modell))
            with wave.open(str(entwurf), "wb") as datei:
                # `synthesize_wav` und nicht `synthesize`: Letzteres gibt
                # Blöcke zurück, die der Aufrufer selbst zusammensetzen müsste.
                # Hier soll eine Datei entstehen, und genau das tut diese
                # Methode - samt Kopf mit Rate und Breite.
                sprecher.synthesize_wav(text, datei)
        except VorlesenFehler:
            raise
        except Exception as ursache:  # was immer onnx wirft
            entwurf.unlink(missing_ok=True)
            raise VorlesenFehler(f"Piper konnte nicht sprechen: {ursache}") from ursache
        entwurf.replace(ziel)


# ── Die Auswahl ─────────────────────────────────────────────────────────────


def motor_fuer(stimmenverzeichnis: Path, motorname: str = "piper") -> Motor:
    """Der Motor zu seinem Namen.

    Eine Stelle, an der aus einer Zeichenkette ein Motor wird - und die Liste
    ist kurz, weil es erst einen gibt. Der zweite kommt hier dazu, und alles
    darüber merkt nichts davon.
    """
    if motorname == "piper":
        return PiperMotor(verzeichnis=stimmenverzeichnis)
    raise VorlesenFehler(f"Unbekannter Vorlesemotor: {motorname}")


def stimmen(stimmenverzeichnis: Path, motorname: str = "piper") -> list[Stimme]:
    """Alle Stimmen, die jetzt sprechen können - leer, wenn keine da ist.

    Leer ist kein Fehler, sondern der Normalfall einer frischen Installation:
    Dann liest der Browser vor wie bisher, und wer es besser haben will, legt
    eine Stimme ab (`scripts/vorlesen.py`).
    """
    try:
        return motor_fuer(stimmenverzeichnis, motorname).stimmen()
    except VorlesenFehler:
        return []
