"""Der Läufer: wartet auf Aufträge und rechnet sie ab, einen nach dem anderen.

    python -m apps.lernen.training.laeufer

Der Einstiegspunkt des Trainings-Containers: nachsehen, ob ein offener
Auftrag daliegt, und `finetune.py` darauf ansetzen.

**Ein Verzeichnis statt eines Aufrufs** (`wortlaut/laeufe.py`): Webdienst und
Trainer starten unabhängig neu, ohne Aufträge zu verlieren oder einander
mitzureißen.

**Einer nach dem anderen**, denn es gibt eine Karte. **Im Unterprozess**, denn
nur ein endender Prozess gibt den Kartenspeicher sicher zurück, und der
Läufer übersteht jeden gescheiterten Lauf.

**Anhalten:** Liegt `halt` (`laeufe.HALT`) im Verzeichnis, bekommt der Prozess
SIGTERM, hält an und meldet `abgebrochen` (`finetune.main`). Nach
`GNADENFRIST_S` fällt die ganze Prozessgruppe mit SIGKILL, und der Läufer
trägt den Zustand selbst ein.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from wortlaut import fehlerlog, laeufe

from apps.lernen.backend.config import einstellungen
from apps.lernen.backend.services import register

# Ins Fehlerprotokoll (`wortlaut/fehlerlog.py`); die übrigen Zeilen gehen wie
# bisher nur ins Container-Log.
_log = logging.getLogger("wortlaut.trainer")


# Wie oft nachgesehen wird, ob jemand anhalten will, und wie lange ein
# angehaltener Prozess hat, um von selbst zu gehen.
HALT_TAKT_S = 2.0
GNADENFRIST_S = 60.0


def _wache(lauf: laeufe.Lauf, prozess: subprocess.Popen) -> None:
    """Neben dem Lauf: anhalten, sobald `halt` daliegt - erst höflich, dann nicht mehr."""
    angehalten_um: float | None = None
    while prozess.poll() is None:
        if angehalten_um is None and laeufe.anhalten_verlangt(lauf.verzeichnis):
            print(f"Auftrag {lauf.job_id}: wird angehalten", flush=True)
            prozess.terminate()
            angehalten_um = time.monotonic()
        elif angehalten_um is not None and time.monotonic() - angehalten_um > GNADENFRIST_S:
            print(f"Auftrag {lauf.job_id}: antwortet nicht, wird beendet", flush=True)
            _beende_gruppe(prozess)
            return
        time.sleep(HALT_TAKT_S)


def _beende_gruppe(prozess: subprocess.Popen) -> None:
    """Den Prozess und alles, was er gestartet hat - die Ladefäden von torch etwa."""
    try:
        os.killpg(prozess.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _fuehre_aus(lauf: laeufe.Lauf) -> int:
    """Einen Lauf rechnen lassen und sein Protokoll mitschreiben.

    Jede Zeile geht in die Protokolldatei (für die Oberfläche) und in die
    Container-Logs.
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
            # Eigene Prozessgruppe: Anhalten trifft alles dieses Laufs, nur das.
            start_new_session=True,
        ) as prozess,
    ):
        threading.Thread(target=_wache, args=(lauf, prozess), daemon=True).start()
        assert prozess.stdout is not None
        for zeile in prozess.stdout:
            datei.write(zeile)
            datei.flush()
            print(zeile.rstrip(), flush=True)
        rueckgabe = prozess.wait()
        if laeufe.anhalten_verlangt(lauf.verzeichnis):
            # Was der Prozess an Ladefäden hinterlassen hat, geht mit.
            _beende_gruppe(prozess)
        return rueckgabe


def _nacharbeit(lauf: laeufe.Lauf, rueckgabe: int) -> None:
    """Falls der Unterprozess gestorben ist, ohne etwas zu sagen.

    Nur hier schreibt der Läufer `zustand.json`, sonst gehört sie dem
    rechnenden Prozess: Der Zustand sagt „läuft", obwohl nichts mehr läuft.
    """
    nachher = laeufe.lies_lauf(einstellungen().data_dir, lauf.job_id)
    if nachher is None or nachher.status not in (laeufe.LAEUFT, laeufe.WARTET):
        return
    if laeufe.anhalten_verlangt(nachher.verzeichnis):
        # Mit SIGKILL gefallen; wo er stand, bleibt im Zustand.
        laeufe.schreibe_json(
            nachher.verzeichnis / laeufe.ZUSTAND,
            {**nachher.zustand, "status": laeufe.ABGEBROCHEN, "beendet": laeufe.jetzt()},
        )
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


def _trage_ein(lauf: laeufe.Lauf) -> None:
    """Den beendeten Lauf ins Register (`services/register.py`) - mit der
    Umgebung, die nur hier bekannt ist. Ein Fehler dabei hält den Läufer nicht
    auf; nachtragen lässt sich mit `scripts/register.py`, solange der Lauf da ist."""
    datenverzeichnis = einstellungen().data_dir
    try:
        register.trage_ein(
            datenverzeichnis, lauf.job_id, register.umgebung(datenverzeichnis, lauf.auftrag)
        )
    except Exception:  # noqa: BLE001 - das Register darf den Läufer nicht anhalten
        _log.error("Lauf %s nicht ins Register eingetragen", lauf.job_id, exc_info=True)


def raeume_verwaiste_auf() -> list[str]:
    """Beim Start: Läufe, die `laeuft` sagen, obwohl niemand rechnet.

    Beim Start rechnet nichts - jeder `laeuft` ist übrig, eine Feststellung,
    keine Schätzung wie `Lauf.haengt`. `_nacharbeit` greift nur, wenn der
    Läufer den Unterprozess sterben sieht, nicht wenn beide zugleich fallen
    (Neubau, Neustart der Maschine).
    """
    konfiguration = einstellungen()
    verwaist = []
    for lauf in laeufe.alle_laeufe(konfiguration.data_dir):
        if lauf.status != laeufe.LAEUFT:
            continue
        laeufe.schreibe_json(
            lauf.verzeichnis / laeufe.ZUSTAND,
            {
                **lauf.zustand,
                "status": laeufe.GESCHEITERT,
                "beendet": laeufe.jetzt(),
                "fehler": (
                    "Dieser Lauf rechnete noch, als der Trainer neu startete. "
                    "Was bis dahin gerechnet wurde, steht im Protokoll daneben; "
                    "fortsetzen lässt er sich nicht."
                ),
            },
        )
        _trage_ein(lauf)
        verwaist.append(lauf.job_id)
    return verwaist


def einmal() -> bool:
    """Den nächsten offenen Auftrag abarbeiten; `False`, wenn keiner da war."""
    konfiguration = einstellungen()
    lauf = laeufe.naechster_offener(konfiguration.data_dir)
    if lauf is None:
        return False

    if laeufe.anhalten_verlangt(lauf.verzeichnis):
        # Angehalten, bevor er anfing.
        laeufe.schreibe_json(
            lauf.verzeichnis / laeufe.ZUSTAND,
            {"status": laeufe.ABGEBROCHEN, "beendet": laeufe.jetzt()},
        )
        _trage_ein(lauf)
        return True

    print(
        f"Auftrag {lauf.job_id}: {laeufe.titel(lauf.auftrag)} · Sprecher {lauf.sprecher_id}",
        flush=True,
    )
    rueckgabe = _fuehre_aus(lauf)
    _nacharbeit(lauf, rueckgabe)
    # Zwischenstände räumt der Prozess selbst weg (`finetune.main`) - außer
    # der Kern erschlägt ihn, oft wegen voller Platte.
    entfernt = laeufe.raeume_zwischenstaende_auf(lauf.verzeichnis)
    if entfernt:
        print(f"Zwischenstände weggeräumt: {', '.join(entfernt)}", flush=True)
    print(f"Auftrag {lauf.job_id} beendet ({rueckgabe})", flush=True)
    _trage_ein(lauf)
    nachher = laeufe.lies_lauf(konfiguration.data_dir, lauf.job_id)
    if nachher is not None and nachher.status == laeufe.GESCHEITERT:
        _log.error(
            "Lauf %s (%s) gescheitert: %s",
            lauf.job_id,
            laeufe.titel(lauf.auftrag),
            nachher.zustand.get("fehler") or f"Rückgabe {rueckgabe}",
        )
    return True


def melde_karte() -> None:
    """Die Karte einmal beschreiben (`finetune.py --karte`), damit „lernen"
    anbietet, was darauf passt - im Unterprozess: Der Läufer selbst hält
    keinen CUDA-Kontext, der Platz gehört den Läufen."""
    try:
        subprocess.run(
            [sys.executable, "-m", "apps.lernen.training.finetune", "--karte"],
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        _log.warning("Karte nicht gemeldet - die Messung hing.")


def main() -> int:
    konfiguration = einstellungen()
    fehlerlog.richte_ein(lambda: einstellungen().data_dir, "trainer")
    print(
        f"Läufer bereit. Datenverzeichnis: {konfiguration.data_dir}, "
        f"Takt: {konfiguration.lernen_takt_s} s",
        flush=True,
    )
    melde_karte()
    for job_id in raeume_verwaiste_auf():
        _log.warning("Verwaist aus einem früheren Lauf, als gescheitert vermerkt: %s", job_id)
    while True:
        try:
            if not einmal():
                time.sleep(konfiguration.lernen_takt_s)
        except KeyboardInterrupt:
            print("Läufer beendet.", flush=True)
            return 0
        except Exception as ursache:  # noqa: BLE001 - der Läufer bleibt stehen
            # Ein Fehler beim Nachsehen soll nicht alle folgenden Aufträge mitnehmen.
            _log.error("Läufer: %s: %s", type(ursache).__name__, ursache, exc_info=True)
            time.sleep(konfiguration.lernen_takt_s)


if __name__ == "__main__":
    raise SystemExit(main())
