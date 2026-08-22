"""Was zu einem Sprecher gehört — und damit, was seine Löschung umfasst.

Das Recht auf Löschung muss ausführbar sein, nicht dokumentiert. Ausführbar
heißt: an **einer** Stelle festgehalten, welche Verzeichnisse einer Person
gehören. Sonst löscht die Aufsicht in der Oberfläche etwas anderes als
`scripts/purge_speaker.py` auf der Kommandozeile, und der Unterschied fällt
niemandem auf — bis er auffällt.

Beide benutzen deshalb dieses Modul.

Warum hier der Blick über die App-Grenze geht: Die Diktate von „schreiben"
sind Stimmaufnahmen derselben Person. Eine Löschung, die an der Grenze der App
haltmacht, wäre unvollständig, und Unvollständigkeit ist bei Gesundheitsdaten
kein Schönheitsfehler. Herübergeholt wird ausdrücklich nur die Layout-Funktion
— ein reiner Pfadbau, der keine Umgebung liest und keinen Dienst startet.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from wortlaut import corpus, registry

from apps.schreiben.backend.config import sprecher_relpfad as diktate_relpfad

# Schnappschüsse legt „lernen" an. Damit sie löschbar bleiben, ohne ihr
# Manifest zu deuten, liegt neben dem Manifest eine Datei mit der Sprecher-ID.
SCHNAPPSCHUESSE = "snapshots"
SCHNAPPSCHUSS_MARKE = "sprecher.txt"


def datenverzeichnisse(sprecher_id: str) -> list[str]:
    """Die Verzeichnisse eines Sprechers, relativ zum Datenverzeichnis.

    Ohne die Schnappschüsse: Die stehen nicht unter seinem Namen, sondern unter
    einer Job-Kennung, und werden deshalb gesondert gesucht (`ziele`). Für die
    Sicherung sind sie ohnehin nicht gemeint — ein Schnappschuss ist eine
    Kopie, und eine Kopie sichert man nicht mit.
    """
    return [corpus.sprecher_relpfad(sprecher_id), diktate_relpfad(sprecher_id)]


def ziele(datenverzeichnis: Path, sprecher_id: str) -> list[Path]:
    """Alles, was bei einer vollständigen Löschung verschwindet — nur Vorhandenes.

    Der Korpus, der Arbeitsstand von „schreiben", die Modellstände aus
    „lernen" und die Schnappschüsse, die aus diesem Korpus entstanden sind.
    """
    kandidaten = [
        *(datenverzeichnis / relativ for relativ in datenverzeichnisse(sprecher_id)),
        datenverzeichnis / registry.MODELLE / sprecher_id,
        *schnappschuesse(datenverzeichnis, sprecher_id),
    ]
    return [ziel for ziel in kandidaten if ziel.exists()]


def loesche(datenverzeichnis: Path, sprecher_id: str) -> list[Path]:
    """Entfernt alles aus `ziele()` und gibt zurück, was entfernt wurde."""
    entfernt = ziele(datenverzeichnis, sprecher_id)
    for ziel in entfernt:
        shutil.rmtree(ziel)
    return entfernt


def schnappschuesse(datenverzeichnis: Path, sprecher_id: str) -> list[Path]:
    """Schnappschüsse dieses Sprechers, erkannt an ihrer `sprecher.txt`."""
    wurzel = datenverzeichnis / SCHNAPPSCHUESSE
    if not wurzel.is_dir():
        return []
    return [
        verzeichnis
        for verzeichnis in sorted(wurzel.iterdir())
        if (marke := verzeichnis / SCHNAPPSCHUSS_MARKE).is_file()
        and marke.read_text(encoding="utf-8").strip() == sprecher_id
    ]


def ohne_marke(datenverzeichnis: Path) -> list[Path]:
    """Schnappschüsse ohne `sprecher.txt` — von Hand zu prüfen, nie geraten.

    Wem ein solcher Schnappschuss gehört, steht nur in seinem Manifest. Ihn
    beim Löschen zu übergehen, hinterlässt Stimmdaten; ihn mitzunehmen, könnte
    fremde treffen. Also wird er gemeldet.
    """
    wurzel = datenverzeichnis / SCHNAPPSCHUESSE
    if not wurzel.is_dir():
        return []
    return [
        verzeichnis
        for verzeichnis in sorted(wurzel.iterdir())
        if verzeichnis.is_dir() and not (verzeichnis / SCHNAPPSCHUSS_MARKE).exists()
    ]
