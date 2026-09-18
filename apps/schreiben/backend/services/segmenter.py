"""Vom Diktat zu Abschnitten: umwandeln, transkribieren, schneiden.

Whisper liefert Text **mit Segmentgrenzen**. Genau diese Grenzen sind hier die
Einheit: Ein Abschnitt wird einzeln vorgelesen, einzeln neu eingesprochen und
geht einzeln als Audio-Text-Paar an „hören". Damit das geht, wird die Aufnahme
an den gemeldeten Zeitmarken zerschnitten und je Abschnitt eine WAV-Datei
abgelegt.

Die zusammenhängende Aufnahme wird dabei nicht behalten. Sie wäre eine zweite
Kopie derselben Stimmdaten, und gebraucht wird sie nach dem Schnitt nicht mehr.

**Was Whisper hört, ist die Aufnahme selbst.** Hier stand bis September 2026
eine Aufbereitung dazwischen: Das Diktat wurde vor dem Erkennen lauter
gerechnet, bis seine Spitze knapp unter dem Anschlag stand. Sie ist weg, und
zwar aus demselben Grund, aus dem in „hören" die Abwandlung `pegel` gefallen
ist - Whisper hört ein Log-Mel-Spektrogramm, und eine gleichmäßige Verstärkung
verschiebt darin kaum mehr als einen Summanden. Was sie kostete, waren eine
zweite Datei je Diktat, ein Schalter, eine Tabelle und eine Erklärung; was sie
brachte, war nicht zu messen.

Geschnitten und abgelegt wird aus der Aufnahme, wie sie gesprochen wurde - das
galt vorher und gilt weiter. Aus einer bestätigten Korrektur wird in „hören"
eine Aufnahme im Korpus, und die soll dort so liegen, wie sie entstanden ist.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from wortlaut import audio as klang
from wortlaut import ids, storage, tempo, vorbereitung
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
    schneiden: bool = False,
) -> list[Rohabschnitt]:
    """Aufnahme des Browsers → Abschnitte mit je eigener WAV-Datei.

    Wirft `AudioFehler`, wenn die Umwandlung scheitert; eine Aufnahme ohne
    verstandenes Wort ergibt eine leere Liste - das ist kein Fehler, sondern
    eine Antwort, mit der die Oberfläche umgehen kann.

    **Vorgespult wird nur, was das Modell hört.** Gespeichert und geschnitten
    wird die echte Aufnahme. Das ist kein Feinschliff, sondern die Bedingung
    dafür, dass hinterher noch etwas stimmt: Im Korpus liegt die Stimme dieses
    Menschen, nicht eine beschleunigte Fassung davon, und die Dauer eines
    Abschnitts ist die Zeit, die er wirklich gesprochen hat.

    **Und deshalb müssen die Zeitmarken zurückgerechnet werden.** Whisper
    meldet sie in der Zeit, die es gehört hat - bei Faktor 2 also in halber,
    und bei geschnittenen Rändern ab dem ersten Laut statt ab dem ersten
    Abtastwert. Ungerechnet geschnitten ergäbe das Abschnitte, die bei der
    Hälfte der Aufnahme enden oder um die weggefallene Stille verrutscht sind -
    und niemand sähe daran, woran es liegt, denn der Text stimmt ja.

    **Was hinter dem Ende der Aufnahme liegt, fällt weg.** Whisper meldet
    gelegentlich Segmente, die erst nach dem letzten Abtastwert beginnen - es
    hört ein aufgefülltes Fenster und findet in der Stille Sprache. Ein solcher
    Abschnitt hat kein Audio und wird übergangen, wie ein stummes Segment auch.
    """
    with tempfile.TemporaryDirectory() as verzeichnis:
        wav = _als_wav(eingang, Path(verzeichnis))
        gehoert, versatz_s = _vorbereitet(wav, Path(verzeichnis), faktor, schneiden)
        transkript = transkriptor.transkribiere(gehoert, sprache)

        # Woran die Zeitmarken gemessen werden. Whisper hört nicht die Aufnahme,
        # sondern ein auf 30 Sekunden aufgefülltes Fenster - was es in der
        # Auffüllung zu hören meint, liegt hinter dem letzten Abtastwert.
        aufnahmedauer = klang.dauer(wav)

        abschnitte: list[Rohabschnitt] = []
        for nummer, abschnitt in enumerate(transkript.abschnitte):
            if not abschnitt.text:
                continue  # Whisper meldet gelegentlich stumme Segmente
            start_s = versatz_s + abschnitt.start_s * faktor
            ende_s = min(versatz_s + abschnitt.ende_s * faktor, aufnahmedauer)
            if start_s >= aufnahmedauer:
                # Ein Abschnitt, der erst hinter dem Ende der Aufnahme beginnt.
                # Dazu gibt es kein Audio - also auch keinen Satz, den jemand
                # gesprochen hätte; das ist eine Erfindung aus der Stille.
                #
                # Er wird übergangen wie ein stummes Segment und nicht als
                # Fehler behandelt. Vorher scheiterte am leeren Schnitt das
                # **ganze** Diktat mit „Leerer Ausschnitt 13,00-15,00 s" - alles
                # richtig Verstandene ging mit, und auf dem Telefon stand ein
                # Satz, mit dem niemand etwas anfangen kann.
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
    schneiden: bool = False,
) -> Rohabschnitt:
    """Eine einzelne, kurze Aufnahme für genau einen Abschnitt.

    Hier wird nicht geschnitten: Was der Mensch für einen Abschnitt gesprochen
    hat, *ist* der Abschnitt - auch wenn Whisper darin mehrere Segmente sieht.
    Deren Texte werden deshalb wieder zusammengefügt.
    """
    with tempfile.TemporaryDirectory() as verzeichnis:
        wav = _als_wav(eingang, Path(verzeichnis))
        # Hier wird nicht geschnitten, also braucht auch nichts zurückgerechnet
        # zu werden - der Befund gilt der echten Aufnahme wie eh und je.
        gehoert, _versatz = _vorbereitet(wav, Path(verzeichnis), faktor, schneiden)
        transkript = transkriptor.transkribiere(gehoert, sprache)
        befund = klang.untersuche(wav)
        relpfad = audio_relpfad(sprecher_id, kennung)
        ablage.lege_ab(relpfad, wav)

    return Rohabschnitt(
        id=kennung, text=transkript.text.strip(), blob=relpfad, dauer_s=befund.dauer_s
    )


def _vorbereitet(wav: Path, verzeichnis: Path, faktor: float, schneiden: bool) -> Path:
    """Die Fassung, die das Modell zu hören bekommt - sonst die eigene.

    Was dabei geschieht und in welcher Reihenfolge, steht in
    `wortlaut/vorbereitung.py` - derselben Stelle, die der Trainer und die
    Auswertung fragen. Die Datei lebt so lange wie das temporäre Verzeichnis
    des Aufrufers, also bis das Diktat zerlegt ist. Abgelegt wird sie nirgends:
    Was aufbewahrt wird, ist die echte Aufnahme.
    """
    return vorbereitung.bereite_vor(wav, verzeichnis, faktor=faktor, schneiden=schneiden)


def _als_wav(eingang: bytes, verzeichnis: Path) -> Path:
    """Was der Browser geschickt hat (Opus, MP4, …) → 16 kHz mono, PCM 16 bit."""
    roh = verzeichnis / "eingang"
    roh.write_bytes(eingang)
    wav = verzeichnis / "diktat.wav"
    klang.wandle_in_wav(roh, wav)
    return wav
