"""Was in der Konfiguration jeder App gleich lautet.

Jede der drei Apps liest ihre Einstellungen aus derselben Umgebung, mit
demselben Präfix und aus derselben `.env`. Was sie darin suchen, ist zum
größten Teil verschieden - eine Intake-Adresse gibt es nur in „schreiben", der
Trainerschlüssel nur in „lernen". Vier Angaben sind es aber nicht:

* **wo die Daten liegen** (`WORTLAUT_DATA_DIR`). Alle drei greifen in dasselbe
  Verzeichnis; zwei verschiedene Vorgaben dafür wären zwei Bestände.
* **worauf gerechnet wird** (`WORTLAUT_GERAET`, `WORTLAUT_RECHENART`). Das ist
  nicht nur Ordnung, sondern der ganze Sinn der Sache: „schreiben", die
  Auswertung in „hören" und die Bewertung eines Laufs schicken dieselben
  Modelle über dieselben Aufnahmen, und ihre Rechenzeiten sind nur
  vergleichbar, wenn sie auf demselben Rechenwerk entstanden sind. Was `auto`
  bedeutet und warum auf der Karte `int8_float16` gilt, steht in
  `rechenwerk.py`.

Die Begründung dazu stand wörtlich dreimal da, über drei Feldpaaren, die
dreimal dasselbe hießen. Jetzt steht sie einmal hier, und eine App, die eine
fünfte gemeinsame Angabe braucht, bekommt sie an derselben Stelle.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from . import rechenwerk

# Welche unveränderten Modelle gegeneinander antreten - die Vorgabe für
# `WORTLAUT_AUSWERTUNG_MODELLE`.
#
# Sie steht hier, weil zwei Apps sie lesen: „hören" misst damit (Reiter
# „Auswertung"), „lernen" stellt in der Modellübersicht die eigenen Stände
# daneben. Von dort stammen deren Zahlen - zwei getrennte Vorgaben wären eine
# Gelegenheit, sie auseinanderlaufen zu lassen, und das Ergebnis wäre eine
# Tabellenzeile ohne Messung. Dieselbe Variable gesetzt, gilt sie ohnehin für
# beide; auseinanderlaufen konnten nur die Vorgaben.
#
# Es ist eine Leiter mit drei Sprossen: `small` ist der Alltagsfall und die
# Untergrenze, `medium` zeigt, was mit mehr Rechenzeit noch zu holen wäre, und
# `large-v3` sagt, wo das Verfahren selbst endet. Wer wenig Maschine hat, kürzt
# die Liste - gerechnet wird nur, was darin steht.
#
# Unten stand einmal `tiny`, dann `base`. Beide sind gefallen, und beim zweiten
# Mal aus einem anderen Grund als beim ersten: `tiny` verstand zu wenig, um eine
# Untergrenze zu sein. `base` verstand genug - nur fragt es niemand mehr.
# Trainiert wird auf `small` und `medium`, diktiert wird mit einem eigenen Stand
# oder `small`, und eine Sprosse, unter der nichts mehr steht, ist keine Leiter,
# sondern eine Spalte. Sie kostete je Auswertungslauf Rechenzeit und Speicher
# für eine Zahl, die keine Entscheidung mehr trug.
AUSWERTUNG_MODELLE = "small,medium,large-v3"


class Grundeinstellungen(BaseSettings):
    """Die Felder, die jede App führt. Jede erbt und legt ihre eigenen dazu."""

    model_config = SettingsConfigDict(env_prefix="WORTLAUT_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")

    # ── Vorlesen ────────────────────────────────────────────────────────────
    #
    # Wo die Stimmen für das Vorlesen liegen (`wortlaut/vorlesen.py`). Neben
    # den Whisper-Modellen und aus demselben Grund: Es sind Modelldateien, sie
    # wiegen Dutzende Megabyte je Stück, sie gehören nicht ins Abbild und nicht
    # in die Sicherung - jederzeit neu zu laden, nie gesprochen.
    #
    # Die Vorgabe zeigt in den Modellspeicher, den die compose.yaml ohnehin
    # einhängt. Damit braucht diese Sache kein eigenes Volume.
    stimmen_dir: Path = Path("./modellcache/stimmen")
    # Welcher Motor spricht. Heute gibt es einen; der zweite kommt daneben,
    # nicht an seine Stelle.
    vorlesen_motor: str = "piper"

    geraet: str = rechenwerk.AUTO  # auto | cuda | cpu
    rechenart: str = rechenwerk.AUTO  # auto | int8 | int8_float16 | float16 | float32

    def rechenwerk(self) -> tuple[str, str]:
        """`(geraet, rechenart)` - aufgelöst, `auto` beantwortet."""
        return rechenwerk.waehle(self.geraet, self.rechenart)
