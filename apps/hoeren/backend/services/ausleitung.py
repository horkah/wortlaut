"""Ein Archiv bauen, ausliefern und danach wegräumen - für beide Wege dorthin.

Zwei Aufrufer holen dieselben zwei Dateien: die Aufsicht für einen fremden
Korpus (`api/admin.py`) und ein Sprecher für den eigenen (`api/konto.py`).
Gepackt wird beides Mal dasselbe, und zwar hier - sonst gäbe es zwei
Vorstellungen davon, was „diese Daten mitnehmen" heißt, und sie liefen mit der
Zeit auseinander.

Was in den beiden Formaten steckt und warum es zwei sind, steht in
`services/export.py`.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from wortlaut import sicherung, storage

from ..config import einstellungen
from ..db.models import Sprecher
from . import export, loeschung


def kurz(sprecher: Sprecher) -> dict[str, str]:
    """Wie ein Sprecher in der Beschreibung einer Sicherung steht."""
    return {"id": sprecher.id, "name": sprecher.name}


def sicherung_eines(sprecher: Sprecher) -> FileResponse:
    """Der vollständige Stand eines Sprechers als `.tgz` - zum Zurückspielen.

    Enthält Korpus und Diktate, wie sie im Datenverzeichnis liegen, mit einer
    in sich stimmigen Kopie der Datenbank. Zurück kommt der Stand mit
    `scripts/restore.py` oder schlicht mit `tar xzf` (siehe
    `wortlaut/sicherung.py`).
    """
    beschreibung = {"umfang": "sprecher", "sprecher": [kurz(sprecher)]}
    return archiv(
        f"wortlaut-{sprecher.id}-{sicherung.zeitmarke()}.tgz",
        lambda ziel: sicherung.schreibe_archiv(
            einstellungen().data_dir,
            loeschung.datenverzeichnisse(sprecher.id),
            ziel,
            beschreibung=beschreibung,
        ),
        "application/gzip",
    )


def datensatz_eines(sitzung: Session, sprecher: Sprecher, ablage: storage.Ablage) -> FileResponse:
    """Text-Audio-Paare als `.zip` - für Training und Ansehen von außen.

    Keine Sicherung, sondern ein Auszug in Ordnerform (siehe
    `services/export.py`).
    """
    return archiv(
        f"wortlaut-{sprecher.id}-datensatz-{sicherung.zeitmarke()}.zip",
        lambda ziel: export.datensatz_zip(sitzung, sprecher, ablage, ziel),
        "application/zip",
    )


def archiv(dateiname: str, baue: Callable[[Path], Path], medientyp: str) -> FileResponse:
    """Ein Archiv bauen, ausliefern und danach wieder wegräumen.

    Gebaut wird in eine temporäre Datei und nicht in den Arbeitsspeicher: Ein
    Korpus kann Gigabyte groß sein. Aufgeräumt wird über eine
    Hintergrundaufgabe - sie läuft, nachdem die Antwort durch ist, denn vorher
    liest Starlette noch aus genau dieser Datei.
    """
    verzeichnis = Path(tempfile.mkdtemp(prefix="wortlaut-ausleitung-"))
    try:
        baue(verzeichnis / dateiname)
    except Exception:
        shutil.rmtree(verzeichnis, ignore_errors=True)
        raise
    return FileResponse(
        verzeichnis / dateiname,
        media_type=medientyp,
        filename=dateiname,
        background=BackgroundTask(shutil.rmtree, verzeichnis, ignore_errors=True),
    )
