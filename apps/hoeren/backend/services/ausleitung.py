"""Ein Archiv bauen, ausliefern und danach wegräumen - für beide Wege dorthin.

Die Aufsicht für einen fremden Korpus (`api/admin.py`) und ein Sprecher für
den eigenen (`api/konto.py`) bekommen hier dasselbe gepackt. Die beiden
Formate stehen in `services/export.py`, was draußen bleibt, in `abgeleitet()`.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path

from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from wortlaut import corpus, sicherung, storage

from ..config import einstellungen
from ..db.models import Erkennung, Sprecher
from . import export, loeschung


def kurz(sprecher: Sprecher) -> dict[str, str]:
    """Wie ein Sprecher in der Beschreibung einer Sicherung steht."""
    return {"id": sprecher.id, "name": sprecher.name}


def abgeleitet(sprecher_ids: Iterable[str]) -> sicherung.Abgeleitetes:
    """Was eine Sicherung auslässt, weil es sich jederzeit neu rechnen lässt.

    Gesichert wird, was nirgends sonst existiert: Aufnahmen, Vorlagen,
    Textquellen, Diktate, Profil. Draußen bleiben Rechenergebnisse, die von
    selbst zurückkommen:

    * **Varianten** (`korpus/…/audio/varianten/`), sobald jemand misst;
    * **Vorlesungen** (`korpus/…/vorlesen/`), beim nächsten Vorlesen;
    * **Messwerte** (Tabelle `erkennungen`), mit dem nächsten Auswertungslauf.

    **Zuschnitte bleiben drin.** Nachschneiden dürfte nur „hören", der
    Zuschnitt ist aber auch die Arbeitsdatei von „lernen", das den Korpus nur
    liest (Grundentscheidung 6). Und er ist kürzer als sein Original.

    Modellstände und Laufverzeichnisse stehen gar nicht erst in
    `loeschung.datenverzeichnisse()`.
    """
    return sicherung.Abgeleitetes(
        verzeichnisse=(
            *(corpus.varianten_relpfad(kennung) for kennung in sprecher_ids),
            *(corpus.vorlesen_relpfad(kennung) for kennung in sprecher_ids),
        ),
        tabellen={corpus.DATENBANKNAME: (Erkennung.__tablename__,)},
    )


def sicherung_eines(sprecher: Sprecher) -> FileResponse:
    """Der vollständige Stand eines Sprechers als `.tgz` - zum Zurückspielen.

    Korpus und Diktate ohne das Abgeleitete (`abgeleitet()`), zurück mit
    `scripts/restore.py` oder `tar xzf` (`wortlaut/sicherung.py`).
    """
    beschreibung = {"umfang": "sprecher", "sprecher": [kurz(sprecher)]}
    return archiv(
        f"wortlaut-{sprecher.id}-{sicherung.zeitmarke()}.tgz",
        lambda ziel: sicherung.schreibe_archiv(
            einstellungen().data_dir,
            loeschung.datenverzeichnisse(sprecher.id),
            ziel,
            beschreibung=beschreibung,
            ohne=abgeleitet([sprecher.id]),
        ),
        "application/gzip",
    )


def datensatz_eines(sitzung: Session, sprecher: Sprecher, ablage: storage.Ablage) -> FileResponse:
    """Text-Audio-Paare als `.zip` - für Training und Ansehen von außen.

    Keine Sicherung (`services/export.py`).
    """
    return archiv(
        f"wortlaut-{sprecher.id}-datensatz-{sicherung.zeitmarke()}.zip",
        lambda ziel: export.datensatz_zip(sitzung, sprecher, ablage, ziel),
        "application/zip",
    )


def archiv(dateiname: str, baue: Callable[[Path], Path], medientyp: str) -> FileResponse:
    """Ein Archiv bauen, ausliefern und danach wieder wegräumen.

    In eine temporäre Datei, denn ein Korpus kann Gigabyte groß sein;
    aufgeräumt wird, nachdem Starlette sie ausgeliefert hat.
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
