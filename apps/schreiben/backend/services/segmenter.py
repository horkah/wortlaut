"""Vom Diktat zu Abschnitten: umwandeln, transkribieren, schneiden.

Whisper liefert Text **mit Segmentgrenzen**. Genau diese Grenzen sind hier die
Einheit: Ein Abschnitt wird einzeln vorgelesen, einzeln neu eingesprochen und
geht einzeln als Audio-Text-Paar an „hören". Damit das geht, wird die Aufnahme
an den gemeldeten Zeitmarken zerschnitten und je Abschnitt eine WAV-Datei
abgelegt.

Die zusammenhängende Aufnahme wird nicht behalten - eine zweite Kopie
derselben Stimmdaten. Whisper hört die Aufnahme, wie sie gesprochen wurde, und
so wird sie auch geschnitten: Aus einer bestätigten Korrektur wird in „hören"
eine Aufnahme im Korpus.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from wortlaut import audio as klang
from wortlaut import ids, storage, tempo
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
    faktor: float = tempo.VORGABE,
) -> list[Rohabschnitt]:
    """Aufnahme des Browsers → Abschnitte mit je eigener WAV-Datei.

    Wirft `AudioFehler`, wenn die Umwandlung scheitert; eine Aufnahme ohne
    verstandenes Wort ergibt eine leere Liste - das ist kein Fehler, sondern
    eine Antwort, mit der die Oberfläche umgehen kann.

    Vorgespult wird nur, was das Modell hört; gespeichert und geschnitten wird
    die echte Aufnahme. Die Zeitmarken meldet Whisper in gehörter Zeit und
    werden deshalb mit dem Faktor zurückgerechnet.

    Segmente hinter dem letzten Abtastwert - Whisper findet in der Auffüllung
    manchmal Sprache - haben kein Audio und fallen weg.
    """
    with tempfile.TemporaryDirectory() as verzeichnis:
        wav = _als_wav(eingang, Path(verzeichnis))
        transkript = transkriptor.transkribiere(
            _vorgespult(wav, Path(verzeichnis), faktor), sprache
        )

        # Woran die Zeitmarken gemessen werden. Whisper hört nicht die Aufnahme,
        # sondern ein auf 30 Sekunden aufgefülltes Fenster - was es in der
        # Auffüllung zu hören meint, liegt hinter dem letzten Abtastwert.
        aufnahmedauer = klang.dauer(wav)

        abschnitte: list[Rohabschnitt] = []
        for nummer, abschnitt in enumerate(transkript.abschnitte):
            if not abschnitt.text:
                continue  # Whisper meldet gelegentlich stumme Segmente
            start_s = abschnitt.start_s * faktor
            ende_s = min(abschnitt.ende_s * faktor, aufnahmedauer)
            if start_s >= aufnahmedauer:
                # Beginnt hinter dem Ende der Aufnahme: eine Erfindung aus der
                # Stille. Übergangen, damit das übrige Diktat nicht mitscheitert.
                continue
            kennung = ids.neue_id("seg")
            ausschnitt = Path(verzeichnis) / f"{nummer}.wav"
            klang.schneide_ausschnitt(wav, ausschnitt, start_s, ende_s)
            relpfad = audio_relpfad(sprecher_id, kennung)
            # `lege_ab` verschiebt - die Ausschnitte sind temporäre Dateien.
            ablage.lege_ab(relpfad, ausschnitt)
            abschnitte.append(
                Rohabschnitt(
                    id=kennung,
                    text=abschnitt.text,
                    blob=relpfad,
                    # Die gestutzte Grenze, nicht die gemeldete: Was hier steht,
                    # soll die Datei daneben auch hergeben.
                    dauer_s=max(0.0, ende_s - start_s),
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
    faktor: float = tempo.VORGABE,
) -> Rohabschnitt:
    """Eine einzelne, kurze Aufnahme für genau einen Abschnitt.

    Hier wird nicht geschnitten: Was der Mensch für einen Abschnitt gesprochen
    hat, *ist* der Abschnitt - auch wenn Whisper darin mehrere Segmente sieht.
    Deren Texte werden deshalb wieder zusammengefügt.
    """
    with tempfile.TemporaryDirectory() as verzeichnis:
        wav = _als_wav(eingang, Path(verzeichnis))
        # Ohne Schnitt nichts zurückzurechnen; der Befund gilt der echten Aufnahme.
        transkript = transkriptor.transkribiere(
            _vorgespult(wav, Path(verzeichnis), faktor), sprache
        )
        befund = klang.untersuche(wav)
        relpfad = audio_relpfad(sprecher_id, kennung)
        ablage.lege_ab(relpfad, wav)

    return Rohabschnitt(
        id=kennung, text=transkript.text.strip(), blob=relpfad, dauer_s=befund.dauer_s
    )


def _vorgespult(wav: Path, verzeichnis: Path, faktor: float) -> Path:
    """Die Fassung, die das Modell zu hören bekommt - bei Faktor 1 die eigene.

    Die Datei lebt so lange wie das temporäre Verzeichnis des Aufrufers, also
    bis das Diktat zerlegt ist. Abgelegt wird sie nirgends: Was aufbewahrt
    wird, ist die echte Aufnahme.
    """
    if not tempo.vorspulen_noetig(faktor):
        return wav
    schnell = verzeichnis / "vorgespult.wav"
    tempo.spule_vor(wav, schnell, faktor)
    return schnell


def _als_wav(eingang: bytes, verzeichnis: Path) -> Path:
    """Was der Browser geschickt hat (Opus, MP4, …) → 16 kHz mono, PCM 16 bit."""
    roh = verzeichnis / "eingang"
    roh.write_bytes(eingang)
    wav = verzeichnis / "diktat.wav"
    klang.wandle_in_wav(roh, wav)
    return wav
