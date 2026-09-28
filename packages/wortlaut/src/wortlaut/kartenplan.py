"""Was eine Karte kann - und wie ein Training darauf zugeschnitten wird.

Ein Lauf soll auf einer geteilten 11-GB-Karte laufen und auf einer mit 80 GB
schneller, ohne dass jemand ein Rezept anfasst. Das Rezept sagt, **was**
gelernt wird (Lernrate, wirksamer Stapel, Durchgänge); wie das auf die Karte
passt, entscheidet dieser Plan:

* **Genauigkeit.** `bf16` ab Ampere (Rechenfähigkeit 8.0), darunter `fp16` -
  Turing kann bf16 nicht in Hardware. Ohne Karte `fp32`.
* **Halbe Grundgewichte bei LoRA.** Das eingefrorene Grundmodell liegt in der
  halben Genauigkeit, der Zusatz in `float32` - bei `large-v3` drei Gigabyte
  weniger, am Ergebnis nichts: Gelernt wird nur der Zusatz.
* **Stapel und Gradientensparen.** Der wirksame Stapel des Rezepts bleibt;
  wie viele Proben je Schritt auf der Karte liegen, probiert der Trainer aus
  (`kandidaten`, `passt`), den Rest holt die Akkumulation nach. Erst ohne
  Gradientensparen - es kostet ein Drittel Rechenzeit -, dann mit, dann mit
  halbem Stapel.
* **Welche Methoden überhaupt gehen** (`methoden`): volles Feintuning braucht
  Gewichte, Gradienten und Adam in `float32`, sechzehn Byte je Gewicht. Auf
  11 GB passt das für `small`, auf 40 GB für `large-v3`.
* **Welcher LoRA-Zusatz geht** (`lora_passt`): Der Zusatz kostet dieselben
  sechzehn Byte je Gewicht, und wie viele es sind, hängt an Rang und Zielen
  (`lora_parameter`). Auf der 2080 Ti passt bei `large-v3` jede Wahl - alle
  Projektionen mit Rang 64 brauchen im Probeschritt 5,3 GB -, auf kleineren
  Karten nicht mehr.

**Gemessen, nicht angenommen.** Der Trainer beschreibt seine Karte
(`Karte`) und legt sie neben die Läufe (`karte.json`), `lernen` liest sie und
bietet nur an, was passt. Solange der Trainer nichts gemeldet hat, gilt die
Karte, für die wortlaut gebaut ist (`VORGABE`).

Gerechnet wird auf **einer** Karte je Lauf; sind mehrere da, die erste.

Ohne torch - geprüft wird es ohne Karte.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

# Neben den Läufen, geschrieben vom Trainer (`training/finetune.py`).
KARTE = "karte.json"

# Ab dieser Rechenfähigkeit rechnet die Karte bf16 in Hardware (Ampere).
BF16_AB = (8, 0)

# Gewichte in Millionen, aus den Modellkarten von OpenAI.
PARAMETER_MIO = {
    "tiny": 39,
    "base": 74,
    "small": 244,
    "medium": 769,
    "large": 1550,
    "large-v2": 1550,
    "large-v3": 1550,
    "large-v3-turbo": 809,
}
# Ein unbekanntes Modell wird behandelt wie das größte bekannte.
UNBEKANNT_MIO = max(PARAMETER_MIO.values())

# Breite und Schichten in Encoder und Decoder - für die Größe eines LoRA-Zusatzes.
ABMESSUNGEN = {
    "tiny": (384, 4, 4),
    "base": (512, 6, 6),
    "small": (768, 12, 12),
    "medium": (1024, 24, 24),
    "large": (1280, 32, 32),
    "large-v2": (1280, 32, 32),
    "large-v3": (1280, 32, 32),
    "large-v3-turbo": (1280, 32, 4),
}
UNBEKANNT_ABMESSUNGEN = max(ABMESSUNGEN.values())
# Die Projektionen der Aufmerksamkeit; `fc1` und `fc2` sind die des Feedforward.
AUFMERKSAMKEIT = ("q_proj", "k_proj", "v_proj", "out_proj")

# Byte je Gewicht, das auf der Karte liegt.
BYTE_VOLL = 16  # float32: Gewicht, Gradient, zwei Adam-Momente
BYTE_HALB = 2  # das eingefrorene Grundmodell bei LoRA
BYTE_GANZ = 4  # dasselbe in float32, ohne Karte oder ohne halbe Genauigkeit
# Was außer den Gewichten mindestens anfällt - CUDA-Kontext, Aktivierungen
# eines Stapels mit Gradientensparen, Zwischenspeicher. Grob, deshalb nur für
# die Frage, ob eine Methode überhaupt in Frage kommt; den Stapel misst der
# Trainer (`passt`).
GRUNDLAST_MB = 1500.0


@dataclass(frozen=True)
class Karte:
    """Eine Grafikkarte, wie der Trainer sie sieht."""

    name: str
    speicher_mb: float
    rechenfaehigkeit: tuple[int, int]
    # Wie viele Karten sichtbar sind - gerechnet wird auf einer.
    anzahl: int = 1

    @property
    def bf16(self) -> bool:
        return tuple(self.rechenfaehigkeit) >= BF16_AB

    def als_dict(self) -> dict:
        return {**asdict(self), "rechenfaehigkeit": list(self.rechenfaehigkeit)}


# Was ein Lauf den Erkennern des Webdienstes übrig lässt, wenn nichts anderes
# eingestellt ist (`WORTLAUT_LERNEN_RESERVE_MB`): genug für `medium` beim Diktieren.
RESERVE_MB = 2000.0

# Die Karte, für die wortlaut gebaut ist - bis der Trainer seine meldet.
VORGABE = Karte(name="NVIDIA GeForce RTX 2080 Ti", speicher_mb=11539.0, rechenfaehigkeit=(7, 5))


def schreibe_karte(wurzel: Path, karte: Karte) -> None:
    """`wurzel` ist das Verzeichnis der Läufe (`laeufe.wurzel`)."""
    wurzel.mkdir(parents=True, exist_ok=True)
    zwischen = wurzel / f".{KARTE}.neu"
    zwischen.write_text(json.dumps(karte.als_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    zwischen.replace(wurzel / KARTE)


def lies_karte(wurzel: Path) -> Karte | None:
    """Die zuletzt gemeldete Karte - `None`, solange der Trainer nichts gemeldet hat."""
    try:
        roh = json.loads((wurzel / KARTE).read_text(encoding="utf-8"))
        return Karte(
            name=str(roh["name"]),
            speicher_mb=float(roh["speicher_mb"]),
            rechenfaehigkeit=(int(roh["rechenfaehigkeit"][0]), int(roh["rechenfaehigkeit"][1])),
            anzahl=int(roh.get("anzahl", 1)),
        )
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def parameter(kurzname: str) -> float:
    """Die Zahl der Gewichte eines Grundmodells (`small`, `large-v3`, …)."""
    return PARAMETER_MIO.get(kurzname, UNBEKANNT_MIO) * 1e6


def bedarf_mb(kurzname: str, methode: str, halbe_grundgewichte: bool = True) -> float:
    """Wie viel Karte ein Training mindestens braucht - mit dem kleinsten Stapel.

    `methode` ist `full` oder `lora` (`laeufe.METHODEN`).
    """
    gewichte = parameter(kurzname)
    if methode == "full":
        je_gewicht = BYTE_VOLL
    else:
        je_gewicht = BYTE_HALB if halbe_grundgewichte else BYTE_GANZ
    return gewichte * je_gewicht / 1e6 + GRUNDLAST_MB


def lora_parameter(
    kurzname: str, module: tuple[str, ...], teile: tuple[str, ...], rang: int
) -> int:
    """Wie viele Gewichte ein LoRA-Zusatz hat: je Projektion Rang mal (Eingang + Ausgang).

    Im Decoder gibt es jede Projektion der Aufmerksamkeit zweimal - Selbst- und
    Kreuzaufmerksamkeit. Der Feedforward ist viermal so breit wie das Modell.
    """
    breite, encoder, decoder = ABMESSUNGEN.get(kurzname, UNBEKANNT_ABMESSUNGEN)
    je_modul = {name: 2 * breite for name in AUFMERKSAMKEIT} | {
        "fc1": 5 * breite,
        "fc2": 5 * breite,
    }
    gesamt = 0
    for teil, schichten in (("encoder", encoder), ("decoder", decoder)):
        if teil not in teile:
            continue
        for name in module:
            anzahl = 2 if teil == "decoder" and name in AUFMERKSAMKEIT else 1
            gesamt += schichten * anzahl * je_modul.get(name, 2 * breite) * rang
    return gesamt


def lora_passt(
    kurzname: str,
    module: tuple[str, ...],
    teile: tuple[str, ...],
    rang: int,
    karte: Karte | None,
    reserve_mb: float,
) -> bool:
    """Ob LoRA mit diesem Zusatz auf diese Karte passt - Grundmodell halb, Zusatz voll.

    Ohne Karte ja, wie bei `methoden`.
    """
    if karte is None:
        return True
    zusatz = lora_parameter(kurzname, module, teile, rang) * BYTE_VOLL / 1e6
    return bedarf_mb(kurzname, "lora") + zusatz <= nutzbar_mb(karte, reserve_mb)


def nutzbar_mb(karte: Karte, reserve_mb: float) -> float:
    """Was ein Lauf von dieser Karte höchstens nehmen darf.

    `reserve_mb` bleibt für die Erkenner des Webdienstes: Wer diktiert,
    während trainiert wird, soll nicht auf den Trainer warten.
    """
    return karte.speicher_mb - reserve_mb


def methoden(kurzname: str, karte: Karte | None, reserve_mb: float) -> tuple[str, ...]:
    """Die Methoden, die mit diesem Grundmodell auf diese Karte passen - LoRA zuletzt.

    Ohne Karte (auf dem Prozessor) beide: Dort begrenzt der Hauptspeicher, und
    das zeigt erst der Versuch.
    """
    if karte is None:
        return ("full", "lora")
    return tuple(
        methode
        for methode in ("full", "lora")
        if bedarf_mb(kurzname, methode) <= nutzbar_mb(karte, reserve_mb)
    )


@dataclass(frozen=True)
class Plan:
    """Wie ein Lauf auf dieser Karte rechnet - steht im Protokoll und im Manifest."""

    # `bf16`, `fp16` oder `fp32`.
    genauigkeit: str
    # LoRA: das Grundmodell in `genauigkeit`, der Zusatz in `float32`.
    halbe_grundgewichte: bool
    # Proben je Schritt auf der Karte, und wie oft gesammelt wird, bis der
    # wirksame Stapel des Rezepts erreicht ist.
    stapel: int
    akkumulation: int
    gradientensparsam: bool
    # Immer `sdpa`: die Aufmerksamkeit von torch selbst, auf neuen Karten mit
    # den Flash-Kernen, auf alten ohne - kein zusätzliches Paket.
    aufmerksamkeit: str = "sdpa"

    @property
    def wirksam(self) -> int:
        return self.stapel * self.akkumulation

    def als_dict(self) -> dict:
        return {**asdict(self), "wirksamer_stapel": self.wirksam}

    def beschreibung(self) -> str:
        return (
            f"{self.genauigkeit}, {self.aufmerksamkeit}, Stapel {self.stapel}"
            f" × {self.akkumulation} = {self.wirksam}"
            + (", Gradientensparen" if self.gradientensparsam else "")
            + (", Grundmodell halb" if self.halbe_grundgewichte else "")
        )


def genauigkeit(karte: Karte | None) -> str:
    if karte is None:
        return "fp32"
    return "bf16" if karte.bf16 else "fp16"


def kandidaten(wirksam: int) -> list[tuple[int, bool]]:
    """(Stapel, Gradientensparen) in der Reihenfolge, in der probiert wird.

    Erst der ganze Stapel ohne Sparen - am schnellsten -, dann mit Sparen,
    dann mit jedem kleineren Teiler des wirksamen Stapels. Nur Teiler: Die
    Akkumulation holt sie genau auf den wirksamen Stapel zurück.
    """
    wirksam = max(1, int(wirksam))
    teiler = [stapel for stapel in range(wirksam, 0, -1) if wirksam % stapel == 0]
    return [(wirksam, False), *((stapel, True) for stapel in teiler)]


def plan(
    karte: Karte | None, methode: str, wirksam: int, stapel: int, gradientensparsam: bool
) -> Plan:
    """Der Plan für einen gewählten Kandidaten."""
    stapel = max(1, int(stapel))
    return Plan(
        genauigkeit=genauigkeit(karte),
        halbe_grundgewichte=methode == "lora" and karte is not None,
        stapel=stapel,
        akkumulation=max(1, int(wirksam) // stapel),
        gradientensparsam=gradientensparsam,
    )


def optimierer_mb(trainierbar: int) -> float:
    """Was nach dem Probeschritt noch kommt: die Momente des Optimierers.

    Adam hält zwei `float32`-Werte je trainierbarem Gewicht; der Probeschritt
    rechnet einen Gradienten, aber keinen Optimiererschritt.
    """
    return trainierbar * 8 / 1e6


def passt(
    spitze_mb: float, zusatz: float, gesamt_mb: float, fremd_mb: float, reserve_mb: float
) -> bool:
    """Ob ein Kandidat passt: seine Spitze im Probeschritt, der Optimierer dazu,
    neben dem, was andere Prozesse halten, und der Reserve für die Erkenner."""
    return spitze_mb + zusatz <= gesamt_mb - fremd_mb - reserve_mb
