"""Wo gerechnet wird - eine Entscheidung für alle, die rechnen.

Drei Stellen in diesem Projekt schicken Sprache durch ein Whisper-Modell:
„schreiben" beim Diktieren, die Auswertung in „hören", und der Trainer, wenn er
seinen fertigen Stand auf den Testaufnahmen misst. Sie liefen lange auf
verschiedenen Maschinen und mit verschiedenen Einstellungen - der Trainer auf
der Karte in `float16`, die beiden anderen auf dem Prozessor in `int8`.

Das hatte zwei Folgen, und beide waren Fehler:

* **Diktieren war langsam.** Eine Karte lag im selben Rechner und blieb
  ungenutzt, weil eine alte Regel sagte, GPU-Arbeit gehöre nicht in den
  Web-Prozess. Gemeint war damit das **Training** - Stunden, die keine Anfrage
  aussitzt. Eine Erkennung dauert Sekunden; sie gehört dorthin, wo die Anfrage
  ist, und nimmt die Karte, wenn eine da ist.
* **Die Rechenzeiten waren nicht vergleichbar.** In der Modellübersicht stand
  ein Grundmodell mit vier Sekunden neben einem trainierten Stand derselben
  Größe mit einer Viertelsekunde. Beide Zahlen stimmten; sie stammten von
  verschiedenen Rechnern. Nebeneinander waren sie eine Falle.

Beides beantwortet dieses Modul: Es sagt genau einmal, worauf gerechnet wird,
und alle drei fragen hier.

**Was `auto` bedeutet.** Ist eine Karte da, wird sie genommen; sonst der
Prozessor. Geprüft wird das über CTranslate2 selbst und nicht über eine
Umgebungsvariable - was zählt, ist nicht, ob jemand eine Karte gemeint hat,
sondern ob die Laufzeit eine sieht.

**Warum `int8_float16` auf der Karte und nicht `float16`.** Speicher. Die
Auswertung hält vier Modelle gleichzeitig im Speicher (sie rechnet
aufnahmeweise, nicht modellweise), `large-v3` darunter; in `float16` sind das
gut sechs Gigabyte. Daneben will ein volles Training acht und das Sprachmodell
für die Textquelle weitere sechs - auf einer einzelnen Karte mit elf geht das
nicht auf. `int8_float16` halbiert den Bedarf bei einem Verlust, der neben dem
Unterschied zwischen zwei Modellgrößen nicht ins Gewicht fällt. Auf dem
Prozessor ist `int8` die entsprechende Wahl.

**Warum der Rückfall auf den Prozessor kein Sonderfall ist.** Die Karte kann
belegt sein - ein Training läuft, das Sprachmodell hält seinen Speicher. Ein
Diktat darf daran nicht scheitern: Lieber langsam verstanden als gar nicht.
Deshalb versucht `LokalerTranskriptor` die Karte und weicht aus, wenn sie ihn
abweist (siehe `whisper/local.py`).

**Warum jede Messung ihr Rechenwerk mitschreibt.** Weil genau daran die
Vergleichbarkeit hängt und weil ein Rückfall auf den Prozessor unbemerkt
bliebe. `marke()` liefert die Zeichenkette, die neben jeder Messung steht -
`cuda/int8_float16` oder `cpu/int8`. Wer zwei Zahlen vergleicht, kann damit
prüfen, ob er darf.
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

    Über CTranslate2 und nicht über `torch`: Der Web-Prozess hat kein torch
    (das wiegt Gigabyte und wird nur zum Trainieren gebraucht), und es wäre
    ohnehin die falsche Auskunft - rechnen wird CTranslate2.

    Fehlt CTranslate2 ganz - eine Installation ohne `[asr]` -, gibt es hier
    keine Karte. Wer nicht erkennt, braucht auch keine.
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
    gilt unverändert - auch ein unsinniger: Wer `cuda` erzwingt, wo keine Karte
    ist, soll den Fehler sehen und nicht stillschweigend auf dem Prozessor
    landen und sich über die Rechenzeit wundern.
    """
    if geraet == AUTO:
        geraet = CUDA if karte_da() else CPU
    if rechenart == AUTO:
        rechenart = RECHENART_CUDA if geraet == CUDA else RECHENART_CPU
    return geraet, rechenart


def marke(geraet: str, rechenart: str) -> str:
    """Wie ein Rechenwerk neben einer Messung steht: `cuda/int8_float16`.

    Eine Zeichenkette und keine zwei Spalten: Sie wird nur verglichen und nie
    zerlegt, und eine Messung stammt immer aus genau einer Kombination.
    """
    return f"{geraet}/{rechenart}"


def gilt() -> str:
    """Die Marke des Rechenwerks, das gerade gälte - für „ist das noch aktuell?"."""
    return marke(*waehle())
