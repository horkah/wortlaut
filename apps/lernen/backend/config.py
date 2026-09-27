"""Einstellungen aus der Umgebung - ein Ort, nirgends sonst `os.environ`.

Die Feldnamen entsprechen den Variablen mit dem Präfix `WORTLAUT_`,
`lernen_basismodell` also `WORTLAUT_LERNEN_BASISMODELL`.

Der Sprecher kommt aus dem Zugang (`deps.py`); hier steht, was der Maschine
gehört: worauf trainiert wird und mit welchen Grenzen.
"""

from __future__ import annotations

from functools import lru_cache

from wortlaut.einstellungen import AUSWERTUNG_MODELLE, Grundeinstellungen

# `lernen/<sprecher>` - diese App schreibt dort nichts, die Löschung nimmt ein
# vorhandenes Verzeichnis aber mit (`hoeren/services/loeschung.py`).
LERNEN = "lernen"


def sprecher_relpfad(sprecher_id: str) -> str:
    return f"{LERNEN}/{sprecher_id}"


class Einstellungen(Grundeinstellungen):
    # Wer ein Training anstoßen darf (`X-Trainer-Key` vor Beauftragen und
    # Neustart). Der Sprecherzugang sagt, wessen Modell entsteht, nicht, wer
    # die Karte stundenlang belegen darf. Leer heißt abgeschaltet.
    trainer_key: str = ""

    # Die Vorgabe, worauf trainiert wird: die kleinste Stufe, die ganze Sätze
    # trifft, und dieselbe, gegen die „hören" misst.
    lernen_basismodell: str = "openai/whisper-small"
    # Was darüber hinaus zur Wahl steht; jedes muss in `auswertung_modelle`
    # stehen, sonst fehlt seine Baseline. `medium` und größer nur mit LoRA.
    lernen_grundmodelle: str = "openai/whisper-small,openai/whisper-medium"
    # Dieselbe Liste wie in der Auswertung von „hören" - von dort stammen die
    # Zahlen der Modelltafel.
    auswertung_modelle: str = AUSWERTUNG_MODELLE
    # Worauf trainiert wird. Anders als beim Erkennen gibt es kein Ausweichen
    # auf den Prozessor - dort dauerte es Tage.
    lernen_geraet: str = "cuda"
    # Wie oft der Läufer nach Aufträgen sieht, in Sekunden.
    lernen_takt_s: int = 5


    def grundmodelle(self) -> list[str]:
        """Die wählbaren Grundmodelle, die Vorgabe zuerst.

        Die Vorgabe ist immer dabei, auch wenn sie in
        `WORTLAUT_LERNEN_GRUNDMODELLE` fehlt.
        """
        genannt = [teil.strip() for teil in self.lernen_grundmodelle.split(",") if teil.strip()]
        return [self.lernen_basismodell] + [
            modell for modell in genannt if modell != self.lernen_basismodell
        ]


@lru_cache
def einstellungen() -> Einstellungen:
    """Einmal lesen, überall dieselbe Instanz."""
    return Einstellungen()
