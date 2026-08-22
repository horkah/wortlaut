"""Einen Sprecher vollständig löschen.

    uv run python scripts/purge_speaker.py spr_7f2a --ja-wirklich

Das Recht auf Löschung muss ausführbar sein, nicht dokumentiert. Entfernt
werden Profil, Vorlagen, Aufnahmen, Modellstände, die Schnappschüsse, die aus
diesem Korpus entstanden sind, und die Diktate von „schreiben".

Was dazugehört, steht nicht hier, sondern in
`apps/hoeren/backend/services/loeschung.py` — dieselbe Stelle, die auch die
Aufsicht in der Oberfläche fragt. Sonst löschten Kommandozeile und Oberfläche
Verschiedenes, und der Unterschied fiele niemandem auf.

Vor dem Löschen lässt sich der Stand sichern: die Aufsicht gibt ihn als `.tgz`
aus (`/api/admin/speakers/{id}/sicherung`), zurück kommt er mit
`scripts/restore.py`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.services import loeschung


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
    vorhanden = loeschung.ziele(datenverzeichnis, argumente.sprecher_id)

    for verzeichnis in loeschung.ohne_marke(datenverzeichnis):
        print(
            f"Achtung: {verzeichnis} hat keine {loeschung.SCHNAPPSCHUSS_MARKE} "
            "— bitte von Hand prüfen."
        )

    if not vorhanden:
        print(f"Nichts gefunden für {argumente.sprecher_id}.")
        return 1

    if not argumente.ja_wirklich:
        for ziel in vorhanden:
            print(f"würde löschen: {ziel}")
        print("\nProbelauf. Mit --ja-wirklich wird tatsächlich gelöscht.")
        return 0

    for ziel in loeschung.loesche(datenverzeichnis, argumente.sprecher_id):
        print(f"gelöscht: {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
