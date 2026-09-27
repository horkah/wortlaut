"""Worauf erkannt wird - eine Entscheidung für alle, die erkennen.

Drei Stellen schicken Sprache durch Whisper: „schreiben" beim Diktieren, die
Auswertung in „hören" und der Trainer beim Messen seiner Faltungen. Ihre
Rechenzeiten stehen in der Modelltafel nebeneinander und sind nur
vergleichbar, wenn sie auf demselben Rechenwerk entstehen - zwischen Karte und
Prozessor liegt das Zehn- bis Zwanzigfache. Alle drei fragen deshalb hier.

**`auto`** nimmt die Karte, wenn CTranslate2 eine sieht, sonst den Prozessor.

**`int8_float16` auf der Karte**, weil die Auswertung alle Grundmodelle
gleichzeitig hält, `large-v3` darunter - in `float16` gut sechs Gigabyte neben
Training und Sprachmodell auf einer Karte mit elf. Der Verlust fällt neben dem
Unterschied zweier Modellgrößen nicht ins Gewicht. Auf dem Prozessor `int8`.

**Der Rückfall auf den Prozessor** ist Absicht: Ist die Karte belegt, soll ein
Diktat langsam verstanden werden statt gar nicht (`whisper/local.py`).

**Jede Messung schreibt ihr Rechenwerk mit** (`marke()`, etwa
`cuda/int8_float16`) - daran hängt die Vergleichbarkeit, und ein Rückfall
bliebe sonst unbemerkt.
"""

from __future__ import annotations

from functools import lru_cache

# Die Wünsche, die in der Konfiguration stehen dürfen.
AUTO = "auto"
CUDA = "cuda"
CPU = "cpu"
GERAETE = (AUTO, CUDA, CPU)

# Was auf dem jeweiligen Gerät gerechnet wird, wenn niemand etwas anderes sagt.
# Beide Male die kleinste Darstellung, die das Modell nicht hörbar verschlechtert.
RECHENART_CUDA = "int8_float16"
RECHENART_CPU = "int8"


@lru_cache
def karte_da() -> bool:
    """Ob die Laufzeit eine Karte sieht. Einmal gefragt, danach gemerkt.

    Über CTranslate2, denn das rechnet; der Webprozess hat kein torch. Ohne
    CTranslate2 (Installation ohne `[asr]`) gibt es keine Karte.
    """
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001 - jede Ursache heißt hier dasselbe
        return False


def waehle(geraet: str = AUTO, rechenart: str = AUTO) -> tuple[str, str]:
    """Worauf gerechnet wird, als `(geraet, rechenart)`.

    `auto` beim Gerät heißt „die Karte, wenn eine da ist"; `auto` bei der
    Rechenart heißt „die Vorgabe für dieses Gerät". Ein ausdrücklicher Wunsch
    gilt unverändert: Wer `cuda` erzwingt, wo keine Karte ist, sieht den
    Fehler.
    """
    if geraet == AUTO:
        geraet = CUDA if karte_da() else CPU
    if rechenart == AUTO:
        rechenart = RECHENART_CUDA if geraet == CUDA else RECHENART_CPU
    return geraet, rechenart


def marke(geraet: str, rechenart: str) -> str:
    """Wie ein Rechenwerk neben einer Messung steht: `cuda/int8_float16`."""
    return f"{geraet}/{rechenart}"


def gilt() -> str:
    """Die Marke des Rechenwerks, das gerade gälte - für „ist das noch aktuell?"."""
    return marke(*waehle())
