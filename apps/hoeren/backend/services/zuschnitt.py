"""Der Zuschnitt einer Aufnahme - und die eine Regel, welche Datei gilt.

Aufgenommen wird äußerungsweise: Jemand liest einen Satz vor, drückt vorher
auf einen Knopf und nachher noch einmal. Zwischen dem ersten Druck und dem
ersten Laut liegt eine Sekunde, zwischen dem letzten Laut und dem zweiten
Druck oft zwei - und bei jemandem, der langsam spricht und schlecht trifft,
auch mehr. Über einen Korpus von anderthalb Stunden summiert sich das auf eine
halbe Stunde Stille, die mittrainiert und mitgemessen wird.

Diese Datei schneidet sie weg, und zwar **nicht** von selbst: Was wirklich
geschnitten wird, entscheidet ein Mensch in der Zuschnittansicht
(`api/zuschnitt.py`). Hier steht, was dabei mit den Dateien geschieht.

## Die Regel

    Gibt es zu einer Aufnahme einen Zuschnitt, gilt der Zuschnitt.
    Sonst gilt das Original.

Das ist `arbeitsblob`, und es ist die **einzige** Stelle, an der diese Frage
beantwortet wird. Jeder Weg, der Audio anfasst, geht über sie: das Anhören in
„Meine Daten", die Abwandlungen, die Auswertung, das Manifest eines
Trainingslaufs, der Datensatz zum Mitnehmen. Ein Schalter „Zuschnitt
benutzen" daneben wäre eine zweite Frage zu derselben Sache - und irgendwann
trainierte jemand auf einer Datei, die er in der Ansicht nicht hört.

## Was bleibt

Das Original bleibt liegen und unverändert. `recordings.blob` zeigt weiter
darauf, die Sicherung trägt es weg, und ein Zuschnitt lässt sich zurücknehmen,
ohne dass jemand noch einmal sprechen muss. Eine Aufnahme ist das, was ein
Mensch gesprochen hat; ein Zuschnitt ist eine Entscheidung darüber.

## Verlustfrei

Der Korpus liegt in 16 kHz mono PCM 16 bit (`wortlaut/audio.py`). Ein Rahmen
ist dort zwei Byte und zugleich der kleinste Block, an dem sich schneiden
lässt - ein Schnitt ist das Kopieren eines Byte-Bereichs, und was dabei
herauskommt, ist Abtastwert für Abtastwert dasselbe wie im Original.

Es braucht dafür weder ffmpeg noch `-c copy` noch eine Rundung auf
Blockgrenzen: Bei PCM gibt es keine Blöcke, die größer wären als ein
Abtastwert. Gerundet wird trotzdem, nämlich **nach außen** - Anfang abwärts,
Ende aufwärts (`audio.schneide_ausschnitt`, `nach_aussen=True`). Ein Rahmen zu
viel sind 62 Mikrosekunden Stille, ein Rahmen zu wenig wäre ein
angeschnittener Abtastwert.

Eine Ein- und Ausblendung gegen Knackser gibt es aus demselben Grund nicht:
Sie würde Abtastwerte verändern, und geschnitten wird ohnehin in der Stille,
wo nichts knackst.
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

from sqlalchemy import func
from wortlaut import audio as klang
from wortlaut import corpus, storage

from ..db.models import Aufnahme


def hat_zuschnitt(aufnahme: Aufnahme) -> bool:
    """Ob zu dieser Aufnahme ein Zuschnitt eingetragen ist."""
    return aufnahme.zuschnitt_start_s is not None and aufnahme.zuschnitt_ende_s is not None


def zuschnitt_blob(aufnahme: Aufnahme) -> str:
    """Wo der Zuschnitt dieser Aufnahme liegt - ob er schon da ist oder nicht."""
    return corpus.zuschnitt_relpfad(aufnahme.speaker_id, aufnahme.id)


def arbeitsblob(aufnahme: Aufnahme) -> str:
    """**Die Regel.** Die Datei, mit der überall gearbeitet wird.

    Ohne Ablage und ohne Blick ins Dateisystem: Was gilt, steht in der Zeile,
    nicht auf der Platte. Fehlt die eingetragene Datei, ist das ein Fehler und
    kein stiller Rückfall auf das Original - sonst träte an die Stelle einer
    Entscheidung ein Zufall, und niemand sähe es der Zahl danach an.
    """
    return zuschnitt_blob(aufnahme) if hat_zuschnitt(aufnahme) else aufnahme.blob


def arbeitsdauer(aufnahme: Aufnahme) -> float:
    """Wie lang die Arbeitsdatei ist - gerechnet, nicht gespeichert.

    `recordings.dauer_s` bleibt die Dauer des Originals; sie ist ein Messwert
    und soll einer bleiben. Eine dritte Spalte für die Dauer des Zuschnitts
    wäre eine Zahl, die mit den beiden Grenzen daneben auseinanderlaufen kann.
    """
    if not hat_zuschnitt(aufnahme):
        return aufnahme.dauer_s
    return aufnahme.zuschnitt_ende_s - aufnahme.zuschnitt_start_s


def schneide(
    ablage: storage.Ablage, aufnahme: Aufnahme, start_s: float, ende_s: float
) -> tuple[float, float]:
    """Den Zuschnitt schreiben und die Grenzen in die Zeile eintragen.

    Ein zweiter Schnitt ersetzt den ersten: Es liegt je Aufnahme genau eine
    zugeschnittene Datei, und die Grenzen in der Zeile beschreiben immer sie.
    Eine Kette von Fassungen wäre eine Versionsgeschichte in einem Verzeichnis,
    das jede andere App als „die Arbeitsdatei" liest.

    Geschrieben wird aus dem **Original**, nie aus einem vorherigen Zuschnitt.
    Sonst wanderte die Grenze mit jedem Durchgang nach innen, und nach dem
    dritten Mal wäre der erste Laut weg - unwiederbringlich, denn was der
    Schnitt weglässt, steht danach in keiner Arbeitsdatei mehr.

    Eingetragen werden die Grenzen, die der Schnitt wirklich erreicht hat, und
    nicht die gewünschten. Sie sind auf Rahmen gerundet und auf die Datei
    zurechtgestutzt; was in der Zeile steht, soll beschreiben, was in der Datei
    steht.
    """
    quelle = ablage.pfad(aufnahme.blob)
    if not quelle.is_file():
        raise klang.AudioFehler(f"Audio fehlt: {aufnahme.blob}")
    if not ende_s > start_s:
        raise klang.AudioFehler(
            f"Das Ende muss hinter dem Anfang liegen ({start_s:.2f} bis {ende_s:.2f} s)."
        )

    # Erst daneben schreiben, dann ablegen: `lege_ab` verschiebt, und eine halb
    # geschriebene Datei am Zielort sähe für den nächsten Blick fertig aus -
    # genau wie bei den abgewandelten Fassungen (`services/augmentierung.py`).
    with tempfile.TemporaryDirectory() as verzeichnis:
        entwurf = Path(verzeichnis) / "zuschnitt.wav"
        erreicht = klang.schneide_ausschnitt(quelle, entwurf, start_s, ende_s, nach_aussen=True)
        ablage.lege_ab(zuschnitt_blob(aufnahme), entwurf)

    aufnahme.zuschnitt_start_s, aufnahme.zuschnitt_ende_s = erreicht
    return erreicht


def nimm_zurueck(ablage: storage.Ablage, aufnahme: Aufnahme) -> bool:
    """Den Zuschnitt verwerfen; ab dann gilt wieder das Original.

    Gibt zurück, ob es etwas zurückzunehmen gab. Die Datei geht mit: Sie ist
    abgeleitet, und eine liegengebliebene Datei ohne Zeile wäre dasselbe
    Durcheinander wie eine Zeile ohne Datei.
    """
    if not hat_zuschnitt(aufnahme):
        return False
    ablage.loesche(zuschnitt_blob(aufnahme))
    aufnahme.zuschnitt_start_s = None
    aufnahme.zuschnitt_ende_s = None
    return True


def stelle_her(ablage: storage.Ablage, aufnahme: Aufnahme) -> bool:
    """Eine fehlende Zuschnittdatei aus dem Original und den Grenzen nachrechnen.

    Der Regelfall ist, dass sie da ist: Anders als die abgewandelten Fassungen
    wird der Zuschnitt **mitgesichert** (`services/ausleitung.py`). Gebraucht
    wird das hier trotzdem, und zwar für den Bestand, in dem doch einmal eine
    Datei fehlt - ein halb kopiertes Verzeichnis, eine Sicherung von vor der
    Regel. Die Zuschnittansicht ruft es beim Auflisten; dort ist es ein Blick
    ins Dateisystem je Zeile einer Seite und kostet nichts.

    Was dabei entsteht, ist Byte für Byte dasselbe wie vorher: Der Schnitt
    liest dieselbe Quelle und dieselben Grenzen, und er rechnet nicht, er
    kopiert.
    """
    if not hat_zuschnitt(aufnahme) or ablage.pfad(zuschnitt_blob(aufnahme)).is_file():
        return False
    schneide(ablage, aufnahme, aufnahme.zuschnitt_start_s, aufnahme.zuschnitt_ende_s)
    return True


def loesche(ablage: storage.Ablage, aufnahme: Aufnahme) -> None:
    """Die zugeschnittene Fassung entfernen. Das Original bleibt unangetastet.

    Für die Löschwege (`api/recordings.py`, `api/admin.py`), die den Blob
    selbst schon anfassen - dieselbe Aufteilung wie bei
    `augmentierung.loesche`. Ein Zuschnitt ist dieselbe Stimme, nur kürzer,
    und damit derselbe Gesundheitsdatensatz wie das Original.
    """
    ablage.loesche(zuschnitt_blob(aufnahme))


def reihenfolge() -> tuple:
    """Wie Aufnahmen der Reihe nach stehen: nach Datum, und bei gleichem Datum
    das Original vor seinen Teilen (`017_teilen.sql`).

    Für `order_by(*zuschnitt.reihenfolge())`. Absteigend - wie in „Meine
    Daten" - kehrt sich beides um, und die Teile stehen dann vor dem Original;
    beieinander bleiben sie trotzdem.
    """
    return (Aufnahme.erstellt, func.coalesce(Aufnahme.sortierschluessel, Aufnahme.id))


def teile(
    ablage: storage.Ablage,
    aufnahme: Aufnahme,
    start_s: float,
    teilung_s: float,
    ende_s: float,
    ziel_vorn: str,
    ziel_hinten: str,
) -> tuple[klang.Befund, klang.Befund]:
    """Aus dem Original zwei Dateien schneiden: [start, teilung) und [teilung, ende).

    Aus dem **Original** wie jeder Schnitt hier - die Ansicht zeigt dessen
    Kurve, und in ihr stehen die drei Linien. Ein Zuschnitt, der auf der
    Aufnahme liegt, geht die Teile nichts an: Ihre Ränder sind die beiden
    äußeren Linien.

    **Die Teilung sitzt auf genau einem Rahmen.** Außen wird nach außen
    gerundet, wie beim Zuschneiden. Innen darf das nicht sein: Der eine Teil
    endete einen Rahmen später, als der andere beginnt, und ein Abtastwert
    stünde in beiden. Die Teilung wird deshalb zuerst auf einen Rahmen gelegt
    und dann so übergeben, dass beide Rundungen auf ihm landen - der vordere
    Teil schneidet dort ab, der hintere rundet dorthin ab. Aneinandergelegt
    sind die beiden Byte für Byte der Bereich des Originals.

    Gibt die Befunde beider Teile zurück; abgelegt ist danach beides.
    """
    quelle = ablage.pfad(aufnahme.blob)
    if not quelle.is_file():
        raise klang.AudioFehler(f"Audio fehlt: {aufnahme.blob}")
    if not start_s < teilung_s < ende_s:
        raise klang.AudioFehler(
            "Die Teilung muss zwischen Anfang und Ende liegen "
            f"({start_s:.2f} < {teilung_s:.2f} < {ende_s:.2f} s)."
        )
    with wave.open(str(quelle), "rb") as datei:
        rate = datei.getframerate()
    # Ein Viertelrahmen hinter der Rahmengrenze: `int` schneidet ihn für den
    # vorderen Teil ab, `floor` rundet ihn für den hinteren ebenfalls ab -
    # beide landen auf demselben Rahmen, und keine Gleitkommazahl kann einen
    # der beiden auf den Nachbarn kippen lassen.
    innen = (round(teilung_s * rate) + 0.25) / rate

    with tempfile.TemporaryDirectory() as verzeichnis:
        vorn = Path(verzeichnis) / "vorn.wav"
        hinten = Path(verzeichnis) / "hinten.wav"
        klang.schneide_ausschnitt(quelle, vorn, start_s, innen)
        klang.schneide_ausschnitt(quelle, hinten, innen, ende_s, nach_aussen=True)
        befunde = (klang.untersuche(vorn), klang.untersuche(hinten))
        ablage.lege_ab(ziel_vorn, vorn)
        ablage.lege_ab(ziel_hinten, hinten)
    return befunde
