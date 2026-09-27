"""Das Endmodell eines fertigen Laufs neu rechnen - nur das siebte Training.

Das Endmodell übernimmt aus den Faltungen Durchgänge, α, Tempo
(`kreuzvalidierung` im Manifest des Standes) und ihren Lernratenplan
(`finetune.trainiere`, `docs/lernen.md`); den Plan liest `plan_aus_dem_lauf`
aus dem Fortschritt. Alles Übrige liegt im Schnappschuss.

Ersetzt werden die Gewichte, mit denen diktiert wird. Die Zahlen in „lernen"
und „hören" stammen aus den Faltungen und bleiben; nur die Zeilen, die das
Endmodell in der Auswertung selbst gerechnet hat, gehen, damit sie neu
gemessen werden. Seit dem Lauf verworfene Aufnahmen fehlen
(`laeufe.zeilen_fuer_faltung`).

Aufruf im Trainingscontainer, der die Karte hat:

    docker compose --profile training exec training \\
        python -m apps.lernen.training.nachziehen --liste
    docker compose --profile training exec training \\
        python -m apps.lernen.training.nachziehen <sprecher>/<version> …
    docker compose --profile training exec training \\
        python -m apps.lernen.training.nachziehen --alle
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from wortlaut import corpus, laeufe, registry

from apps.lernen.backend.config import einstellungen


def plan_aus_dem_lauf(verzeichnis: Path) -> float:
    """Über wie viele Durchgänge die Faltungen ihre Lernrate geplant hatten.

    Jede Faltung meldet beim Start ihre `epochen` in den Fortschritt
    (`finetune._rueckmeldung`). Die erste Meldung genügt: Alle sechs planen
    gleich, sie unterscheiden sich nur darin, wann die Geduld aufgebraucht war.

    Null: nicht zu ermitteln - dann plant das Endmodell über seine
    Durchgänge, statt einen Horizont zu raten.
    """
    for zeile in laeufe.lies_zeilen(verzeichnis / laeufe.FORTSCHRITT):
        if zeile.get("art") == "start" and zeile.get("epochen"):
            return float(zeile["epochen"])
    return 0.0


def _vergiss_eigene_messungen(datenverzeichnis: Path, ref: str) -> int:
    """Die Zeilen wegräumen, die das ersetzte Endmodell selbst gerechnet hat.

    `herkunft = 'gemessen'` in der Auswertung von „hören"; die übernommenen
    Faltungszeilen bleiben. Über SQL, weil dieses Abbild `apps/hoeren` nicht
    trägt (`Dockerfile`).
    """
    sprecher_id = ref.split(registry.TRENNER, 1)[0]
    datei = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id) / "hoeren.sqlite"
    if not datei.is_file():
        return 0
    with sqlite3.connect(datei) as db:
        cursor = db.execute(
            "DELETE FROM erkennungen WHERE modell = ? AND herkunft = 'gemessen'", (ref,)
        )
        return cursor.rowcount or 0


def ziehe_nach(datenverzeichnis: Path, ref: str) -> str:
    """Einen Stand neu rechnen; gibt zurück, was dabei herauskam."""
    from .bewerten import gib_frei
    from .finetune import Bericht, trainiere_geduldig

    sprecher_id, version = ref.split(registry.TRENNER, 1)
    manifest = registry.lies_stand(datenverzeichnis, sprecher_id, version)
    job_id = str(manifest.get("job_id") or "")
    verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job_id)
    if not (verzeichnis / laeufe.MANIFEST).is_file():
        raise SystemExit(f"{ref}: Der Schnappschuss {job_id} liegt nicht mehr da.")

    auftrag = json.loads((verzeichnis / laeufe.AUFTRAG).read_text(encoding="utf-8"))
    mitgenommen: dict[str, Any] = dict(manifest.get("kreuzvalidierung") or {})
    if not mitgenommen.get("durchgaenge"):
        raise SystemExit(f"{ref}: Ohne die Durchgänge der Faltungen geht es nicht.")
    plan = plan_aus_dem_lauf(verzeichnis)
    if plan:
        mitgenommen["plan"] = plan
    zeilen = list(laeufe.lies_zeilen(verzeichnis / laeufe.BEWERTUNG))

    # Ohne Spuren: Der Lauf ist fertig und bleibt es. Mit liest ein Mensch.
    bericht = Bericht(verzeichnis, spuren=False)

    # Erst den bestehenden Stand prüfen: Standen die Faltungen sehr früh am
    # besten, hält der geerbte Plan das Endmodell auf der Spitze der Lernrate
    # an, und ohne Validierung fängt das niemand auf. Das bessere bleibt.
    vorher = pruefe_nur(datenverzeichnis, ref, bericht)

    # Die bisherigen Gewichte gehen zur Seite; sie fallen erst, wenn der neue
    # Stand seine Prüfung besteht.
    gewichte_alt = registry.ct2_verzeichnis(datenverzeichnis, ref)
    beiseite = gewichte_alt.with_name("ct2-vorher")
    shutil.rmtree(beiseite, ignore_errors=True)
    if gewichte_alt.is_dir():
        gewichte_alt.rename(beiseite)
    # Ihr Manifest geht mit - es beschreibt diese Gewichte.
    steckbrief = gewichte_alt.parent / registry.MANIFEST
    steckbrief_alt = steckbrief.read_bytes() if steckbrief.is_file() else b""

    bericht.sage(
        f"── {registry.beschriftung(ref)}: Endmodell neu, Plan über "
        f"{mitgenommen.get('plan', mitgenommen['durchgaenge']):.1f} Durchgänge, "
        f"Schluss nach {float(mitgenommen['durchgaenge']):.1f}"
    )
    gewichte, ergebnis, kennzahlen = trainiere_geduldig(
        verzeichnis, datenverzeichnis, bericht, faltung=None, vorgaben=mitgenommen
    )
    neu = gib_frei(
        verzeichnis,
        datenverzeichnis,
        gewichte,
        auftrag,
        bericht,
        ergebnis,
        zeilen=zeilen,
        mitgenommen=mitgenommen,
        zuschnitt=kennzahlen.get("zuschnitt"),
    )
    pruefung = (registry.lies_stand(datenverzeichnis, sprecher_id, version).get("pruefung")) or {}
    schlechter = bool(
        vorher.get("stichprobe")
        and pruefung.get("stichprobe")
        and float(pruefung["wer_median"]) > float(vorher["wer_median"])
    )
    if schlechter:
        bericht.sage(
            f"{registry.beschriftung(ref)}: neu {pruefung['wer_median']:.2f} gegen alt "
            f"{vorher['wer_median']:.2f} - der alte Stand war besser."
        )
    if (pruefung.get("auffaellig") or schlechter) and beiseite.is_dir():
        shutil.rmtree(gewichte_alt, ignore_errors=True)
        beiseite.rename(gewichte_alt)
        if steckbrief_alt:
            steckbrief.write_bytes(steckbrief_alt)
        bericht.sage(
            f"{registry.beschriftung(ref)}: Der neue Stand ist weg, die alten Gewichte "
            "stehen wieder da - samt ihrem Steckbrief."
        )
        return neu

    bericht.sage(
        f"{registry.beschriftung(ref)}: neu {pruefung.get('wer_median', float('nan')):.2f} "
        f"gegen alt {vorher.get('wer_median', float('nan')):.2f} - der neue Stand bleibt."
    )

    shutil.rmtree(beiseite, ignore_errors=True)
    weg = _vergiss_eigene_messungen(datenverzeichnis, ref)
    if weg:
        bericht.sage(f"{weg} Messzeilen des alten Endmodells weggeräumt - sie messen es nicht mehr.")
    return neu


def pruefe_nur(datenverzeichnis: Path, ref: str, bericht=None) -> dict[str, Any]:
    """Den Stand ansehen, der dasteht - ohne ihn anzufassen.

    Für Stände ohne Befund. Er wandert ins Manifest und steht in „Modelle".
    """
    from .bewerten import pruefe_endmodell
    from .finetune import Bericht

    sprecher_id, version = ref.split(registry.TRENNER, 1)
    manifest = registry.lies_stand(datenverzeichnis, sprecher_id, version)
    verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, str(manifest.get("job_id") or ""))
    if not (verzeichnis / laeufe.MANIFEST).is_file():
        raise SystemExit(f"{ref}: Der Schnappschuss liegt nicht mehr da.")

    auftrag = json.loads((verzeichnis / laeufe.AUFTRAG).read_text(encoding="utf-8"))
    # Mit gereichtem Bericht der erste Schritt von `ziehe_nach` - dann gehört
    # der Befund dem Stand, der am Ende dasteht.
    allein = bericht is None
    bericht = bericht or Bericht(verzeichnis, spuren=False)
    bericht.sage(f"── {registry.beschriftung(ref)}: {'nur prüfen' if allein else 'erst ansehen'}")
    befund = pruefe_endmodell(
        verzeichnis,
        datenverzeichnis,
        registry.ct2_verzeichnis(datenverzeichnis, ref),
        auftrag,
        bericht,
        list(laeufe.lies_zeilen(verzeichnis / laeufe.BEWERTUNG)),
        float(manifest.get("tempo") or 1.0),
    )
    if allein:
        registry.schreibe_stand(datenverzeichnis, {**manifest, "pruefung": befund})
    return befund


def _staende(datenverzeichnis: Path) -> list[str]:
    """Alle trainierten Stände aller Sprecher, mit Gewichten und Schnappschuss."""
    wurzel = datenverzeichnis / registry.MODELLE
    return sorted(
        ref
        for sprecher in (wurzel.iterdir() if wurzel.is_dir() else [])
        if sprecher.is_dir()
        for manifest in registry.alle_staende(datenverzeichnis, sprecher.name)
        if (ref := str(manifest.get("id", ""))) and manifest.get("job_id")
    )


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__)
    zerleger.add_argument("stand", nargs="*", help="<sprecher>/<version>")
    zerleger.add_argument("--alle", action="store_true", help="jeden Stand, der dasteht")
    zerleger.add_argument("--liste", action="store_true", help="nur zeigen, was da ist")
    zerleger.add_argument(
        "--pruefen", action="store_true", help="nur ansehen, was dasteht - nichts rechnen"
    )
    argumente = zerleger.parse_args(argv)

    datenverzeichnis = einstellungen().data_dir
    refs = (
        _staende(datenverzeichnis)
        if (argumente.alle or argumente.liste) or (argumente.pruefen and not argumente.stand)
        else argumente.stand
    )
    if not refs:
        zerleger.error("Kein Stand genannt - `--liste` zeigt, was dasteht.")

    if argumente.liste:
        for ref in refs:
            sprecher_id, version = ref.split(registry.TRENNER, 1)
            manifest = registry.lies_stand(datenverzeichnis, sprecher_id, version)
            verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, str(manifest.get("job_id")))
            plan = plan_aus_dem_lauf(verzeichnis)
            kv = manifest.get("kreuzvalidierung") or {}
            print(
                f"{registry.beschriftung(ref):8s} {ref}\n"
                f"         Durchgänge {kv.get('durchgaenge', '?')}, Plan "
                f"{plan or 'nicht zu ermitteln'}, Schnappschuss "
                f"{'da' if (verzeichnis / laeufe.MANIFEST).is_file() else 'FEHLT'}"
            )
        return 0

    for ref in refs:
        try:
            if argumente.pruefen:
                pruefe_nur(datenverzeichnis, ref)
            else:
                ziehe_nach(datenverzeichnis, ref)
        except SystemExit as grund:
            print(grund, file=sys.stderr)
        except Exception as ursache:  # noqa: BLE001 - ein Stand soll die übrigen nicht aufhalten
            print(f"{ref}: {type(ursache).__name__}: {ursache}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
