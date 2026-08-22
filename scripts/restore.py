"""Eine Sicherung zurückspielen.

    uv run python scripts/restore.py wortlaut-gesamt-20260822-174500.tgz
    uv run python scripts/restore.py sicherung.tgz --ueberschreiben
    uv run python scripts/restore.py sicherung.tgz --nur-ansehen

Die Gegenrichtung zu den Sicherungen der Aufsicht (`/api/admin/…/sicherung`).
Ohne `--ueberschreiben` bricht der Lauf ab, sobald eine Datei schon dasteht —
und zwar bevor irgendetwas geschrieben wurde.

**Der Dienst soll dabei stehen.** SQLite hält eine laufende Datenbank offen;
wer sie unter dem laufenden Prozess austauscht, bekommt einen Mischmasch aus
altem Zwischenspeicher und neuer Datei. Also erst anhalten, dann einspielen,
dann starten:

    docker compose stop
    uv run python scripts/restore.py sicherung.tgz --ueberschreiben
    docker compose start

Wer diese Anwendung gar nicht mehr hat, kommt genauso weit mit

    tar xzf sicherung.tgz && cp -a daten/. /srv/wortlaut/data/

— das Archiv bildet das Datenverzeichnis eins zu eins ab (siehe
`packages/wortlaut/src/wortlaut/sicherung.py`). Dieses Skript nimmt einem nur
die Prüfungen und das Nachzählen ab.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wortlaut import sicherung

from apps.hoeren.backend.config import einstellungen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archiv", type=Path, help="die .tgz-Sicherung")
    parser.add_argument(
        "--ueberschreiben",
        action="store_true",
        help="einen vorhandenen Stand ersetzen (sonst bricht der Lauf ab)",
    )
    parser.add_argument(
        "--nur-ansehen",
        action="store_true",
        help="nur zeigen, was in der Sicherung steht, und nichts schreiben",
    )
    argumente = parser.parse_args()

    if not argumente.archiv.is_file():
        print(f"Nicht gefunden: {argumente.archiv}")
        return 1

    try:
        manifest = sicherung.lies_manifest(argumente.archiv)
    except (ValueError, OSError) as fehler:
        print(f"Lässt sich nicht lesen: {fehler}")
        return 1

    dateien = manifest.get("dateien", {})
    print(f"Sicherung vom {manifest.get('erstellt', '?')}, Umfang: {manifest.get('umfang', '?')}")
    for person in manifest.get("sprecher", []):
        print(f"  {person.get('id')}  {person.get('name')}")
    print(f"  {len(dateien)} Datei(en), {_lesbar(sum(a['bytes'] for a in dateien.values()))}")

    ziel = einstellungen().data_dir
    if argumente.nur_ansehen:
        print(f"\nProbelauf. Ohne --nur-ansehen würde nach {ziel} geschrieben.")
        return 0

    try:
        geschrieben = sicherung.stelle_wieder_her(
            argumente.archiv, ziel, ueberschreiben=argumente.ueberschreiben
        )
    except FileExistsError as fehler:
        print(f"\nAbgebrochen, nichts geschrieben: {fehler}")
        return 1

    print(f"\n{len(geschrieben)} Datei(en) nach {ziel} geschrieben.")
    print("Danach einmal `make migrate`, falls die Sicherung älter ist als das Schema.")
    return 0


def _lesbar(bytes_: int) -> str:
    wert = float(bytes_)
    for einheit in ("B", "kB", "MB", "GB"):
        if wert < 1024 or einheit == "GB":
            return f"{wert:.1f} {einheit}"
        wert /= 1024
    return f"{wert:.1f} GB"


if __name__ == "__main__":
    raise SystemExit(main())
