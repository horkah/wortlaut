"""Aufnahmen übernehmen, die außerhalb von „hören" entstanden sind.

    uv run python scripts/importieren.py <sprecher_id> <ordner>                        # auf dem Wirt
    docker compose exec wortlaut python scripts/importieren.py <sprecher_id> <ordner>  # im Container

Ein Ordner ist eine Textquelle, benannt nach dem Ordner. Darin liegen Paare aus
Ton und Text mit gleichem Namen - `S. 8 Das Turnier.m4a` neben
`S. 8 Das Turnier.txt`. Jedes Paar wird eine Vorlage mit genau einer Aufnahme,
in der Reihenfolge der Zahlen im Namen (S. 8 vor S. 10).

Der Ton geht denselben Weg wie beim Aufnehmen im Browser (`api/recordings.py`):
ffmpeg macht daraus 16 kHz Mono-WAV, gemessen wird am Ergebnis, abgelegt wird
erst danach, und die abgewandelten Fassungen kommen gleich mit.

**Lange Aufnahmen sind hier gewollt.** Eine Buchseite am Stück dauert eine bis
zwei Minuten, weit mehr als eine Einheit. Zerlegt wird sie danach in der
Zuschnittansicht (`api/zuschnitt.py`, „Teilen") - dort, wo ein Mensch hört,
wo ein Satz endet.

Ein zweiter Lauf legt nichts doppelt an: Jede Aufnahme trägt Ordner und
Dateinamen als `externe_id`, und was es schon gibt, wird übersprungen.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

# Ausführbar ohne Installation: Repository-Wurzel in den Suchpfad legen.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import audio, corpus, db, ids, storage
from wortlaut.text import chunker

from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.db.models import Aufnahme, Sprecher, Textquelle, Vorlage, jetzt
from apps.hoeren.backend.services import augmentierung, quality
from apps.hoeren.backend.services.prompt_queue import naechste_position

TONENDUNGEN = (".m4a", ".mp3", ".wav", ".ogg", ".opus", ".flac")


def _reihenfolge(pfad: Path) -> tuple:
    """Zahlen im Namen als Zahlen: „S. 8" vor „S. 10"."""
    return tuple(
        (0, int(teil)) if teil.isdigit() else (1, teil)
        for teil in re.split(r"(\d+)", pfad.stem)
        if teil
    )


def _paare(ordner: Path) -> list[tuple[Path, Path]]:
    toene = sorted(
        (p for p in ordner.iterdir() if p.suffix.lower() in TONENDUNGEN), key=_reihenfolge
    )
    paare = []
    for ton in toene:
        text = ton.with_suffix(".txt")
        if not text.is_file():
            raise SystemExit(f"Zu {ton.name} fehlt {text.name}.")
        paare.append((ton, text))
    return paare


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip().splitlines()[2])
        return 2
    sprecher_id, ordner = sys.argv[1], Path(sys.argv[2])
    if not ordner.is_dir():
        raise SystemExit(f"Kein Ordner: {ordner}")

    konfiguration = einstellungen()
    ablage = storage.oeffne_ablage(konfiguration.storage, konfiguration.data_dir)
    pfad = corpus.datenbank_pfad(konfiguration.data_dir, sprecher_id)
    # Vor dem Migrieren: Das legte eine fehlende Datenbank sonst still an.
    if not pfad.is_file():
        raise SystemExit(f"Kein Korpus für {sprecher_id}.")
    db.wende_migrationen_an(pfad, konfiguration.migrationsverzeichnis)

    paare = _paare(ordner)
    with Session(db.verbinde(pfad)) as sitzung:
        sprecher = sitzung.get(Sprecher, sprecher_id)
        if sprecher is None:
            raise SystemExit(f"Kein Sprecher {sprecher_id} in {pfad}.")

        quelle: Textquelle | None = None
        for ton, textdatei in paare:
            externe_id = f"import:{ordner.name}/{ton.name}"
            if sitzung.scalars(
                select(Aufnahme).where(Aufnahme.externe_id == externe_id)
            ).first():
                print(f"  {ton.name}: schon übernommen")
                continue

            # Zeilenumbrüche stammen aus dem Satz des Buchs, nicht aus der Sprache.
            text = " ".join(textdatei.read_text(encoding="utf-8").split())
            if not text:
                raise SystemExit(f"{textdatei.name} ist leer.")

            if quelle is None:
                quelle = Textquelle(
                    id=ids.neue_id("src"),
                    speaker_id=sprecher_id,
                    art="upload",
                    titel=ordner.name[:200],
                    parameter=json.dumps(
                        {"herkunft": "import", "ordner": ordner.name}, ensure_ascii=False
                    ),
                    erstellt=jetzt(),
                )
                sitzung.add(quelle)
                sitzung.flush()

            aufnahme_id = ids.neue_id("rec")
            relpfad = corpus.audio_relpfad(sprecher_id, aufnahme_id)
            with tempfile.TemporaryDirectory() as verzeichnis:
                wav = Path(verzeichnis) / "aufnahme.wav"
                audio.wandle_in_wav(ton, wav)
                befund = audio.untersuche(wav)
                ablage.lege_ab(relpfad, wav)

            vorlage = Vorlage(
                id=ids.neue_id("prm"),
                source_id=quelle.id,
                speaker_id=sprecher_id,
                position=naechste_position(sitzung, sprecher_id),
                text=text,
                dauer_geschaetzt_s=chunker.dauer(text, sprecher.sprache),
                erstellt=jetzt(),
            )
            sitzung.add(vorlage)
            sitzung.flush()
            aufnahme = Aufnahme(
                id=aufnahme_id,
                prompt_id=vorlage.id,
                speaker_id=sprecher_id,
                session_id=None,
                blob=relpfad,
                dauer_s=befund.dauer_s,
                pegel_dbfs=befund.pegel_dbfs,
                spitze_dbfs=befund.spitze_dbfs,
                clipping_anteil=befund.clipping_anteil,
                stille_vorn_s=befund.stille_vorn_s,
                stille_hinten_s=befund.stille_hinten_s,
                modus="gelesen",
                status="ok",
                hinweise=json.dumps(
                    quality.pruefe(befund, vorlage.dauer_geschaetzt_s), ensure_ascii=False
                ),
                externe_id=externe_id,
                erstellt=jetzt(),
            )
            sitzung.add(aufnahme)
            sitzung.commit()

            try:
                augmentierung.stelle_alle_her(ablage, aufnahme)
            except audio.AudioFehler as ursache:
                print(f"  {ton.name}: Fassungen später ({ursache})")
            print(f"  {ton.name}: {aufnahme_id}, {befund.dauer_s:.1f} s, {len(text.split())} Wörter")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
