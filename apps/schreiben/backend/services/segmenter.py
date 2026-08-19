"""Vom Diktat zu Abschnitten: umwandeln, transkribieren, schneiden.

Whisper liefert Text **mit Segmentgrenzen**. Genau diese Grenzen sind hier die
Einheit: Ein Abschnitt wird einzeln vorgelesen, einzeln neu eingesprochen und
geht einzeln als Audio-Text-Paar an „hören". Damit das geht, wird die Aufnahme
an den gemeldeten Zeitmarken zerschnitten und je Abschnitt eine WAV-Datei
abgelegt.

Die zusammenhängende Aufnahme wird dabei nicht behalten. Sie wäre eine zweite
Kopie derselben Stimmdaten, und gebraucht wird sie nach dem Schnitt nicht mehr.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from wortlaut import audio as klang
from wortlaut import ids, storage
from wortlaut.whisper import Transkriptor

from ..config import audio_relpfad


@dataclass(frozen=True)
class Rohabschnitt:
    """Ein fertig geschnittener Abschnitt, noch ohne Datenbankzeile."""

    id: str
    text: str
    blob: str
    dauer_s: float


def zerlege(
    eingang: bytes,
    transkriptor: Transkriptor,
    ablage: storage.Ablage,
    sprache: str,
    sprecher_id: str,
) -> list[Rohabschnitt]:
    """Aufnahme des Browsers → Abschnitte mit je eigener WAV-Datei.

    Wirft `AudioFehler`, wenn die Umwandlung scheitert; eine Aufnahme ohne
    verstandenes Wort ergibt eine leere Liste — das ist kein Fehler, sondern
    eine Antwort, mit der die Oberfläche umgehen kann.
    """
    with tempfile.TemporaryDirectory() as verzeichnis:
        wav = _als_wav(eingang, Path(verzeichnis))
        transkript = transkriptor.transkribiere(wav, sprache)

        abschnitte: list[Rohabschnitt] = []
        for nummer, abschnitt in enumerate(transkript.abschnitte):
            if not abschnitt.text:
                continue  # Whisper meldet gelegentlich stumme Segmente
            kennung = ids.neue_id("seg")
            ausschnitt = Path(verzeichnis) / f"{nummer}.wav"
            klang.schneide_ausschnitt(wav, ausschnitt, abschnitt.start_s, abschnitt.ende_s)
            relpfad = audio_relpfad(sprecher_id, kennung)
            # `lege_ab` verschiebt — die Ausschnitte sind temporäre Dateien.
            ablage.lege_ab(relpfad, ausschnitt)
            abschnitte.append(
                Rohabschnitt(
                    id=kennung,
                    text=abschnitt.text,
                    blob=relpfad,
                    dauer_s=max(0.0, abschnitt.ende_s - abschnitt.start_s),
                )
            )
        return abschnitte


def sprich_neu_ein(
    eingang: bytes,
    transkriptor: Transkriptor,
    ablage: storage.Ablage,
    sprache: str,
    sprecher_id: str,
    kennung: str,
) -> Rohabschnitt:
    """Eine einzelne, kurze Aufnahme für genau einen Abschnitt.

    Hier wird nicht geschnitten: Was der Mensch für einen Abschnitt gesprochen
    hat, *ist* der Abschnitt — auch wenn Whisper darin mehrere Segmente sieht.
    Deren Texte werden deshalb wieder zusammengefügt.
    """
    with tempfile.TemporaryDirectory() as verzeichnis:
        wav = _als_wav(eingang, Path(verzeichnis))
        transkript = transkriptor.transkribiere(wav, sprache)
        befund = klang.untersuche(wav)
        relpfad = audio_relpfad(sprecher_id, kennung)
        ablage.lege_ab(relpfad, wav)

    return Rohabschnitt(
        id=kennung, text=transkript.text.strip(), blob=relpfad, dauer_s=befund.dauer_s
    )


def _als_wav(eingang: bytes, verzeichnis: Path) -> Path:
    """Was der Browser geschickt hat (Opus, MP4, …) → 16 kHz mono, PCM 16 bit."""
    roh = verzeichnis / "eingang"
    roh.write_bytes(eingang)
    wav = verzeichnis / "diktat.wav"
    klang.wandle_in_wav(roh, wav)
    return wav
