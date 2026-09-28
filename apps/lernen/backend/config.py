"""Einstellungen aus der Umgebung - ein Ort, nirgends sonst `os.environ`.

Die Feldnamen entsprechen den Variablen mit dem Präfix `WORTLAUT_`,
`lernen_basismodell` also `WORTLAUT_LERNEN_BASISMODELL`.

Der Sprecher kommt aus dem Zugang (`deps.py`); hier steht, was der Maschine
gehört: worauf trainiert wird und mit welchen Grenzen.
"""

from __future__ import annotations

from functools import lru_cache

from wortlaut import kartenplan, laeufe
from wortlaut.einstellungen import AUSWERTUNG_MODELLE, Grundeinstellungen

# `lernen/<sprecher>` - diese App schreibt dort nichts, die Löschung nimmt ein
# vorhandenes Verzeichnis aber mit (`hoeren/services/loeschung.py`).
LERNEN = "lernen"


def sprecher_relpfad(sprecher_id: str) -> str:
    return f"{LERNEN}/{sprecher_id}"


class Einstellungen(Grundeinstellungen):
    # Die Vorgabe, worauf trainiert wird: die kleinste Stufe, die ganze Sätze
    # trifft, und dieselbe, gegen die „hören" misst.
    lernen_basismodell: str = "openai/whisper-small"
    # Was darüber hinaus zur Wahl steht; jedes muss in `auswertung_modelle`
    # stehen, sonst fehlt seine Baseline. Mit welcher Methode, entscheidet die
    # Karte (`methoden_fuer`).
    lernen_grundmodelle: str = (
        "openai/whisper-small,openai/whisper-medium,openai/whisper-large-v3"
    )
    # Dieselbe Liste wie in der Auswertung von „hören" - von dort stammen die
    # Zahlen der Modelltafel.
    auswertung_modelle: str = AUSWERTUNG_MODELLE
    # Worauf trainiert wird. Anders als beim Erkennen gibt es kein Ausweichen
    # auf den Prozessor - dort dauerte es Tage.
    lernen_geraet: str = "cuda"
    # Wie oft der Läufer nach Aufträgen sieht, in Sekunden.
    lernen_takt_s: int = 5
    # Was ein Lauf auf der Karte für die Erkenner des Webdienstes übrig lässt
    # - wer während eines Trainings diktiert, wartet nicht (`kartenplan.py`).
    lernen_reserve_mb: float = kartenplan.RESERVE_MB
    # Wo Ollama zu erreichen ist, damit der Trainer ihm vor jedem Lauf die
    # Karte abnimmt (`training/karte.entlade_ollama`). Leer: kein Ollama.
    ollama_url: str = "http://ollama:11434"

    def grundmodelle(self) -> list[str]:
        """Die wählbaren Grundmodelle, die Vorgabe zuerst.

        Die Vorgabe ist immer dabei, auch wenn sie in
        `WORTLAUT_LERNEN_GRUNDMODELLE` fehlt.
        """
        genannt = [teil.strip() for teil in self.lernen_grundmodelle.split(",") if teil.strip()]
        return [self.lernen_basismodell] + [
            modell for modell in genannt if modell != self.lernen_basismodell
        ]

    def methoden_fuer(self, basismodell: str) -> tuple[str, ...]:
        """Welche Methoden mit diesem Grundmodell gehen - auf der Karte, die der
        Trainer zuletzt gemeldet hat, sonst auf der, für die wortlaut gebaut ist."""
        return laeufe.methoden_fuer(basismodell, self.karte(), self.lernen_reserve_mb)

    def lora_fuer(self, basismodell: str) -> list[str]:
        """Welche LoRA-Zusätze (`ziele/rang`) mit diesem Grundmodell auf die Karte passen."""
        return laeufe.lora_wahlen(basismodell, self.karte(), self.lernen_reserve_mb)

    def karte(self) -> kartenplan.Karte:
        """Die Karte, die der Trainer zuletzt gemeldet hat, sonst die, für die wortlaut gebaut ist."""
        return kartenplan.lies_karte(laeufe.wurzel(self.data_dir)) or kartenplan.VORGABE


@lru_cache
def einstellungen() -> Einstellungen:
    """Einmal lesen, überall dieselbe Instanz."""
    return Einstellungen()
