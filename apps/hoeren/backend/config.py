"""Einstellungen aus der Umgebung - ein Ort, nirgends sonst `os.environ`.

Die Feldnamen entsprechen den Variablen mit dem Präfix `WORTLAUT_`,
`data_dir` also `WORTLAUT_DATA_DIR`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from wortlaut import rechenwerk


class Einstellungen(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORTLAUT_", env_file=".env", extra="ignore")

    # gemeinsam
    data_dir: Path = Path("./data")
    storage: str = "local"

    # Textquelle „LLM". Leer heißt: abgeschaltet, es bleibt der Textupload.
    llm_provider: str = ""
    llm_api_key: str = ""
    # Zum Vorgabeanbieter passend: das lokale Ollama-Modell aus der
    # .env.example. Bei anbieter="anthropic" gehört hier eine Claude-Kennung
    # hin, etwa claude-opus-4-8.
    llm_model: str = "gemma2:9b"
    # Nur für OpenAI-kompatible Anbieter (anbieter="openai"): wohin die Anfrage
    # geht. Lokal etwa http://ollama:11434/v1, sonst die URL von Groq, Gemini,
    # Mistral … Bei anbieter="anthropic" ohne Bedeutung.
    llm_base_url: str = ""

    # Die Verwaltung: legt Sprecherprofile an, gibt Zugänge aus und zieht sie
    # zurück. Leer heißt **abgeschaltet**, nicht „offen" - auch nicht für die
    # Entwicklung: Keine Installation weiß, ob sie eine ist.
    auth_token: str = ""

    # Die Aufsicht: sieht jeden Korpus, sichert ihn und löscht daraus. Leer
    # heißt auch hier abgeschaltet: Ein Zugang, der löschen darf, darf nicht
    # versehentlich offenstehen.
    admin_token: str = ""

    # Die Auswertung: welche Erkenner gegeneinander antreten (siehe
    # `services/auswertung.py`). Namen, die faster-whisper versteht, durch
    # Komma getrennt - später darf hier auch der Pfad eines eigenen Standes
    # aus „lernen" stehen. Die Reihenfolge ist zugleich die der Anzeige.
    #
    # Die Vorgabe ist eine Leiter mit vier Sprossen: `base` ist die
    # Untergrenze, `small` der Alltagsfall, `medium` zeigt, was mit mehr
    # Rechenzeit noch zu holen wäre, und `large-v3` sagt, wo das Verfahren
    # selbst endet. Wer wenig Maschine hat, kürzt die Liste - gerechnet wird
    # nur, was darin steht.
    #
    # Unten steht `base` und nicht mehr `tiny`. Eine Untergrenze soll zeigen,
    # wo das Verstehen abzubrechen beginnt, und dafür muss sie selbst noch
    # etwas verstehen: `tiny` traf bei abweichender Aussprache so wenig, dass
    # seine Zeile nur noch aussagte, dass ein zu kleines Modell zu klein ist.
    # `base` kostet kaum mehr Rechenzeit und liefert eine Reihe, gegen die
    # sich `small` lesen lässt.
    #
    # Oben steht `large-v3`, und das ist die teuerste Zeile der Liste: gut
    # anderthalb Gigabyte zusätzlich im Speicher und je Aufnahme ein
    # Vielfaches der Rechenzeit von `medium`. Sie gehört trotzdem dazu, weil
    # die Frage dieser Ansicht nicht „welches der kleinen Modelle?" ist,
    # sondern „reicht ein fertiges Modell für diese Stimme überhaupt?" - und
    # die beantwortet nur das größte. Bleibt auch `large-v3` deutlich hinter
    # der Vorlage, ist das das Argument für ein eigenes Feintuning; trifft es,
    # war der Weg nicht nötig.
    auswertung_modelle: str = "base,small,medium,large-v3"

    # Worauf gerechnet wird - dieselbe Einstellung in allen drei Apps und beim
    # Trainer, und das ist der ganze Sinn: „schreiben", die Auswertung in
    # „hören" und die Bewertung eines Laufs schicken dieselben Modelle über
    # dieselben Aufnahmen, und ihre Rechenzeiten sind nur vergleichbar, wenn
    # sie auf demselben Rechenwerk entstanden sind. Was `auto` bedeutet und
    # warum auf der Karte `int8_float16` gilt, steht in
    # `wortlaut/rechenwerk.py`.
    geraet: str = rechenwerk.AUTO  # auto | cuda | cpu
    rechenart: str = rechenwerk.AUTO  # auto | int8 | int8_float16 | float16 | float32

    def rechenwerk(self) -> tuple[str, str]:
        """`(geraet, rechenart)` - aufgelöst, `auto` beantwortet."""
        return rechenwerk.waehle(self.geraet, self.rechenart)

    @model_validator(mode="after")
    def _tokens_muessen_sich_unterscheiden(self) -> Einstellungen:
        """Ein Token, zwei Rollen wäre eine stille Rechteausweitung.

        Wer beide Werte gleich setzt - etwa beim Kopieren der `.env` -, macht
        jeden Verwalter unbemerkt zur Aufsicht: Der Server prüft die Aufsicht
        zuerst und käme gar nicht mehr zur Verwaltung. Das fällt niemandem auf,
        weil nichts fehlschlägt; es geht bloß plötzlich mehr. Also lieber
        gleich beim Start abbrechen als später rätseln.
        """
        if self.admin_token and self.admin_token == self.auth_token:
            raise ValueError(
                "WORTLAUT_ADMIN_TOKEN und WORTLAUT_AUTH_TOKEN müssen verschieden sein: "
                "Sonst wäre jeder Verwalter zugleich die Aufsicht."
            )
        return self

    @property
    def migrationsverzeichnis(self) -> Path:
        return Path(__file__).parent / "db" / "migrations"


@lru_cache
def einstellungen() -> Einstellungen:
    """Einmal lesen, überall dieselbe Instanz."""
    return Einstellungen()
