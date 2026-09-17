"""Das Endmodell eines fertigen Laufs mit dem heutigen Verfahren neu rechnen.

**Wozu.** Bis September 2026 übernahm das Endmodell aus den Faltungen nur die
Durchgangszahl und baute seinen Lernratenverlauf in diesen Horizont neu - ein
anderer Lauf als der, aus dem die Zahl stammte, und das Ergebnis franste aus
(siehe `finetune.trainiere` und `docs/lernen.md`). Die Faltungen selbst waren
davon nie betroffen: Sie liefen auf ihrem eigenen Plan und wurden auf ihrem
besten Stand gemessen. Deshalb genügt es, das **siebte** Training zu
wiederholen - ein Training statt sieben.

**Was dafür dastehen muss.** Alles liegt im Schnappschuss des Laufs: das
Manifest mit den Aufnahmen und ihren Faltungen, der Auftrag mit den Achsen, die
Bewertung der sechs Faltungen. Was daraus mitgenommen wird - Durchgänge, α,
Tempo -, steht im Manifest des Standes unter `kreuzvalidierung`. Einzig der
**Plan** ist neu und stand dort noch nicht; er lässt sich aus dem Fortschritt
des Laufs zurücklesen, wo jede Faltung beim Start ihre geplanten Durchgänge
gemeldet hat.

**Was sich ändert und was nicht.** Ersetzt werden die Gewichte des Standes -
das Modell also, mit dem diktiert wird. Die Zahlen in „lernen" und „hören"
ändern sich dadurch **nicht**: Sie stammen aus den sechs Faltungen und messen
nicht dieses Modell. Was sich ändert, sind die Zeilen, die das alte Endmodell
in der Auswertung selbst gerechnet hat - sie gehören zu Gewichten, die es nicht
mehr gibt, und werden weggeräumt, damit der nächste Lauf sie neu misst.

**Was verloren ist, bleibt verloren.** Aufnahmen, die seit dem Lauf verworfen
wurden, sind nicht wiederherstellbar; das neue Endmodell lernt ohne sie
(`daten.zeilen_fuer_faltung`). Es ist damit nicht Zeile für Zeile dasselbe
Training wie damals - aber es ist dasselbe Verfahren auf demselben Rezept, und
das ist der Punkt.

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

    Null heißt: nicht zu ermitteln. Dann bleibt es beim alten Verhalten, und
    das ist die ehrlichere Antwort als ein geratener Horizont.
    """
    for zeile in laeufe.lies_zeilen(verzeichnis / laeufe.FORTSCHRITT):
        if zeile.get("art") == "start" and zeile.get("epochen"):
            return float(zeile["epochen"])
    return 0.0


def _vergiss_eigene_messungen(datenverzeichnis: Path, ref: str) -> int:
    """Die Zeilen wegräumen, die das **alte** Endmodell selbst gerechnet hat.

    Sie stehen in der Auswertung von „hören" (`herkunft = 'gemessen'`) und
    gehören zu Gewichten, die es nicht mehr gibt. Die übernommenen
    Faltungszeilen bleiben: Sie stammen von den sechs Modellen und sind von
    dieser Änderung unberührt.

    Unmittelbar über SQL und nicht über die Modelle von „hören": Dieses Abbild
    trägt `apps/hoeren` nicht (siehe `Dockerfile`), und eine Abhängigkeit dazu
    einzuführen, um eine Zeile zu löschen, wäre der teurere Weg.
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
    from .finetune import Bericht, trainiere

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

    # **Die alten Gewichte gehen zur Seite, nicht weg.** Was hier entsteht,
    # ersetzt ein Modell, mit dem vielleicht gerade diktiert wird. Erst wenn
    # der neue Stand die Prüfung bei seiner Freigabe besteht, fällt der alte;
    # besteht er sie nicht, kommt der alte zurück, und es hat sich nichts
    # geändert außer einer Stunde Rechenzeit.
    gewichte_alt = registry.ct2_verzeichnis(datenverzeichnis, ref)
    beiseite = gewichte_alt.with_name("ct2-vorher")
    shutil.rmtree(beiseite, ignore_errors=True)
    if gewichte_alt.is_dir():
        gewichte_alt.rename(beiseite)

    # Ein Bericht ohne Spuren: Der alte Lauf ist fertig und bleibt es. Gesagt
    # wird trotzdem alles - der Läufer hört hier nicht mit, dafür ein Mensch.
    bericht = Bericht(verzeichnis, spuren=False)
    bericht.sage(
        f"── {registry.beschriftung(ref)}: Endmodell neu, Plan über "
        f"{mitgenommen.get('plan', mitgenommen['durchgaenge']):.1f} Durchgänge, "
        f"Schluss nach {float(mitgenommen['durchgaenge']):.1f}"
    )
    gewichte, ergebnis, _kennzahlen = trainiere(
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
    )
    pruefung = (registry.lies_stand(datenverzeichnis, sprecher_id, version).get("pruefung")) or {}
    if pruefung.get("auffaellig") and beiseite.is_dir():
        shutil.rmtree(gewichte_alt, ignore_errors=True)
        beiseite.rename(gewichte_alt)
        bericht.sage(
            f"{registry.beschriftung(ref)}: Der neue Stand ist durchgefallen - die alten "
            "Gewichte stehen wieder da. Das Manifest trägt den Befund."
        )
        return neu

    shutil.rmtree(beiseite, ignore_errors=True)
    weg = _vergiss_eigene_messungen(datenverzeichnis, ref)
    if weg:
        bericht.sage(f"{weg} Messzeilen des alten Endmodells weggeräumt - sie messen es nicht mehr.")
    return neu


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
    argumente = zerleger.parse_args(argv)

    datenverzeichnis = einstellungen().data_dir
    refs = _staende(datenverzeichnis) if (argumente.alle or argumente.liste) else argumente.stand
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
            ziehe_nach(datenverzeichnis, ref)
        except SystemExit as grund:
            print(grund, file=sys.stderr)
        except Exception as ursache:  # noqa: BLE001 - ein Stand soll die übrigen nicht aufhalten
            print(f"{ref}: {type(ursache).__name__}: {ursache}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
