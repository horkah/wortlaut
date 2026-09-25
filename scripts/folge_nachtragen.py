"""Die Folge (`/43`, `/43b`, …) für Läufe nachtragen, die vor ihr entstanden sind.

    uv run python scripts/folge_nachtragen.py                        # auf dem Wirt
    docker compose exec wortlaut python scripts/folge_nachtragen.py  # im Container

Seit September 2026 bekommt jeder Auftrag hinter seinem Optionscode die Zahl
seiner Aufnahmen und, wenn es Code und Zahl schon gibt, einen Buchstaben
(`wortlaut/laeufe.py`, „Die Folge"). Vergeben wird sie beim Auftrag. Die Läufe
davor haben keine - dieses Skript gibt sie ihnen, einmal und nach derselben
Regel: Sprecher für Sprecher, ältester Lauf zuerst, gemessen an den älteren,
die es noch gibt.

Geschrieben wird in `auftrag.json` und, falls der Lauf schon einen Stand
hervorgebracht hat, in dessen Manifest. Der Trainer liest `auftrag.json` nur;
ein laufender oder wartender Lauf verträgt das Nachtragen also.

Ein zweiter Aufruf ändert nichts: Wer schon eine Folge trägt, behält sie.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ausführbar ohne Installation: Repository-Wurzel in den Suchpfad legen.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wortlaut import laeufe, registry

from apps.lernen.backend.config import einstellungen


def main() -> None:
    datenverzeichnis = einstellungen().data_dir
    gesehen: dict[str, list[dict]] = {}
    for lauf in laeufe.alle_laeufe(datenverzeichnis):
        frueher = gesehen.setdefault(lauf.sprecher_id, [])
        auftrag = dict(lauf.auftrag)
        if not auftrag.get(laeufe.FOLGE):
            auftrag[laeufe.FOLGE] = laeufe.naechste_folge(auftrag, frueher)
            laeufe.schreibe_json(lauf.verzeichnis / laeufe.AUFTRAG, auftrag)
            print(f"{lauf.sprecher_id}  {lauf.job_id}  {laeufe.titel(auftrag)}")
        frueher.append(auftrag)

        stand = registry.stand_zu_lauf(datenverzeichnis, lauf.sprecher_id, lauf.job_id)
        if stand is not None and stand.get(laeufe.FOLGE) != auftrag[laeufe.FOLGE]:
            stand[laeufe.FOLGE] = auftrag[laeufe.FOLGE]
            registry.schreibe_stand(datenverzeichnis, stand)


if __name__ == "__main__":
    main()
