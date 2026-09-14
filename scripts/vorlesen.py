"""Stimmen holen und alle Vorlagen vorlesen lassen - vorab statt beim Klick.

    uv run python scripts/vorlesen.py --hole de_DE-thorsten-high   # auf dem Wirt
    docker compose exec wortlaut python scripts/vorlesen.py        # im Container

Vorgelesen wird von selbst: Wer in „hören" auf den Knopf drückt, bekommt den
Satz, und beim zweiten Mal liegt er schon da (`services/vorlesen.py`). Nötig
ist dieses Skript deshalb nicht.

Es ist der Weg, das für alle Korpora auf einmal und **vorher** zu tun - vor
einer Aufnahmesitzung, in der niemand auf den ersten Satz warten soll. Ein
zweiter Lauf tut nichts: Was da ist, wird nicht neu gesprochen.

**`--hole <stimme>` lädt eine Piper-Stimme nach.** Sie liegen nicht im Abbild,
sondern im Modellspeicher daneben - je Stimme einige Dutzend Megabyte, und
welche jemand haben will, entscheidet er und nicht der Bau. Ohne eine einzige
Stimme liest weiterhin der Browser vor, und das ist kein Fehler, sondern der
Ausgangszustand.

Bekannte deutsche Stimmen (es gibt mehr, siehe die Sammlung auf Hugging Face):

    de_DE-thorsten-high      klar und ruhig, die kräftigste der freien
    de_DE-thorsten-medium    dasselbe eine Stufe kleiner
    de_DE-kerstin-low        weiblich, hell
    de_DE-pavoque-low        männlich, ruhiger und tiefer als Thorsten
    de_DE-ramona-low         weiblich
    de_DE-karlsson-low       männlich
    de_DE-eva_k-x_low        weiblich, sehr genügsam

**Zur Auflösung.** `high` gibt es auf Deutsch nur bei Thorsten; alles andere
endet bei `low`, und das heißt 16 kHz statt 22,05. Wer eine zweite Stimme
holt, holt sie der Abwechslung wegen und nicht der Schärfe wegen - für den
Zweck hier, einen Satz zu hören und ihn nachzusprechen, zählt ohnehin die
Deutlichkeit und nicht die Bandbreite.
"""

from __future__ import annotations

import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Ausführbar ohne Installation: Repository-Wurzel in den Suchpfad legen.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import corpus, db, storage, vorlesen

from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.db.models import Vorlage
from apps.hoeren.backend.services import vorlesen as vorlesedienst

# Woher die Stimmen kommen. Eine feste Adresse und kein Verzeichnisdienst: Die
# Sammlung ist nach Sprache, Stimme und Auflösung gegliedert, und der Name
# einer Stimme sagt alles, was für den Pfad nötig ist.
QUELLE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def _pfadteile(stimme: str) -> tuple[str, str, str]:
    """`de_DE-thorsten-high` → (`de_DE`, `thorsten`, `high`).

    Der Name trägt alles: Sprachfamilie, Gebiet, Stimme, Auflösung. Ihn zu
    zerlegen ist deshalb kein Raten, sondern Lesen - und es spart eine Tabelle,
    die jemand pflegen müsste.
    """
    gebiet, rest = stimme.split("-", 1)
    person, aufloesung = rest.rsplit("-", 1)
    return gebiet, person, aufloesung


# Wie oft ein Download wiederholt wird, bevor aufgegeben wird - und wie lange
# eine einzelne Leseoperation stocken darf.
#
# Beides steht hier, weil genau das einmal schiefging: Die 114 MB der Stimme
# kamen durch, die 5 kB der Beschreibung daneben blieben in einer stockenden
# Verbindung hängen, und nach zwei Stunden stand „the operation timed out" da.
# Zurück blieb eine Stimme, die vollständig aussah und keine war - `stimmen()`
# verlangt beide Dateien.
#
# Ein kurzer Zeitüberschreitungswert **mit** Wiederholung ist dagegen die
# richtige Wahl: Eine Leitung, die zwei Minuten lang tröpfelt, ist tot, und ein
# neuer Versuch kostet Sekunden.
VERSUCHE = 3
ZEITGRENZE_S = 30


def _lade(adresse: str, datei: Path) -> None:
    """Eine Datei holen - mit Wiederholung, strömend, und erst am Ende sichtbar.

    Erst daneben, dann an die Stelle: Ein abgebrochener Download soll nicht wie
    eine fertige Stimme aussehen.

    Strömend und nicht `read()` am Stück: Die Stimme wiegt über hundert
    Megabyte, und die brauchen nicht alle gleichzeitig in den Arbeitsspeicher.
    """
    entwurf = datei.with_name(datei.name + ".neu")
    letzte: Exception | None = None
    for versuch in range(1, VERSUCHE + 1):
        try:
            with (
                urllib.request.urlopen(adresse, timeout=ZEITGRENZE_S) as quelle,
                entwurf.open("wb") as offen,
            ):
                shutil.copyfileobj(quelle, offen, 1 << 20)
            entwurf.replace(datei)
            return
        except (urllib.error.URLError, OSError, TimeoutError) as ursache:
            letzte = ursache
            entwurf.unlink(missing_ok=True)
            if versuch < VERSUCHE:
                print(f"    Versuch {versuch} gescheitert ({ursache}) - noch einmal …")
                time.sleep(2 * versuch)
    raise VorlesenDownloadFehler(f"{datei.name}: {letzte}")


class VorlesenDownloadFehler(RuntimeError):
    """Eine Stimmdatei ließ sich nicht holen."""


def hole(stimme: str, ziel: Path) -> int:
    """Eine Piper-Stimme herunterladen; gibt zurück, wie viele Dateien kamen.

    **Die Beschreibung zuerst, das Modell danach.** Sie ist fünf Kilobyte groß
    und entscheidet trotzdem darüber, ob die Stimme zählt. Scheitert sie, hat
    man Sekunden verloren statt hundert Megabyte - andersherum war es einmal,
    und das war die falsche Reihenfolge.
    """
    gebiet, person, aufloesung = _pfadteile(stimme)
    sprache = gebiet.split("_", 1)[0]
    ziel.mkdir(parents=True, exist_ok=True)

    geholt = 0
    for endung in (".onnx.json", ".onnx"):
        datei = ziel / f"{stimme}{endung}"
        if datei.is_file():
            print(f"  {datei.name}: liegt schon da")
            continue
        adresse = f"{QUELLE}/{sprache}/{gebiet}/{person}/{aufloesung}/{stimme}{endung}"
        print(f"  {datei.name}: wird geladen …")
        try:
            _lade(adresse, datei)
        except VorlesenDownloadFehler as ursache:
            print(f"  gescheitert: {ursache}")
            print("  Ein erneuter Aufruf holt nur, was noch fehlt.")
            return geholt
        print(f"  {datei.name}: {datei.stat().st_size / 1e6:.1f} MB")
        geholt += 1
    return geholt


def lies_alles_vor(stimme: str) -> int:
    """Jede Vorlage jedes Korpus in dieser Stimme; gibt die neuen zurück."""
    konfiguration = einstellungen()
    ablage = storage.oeffne_ablage(konfiguration.storage, konfiguration.data_dir)
    sprecher = corpus.sprecher_ids(konfiguration.data_dir)
    if not sprecher:
        print(f"Keine Korpora unter {konfiguration.data_dir / corpus.KORPUS} - nichts zu tun.")
        return 0

    neu_gesamt = 0
    for sprecher_id in sprecher:
        pfad = corpus.datenbank_pfad(konfiguration.data_dir, sprecher_id)
        db.wende_migrationen_an(pfad, konfiguration.migrationsverzeichnis)
        neu = 0
        with Session(db.verbinde(pfad)) as sitzung:
            vorlagen = sitzung.scalars(select(Vorlage).order_by(Vorlage.position)).all()
            for vorlage in vorlagen:
                schon = ablage.pfad(vorlesedienst.relpfad(vorlage, stimme)).is_file()
                if schon:
                    continue
                if vorlesedienst.stelle_her(
                    ablage,
                    vorlage,
                    stimme,
                    konfiguration.stimmen_dir,
                    konfiguration.vorlesen_motor,
                ):
                    neu += 1
        print(f"{sprecher_id}: {len(vorlagen)} Vorlagen, {neu} neu gesprochen")
        neu_gesamt += neu
    return neu_gesamt


def main(argumente: list[str]) -> int:
    konfiguration = einstellungen()

    if "--hole" in argumente:
        stelle = argumente.index("--hole")
        if stelle + 1 >= len(argumente):
            print("Aufruf: --hole de_DE-thorsten-high")
            return 2
        name = argumente[stelle + 1]
        print(f"Stimme {name} nach {konfiguration.stimmen_dir}:")
        hole(name, konfiguration.stimmen_dir)

    vorhanden = vorlesen.stimmen(konfiguration.stimmen_dir, konfiguration.vorlesen_motor)
    if not vorhanden:
        print(
            f"Keine Stimme unter {konfiguration.stimmen_dir}. "
            "Mit --hole de_DE-thorsten-high eine laden; bis dahin liest der Browser vor."
        )
        return 1
    print("Vorhandene Stimmen: " + ", ".join(s.schluessel for s in vorhanden))

    # Ohne Angabe alle vorhandenen: Wer zwei Stimmen abgelegt hat, will sie
    # vermutlich auch beide vergleichen können, ohne auf den ersten Satz zu
    # warten.
    gewuenscht = [a for a in argumente if not a.startswith("--") and "/" in a]
    ziel = gewuenscht or [s.schluessel for s in vorhanden]

    gesamt = 0
    for stimme in ziel:
        print(f"\n── {stimme}")
        gesamt += lies_alles_vor(stimme)
    print(f"\n{gesamt} Sätze neu gesprochen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
