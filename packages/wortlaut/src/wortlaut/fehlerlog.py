"""Das Fehlerprotokoll - alle Warnungen und Fehler der letzten sieben Tage.

    data/protokoll/fehler.jsonl     je Zeile ein Eintrag, ältester zuerst

Ein `logging.Handler` ab `WARNING`, eingehängt im Webdienst (`apps/gesamt.py`)
und im Trainer (`training/laeufer.py`, `training/finetune.py`). Beide
schreiben in dieselbe Datei im Datenverzeichnis, das sie teilen; eine
Dateisperre hält gleichzeitige Zeilen auseinander. `dienst` sagt, woher ein
Eintrag stammt.

**Sieben Tage, dann weg.** Älteres fällt beim Lesen und spätestens stündlich
beim Schreiben heraus - ein Protokoll, das nie jemand liest, soll trotzdem
nicht wachsen. Dazu eine Obergrenze an Einträgen gegen einen Fehler, der sich
in einer Schleife wiederholt.

Gezeigt wird es unter „Fehlerprotokoll" im Menü (`packages/ui`), abgefragt
über `GET /api/fehlerlog` in „hören".
"""

from __future__ import annotations

import fcntl
import json
import logging
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ORDNER = "protokoll"
DATEI = "fehler.jsonl"
AUFBEWAHRUNG = timedelta(days=7)
# Mehr behält die Datei nicht - der jüngste Teil zählt.
HOECHSTENS = 5000
# Wie oft beim Schreiben ausgedünnt wird.
AUSDUENNEN_ALLE_S = 3600


def pfad(datenverzeichnis: Path) -> Path:
    return datenverzeichnis / ORDNER / DATEI


def _zeile(eintrag: logging.LogRecord, dienst: str) -> dict[str, Any]:
    ausnahme = ""
    if eintrag.exc_info:
        ausnahme = "".join(traceback.format_exception(*eintrag.exc_info)).strip()
    return {
        "zeit": datetime.fromtimestamp(eintrag.created, UTC).isoformat(timespec="seconds"),
        "stufe": "fehler" if eintrag.levelno >= logging.ERROR else "warnung",
        "dienst": dienst,
        "quelle": eintrag.name,
        "text": eintrag.getMessage(),
        "ausnahme": ausnahme,
    }


def _gueltig(zeilen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Was jünger als sieben Tage ist, höchstens `HOECHSTENS` Einträge."""
    grenze = (datetime.now(UTC) - AUFBEWAHRUNG).isoformat(timespec="seconds")
    return [zeile for zeile in zeilen if str(zeile.get("zeit", "")) >= grenze][-HOECHSTENS:]


def _lies_roh(datei: Path) -> list[dict[str, Any]]:
    zeilen = []
    for roh in datei.read_text(encoding="utf-8").splitlines():
        try:
            zeilen.append(json.loads(roh))
        except ValueError:
            continue
    return zeilen


def duenne_aus(datenverzeichnis: Path) -> None:
    """Älteres als sieben Tage entfernen - unter der Sperre, an Ort und Stelle."""
    datei = pfad(datenverzeichnis)
    if not datei.is_file():
        return
    with datei.open("r+", encoding="utf-8") as offen:
        fcntl.flock(offen, fcntl.LOCK_EX)
        alle = _lies_roh(datei)
        gueltig = _gueltig(alle)
        if len(gueltig) != len(alle):
            offen.seek(0)
            offen.truncate()
            offen.writelines(json.dumps(zeile, ensure_ascii=False) + "\n" for zeile in gueltig)


def lies(datenverzeichnis: Path) -> list[dict[str, Any]]:
    """Die Einträge der letzten sieben Tage, jüngster zuerst."""
    datei = pfad(datenverzeichnis)
    if not datei.is_file():
        return []
    duenne_aus(datenverzeichnis)
    return list(reversed(_gueltig(_lies_roh(datei))))


class Fehlerprotokoll(logging.Handler):
    """Schreibt jede Warnung und jeden Fehler als Zeile in `fehler.jsonl`."""

    def __init__(self, datenverzeichnis: Callable[[], Path], dienst: str) -> None:
        super().__init__(level=logging.WARNING)
        self.datenverzeichnis = datenverzeichnis
        self.dienst = dienst
        self._ausgeduennt = 0.0

    def emit(self, eintrag: logging.LogRecord) -> None:
        try:
            wurzel = self.datenverzeichnis()
            datei = pfad(wurzel)
            datei.parent.mkdir(parents=True, exist_ok=True)
            with datei.open("a", encoding="utf-8") as offen:
                fcntl.flock(offen, fcntl.LOCK_EX)
                offen.write(json.dumps(_zeile(eintrag, self.dienst), ensure_ascii=False) + "\n")
            if time.monotonic() - self._ausgeduennt > AUSDUENNEN_ALLE_S:
                self._ausgeduennt = time.monotonic()
                duenne_aus(wurzel)
        except Exception:  # noqa: BLE001 - ein Protokoll darf nichts zum Absturz bringen
            self.handleError(eintrag)


# Loggers, die nicht bis zur Wurzel weiterreichen: uvicorn meldet dort seine
# Ausnahmen („Exception in ASGI application").
EIGENSTAENDIG = ("uvicorn",)


def richte_ein(datenverzeichnis: Callable[[], Path], dienst: str) -> None:
    """Das Fehlerprotokoll einhängen - einmal je Prozess, ein zweiter Aufruf ändert nichts.

    Dazu gehen Pythons `warnings` über `logging` (`captureWarnings`), damit
    auch sie hier landen.
    """
    wurzel = logging.getLogger()
    if any(isinstance(handler, Fehlerprotokoll) for handler in wurzel.handlers):
        return
    if not wurzel.handlers:
        # Ohne eigenen Handler gab `logging` Warnungen über seinen Notbehelf
        # auf stderr aus; mit dem Protokoll fiele der weg - und damit das
        # Container-Log.
        auf_konsole = logging.StreamHandler()
        auf_konsole.setLevel(logging.WARNING)
        wurzel.addHandler(auf_konsole)
    handler = Fehlerprotokoll(datenverzeichnis, dienst)
    for logger in (wurzel, *(logging.getLogger(name) for name in EIGENSTAENDIG)):
        logger.addHandler(handler)
    if wurzel.level > logging.WARNING:
        wurzel.setLevel(logging.WARNING)
    logging.captureWarnings(True)
