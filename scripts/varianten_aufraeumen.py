"""Abgewandelte Fassungen wegräumen, die es nicht mehr gibt.

    uv run python scripts/varianten_aufraeumen.py                        # auf dem Wirt
    docker compose exec wortlaut python scripts/varianten_aufraeumen.py  # im Container

Unter `korpus/<sprecher>/audio/varianten/` liegt zu jeder Aufnahme eine Datei
je Abwandlung (`wortlaut/augmentierung.py`). Wird eine Abwandlung abgeschafft,
bleiben ihre Dateien liegen: Sie stehen in keiner Tabelle, also räumt sie auch
keine Migration weg, und wer über das Verzeichnis läuft, hält sie für gültig.

Dieses Skript ist die Antwort darauf, und es kennt keine Namensliste: Es
vergleicht, was auf der Platte liegt, mit dem, was `augmentierung.VARIANTEN`
heute nennt, und entfernt den Rest. Damit gilt es auch für die nächste
Abwandlung, die einmal wegfällt - und für die, die jemand versehentlich unter
falschem Namen ablegt.

Anlass war der Herbst 2026: `pegel` und `lauter` sind verworfen worden, weil
sie an Whisper nahezu wirkungslos sind (siehe `009_ohne_pegelvarianten.sql`).
Bei 400 Aufnahmen sind das 800 Dateien.

Ein zweiter Lauf tut nichts, und ohne `--wirklich` tut auch der erste nichts:
Vorgabe ist die Liste dessen, was wegginge.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ausführbar ohne Installation: Repository-Wurzel in den Suchpfad legen.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wortlaut import augmentierung, corpus, storage

from apps.hoeren.backend.config import einstellungen


def variante_aus_name(datei: Path) -> str:
    """Der Fassungsname aus `<aufnahme_id>.<variante>.wav`.

    Aufnahmekennungen enthalten keinen Punkt (siehe `wortlaut/corpus.py`), der
    Name ist damit eindeutig zu zerlegen. Was sich nicht zerlegen lässt, gilt
    als fremd und wird gemeldet, nicht gelöscht: Eine Datei, die hier nicht
    hingehört, ist ein Befund und keine Aufräumaufgabe.
    """
    teile = datei.stem.split(".")
    return teile[-1] if len(teile) == 2 else ""


def main(argumente: list[str]) -> int:
    wirklich = "--wirklich" in argumente
    konfiguration = einstellungen()
    ablage = storage.oeffne_ablage(konfiguration.storage, konfiguration.data_dir)
    sprecher = corpus.sprecher_ids(konfiguration.data_dir)
    if not sprecher:
        print(f"Keine Korpora unter {konfiguration.data_dir / corpus.KORPUS} - nichts zu tun.")
        return 0

    gueltig = set(augmentierung.VARIANTEN)
    print(f"Gültige Fassungen: {', '.join(sorted(gueltig))}")

    gesamt = 0
    fremd = 0
    for sprecher_id in sprecher:
        ordner = konfiguration.data_dir / corpus.varianten_relpfad(sprecher_id)
        if not ordner.is_dir():
            continue

        weg: list[Path] = []
        for datei in sorted(ordner.glob("*.wav")):
            name = variante_aus_name(datei)
            if not name:
                print(f"  ? {datei.name} - kein Fassungsname, bleibt liegen")
                fremd += 1
                continue
            if name not in gueltig:
                weg.append(datei)

        for datei in weg:
            if wirklich:
                # Über die Ablage und nicht über `unlink`: Sie ist die eine
                # Stelle, die weiß, wo Blobs liegen - auch wenn das eines Tages
                # kein Dateisystem mehr ist.
                ablage.loesche(f"{corpus.varianten_relpfad(sprecher_id)}/{datei.name}")
            else:
                print(f"  - {datei.name}")
        gesamt += len(weg)
        tat = "gelöscht" if wirklich else "zu löschen"
        print(f"{sprecher_id}: {len(weg)} Dateien {tat}")

    if not wirklich and gesamt:
        print(f"\n{gesamt} Dateien insgesamt. Mit --wirklich werden sie entfernt.")
    return 1 if fremd else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
