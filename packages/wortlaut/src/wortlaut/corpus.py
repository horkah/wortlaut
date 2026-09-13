"""Das Korpus-Layout - ein Verzeichnis, kein Dienst.

    data/korpus/<sprecher_id>/
    ├── audio/
    │   ├── <aufnahme_id>.wav                    16 kHz mono, PCM 16 bit
    │   └── varianten/
    │       └── <aufnahme_id>.<variante>.wav     abgewandelte Fassungen
    └── hoeren.sqlite                            Vorlagen, Aufnahmen, Sitzungen

Je Sprecher eine Datenbank: „lernen" liest damit genau eine Datei, und die
vollständige Löschung eines Sprechers ist das Entfernen eines Verzeichnisses.
Diese Datei ist die einzige Stelle, die das Layout kennt.

**Warum die Varianten ein Stockwerk tiefer liegen.** Abgewandelte Fassungen
(`wortlaut/augmentierung.py`) sind gerechnet und nicht gesprochen. Lägen sie
neben den Aufnahmen, hieße `audio/` plötzlich „Aufnahmen und was daraus
gerechnet wurde", und jedes Werkzeug, das über das Verzeichnis läuft, müsste
den Unterschied am Dateinamen erraten - beim vierten würde es jemand
vergessen. So bleibt `audio/` genau das, was die Datenbank in `recordings.blob`
stehen hat, und `audio/varianten/` ist das Abgeleitete, das sich jederzeit neu
rechnen lässt.

Der Name trägt beides: erst die Aufnahme, dann die Variante. Ein sortiertes
Verzeichnis liegt damit nach Aufnahmen geordnet da, und keine Variante kann
mit einer Aufnahme verwechselt werden - Aufnahmekennungen enthalten keinen
Punkt.
"""

from __future__ import annotations

from pathlib import Path

KORPUS = "korpus"
DATENBANKNAME = "hoeren.sqlite"
VARIANTENORDNER = "audio/varianten"


def sprecher_relpfad(sprecher_id: str) -> str:
    return f"{KORPUS}/{sprecher_id}"


def audio_relpfad(sprecher_id: str, aufnahme_id: str) -> str:
    return f"{KORPUS}/{sprecher_id}/audio/{aufnahme_id}.wav"


def varianten_relpfad(sprecher_id: str) -> str:
    """Wo alle abgewandelten Fassungen eines Sprechers liegen.

    Ein eigener Name für das Verzeichnis, weil es als Ganzes angesprochen wird:
    Es ist das Abgeleitete am Korpus, und eine Sicherung lässt es draußen
    (`wortlaut/sicherung.py`).
    """
    return f"{KORPUS}/{sprecher_id}/{VARIANTENORDNER}"


def variante_relpfad(sprecher_id: str, aufnahme_id: str, variante: str) -> str:
    """Wo die abgewandelte Fassung einer Aufnahme liegt.

    Aus Kennung und Variantenname allein zu berechnen, und das ist Absicht:
    Die Datei ist abgeleitet und jederzeit neu zu rechnen. Stünde ihr Pfad in
    einer Tabelle, gäbe es zwei Wahrheiten darüber, wo sie liegt - und
    irgendwann eine Zeile, zu der keine Datei mehr gehört.
    """
    return f"{KORPUS}/{sprecher_id}/{VARIANTENORDNER}/{aufnahme_id}.{variante}.wav"


VORLESENORDNER = "vorlesen"


def vorlesen_relpfad(sprecher_id: str) -> str:
    """Wo die vorgelesenen Vorlagen eines Sprechers liegen.

    Ein eigener Ordner neben `audio/`, und das ist dieselbe Trennung wie bei
    den Varianten: In `audio/` liegt, was ein Mensch gesprochen hat, hier liegt,
    was eine Maschine gesprochen hat. Sie zu vermischen hieße, dass jedes
    Werkzeug, das über den Korpus läuft, den Unterschied am Dateinamen erraten
    müsste - beim vierten würde es jemand vergessen.

    Abgeleitet wie die Varianten: jederzeit neu zu rechnen, nicht in der
    Sicherung (`wortlaut/sicherung.py`), und mit dem Sprecher gelöscht.
    """
    return f"{KORPUS}/{sprecher_id}/{VORLESENORDNER}"


def vorlesung_relpfad(sprecher_id: str, vorlage_id: str, stimme: str) -> str:
    """Wo die vorgelesene Fassung einer Vorlage liegt - je Stimme eine Datei.

    Der Stimmenname steht im Dateinamen und nicht in einer Tabelle: Die Datei
    ist abgeleitet, und zwei Wahrheiten darüber, welche Stimme sie spricht,
    wären eine zu viel. Er wird dafür auf das beschränkt, was in einen
    Dateinamen gehört (siehe `stimmenname`).
    """
    return f"{KORPUS}/{sprecher_id}/{VORLESENORDNER}/{vorlage_id}.{stimmenname(stimme)}.wav"


def stimmenname(stimme: str) -> str:
    """Ein Stimmenschlüssel als Teil eines Dateinamens.

    `piper/de_DE-thorsten-high` wird zu `piper-de_DE-thorsten-high`. Der
    Schrägstrich trennt Motor und Stimme und darf in keinen Pfad; der Punkt
    trennt im Dateinamen die Vorlage von der Stimme und darf es ebenso wenig.
    """
    return stimme.replace("/", "-").replace(".", "-")


def datenbank_pfad(datenverzeichnis: Path, sprecher_id: str) -> Path:
    return datenverzeichnis / KORPUS / sprecher_id / DATENBANKNAME


def sprecher_ids(datenverzeichnis: Path) -> list[str]:
    """Alle Sprecher, für die ein Korpus existiert - sortiert, also nach Alter."""
    wurzel = datenverzeichnis / KORPUS
    if not wurzel.is_dir():
        return []
    return sorted(
        eintrag.name for eintrag in wurzel.iterdir() if (eintrag / DATENBANKNAME).is_file()
    )
