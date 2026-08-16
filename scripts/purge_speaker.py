"""Einen Sprecher vollständig löschen.

    uv run python scripts/purge_speaker.py spr_7f2a --ja-wirklich

Das Recht auf Löschung muss ausführbar sein, nicht dokumentiert. Entfernt
werden Profil, Vorlagen, Aufnahmen, Modellstände und die Schnappschüsse, die
aus diesem Korpus entstanden sind.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wortlaut import corpus, registry

from apps.hoeren.backend.config import einstellungen

# Schnappschüsse legt „lernen" an. Damit sie löschbar bleiben, ohne ihr
# Manifest zu deuten, liegt neben dem Manifest eine Datei mit der Sprecher-ID.
SCHNAPPSCHUSS_MARKE = "sprecher.txt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sprecher_id")
    parser.add_argument(
        "--ja-wirklich",
        action="store_true",
        help="ohne diesen Schalter wird nur angezeigt, was gelöscht würde",
    )
    argumente = parser.parse_args()

    datenverzeichnis = einstellungen().data_dir
    ziele = [
        datenverzeichnis / corpus.sprecher_relpfad(argumente.sprecher_id),
        datenverzeichnis / registry.MODELLE / argumente.sprecher_id,
        *_schnappschuesse(datenverzeichnis, argumente.sprecher_id),
    ]
    vorhanden = [ziel for ziel in ziele if ziel.exists()]

    if not vorhanden:
        print(f"Nichts gefunden für {argumente.sprecher_id}.")
        return 1

    for ziel in vorhanden:
        if argumente.ja_wirklich:
            shutil.rmtree(ziel)
            print(f"gelöscht: {ziel}")
        else:
            print(f"würde löschen: {ziel}")

    if not argumente.ja_wirklich:
        print("\nProbelauf. Mit --ja-wirklich wird tatsächlich gelöscht.")
    return 0


def _schnappschuesse(datenverzeichnis: Path, sprecher_id: str) -> list[Path]:
    wurzel = datenverzeichnis / "snapshots"
    if not wurzel.is_dir():
        return []
    treffer = []
    for verzeichnis in sorted(wurzel.iterdir()):
        marke = verzeichnis / SCHNAPPSCHUSS_MARKE
        if marke.is_file() and marke.read_text(encoding="utf-8").strip() == sprecher_id:
            treffer.append(verzeichnis)
        elif verzeichnis.is_dir() and not marke.exists():
            print(
                f"Achtung: {verzeichnis} hat keine {SCHNAPPSCHUSS_MARKE} — bitte von Hand prüfen."
            )
    return treffer


if __name__ == "__main__":
    raise SystemExit(main())
