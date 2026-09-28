"""Einen Lauf beauftragen und ihm zusehen, bis er fertig ist.

    make train SPEAKER=spr_… RECIPE=whisper_lora [MODELL=large-v3] [ACHSEN="dauer=geduldig"]
    uv run python scripts/trainieren.py <sprecher_id> <rezept> [--grundmodell large-v3] [achse=wert …]
    docker compose exec wortlaut python scripts/trainieren.py …          # im Betrieb

`<rezept>` ist eine Datei aus `apps/lernen/training/rezepte/` ohne Endung -
`whisper_lora` oder `whisper_full` - und bestimmt die Methode. Die übrigen
Achsen des Auftrags (`ACHSEN`, siehe `docs/lernen.md`) stehen auf ihrer
Vorgabe, solange keine `achse=wert` sie ändert.

**Beauftragt wird über dieselbe Stelle wie in der Oberfläche**
(`services/auftraege.bestelle`): dieselben Prüfungen, dasselbe
Laufverzeichnis. **Gerechnet wird hier nicht** - der Läufer im
Trainings-Container nimmt den Auftrag (Grundentscheidung 5). Dieses Skript
liest danach Zustand und Protokoll mit, bis der Lauf endet; Strg-C beendet
nur das Zusehen.

Am Ende stehen im Protokoll WER und CER des Laufs neben denen des
unveränderten Grundmodells, und wie er freigegeben wird: `make release JOB=…`.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ausführbar ohne Installation: Repository-Wurzel in den Suchpfad legen.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session
from wortlaut import corpus, db, laeufe, registry

from apps.hoeren.backend.db.models import Sprecher
from apps.lernen.backend.config import einstellungen
from apps.lernen.backend.services import auftraege

REZEPTE = Path(__file__).resolve().parents[1] / "apps" / "lernen" / "training" / "rezepte"
ACHSEN = (
    "lora_ziele",
    "lora_rang",
    "daten",
    "auswahl",
    "korrekturgewicht",
    "selbsttraining",
    "abschluss",
    "augmentierung",
    "dauer",
    "steuerung",
    "fenster",
    "tempowahl",
)
TAKT_S = 5.0
# Wie lange ein Auftrag warten darf, bis der Hinweis auf den Läufer kommt.
LAEUFER_HINWEIS_NACH_S = 60.0
ENDE = (laeufe.FERTIG, laeufe.GESCHEITERT, laeufe.ABGEBROCHEN)


def methode_aus(rezept: str) -> str:
    """`whisper_lora` → `lora` - geprüft an der Rezeptdatei."""
    if not (REZEPTE / f"{rezept}.yaml").is_file():
        vorhanden = sorted(pfad.stem for pfad in REZEPTE.glob("*.yaml"))
        raise SystemExit(f"Kein Rezept {rezept}. Vorhanden: {', '.join(vorhanden)}.")
    methode = rezept.removeprefix("whisper_")
    if methode not in laeufe.METHODEN:
        raise SystemExit(f"Rezept {rezept} nennt keine Methode ({', '.join(laeufe.METHODEN)}).")
    return methode


def grundmodell_aus(name: str) -> str:
    """`large-v3` → `openai/whisper-large-v3`; ein voller Name bleibt."""
    return name if "/" in name else f"openai/whisper-{name}"


def achsen_aus(angaben: list[str]) -> dict[str, str]:
    achsen: dict[str, str] = {}
    for angabe in angaben:
        achse, _, wert = angabe.partition("=")
        if achse not in ACHSEN or not wert:
            raise SystemExit(f"Unbekannt: {angabe}. Möglich: {', '.join(f'{a}=…' for a in ACHSEN)}.")
        achsen[achse] = wert
    return achsen


def sieh_zu(datenverzeichnis: Path, job_id: str) -> str:
    """Zustand und Protokoll mitlesen, bis der Lauf endet; gibt den Endzustand zurück."""
    protokoll = laeufe.lauf_verzeichnis(datenverzeichnis, job_id) / laeufe.PROTOKOLL
    gelesen = 0
    beginn = time.monotonic()
    hingewiesen = False
    while True:
        if protokoll.is_file():
            with protokoll.open(encoding="utf-8") as datei:
                datei.seek(gelesen)
                neu = datei.read()
                gelesen = datei.tell()
            if neu:
                print(neu, end="", flush=True)
        lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
        status = str((lauf.zustand if lauf else {}).get("status") or laeufe.WARTET)
        if status in ENDE:
            return status
        if (
            status == laeufe.WARTET
            and not hingewiesen
            and time.monotonic() - beginn > LAEUFER_HINWEIS_NACH_S
        ):
            print(
                "Der Auftrag wartet noch auf den Läufer. Läuft der Trainings-Container?\n"
                "  docker compose --profile training up -d training   (oder: make trainer)",
                flush=True,
            )
            hingewiesen = True
        time.sleep(TAKT_S)


def main() -> int:
    argumente = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    argumente.add_argument("sprecher_id")
    argumente.add_argument("rezept", help="whisper_lora oder whisper_full")
    argumente.add_argument("--grundmodell", default="", help="etwa large-v3; leer: die Vorgabe")
    argumente.add_argument("--nicht-warten", action="store_true", help="nur beauftragen")
    argumente.add_argument("achsen", nargs="*", help="achse=wert, etwa dauer=geduldig")
    wahl = argumente.parse_args()

    methode = methode_aus(wahl.rezept)
    konfiguration = einstellungen()
    datenverzeichnis = konfiguration.data_dir
    pfad = corpus.datenbank_pfad(datenverzeichnis, wahl.sprecher_id)
    if not pfad.is_file():
        raise SystemExit(f"Kein Korpus für {wahl.sprecher_id} unter {datenverzeichnis}.")

    with Session(db.verbinde(pfad)) as korpus:
        sprecher = korpus.get(Sprecher, wahl.sprecher_id)
        if sprecher is None:
            raise SystemExit(f"Kein Sprecher {wahl.sprecher_id} in {pfad}.")
        try:
            lauf = auftraege.bestelle(
                datenverzeichnis,
                korpus,
                auftraege.Bestellung(
                    sprecher_id=wahl.sprecher_id,
                    sprache=sprecher.sprache,
                    methode=methode,
                    grundmodell=grundmodell_aus(wahl.grundmodell) if wahl.grundmodell else "",
                    **achsen_aus(wahl.achsen),
                ),
            )
        except auftraege.Abgelehnt as ursache:
            raise SystemExit(f"Abgelehnt: {ursache}") from ursache

    print(
        f"Beauftragt: {lauf.job_id} · {laeufe.titel(lauf.auftrag)} · "
        f"{lauf.auftrag['basismodell']} · {lauf.auftrag['aufnahmen']} Aufnahmen von {sprecher.name}",
        flush=True,
    )
    if wahl.nicht_warten:
        return 0

    try:
        status = sieh_zu(datenverzeichnis, lauf.job_id)
    except KeyboardInterrupt:
        print(f"\nNicht mehr zugesehen - der Lauf rechnet weiter: {lauf.job_id}")
        return 0

    if status != laeufe.FERTIG:
        print(f"\nLauf {lauf.job_id}: {status}.")
        return 1
    version = str(laeufe.lies_lauf(datenverzeichnis, lauf.job_id).zustand.get("version", ""))
    print(
        f"\nFertig: {registry.kurzkennung(version)} ({version}).\n"
        f"Freigeben - dann diktiert „schreiben“ damit:  make release JOB={lauf.job_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
