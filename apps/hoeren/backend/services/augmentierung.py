"""Die abgewandelten Fassungen einer Aufnahme: anlegen, finden, wegräumen.

Was eine Abwandlung ist und wie sie gerechnet wird, steht in
`wortlaut/augmentierung.py` - das ist reine Klangmathematik und gehört ins
gemeinsame Paket. Hier steht der Umgang damit im Korpus: wo die Dateien
liegen, wann sie entstehen und wann sie wieder verschwinden.

**Warum bei Bedarf und nicht nur beim Aufnehmen.** Angelegt werden die
Fassungen an beiden Enden: gleich nach dem Hochladen, damit eine frische
Aufnahme vollständig ist, und noch einmal vor dem Messen, falls eine fehlt.
Das zweite ist kein Gürtel zum Hosenträger, sondern der Weg für alles, was
schon im Korpus liegt: Zu jeder Aufnahme, die vor dieser Änderung entstanden
ist, gibt es keine einzige Fassung, und niemand soll dafür ein Skript suchen
müssen. Teuer ist es nicht - nachzusehen, ob eine Fassung da ist, ist ein
Blick ins Dateisystem, und eine vorhandene Datei wird nie neu gerechnet.

**Warum sie überhaupt liegen bleiben.** Man könnte jede Fassung im
Arbeitsspeicher herstellen, messen und wieder vergessen. Dann wäre die
Auswertung aber das einzige, was je etwas davon hat. So steht ein viermal so
großer Datensatz auf der Platte, den ein späteres Feintuning ohne weiteres
Zutun mitnehmen kann - und der in jeder Sicherung liegt, weil diese das
Datenverzeichnis eins zu eins abbildet (`wortlaut/sicherung.py`).

**Warum sie beim Löschen mitgehen.** Eine abgewandelte Fassung ist dieselbe
Stimme, nur lauter oder verrauscht. Sie ist damit derselbe Gesundheitsdatensatz
wie das Original (Grundentscheidung 6), und wer eine Aufnahme wegwirft, hat
nicht drei Kopien davon gemeint.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from wortlaut import augmentierung as klangwandel
from wortlaut import corpus, storage

from ..db.models import Aufnahme

# Durchgereicht, damit der Rest der App eine Adresse für diese Begriffe hat und
# nicht zwei Pakete tief greifen muss.
ORIGINAL = klangwandel.ORIGINAL
VARIANTEN = klangwandel.VARIANTEN
ABWANDLUNGEN = klangwandel.ABWANDLUNGEN


def relpfad(aufnahme: Aufnahme, variante: str) -> str:
    """Der Blob zu einer Fassung dieser Aufnahme.

    Das Original ist der Blob, der in der Zeile steht - und nicht ein zweites
    Mal berechnet: Eine Aufnahme, die über „schreiben" hereinkam, liegt dort,
    wo ihre Zeile es sagt, und nirgendwo sonst.
    """
    if variante == ORIGINAL:
        return aufnahme.blob
    return corpus.variante_relpfad(aufnahme.speaker_id, aufnahme.id, variante)


def stelle_her(
    ablage: storage.Ablage, quelle_blob: str, ziel_blob: str, variante: str, keim: str
) -> bool:
    """Eine fehlende Fassung rechnen; `True`, wenn dabei eine entstanden ist.

    Nimmt die Blobs und nicht die Zeile, weil der Lauf hier ohne offene
    Sitzung vorbeikommt (`services/auswertung.py`) - ein ORM-Objekt, dessen
    Sitzung zu ist, wäre an dieser Stelle eine Falle.

    Der Keim des Rauschens ist die Aufnahmekennung: Dieselbe Aufnahme ergibt
    auf jeder Maschine dieselbe verrauschte Fassung, und eine gelöschte Datei
    kommt Byte für Byte so zurück, wie sie war. Ohne das wäre eine Wiederholung
    der Messung keine Wiederholung.
    """
    if variante == ORIGINAL or ablage.pfad(ziel_blob).is_file():
        return False

    quelle = ablage.pfad(quelle_blob)
    if not quelle.is_file():
        raise klangwandel.AudioFehler(f"Audio fehlt: {quelle_blob}")

    # Erst daneben schreiben, dann ablegen: `lege_ab` verschiebt, und eine halb
    # geschriebene Datei am Zielort sähe für den nächsten Blick fertig aus.
    with tempfile.TemporaryDirectory() as verzeichnis:
        entwurf = Path(verzeichnis) / f"{variante}.wav"
        klangwandel.wandle_ab(quelle, entwurf, variante, keim=keim)
        ablage.lege_ab(ziel_blob, entwurf)
    return True


def stelle_alle_her(ablage: storage.Ablage, aufnahme: Aufnahme) -> list[str]:
    """Alle fehlenden Fassungen einer Aufnahme rechnen; gibt die neuen zurück."""
    return [
        abwandlung.name
        for abwandlung in ABWANDLUNGEN
        if stelle_her(
            ablage,
            quelle_blob=aufnahme.blob,
            ziel_blob=relpfad(aufnahme, abwandlung.name),
            variante=abwandlung.name,
            keim=aufnahme.id,
        )
    ]


def loesche(ablage: storage.Ablage, aufnahme: Aufnahme) -> None:
    """Alle abgewandelten Fassungen entfernen. Das Original bleibt unangetastet.

    Es zu löschen ist die Sache des Aufrufers: Verwerfen und Wegräumen gehen
    an dieser Stelle verschiedene Wege (siehe `api/recordings.py` und
    `api/admin.py`), und beide fassen den Blob selbst schon an.
    """
    for abwandlung in ABWANDLUNGEN:
        ablage.loesche(relpfad(aufnahme, abwandlung.name))
