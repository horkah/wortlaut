"""Ein Archiv bauen, ausliefern und danach wegräumen - für beide Wege dorthin.

Zwei Aufrufer holen dieselben zwei Dateien: die Aufsicht für einen fremden
Korpus (`api/admin.py`) und ein Sprecher für den eigenen (`api/konto.py`).
Gepackt wird beides Mal dasselbe, und zwar hier - sonst gäbe es zwei
Vorstellungen davon, was „diese Daten mitnehmen" heißt, und sie liefen mit der
Zeit auseinander.

Was in den beiden Formaten steckt und warum es zwei sind, steht in
`services/export.py`.

Und was in **keinem** von beiden steckt, steht in `abgeleitet()`: Ausgeleitet
wird, was dieser Mensch gesprochen und eingerichtet hat, nicht das, was eine
Maschine daraus gerechnet hat.
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

    Eine Sicherung soll enthalten, was Stunden gekostet hat und nirgends sonst
    existiert: die Aufnahmen, die Vorlagen, die Textquellen, die Diktate, das
    Profil. Zwei Dinge im Datenverzeichnis sind davon nichts, sondern
    Rechenergebnisse:

    * **Die abgewandelten Fassungen** (`korpus/…/audio/varianten/`) - dieselbe
      Aufnahme, verrauscht. Eine Datei je Aufnahme, also die Hälfte des Audios
      im Archiv, und sie entsteht von selbst wieder, sobald jemand misst
      (`services/augmentierung.py`).
    * **Die vorgelesenen Vorlagen** (`korpus/…/vorlesen/`) - Sätze, die eine
      Maschine gesprochen hat, damit ein Mensch sie nachsprechen kann. Kein
      Byte davon ist gesprochen worden; es entsteht in Sekundenbruchteilen
      wieder (`services/vorlesen.py`).
    * **Die Messwerte der Auswertung** (Tabelle `erkennungen`) - was welches
      Modell aus welcher Fassung gemacht hat. Daraus entstehen die Kurven; ein
      zweiter Lauf rechnet ohnehin nur, was fehlt (`services/auswertung.py`).

    **Die Zuschnitte (`korpus/…/audio/zuschnitt/`) bleiben dagegen drin**,
    obwohl auch sie sich aus dem Original und zwei Zahlen neu schneiden ließen.
    Der Unterschied zu den beiden oben ist nicht die Rechenzeit, sondern wer
    nachrechnen dürfte: Eine fehlende Abwandlung holt sich die Auswertung
    selbst, und die läuft in „hören", dem Schreiber des Korpus. Der Zuschnitt
    ist die Arbeitsdatei auch für „lernen" - und „lernen" liest den Korpus, es
    schreibt ihn nicht (Grundentscheidung 6). Ein Trainingslauf, der über einer
    zurückgespielten Sicherung eine fehlende Datei nachschneiden müsste, wäre
    genau der Sonderfall, den diese Regel ausschließt.

    Teuer ist es nicht: Ein Zuschnitt ist **kürzer** als sein Original - das
    ist sein ganzer Zweck -, und es gibt höchstens einen je Aufnahme, während
    es drei Abwandlungen sind.

    Die Modellstände und die Schnappschüsse sind ohnehin draußen: Sie stehen
    gar nicht erst in `loeschung.datenverzeichnisse()`.

    Das kostet im Ernstfall Rechenzeit und keine einzige Aufnahme - und es ist
    der Unterschied zwischen einer Sicherung, die man wöchentlich wegträgt,
    und einer, die man ihrer Größe wegen lieber sein lässt.

    Hier stand einmal eine Ausnahme: die Aufteilung in Lernen und Prüfen
    (`lernen/…/lernen.sqlite`). Sie blieb drin, weil sie sich nicht neu rechnen
    ließ, sondern nur neu erfinden - eine andere Aufteilung hätte jeden
    Vergleich mit früheren Läufen entwertet. Seit September 2026 gibt es sie
    nicht mehr: „lernen“ hat keine eigene Datenbank, und die Faltungen der
    Kreuzvalidierung folgen der Reihenfolge des Korpus. Was aus einer Sicherung
    zurückkommt, ergibt damit dieselben Faltungen wie vorher.
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

    Enthält Korpus und Diktate, wie sie im Datenverzeichnis liegen, mit einer
    in sich stimmigen Kopie der Datenbank - ohne das Abgeleitete, siehe
    `abgeleitet()`. Zurück kommt der Stand mit `scripts/restore.py` oder
    schlicht mit `tar xzf` (siehe `wortlaut/sicherung.py`).
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
