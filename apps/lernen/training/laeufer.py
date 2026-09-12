"""Der Läufer: wartet auf Aufträge und rechnet sie ab, einen nach dem anderen.

    python -m apps.lernen.training.laeufer

Das ist der Einstiegspunkt des Trainings-Containers. Er tut wenig und
absichtlich wenig: nachsehen, ob ein Verzeichnis mit offenem Auftrag da ist,
und wenn ja, `finetune.py` darauf loslassen.

**Warum Nachsehen und kein Aufruf.** Zwischen der Oberfläche und der Karte
liegt kein Netzwerkweg, sondern ein Verzeichnis (`wortlaut/laeufe.py`). Das hat
drei Folgen, und alle drei sind der Grund dafür: Der Webdienst kann neu
starten, während ein Training läuft. Der Trainer kann neu starten, ohne dass
ein Auftrag verlorengeht. Und es gibt keinen Weg, auf dem der eine den anderen
zum Absturz bringt.

**Warum einer nach dem anderen.** Es gibt eine Karte. Zwei Läufe darauf wären
zusammen langsamer als nacheinander und passten oft nicht in den Speicher -
dieselbe Überlegung wie beim Lauf der Auswertung in „hören".

**Warum ein Unterprozess.** Ein Feintuning belegt Speicher auf der Karte, und
PyTorch gibt ihn nach einem Fehler nicht immer zurück. Ein Prozess, der endet,
gibt alles zurück. Zugleich überlebt der Läufer damit einen Lauf, der sich an
einem kaputten Modell verschluckt - er nimmt den nächsten.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from wortlaut import laeufe

from apps.lernen.backend.config import einstellungen


def _fuehre_aus(lauf: laeufe.Lauf) -> int:
    """Einen Lauf rechnen lassen und sein Protokoll mitschreiben.

    Die Ausgabe wandert zeilenweise in zwei Richtungen: in die Protokolldatei
    des Laufs, wo die Oberfläche sie zeigt, und auf die eigene Ausgabe, wo sie
    in den Container-Logs landet. Wer einen Fehler sucht, sucht ihn mal hier,
    mal dort - und soll ihn nicht an der falschen Stelle vermissen.
    """
    protokoll = lauf.verzeichnis / laeufe.PROTOKOLL
    with (
        protokoll.open("a", encoding="utf-8") as datei,
        subprocess.Popen(
            [sys.executable, "-u", "-m", "apps.lernen.training.finetune", str(lauf.verzeichnis)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as prozess,
    ):
        assert prozess.stdout is not None
        for zeile in prozess.stdout:
            datei.write(zeile)
            datei.flush()
            print(zeile.rstrip(), flush=True)
        return prozess.wait()


def _nacharbeit(lauf: laeufe.Lauf, rueckgabe: int) -> None:
    """Falls der Unterprozess gestorben ist, ohne etwas zu sagen.

    Der einzige Fall, in dem der Läufer `zustand.json` anfasst. Sonst gehört
    die Datei dem rechnenden Prozess - zwei Schreiber ergäben irgendwann einen
    Zustand, der von beiden halb stammt. Hier ist der Zustand aber „läuft",
    während nachweislich nichts mehr läuft: ein Lauf, auf den die Oberfläche
    sonst ewig wartete.
    """
    nachher = laeufe.lies_lauf(einstellungen().data_dir, lauf.job_id)
    if nachher is None or nachher.status not in (laeufe.LAEUFT, laeufe.WARTET):
        return
    laeufe.schreibe_json(
        nachher.verzeichnis / laeufe.ZUSTAND,
        {
            "status": laeufe.GESCHEITERT,
            "beendet": laeufe.jetzt(),
            "fehler": (
                f"Der Trainingsprozess endete mit {rueckgabe}, ohne ein Ergebnis zu "
                "hinterlassen. Das Protokoll steht daneben."
            ),
        },
    )


def einmal() -> bool:
    """Den nächsten offenen Auftrag abarbeiten; `False`, wenn keiner da war."""
    konfiguration = einstellungen()
    lauf = laeufe.naechster_offener(konfiguration.data_dir)
    if lauf is None:
        return False

    print(
        f"Auftrag {lauf.job_id}: {lauf.auftrag.get('methode')} · "
        f"{lauf.auftrag.get('daten')} · Sprecher {lauf.sprecher_id}",
        flush=True,
    )
    rueckgabe = _fuehre_aus(lauf)
    _nacharbeit(lauf, rueckgabe)
    print(f"Auftrag {lauf.job_id} beendet ({rueckgabe})", flush=True)
    return True


def main() -> int:
    konfiguration = einstellungen()
    print(
        f"Läufer bereit. Datenverzeichnis: {konfiguration.data_dir}, "
        f"Takt: {konfiguration.lernen_takt_s} s",
        flush=True,
    )
    while True:
        try:
            if not einmal():
                time.sleep(konfiguration.lernen_takt_s)
        except KeyboardInterrupt:
            print("Läufer beendet.", flush=True)
            return 0
        except Exception as ursache:  # noqa: BLE001 - der Läufer bleibt stehen
            # Was hier ankommt, betrifft das Nachsehen selbst - ein kaputtes
            # Verzeichnis etwa. Ein Läufer, der daran stirbt, nimmt auch jeden
            # gesunden Auftrag danach mit; also weitermachen und es sagen.
            print(f"Läufer: {type(ursache).__name__}: {ursache}", flush=True)
            time.sleep(konfiguration.lernen_takt_s)


if __name__ == "__main__":
    raise SystemExit(main())
