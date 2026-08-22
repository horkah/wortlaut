"""Sicherung und Wiederherstellung — ein Archiv, kein Dienst.

Eine Sicherung ist ein `.tar.gz`, das den Datenbestand so enthält, wie er unter
`WORTLAUT_DATA_DIR` liegt:

    wortlaut-sicherung-<zeit>.tgz
    ├── sicherung.json               was drin ist, wann gezogen, mit Prüfsummen
    └── daten/
        ├── korpus/spr_…/hoeren.sqlite
        ├── korpus/spr_…/audio/rec_….wav
        └── diktate/spr_…/…          Arbeitsstand von „schreiben"

`daten/` bildet das Datenverzeichnis eins zu eins ab. Das ist der ganze Trick
der Wiederherstellung: Sie ist ein Auspacken an die richtige Stelle, kein
Einspielen. Wer keinen Server mehr hat, auf dem diese Anwendung läuft, kommt
mit `tar xzf` genauso weit wie mit `scripts/restore.py` — eine Sicherung, die
ein laufendes Programm zum Lesen braucht, ist im Ernstfall keine.

Die Datenbanken werden dabei nicht kopiert, sondern über `db.sichere_kopie()`
gezogen: Im WAL-Modus steht ein Teil der Daten neben der `.sqlite`-Datei, und
eine schlichte Kopie wäre ein Stand, den es nie gegeben hat.

Diese Datei ist die einzige Stelle, die das Archivformat kennt — so wie
`corpus.py` die einzige ist, die das Korpus-Layout kennt.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import db

MANIFEST = "sicherung.json"
DATEN = "daten"
FORMAT = "wortlaut-sicherung"
VERSION = 1

DATENBANK_ENDUNG = ".sqlite"
# Die Begleitdateien von SQLite im WAL-Modus. Sie gehören ausdrücklich nicht
# ins Archiv: `sichere_kopie()` hat ihren Inhalt bereits eingearbeitet, und
# eine mitgesicherte `-wal` neben einer vollständigen Datenbank wäre beim
# Auspacken ein Widerspruch.
BEGLEITER = ("-wal", "-shm")


def zeitmarke() -> str:
    """Für Dateinamen: `20260822-174500`. Sortierbar, ohne Sonderzeichen."""
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def schreibe_archiv(
    datenverzeichnis: Path,
    verzeichnisse: Iterable[str],
    ziel: Path,
    *,
    beschreibung: dict[str, Any] | None = None,
) -> Path:
    """Sichert die genannten Unterverzeichnisse des Datenverzeichnisses nach `ziel`.

    `verzeichnisse` sind relative Pfade wie `korpus/spr_…` oder `diktate/spr_…`.
    Was es nicht gibt, wird übergangen — ein Sprecher ohne Diktate ist kein
    Fehlerfall, sondern der Normalfall.

    `beschreibung` wandert unverändert ins Manifest; dort steht, wofür diese
    Sicherung gezogen wurde — ein Sprecher oder der ganze Bestand.
    """
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
                name, angaben = _lege_bei(archiv, Path(arbeit), datenverzeichnis, datei)
                dateien[name] = angaben

        manifest = {
            "format": FORMAT,
            "version": VERSION,
            "erstellt": datetime.now(UTC).isoformat(timespec="seconds"),
            **(beschreibung or {}),
            "dateien": dateien,
        }
        _lege_text_bei(archiv, MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))

    return ziel


def lies_manifest(archiv: Path) -> dict[str, Any]:
    """Das Manifest einer Sicherung, ohne sie auszupacken."""
    with tarfile.open(archiv, "r:gz") as geoeffnet:
        eintrag = geoeffnet.extractfile(MANIFEST)
        if eintrag is None:
            raise ValueError(f"{archiv} enthält kein {MANIFEST} — das ist keine Sicherung.")
        manifest = json.loads(eintrag.read().decode("utf-8"))
    if manifest.get("format") != FORMAT:
        raise ValueError(f"{archiv} ist keine wortlaut-Sicherung.")
    return manifest


def stelle_wieder_her(
    archiv: Path, datenverzeichnis: Path, *, ueberschreiben: bool = False
) -> list[str]:
    """Packt `daten/` aus dem Archiv ins Datenverzeichnis; gibt die Pfade zurück.

    Ohne `ueberschreiben` bricht der Vorgang ab, sobald eine Datei schon da
    ist — und zwar bevor irgendetwas geschrieben wurde. Eine Wiederherstellung,
    die einen laufenden Bestand halb überschreibt, wäre schlimmer als keine.
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

    # Erst in ein Zwischenlager auspacken, dann an den richtigen Ort schieben.
    # Der Umweg hält das `daten/` aus dem Archivnamen aus dem Zielpfad heraus,
    # ohne die Prüfung von `filter="data"` zu umgehen: Die weist Pfade ab, die
    # aus dem Zielverzeichnis herausführen (`../…`, absolute Pfade, Verweise).
    # Ohne sie könnte ein untergeschobenes Archiv beim Auspacken überallhin
    # schreiben.
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
    archiv: tarfile.TarFile, arbeit: Path, datenverzeichnis: Path, datei: Path
) -> tuple[str, dict[str, Any]]:
    """Eine Datei ins Archiv legen; Datenbanken über die Sicherungskopie."""
    relativ = datei.relative_to(datenverzeichnis)
    name = f"{DATEN}/{relativ.as_posix()}"

    quelle = datei
    if datei.suffix == DATENBANK_ENDUNG:
        quelle = db.sichere_kopie(datei, arbeit / relativ)

    archiv.add(quelle, arcname=name)
    return name, {"bytes": quelle.stat().st_size, "sha256": _pruefsumme(quelle)}


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

    Beim Überschreiben eines bestehenden Bestands blieben sonst die
    Begleitdateien des alten Standes liegen. SQLite hielte sie für den
    Nachtrag zu der neuen Datei und läse einen Mischmasch aus beidem.
    """
    for relativ in geschrieben:
        if not relativ.endswith(DATENBANK_ENDUNG):
            continue
        for anhang in BEGLEITER:
            (datenverzeichnis / f"{relativ}{anhang}").unlink(missing_ok=True)
