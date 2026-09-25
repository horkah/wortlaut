"""Worauf wortlaut läuft und wie ausgelastet es gerade ist - die Auskunft für „System".

Zwei Arten von Werten stehen hier nebeneinander: was die Maschine **ist**
(Prozessor, Arbeitsspeicher, Karte, Platten) und was sie gerade **tut**
(Auslastung, belegter Speicher, Temperatur). Die Oberfläche fragt beides in
einem Aufruf ab, einmal je Sekunde, solange die Ansicht offen ist
(`packages/ui/System.svelte`).

**Woher die Werte kommen.** Aus dem, was der Prozess ohnehin sehen kann:
`/proc` für Prozessor und Speicher, `nvidia-smi` für die Karte. Keine neue
Abhängigkeit - `nvidia-smi` legt die nvidia-Laufzeit in jeden Container mit
Karte, und `/proc/stat` und `/proc/meminfo` sind in einem Container die der
Maschine, nicht die des Containers. Genau das ist hier gewollt: Die Frage ist,
ob die Maschine zu tun hat, nicht, ob dieser eine Prozess es hat. Ein
Training in seinem eigenen Container ist darin enthalten.

**Was fehlt, fehlt still.** Ohne Karte ist die Liste der Karten leer, ohne
`/proc` (etwa auf einem Mac in der Entwicklung) stehen die Werte auf `None`.
Eine Auskunftsseite, die an einer fehlenden Quelle scheitert, zeigt gar nichts
- dabei wäre alles andere richtig gewesen.

**Warum die Prozessorlast einen Zustand braucht.** `/proc/stat` zählt nur
auf: so viele Takte gerechnet, so viele gewartet, seit dem Start. Eine
Auslastung ist erst der Unterschied zwischen zwei Ablesungen. Die vorige steht
deshalb hier im Modul; liegt sie zu weit zurück oder fehlt sie, wird kurz
gewartet und ein zweites Mal gelesen.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# Was `nvidia-smi` je Karte liefern soll, in dieser Reihenfolge. Die Namen sind
# die der `--query-gpu`-Schnittstelle; `nvidia-smi --help-query-gpu` listet sie.
_KARTENFELDER = (
    "index",
    "name",
    "driver_version",
    "compute_cap",
    "memory.total",
    "memory.used",
    "utilization.gpu",
    "utilization.memory",
    "temperature.gpu",
    "power.draw",
    "power.limit",
    "fan.speed",
    "clocks.gr",
    "clocks.max.gr",
    "pcie.link.gen.current",
    "pcie.link.width.current",
)

# Länger als eine Sekunde darf `nvidia-smi` nicht brauchen, sonst überholt die
# nächste Abfrage die vorige. Hängt der Treiber, steht die Karte eben nicht da.
_ZEITLIMIT_S = 2.0

# Wie alt die vorige Ablesung von `/proc/stat` höchstens sein darf, damit die
# Last daraus noch „jetzt" heißt, und wie lange sonst für eine frische gewartet
# wird.
_HOECHSTENS_ALT_S = 5.0
_KURZ_WARTEN_S = 0.25


@dataclass(frozen=True)
class Karte:
    """Eine Grafikkarte: was sie ist und was sie gerade tut."""

    index: int
    name: str
    treiber: str | None
    compute_capability: str | None
    speicher_mib: int | None
    speicher_belegt_mib: int | None
    auslastung: float | None
    speicher_auslastung: float | None
    temperatur: float | None
    leistung_w: float | None
    leistung_grenze_w: float | None
    luefter: float | None
    takt_mhz: float | None
    takt_max_mhz: float | None
    pcie: str | None


@dataclass(frozen=True)
class Prozessor:
    modell: str | None
    kerne: int | None
    # Wie viele davon dieser Prozess nutzen darf - im Container womöglich weniger.
    kerne_verfuegbar: int | None
    auslastung: float | None
    je_kern: list[float] = field(default_factory=list)
    # Die Lastmittel über 1, 5 und 15 Minuten, wie `uptime` sie nennt.
    lastmittel: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class Speicher:
    gesamt: int | None
    belegt: int | None
    swap_gesamt: int | None
    swap_belegt: int | None
    # Die Obergrenze des Containers, falls eine gesetzt ist.
    grenze: int | None


@dataclass(frozen=True)
class Ablage:
    name: str
    pfad: str
    gesamt: int
    belegt: int


@dataclass(frozen=True)
class Systemlage:
    kernel: str
    betriebszeit_s: float | None
    prozessor: Prozessor
    speicher: Speicher
    karten: list[Karte]
    ablagen: list[Ablage]


# ── Grafikkarte ─────────────────────────────────────────────────────────────


def _zahl(wert: str) -> float | None:
    """`nvidia-smi` schreibt „[N/A]" oder „[Not Supported]", wo es nichts weiß."""
    try:
        return float(wert)
    except ValueError:
        return None


def _text(wert: str) -> str | None:
    return None if not wert or wert.startswith("[") else wert


def lies_karten(ausgabe: str) -> list[Karte]:
    """Die CSV-Ausgabe von `nvidia-smi --query-gpu` in Karten übersetzen."""
    karten = []
    for zeile in ausgabe.strip().splitlines():
        werte = [wert.strip() for wert in zeile.split(",")]
        if len(werte) != len(_KARTENFELDER):
            continue
        feld = dict(zip(_KARTENFELDER, werte, strict=True))
        speicher = _zahl(feld["memory.total"])
        belegt = _zahl(feld["memory.used"])
        generation = _text(feld["pcie.link.gen.current"])
        breite = _text(feld["pcie.link.width.current"])
        karten.append(
            Karte(
                index=int(_zahl(feld["index"]) or 0),
                name=feld["name"],
                treiber=_text(feld["driver_version"]),
                compute_capability=_text(feld["compute_cap"]),
                speicher_mib=int(speicher) if speicher is not None else None,
                speicher_belegt_mib=int(belegt) if belegt is not None else None,
                auslastung=_zahl(feld["utilization.gpu"]),
                speicher_auslastung=_zahl(feld["utilization.memory"]),
                temperatur=_zahl(feld["temperature.gpu"]),
                leistung_w=_zahl(feld["power.draw"]),
                leistung_grenze_w=_zahl(feld["power.limit"]),
                luefter=_zahl(feld["fan.speed"]),
                takt_mhz=_zahl(feld["clocks.gr"]),
                takt_max_mhz=_zahl(feld["clocks.max.gr"]),
                pcie=f"Gen {generation} ×{breite}" if generation and breite else None,
            )
        )
    return karten


def karten() -> list[Karte]:
    """Alle Karten, die `nvidia-smi` kennt - leer, wenn es keine gibt."""
    programm = shutil.which("nvidia-smi")
    if programm is None:
        return []
    try:
        ergebnis = subprocess.run(  # noqa: S603 - fester Aufruf, keine Eingabe von außen
            [
                programm,
                f"--query-gpu={','.join(_KARTENFELDER)}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=_ZEITLIMIT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return lies_karten(ergebnis.stdout) if ergebnis.returncode == 0 else []


# ── Prozessor ───────────────────────────────────────────────────────────────


def lies_zeiten(stat: str) -> dict[str, tuple[int, int]]:
    """Je `cpu`-Zeile aus `/proc/stat`: (Takte insgesamt, davon untätig).

    Untätig heißt `idle` und `iowait` - wer auf die Platte wartet, rechnet
    nicht. `guest` steckt schon in `user` und bleibt deshalb draußen.
    """
    zeiten = {}
    for zeile in stat.splitlines():
        if not zeile.startswith("cpu"):
            continue
        name, *werte = zeile.split()
        takte = [int(wert) for wert in werte[:8]]
        zeiten[name] = (sum(takte), takte[3] + takte[4])
    return zeiten


def auslastung(
    vorher: dict[str, tuple[int, int]], nachher: dict[str, tuple[int, int]]
) -> dict[str, float]:
    """Der Anteil gerechneter Takte zwischen zwei Ablesungen, in Prozent."""
    last = {}
    for name, (gesamt, untaetig) in nachher.items():
        if name not in vorher:
            continue
        d_gesamt = gesamt - vorher[name][0]
        d_untaetig = untaetig - vorher[name][1]
        last[name] = round(100 * (d_gesamt - d_untaetig) / d_gesamt, 1) if d_gesamt > 0 else 0.0
    return last


class _Ablesung:
    """Die vorige Ablesung von `/proc/stat`, von allen Anfragen geteilt."""

    def __init__(self) -> None:
        self._sperre = threading.Lock()
        self._zeitpunkt = 0.0
        self._zeiten: dict[str, tuple[int, int]] = {}

    def last(self) -> dict[str, float]:
        stat = Path("/proc/stat")
        if not stat.is_file():
            return {}
        with self._sperre:
            vorher, damals = self._zeiten, self._zeitpunkt
            if not vorher or time.monotonic() - damals > _HOECHSTENS_ALT_S:
                vorher = lies_zeiten(stat.read_text())
                time.sleep(_KURZ_WARTEN_S)
            jetzt = lies_zeiten(stat.read_text())
            self._zeiten, self._zeitpunkt = jetzt, time.monotonic()
        return auslastung(vorher, jetzt)


_ablesung = _Ablesung()


def _prozessormodell() -> str | None:
    info = Path("/proc/cpuinfo")
    if info.is_file():
        for zeile in info.read_text().splitlines():
            if zeile.startswith("model name"):
                return zeile.split(":", 1)[1].strip()
    return platform.processor() or None


def prozessor() -> Prozessor:
    last = _ablesung.last()
    je_kern = [
        last[name]
        for name in sorted(
            (name for name in last if name != "cpu"), key=lambda name: int(name[3:])
        )
    ]
    try:
        verfuegbar = len(os.sched_getaffinity(0))
    except AttributeError:  # kein Linux
        verfuegbar = None
    try:
        lastmittel = [round(wert, 2) for wert in os.getloadavg()]
    except OSError:
        lastmittel = []
    return Prozessor(
        modell=_prozessormodell(),
        kerne=os.cpu_count(),
        kerne_verfuegbar=verfuegbar,
        auslastung=last.get("cpu"),
        je_kern=je_kern,
        lastmittel=lastmittel,
    )


# ── Arbeitsspeicher ─────────────────────────────────────────────────────────


def lies_speicher(meminfo: str, grenze: int | None = None) -> Speicher:
    """`/proc/meminfo` lesen; belegt ist, was nicht verfügbar ist.

    „Verfügbar" und nicht „frei": Den Seitencache gibt der Kern auf Zuruf her,
    und eine Maschine, die ihren Speicher als Cache nutzt, ist nicht voll.
    """
    werte = {}
    for zeile in meminfo.splitlines():
        name, _, rest = zeile.partition(":")
        teile = rest.split()
        if teile:
            werte[name] = int(teile[0]) * 1024
    gesamt = werte.get("MemTotal")
    verfuegbar = werte.get("MemAvailable")
    swap = werte.get("SwapTotal")
    swap_frei = werte.get("SwapFree")
    return Speicher(
        gesamt=gesamt,
        belegt=gesamt - verfuegbar if gesamt is not None and verfuegbar is not None else None,
        swap_gesamt=swap,
        swap_belegt=swap - swap_frei if swap is not None and swap_frei is not None else None,
        grenze=grenze,
    )


def _containergrenze() -> int | None:
    """Die Speichergrenze des Containers (cgroup v2), falls eine gesetzt ist."""
    datei = Path("/sys/fs/cgroup/memory.max")
    try:
        wert = datei.read_text().strip()
    except OSError:
        return None
    return int(wert) if wert.isdigit() else None


def speicher() -> Speicher:
    meminfo = Path("/proc/meminfo")
    if not meminfo.is_file():
        return Speicher(gesamt=None, belegt=None, swap_gesamt=None, swap_belegt=None, grenze=None)
    return lies_speicher(meminfo.read_text(), _containergrenze())


# ── Platten ─────────────────────────────────────────────────────────────────


def ablagen(orte: list[tuple[str, Path]]) -> list[Ablage]:
    """Belegung je Ablage - jede Platte nur einmal, auch wenn zwei Orte darauf liegen."""
    gesehen: set[int] = set()
    ergebnis = []
    for name, pfad in orte:
        try:
            geraet = pfad.stat().st_dev
            belegung = shutil.disk_usage(pfad)
        except OSError:
            continue
        if geraet in gesehen:
            continue
        gesehen.add(geraet)
        ergebnis.append(
            Ablage(name=name, pfad=str(pfad), gesamt=belegung.total, belegt=belegung.used)
        )
    return ergebnis


def _betriebszeit() -> float | None:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def lage(orte: list[tuple[str, Path]]) -> Systemlage:
    """Alles auf einmal - das, was `GET /api/system` ausliefert."""
    return Systemlage(
        kernel=f"{platform.system()} {platform.release()}",
        betriebszeit_s=_betriebszeit(),
        prozessor=prozessor(),
        speicher=speicher(),
        karten=karten(),
        ablagen=ablagen(orte),
    )
