"""Einstellungen aus der Umgebung - ein Ort, nirgends sonst `os.environ`.

Die Feldnamen entsprechen den Variablen mit dem Präfix `WORTLAUT_`,
`lernen_basismodell` also `WORTLAUT_LERNEN_BASISMODELL`.

Wer hier trainiert, steht **nicht** in der Konfiguration: Diese App führt
denselben Sprecher wie „hören" und „schreiben", und den bringt der Aufrufer
als Zugang mit (siehe `deps.py`). Ein Modell gehört zu genau einem Menschen
(Grundentscheidung 3) - eine Instanz je Sprecher wäre eine Instanz je Modell
gewesen.

Was bleibt, gehört der Maschine: wo die Daten liegen, worauf trainiert wird und
mit welchen Grenzen.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from wortlaut.einstellungen import AUSWERTUNG_MODELLE, Grundeinstellungen

# Die eigene Ablage dieser App: die Aufteilung in Lernen und Prüfen, je
# Sprecher eine Datei.
#
#     data/lernen/<sprecher_id>/lernen.sqlite
#
# Nach Sprecher gegliedert wie Korpus und Diktate, und aus demselben Grund:
# `scripts/purge_speaker.py` löscht ein Verzeichnis, keinen Filter.
#
# Die Läufe selbst liegen **nicht** hier, sondern unter `data/snapshots/`
# (siehe `wortlaut/laeufe.py`) - ein Verzeichnis je Auftrag, das der Trainer
# in einem anderen Container beschreibt.
LERNEN = "lernen"
DATENBANKNAME = "lernen.sqlite"


def sprecher_relpfad(sprecher_id: str) -> str:
    return f"{LERNEN}/{sprecher_id}"


class Einstellungen(Grundeinstellungen):
    # Wer ein Training anstoßen darf. Vorgelegt als `X-Trainer-Key`, geprüft
    # allein vor `POST /lernen/api/laeufe` (siehe `api/laeufe.py`).
    #
    # Warum überhaupt ein zweites Geheimnis, wo doch schon ein Zugang vorliegt:
    # Der Sprecherzugang sagt, **wessen** Modell entsteht - und das soll er
    # weiter allein sagen (Grundentscheidung 3). Er sagt nichts darüber, ob
    # dieser Mensch die Karte für Stunden belegen darf. Das sind zwei Fragen,
    # und ein Zugang, der beide beantwortet, beantwortet die zweite immer mit
    # ja: Jeder ausgegebene Link wäre ein Knopf, der Rechenzeit kostet, und
    # zwar so oft, wie jemand darauf drückt.
    #
    # Leer heißt **abgeschaltet**, nicht offen - dieselbe Regel wie bei
    # Verwaltung und Aufsicht in „hören" und aus demselben Grund: Keine
    # Installation weiß, ob sie eine Entwicklungsinstallation ist, und ein
    # vergessener Schlüssel darf nicht die großzügigste Einstellung sein. Die
    # Oberfläche sagt dann, dass nicht trainiert werden kann, statt einen Knopf
    # zu zeigen, der 401 antwortet.
    #
    # Was er **nicht** ist: eine Rolle. Er beschränkt genau einen Weg, den
    # teuren. Zusehen, abbrechen, löschen und freigeben bleiben beim Sprecher -
    # das kostet nichts und gehört dem, dessen Stimme darin steckt.
    trainer_key: str = ""

    # Worauf trainiert wird. Fest auf `small` und nicht wählbar: Es ist die
    # kleinste Stufe, die ganze Sätze trifft, sie passt in den Speicher einer
    # einzelnen Karte, und sie ist zugleich die Reihe, gegen die in „hören"
    # schon gemessen wurde (`auswertung_modelle`). Ohne diesen gemeinsamen
    # Nenner wäre der Vergleich mit der Grundlinie keiner.
    lernen_basismodell: str = "openai/whisper-small"
    # Welche unveränderten Modelle in der Modellübersicht gegen die eigenen
    # Stände antreten. Dieselbe Liste wie in der Auswertung von „hören"
    # (`WORTLAUT_AUSWERTUNG_MODELLE`), und das ist kein Zufall: Von dort
    # stammen ihre Zahlen. Auch die Vorgabe ist deshalb dieselbe und steht nur
    # noch einmal da (`wortlaut/einstellungen.py`) - zwei getrennte Listen
    # wären zwei Gelegenheiten, sie auseinanderlaufen zu lassen, und das
    # Ergebnis eine Tabellenzeile ohne Messung.
    auswertung_modelle: str = AUSWERTUNG_MODELLE
    # Worauf **trainiert** wird - `cuda` oder `cpu`, und die Voreinstellung ist
    # die Karte: Ein Feintuning von whisper-small auf einem Prozessor dauert
    # Tage statt Stunden. Das ist etwas anderes als `geraet` unten: Dort geht
    # es ums Erkennen, hier ums Lernen, und nur das Erkennen darf ausweichen.
    lernen_geraet: str = "cuda"

    # Wie oft der Trainer nach einem neuen Auftrag sieht. Sekunden. Kurz genug,
    # dass ein Knopfdruck sich wie einer anfühlt; lang genug, dass ein
    # wartender Container nichts tut.
    lernen_takt_s: int = 5

    @property
    def migrationsverzeichnis(self) -> Path:
        return Path(__file__).parent / "db" / "migrations"

    def datenbank(self, sprecher_id: str) -> Path:
        """Die Lerndatenbank eines Sprechers. Je Sprecher eine Datei."""
        return self.data_dir / sprecher_relpfad(sprecher_id) / DATENBANKNAME


@lru_cache
def einstellungen() -> Einstellungen:
    """Einmal lesen, überall dieselbe Instanz."""
    return Einstellungen()
