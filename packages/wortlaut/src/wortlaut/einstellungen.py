"""Was in der Konfiguration jeder App gleich lautet.

Alle drei Apps lesen dieselbe Umgebung mit demselben Präfix. Gemeinsam sind:

* **wo die Daten liegen** (`WORTLAUT_DATA_DIR`) - zwei Vorgaben wären zwei
  Bestände;
* **wo die Stimmen liegen und wer spricht** (`WORTLAUT_STIMMEN_DIR`,
  `WORTLAUT_VORLESEN_MOTOR`);
* **worauf erkannt wird** (`WORTLAUT_GERAET`, `WORTLAUT_RECHENART`): „schreiben",
  die Auswertung in „hören" und die Bewertung eines Laufs messen dieselben
  Modelle, und ihre Rechenzeiten sind nur auf demselben Rechenwerk
  vergleichbar (`rechenwerk.py`).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from . import rechenwerk

# Welche unveränderten Modelle gegeneinander antreten - die Vorgabe für
# `WORTLAUT_AUSWERTUNG_MODELLE`. Hier, weil „hören" damit misst und „lernen"
# die eigenen Stände daneben stellt; zwei Vorgaben liefen auseinander.
#
# Eine Leiter: `small` ist der Alltagsfall und die Untergrenze, `medium`
# zeigt, was mit mehr Rechenzeit zu holen ist, `large-v3`, wo das Verfahren
# endet. Darunter versteht Whisper abweichende Aussprache zu schlecht.
AUSWERTUNG_MODELLE = "small,medium,large-v3"


class Grundeinstellungen(BaseSettings):
    """Die Felder, die jede App führt. Jede erbt und legt ihre eigenen dazu."""

    model_config = SettingsConfigDict(env_prefix="WORTLAUT_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")

    # Die Stimmen für das Vorlesen (`wortlaut/vorlesen.py`) - Modelldateien wie
    # die Whisper-Modelle, deshalb im selben Modellspeicher, nicht im Abbild
    # und nicht in der Sicherung.
    stimmen_dir: Path = Path("./modellcache/stimmen")
    vorlesen_motor: str = "piper"

    geraet: str = rechenwerk.AUTO  # auto | cuda | cpu
    rechenart: str = rechenwerk.AUTO  # auto | int8 | int8_float16 | float16 | float32

    def rechenwerk(self) -> tuple[str, str]:
        """`(geraet, rechenart)` - aufgelöst, `auto` beantwortet."""
        return rechenwerk.waehle(self.geraet, self.rechenart)
