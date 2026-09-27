"""Den Stand eines Laufs freigeben - „schreiben" diktiert danach damit.

    make release JOB=job_01J8…
    uv run python scripts/freigeben.py <job_id>
    docker compose exec wortlaut python scripts/freigeben.py <job_id>   # im Betrieb

Dieselbe Entscheidung wie der Knopf unter „Modelle" in „lernen", über dieselbe
Stelle (`services/freigabe.py`): Freigegeben ist höchstens ein Modell je
Sprecher, jedes andere wird zurückgezogen. „schreiben" liest die Freigabe
bei jedem Diktat - ein Neustart ist nicht nötig.

Hat die Prüfung des Endmodells angeschlagen, steht es da; freigegeben wird
trotzdem - wie in der Oberfläche entscheidet der Mensch.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ausführbar ohne Installation: Repository-Wurzel in den Suchpfad legen.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wortlaut import registry

from apps.lernen.backend.config import einstellungen
from apps.lernen.backend.services import freigabe


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[2])
        return 2
    job_id = sys.argv[1]
    datenverzeichnis = einstellungen().data_dir
    try:
        stand = freigabe.stand_aus_lauf(datenverzeichnis, job_id)
    except freigabe.NichtFreigebbar as ursache:
        raise SystemExit(str(ursache)) from ursache

    sprecher_id = str(stand["sprecher_id"])
    ref = str(stand["id"])
    vorher = registry.freigegeben(datenverzeichnis, sprecher_id)
    pruefung = stand.get("pruefung") or {}
    if pruefung.get("auffaellig"):
        print(
            f"Achtung: Die Prüfung des Endmodells hat angeschlagen ({pruefung.get('grund', '?')}) "
            "- siehe Modelltafel in „lernen“."
        )
    freigabe.gib_frei(datenverzeichnis, sprecher_id, ref)
    print(
        f"Freigegeben: {registry.beschriftung(ref)} ({ref})"
        + (f" - statt {registry.beschriftung(vorher)}" if vorher and vorher != ref else "")
        + ". „schreiben“ diktiert ab dem nächsten Diktat damit."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
