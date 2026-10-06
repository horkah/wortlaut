"""Die abgewandelten Fassungen einer Aufnahme: anlegen, finden, wegräumen.

Wie eine Abwandlung gerechnet wird, steht in `wortlaut/augmentierung.py`;
hier steht, wo die Dateien liegen und wann sie entstehen und verschwinden.

* **Angelegt beim Hochladen und, falls eine fehlt, vor dem Messen** - so
  bekommt jede Aufnahme ihre Fassungen ohne eigenes Skript. Eine vorhandene
  Datei wird nie neu gerechnet.
* **Abgelegt**, obwohl sie in 33 ms gerechnet wären: Die Ansicht spielt sie
  ab, und das Manifest eines Laufs zeigt auf sie.
* **Nicht in der Sicherung** - nichts davon ist gesprochen, und sie kommen von
  selbst zurück (`services/ausleitung.py`).
* **Beim Löschen dabei** - dieselbe Stimme, derselbe Gesundheitsdatensatz.

Die Abwandlung im Training entsteht im Trainer und bleibt nirgends liegen
(`apps/lernen/training/klangwandel.py`).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from wortlaut import augmentierung as klangwandel
from wortlaut import corpus, storage

from ..db.models import Aufnahme

# Durchgereicht für den Rest der App.
ORIGINAL = klangwandel.ORIGINAL
VARIANTEN = klangwandel.VARIANTEN
ABWANDLUNGEN = klangwandel.ABWANDLUNGEN


def relpfad(aufnahme: Aufnahme, variante: str) -> str:
    """Der Blob zu einer Fassung dieser Aufnahme.

    Hier und nicht bei jedem Aufrufer, damit Auswertung, Anhören und
    Abwandlung dieselbe Datei meinen.
    """
    if variante == ORIGINAL:
        return aufnahme.blob
    return corpus.variante_relpfad(aufnahme.speaker_id, aufnahme.id, variante)


def stelle_her(
    ablage: storage.Ablage, quelle_blob: str, ziel_blob: str, variante: str, keim: str
) -> bool:
    """Eine fehlende Fassung rechnen; `True`, wenn dabei eine entstanden ist.

    Nimmt Blobs statt der Zeile, weil der Auswertungslauf ohne offene Sitzung
    vorbeikommt. Der Keim ist die Aufnahmekennung - dieselbe Datei auf jeder
    Maschine.
    """
    if variante == ORIGINAL or ablage.pfad(ziel_blob).is_file():
        return False

    quelle = ablage.pfad(quelle_blob)
    if not quelle.is_file():
        raise klangwandel.AudioFehler(f"Audio fehlt: {quelle_blob}")

    # Erst daneben schreiben, dann ablegen - nie eine halbe Datei am Zielort.
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

    Das Original fasst der Aufrufer selbst an.
    """
    for abwandlung in ABWANDLUNGEN:
        ablage.loesche(relpfad(aufnahme, abwandlung.name))
