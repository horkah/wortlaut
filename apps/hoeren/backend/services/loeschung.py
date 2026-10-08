"""Was zu einem Sprecher gehört - und damit, was seine Löschung umfasst.

Die eine Stelle, die Oberfläche der Aufsicht und `scripts/purge_speaker.py`
fragen - sonst löschten beide Verschiedenes.

Der Blick geht über die App-Grenze: Diktate aus „schreiben" und alles, was
„lernen" führt, gehören zur selben Person. Herübergeholt werden nur
Pfadfunktionen, die keine Umgebung lesen.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from wortlaut import corpus, laeufe, registry

from apps.lernen.backend.config import sprecher_relpfad as lernen_relpfad
from apps.schreiben.backend.config import sprecher_relpfad as diktate_relpfad


def datenverzeichnisse(sprecher_id: str) -> list[str]:
    """Die Verzeichnisse eines Sprechers, relativ zum Datenverzeichnis.

    Ohne die Laufverzeichnisse, die unter einer Job-Kennung stehen (`ziele`)
    und als Kopien nicht in die Sicherung gehören.
    """
    return [
        corpus.sprecher_relpfad(sprecher_id),
        diktate_relpfad(sprecher_id),
        # Das Register der Läufe (`lernen/<sprecher>`), falls vorhanden.
        lernen_relpfad(sprecher_id),
    ]


def ziele(datenverzeichnis: Path, sprecher_id: str) -> list[Path]:
    """Alles, was bei einer vollständigen Löschung verschwindet - nur Vorhandenes.

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
    wurzel = laeufe.wurzel(datenverzeichnis)
    if not wurzel.is_dir():
        return []
    return [
        verzeichnis
        for verzeichnis in sorted(wurzel.iterdir())
        if (marke := verzeichnis / laeufe.SPRECHER_MARKE).is_file()
        and marke.read_text(encoding="utf-8").strip() == sprecher_id
    ]


def ohne_marke(datenverzeichnis: Path) -> list[Path]:
    """Schnappschüsse ohne `sprecher.txt` - von Hand zu prüfen, nie geraten.

    Übergangen hinterließe er Stimmdaten, mitgenommen träfe er womöglich
    fremde - also wird er gemeldet.
    """
    wurzel = laeufe.wurzel(datenverzeichnis)
    if not wurzel.is_dir():
        return []
    return [
        verzeichnis
        for verzeichnis in sorted(wurzel.iterdir())
        if verzeichnis.is_dir() and not (verzeichnis / laeufe.SPRECHER_MARKE).exists()
    ]
