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

from pydantic_settings import BaseSettings, SettingsConfigDict

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


class Einstellungen(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORTLAUT_", env_file=".env", extra="ignore")

    # gemeinsam
    data_dir: Path = Path("./data")

    # Worauf trainiert wird. Fest auf `small` und nicht wählbar: Es ist die
    # kleinste Stufe, die ganze Sätze trifft, sie passt in den Speicher einer
    # einzelnen Karte, und sie ist zugleich die Reihe, gegen die in „hören"
    # schon gemessen wurde (`auswertung_modelle`). Ohne diesen gemeinsamen
    # Nenner wäre der Vergleich mit der Grundlinie keiner.
    lernen_basismodell: str = "openai/whisper-small"
    # Welche unveränderten Modelle in der Modellübersicht gegen die eigenen
    # Stände antreten. Dieselbe Liste wie in der Auswertung von „hören"
    # (`WORTLAUT_AUSWERTUNG_MODELLE`), und das ist kein Zufall: Von dort
    # stammen ihre Zahlen. Zwei getrennte Listen wären zwei Gelegenheiten,
    # sie auseinanderlaufen zu lassen - und eine Tabellenzeile ohne Messung.
    auswertung_modelle: str = "base,small,medium,large-v3"
    # `cuda` oder `cpu`. Voreinstellung ist die Karte: Ein Feintuning von
    # whisper-small auf einer CPU dauert Tage statt Stunden.
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
