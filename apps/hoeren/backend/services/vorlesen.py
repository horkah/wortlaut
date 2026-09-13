"""Die vorgelesene Fassung einer Vorlage: anlegen, finden, wegräumen.

Wie ein Satz zu Klang wird, steht in `wortlaut/vorlesen.py` - das ist der
Motor und gehört ins gemeinsame Paket. Hier steht der Umgang damit im Korpus:
wo die Dateien liegen, wann sie entstehen und wann sie wieder verschwinden.

**Dasselbe Muster wie bei den Abwandlungen** (`services/augmentierung.py`),
und aus denselben Gründen:

* **Bei Bedarf und nicht auf Vorrat.** Eine Vorlage wird vorgelesen, wenn
  jemand darauf drückt; dann entsteht die Datei, und beim zweiten Mal wird
  nichts mehr gerechnet. Ein eigener Knopf „jetzt alles vorlesen" wäre einer,
  den jemand vergisst - `scripts/vorlesen.py` zieht es trotzdem vor, für den,
  der eine Aufnahmesitzung ohne Wartezeit will.
* **Abgeleitet, also nicht in der Sicherung.** Kein Byte davon ist gesprochen
  worden. Wegtragen wäre teuer, neu rechnen ist billig
  (`services/ausleitung.py`).
* **Mit dem Sprecher gelöscht.** Die Datei liegt in seinem Korpusverzeichnis
  und geht mit ihm - auch wenn niemand seine Stimme darin hört.

**Warum je Sprecher und nicht je Satz.** Dieselbe Vorlage kann bei zwei
Menschen stehen, und dann wird sie zweimal gesprochen und zweimal abgelegt. Das
ist verschwenderisch und trotzdem richtig: Der Korpus eines Menschen ist ein
Verzeichnis, das sich vollständig löschen lässt (Grundentscheidung 6). Ein
gemeinsamer Zwischenspeicher wäre die eine Stelle, an der nach dem Löschen
etwas übrig bliebe - und wenn es nur ein Satz ist, den er sprechen sollte.

**Warum das Vorlesen scheitern darf.** Es ist eine Hilfe und keine Bedingung.
Fehlt die Stimme, ist Piper nicht installiert oder geht sonst etwas schief,
kommt hier nichts zurück und die Oberfläche liest mit der Browserstimme vor wie
bisher (`packages/ui/speak.ts`). Das ist der ganze Rückfallweg, und er ist
absichtlich stumm: Wer einen Satz nachsprechen will, soll ihn hören und keine
Fehlermeldung lesen.
"""

from __future__ import annotations

from pathlib import Path

from wortlaut import corpus, storage
from wortlaut import vorlesen as klangwandel

from ..db.models import Vorlage

# Durchgereicht, damit der Rest der App eine Adresse für diese Begriffe hat.
Stimme = klangwandel.Stimme
VorlesenFehler = klangwandel.VorlesenFehler


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

    Eine vorhandene Datei wird nie neu gerechnet. Das ist die ganze
    Zwischenspeicherung, und sie braucht keine Tabelle: Der Dateiname sagt,
    welche Vorlage in welcher Stimme, und die Datei selbst ist der einzige
    Beleg dafür, dass es sie gibt.
    """
    text = str(vorlage.text or "").strip()
    if not text:
        return None

    blob = relpfad(vorlage, stimme)
    if ablage.pfad(blob).is_file():
        return blob

    try:
        motorkopf = klangwandel.motor_fuer(stimmenverzeichnis, motor)
        # Erst in die Ablage hinein sprechen lassen und nicht daneben: Der
        # Motor schreibt ohnehin über eine Entwurfsdatei (siehe dort), und ein
        # zweiter Umweg über ein temporäres Verzeichnis brächte nur eine
        # weitere Stelle, an der eine halbe Datei liegen bleiben kann.
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

    Unter der Kennung `probe` und damit neben den Vorlesungen: derselbe Ort,
    dieselbe Regel (abgeleitet, nicht in der Sicherung, geht mit dem Sprecher),
    nur eben keine Vorlage dahinter.
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

    Gerufen, wenn eine Vorlage verschwindet. Der Text ist dann weg, und ein
    Satz, den niemand mehr sehen kann, soll auch nicht mehr zu hören sein.
    """
    for stimme in stimmen_schluessel:
        ablage.loesche(relpfad(vorlage, stimme))
