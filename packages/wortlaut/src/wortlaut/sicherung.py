"""Sicherung und Wiederherstellung - ein Archiv, kein Dienst.

Eine Sicherung ist ein `.tar.gz`, das den Datenbestand so enthält, wie er unter
`WORTLAUT_DATA_DIR` liegt:

    wortlaut-sicherung-<zeit>.tgz
    ├── sicherung.json               was drin ist, wann gezogen, mit Prüfsummen
    └── daten/
        ├── korpus/spr_…/hoeren.sqlite
        ├── korpus/spr_…/audio/rec_….wav
        └── diktate/spr_…/…          Arbeitsstand von „schreiben"

`daten/` bildet das Datenverzeichnis ab: Wiederherstellen heißt Auspacken an
die richtige Stelle. `tar xzf` kommt so weit wie `scripts/restore.py`.

Gesichert wird, was ein Mensch hervorgebracht hat. Was eine Maschine daraus
rechnet - Varianten, Vorlesungen, Messwerte (`Abgeleitetes`) -, bleibt
draußen und kommt nach dem Zurückspielen von selbst wieder. `sicherung.json`
nennt das Ausgelassene unter `ausgelassen`.

Die Datenbanken kommen über `db.sichere_kopie()`, nicht als Dateikopie - im
WAL-Modus stünde sonst ein Teil der Daten daneben. Diese Datei ist die einzige
Stelle, die das Archivformat kennt.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import sqlite3
import tarfile
import tempfile
from collections.abc import Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import db

MANIFEST = "sicherung.json"
DATEN = "daten"
FORMAT = "wortlaut-sicherung"
VERSION = 1

DATENBANK_ENDUNG = ".sqlite"
# Die Begleitdateien im WAL-Modus - ihr Inhalt steckt schon in der Kopie.
BEGLEITER = ("-wal", "-shm")


# Tabellennamen gehen in ein `DELETE FROM`, das keinen Platzhalter verträgt.
_BEZEICHNER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Abgeleitetes:
    """Was aus dem Bestand neu zu rechnen ist - und deshalb nicht mitgesichert wird.

    Was abgeleitet ist, sagt der Aufrufer; hier steht nur, wie es wegbleibt:
    Ein Verzeichnis wird übersprungen, eine Tabelle in der Sicherungskopie
    geleert. Schema und alle übrigen Zeilen bleiben.

    `verzeichnisse` sind vollständige Pfade relativ zum Datenverzeichnis,
    `tabellen` bildet den Dateinamen einer Datenbank auf ihre abgeleiteten
    Tabellen ab - `{"hoeren.sqlite": ("erkennungen",)}`.
    """

    verzeichnisse: tuple[str, ...] = ()
    tabellen: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def uebergeht(self, relativ: Path) -> bool:
        """Liegt diese Datei in einem der ausgelassenen Verzeichnisse?"""
        pfad = relativ.as_posix()
        return any(pfad.startswith(f"{ordner}/") for ordner in self.verzeichnisse)

    def tabellen_von(self, datenbank: Path) -> tuple[str, ...]:
        """Die abgeleiteten Tabellen dieser Datenbank - am Dateinamen erkannt."""
        return tuple(self.tabellen.get(datenbank.name, ()))

    def als_manifest(self) -> dict[str, Any]:
        return {
            "verzeichnisse": list(self.verzeichnisse),
            "tabellen": {name: list(tabellen) for name, tabellen in self.tabellen.items()},
        }


def zeitmarke() -> str:
    """Für Dateinamen: `20260822-174500`. Sortierbar, ohne Sonderzeichen."""
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def schreibe_archiv(
    datenverzeichnis: Path,
    verzeichnisse: Iterable[str],
    ziel: Path,
    *,
    beschreibung: dict[str, Any] | None = None,
    ohne: Abgeleitetes | None = None,
) -> Path:
    """Sichert die genannten Unterverzeichnisse des Datenverzeichnisses nach `ziel`.

    `verzeichnisse` sind relative Pfade wie `korpus/spr_…`; was fehlt, wird
    übergangen. `ohne` nennt das Abgeleitete, `beschreibung` wandert
    unverändert ins Manifest.
    """
    ausgelassen = ohne or Abgeleitetes()
    ziel.parent.mkdir(parents=True, exist_ok=True)
    dateien: dict[str, dict[str, Any]] = {}

    # Ein Zwischenverzeichnis allein für die Datenbanken: Ihre Kopien entstehen
    # erst hier, die Audiodateien wandern unverändert aus dem Bestand ins Archiv.
    with tempfile.TemporaryDirectory() as arbeit, tarfile.open(ziel, "w:gz") as archiv:
        for relativ in verzeichnisse:
            quelle = datenverzeichnis / relativ
            if not quelle.is_dir():
                continue
            for datei in sorted(pfad for pfad in quelle.rglob("*") if pfad.is_file()):
                if datei.name.endswith(BEGLEITER):
                    continue
                if ausgelassen.uebergeht(datei.relative_to(datenverzeichnis)):
                    continue
                name, angaben = _lege_bei(
                    archiv, Path(arbeit), datenverzeichnis, datei, ausgelassen
                )
                dateien[name] = angaben

        manifest = {
            "format": FORMAT,
            "version": VERSION,
            "erstellt": datetime.now(UTC).isoformat(timespec="seconds"),
            **(beschreibung or {}),
            "ausgelassen": ausgelassen.als_manifest(),
            "dateien": dateien,
        }
        _lege_text_bei(archiv, MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))

    return ziel


def lies_manifest(archiv: Path) -> dict[str, Any]:
    """Das Manifest einer Sicherung, ohne sie auszupacken."""
    with tarfile.open(archiv, "r:gz") as geoeffnet:
        eintrag = geoeffnet.extractfile(MANIFEST)
        if eintrag is None:
            raise ValueError(f"{archiv} enthält kein {MANIFEST} - das ist keine Sicherung.")
        manifest = json.loads(eintrag.read().decode("utf-8"))
    if manifest.get("format") != FORMAT:
        raise ValueError(f"{archiv} ist keine wortlaut-Sicherung.")
    return manifest


def stelle_wieder_her(
    archiv: Path, datenverzeichnis: Path, *, ueberschreiben: bool = False
) -> list[str]:
    """Packt `daten/` aus dem Archiv ins Datenverzeichnis; gibt die Pfade zurück.

    Ohne `ueberschreiben` bricht der Vorgang ab, bevor etwas geschrieben ist,
    wenn eine Datei schon da ist.
    """
    manifest = lies_manifest(archiv)
    vorhandene = [
        name
        for name in manifest.get("dateien", {})
        if (datenverzeichnis / name.removeprefix(f"{DATEN}/")).exists()
    ]
    if vorhandene and not ueberschreiben:
        raise FileExistsError(
            f"{len(vorhandene)} Datei(en) sind schon da, zuerst {vorhandene[0]}. "
            "Mit --ueberschreiben wird der vorhandene Stand ersetzt."
        )

    datenverzeichnis.mkdir(parents=True, exist_ok=True)
    geschrieben: list[str] = []

    # Über ein Zwischenlager, damit `daten/` aus dem Zielpfad fällt, ohne die
    # Prüfung von `filter="data"` zu umgehen - sie weist Pfade ab, die aus dem
    # Ziel herausführen.
    with tempfile.TemporaryDirectory() as zwischenlager:
        lager = Path(zwischenlager)
        with tarfile.open(archiv, "r:gz") as geoeffnet:
            eintraege = [
                eintrag
                for eintrag in geoeffnet.getmembers()
                if eintrag.name == DATEN or eintrag.name.startswith(f"{DATEN}/")
            ]
            geoeffnet.extractall(lager, members=eintraege, filter="data")

        ausgepackt = lager / DATEN
        for datei in sorted(pfad for pfad in ausgepackt.rglob("*") if pfad.is_file()):
            relativ = datei.relative_to(ausgepackt)
            ziel = datenverzeichnis / relativ
            ziel.parent.mkdir(parents=True, exist_ok=True)
            # `move` statt `replace`: Zwischenlager und Ziel liegen nicht
            # zwingend auf demselben Dateisystem.
            shutil.move(str(datei), ziel)
            geschrieben.append(relativ.as_posix())

    _entferne_veraltete_begleiter(datenverzeichnis, geschrieben)
    return geschrieben


def _lege_bei(
    archiv: tarfile.TarFile,
    arbeit: Path,
    datenverzeichnis: Path,
    datei: Path,
    ausgelassen: Abgeleitetes,
) -> tuple[str, dict[str, Any]]:
    """Eine Datei ins Archiv legen; Datenbanken über die Sicherungskopie."""
    relativ = datei.relative_to(datenverzeichnis)
    name = f"{DATEN}/{relativ.as_posix()}"

    quelle = datei
    if datei.suffix == DATENBANK_ENDUNG:
        quelle = db.sichere_kopie(datei, arbeit / relativ)
        _leere(quelle, ausgelassen.tabellen_von(datei))

    archiv.add(quelle, arcname=name)
    return name, {"bytes": quelle.stat().st_size, "sha256": _pruefsumme(quelle)}


def _leere(datenbank: Path, tabellen: Iterable[str]) -> None:
    """Abgeleitete Zeilen aus der Sicherungskopie werfen - nie aus dem Bestand.

    Eine fehlende Tabelle hat nichts wegzulassen. `VACUUM` macht die Datei
    tatsächlich kleiner.
    """
    namen = list(tabellen)
    ungueltig = [name for name in namen if not _BEZEICHNER.match(name)]
    if ungueltig:
        # Laut: sonst landete Abgeleitetes unbemerkt im Archiv.
        raise ValueError(f"Kein Tabellenname: {ungueltig[0]!r}")
    if not namen:
        return
    with closing(sqlite3.connect(datenbank)) as verbindung:
        vorhanden = {
            zeile[0]
            for zeile in verbindung.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        geleert = [name for name in namen if name in vorhanden]
        for name in geleert:
            verbindung.execute(f"DELETE FROM {name}")  # `_BEZEICHNER` hat ihn geprüft
        verbindung.commit()
        if geleert:
            verbindung.execute("VACUUM")


def _lege_text_bei(archiv: tarfile.TarFile, name: str, inhalt: str) -> None:
    rohwert = inhalt.encode("utf-8")
    eintrag = tarfile.TarInfo(name)
    eintrag.size = len(rohwert)
    eintrag.mtime = int(datetime.now(UTC).timestamp())
    archiv.addfile(eintrag, io.BytesIO(rohwert))


def _pruefsumme(datei: Path) -> str:
    kessel = hashlib.sha256()
    with datei.open("rb") as offen:
        for block in iter(lambda: offen.read(1024 * 1024), b""):
            kessel.update(block)
    return kessel.hexdigest()


def _entferne_veraltete_begleiter(datenverzeichnis: Path, geschrieben: Iterable[str]) -> None:
    """`-wal`/`-shm` neben einer frisch eingespielten Datenbank wegräumen.

    SQLite hielte die alten für den Nachtrag zur neuen Datei.
    """
    for relativ in geschrieben:
        if not relativ.endswith(DATENBANK_ENDUNG):
            continue
        for anhang in BEGLEITER:
            (datenverzeichnis / f"{relativ}{anhang}").unlink(missing_ok=True)
