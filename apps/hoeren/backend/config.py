"""Einstellungen aus der Umgebung - ein Ort, nirgends sonst `os.environ`.

Die Feldnamen entsprechen den Variablen mit dem Präfix `WORTLAUT_`,
`data_dir` also `WORTLAUT_DATA_DIR`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from wortlaut.einstellungen import AUSWERTUNG_MODELLE, Grundeinstellungen


class Einstellungen(Grundeinstellungen):
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

    # Der Zuschnitt: die Stille an den Rändern der eigenen Aufnahmen
    # wegschneiden (siehe `api/zuschnitt.py`). Das zweite Geheimnis dieser App
    # neben Verwaltung und Aufsicht - und wie der Trainerschlüssel in „lernen"
    # beantwortet es eine **andere** Frage als der Zugang.
    #
    # Der Zugang eines Sprechers sagt, wessen Aufnahmen das sind. Er ist an
    # jeden ausgegeben, der aufnimmt, und er gehört auf ein Telefon, das bei
    # einem Menschen liegt, der schlecht liest. Der Zuschnitt dagegen greift in
    # den Bestand: Er entscheidet für jede folgende Messung und jedes folgende
    # Training, welcher Ton gilt, und er wirft die vorhandenen Messwerte weg.
    # Das ist keine Handlung, die man versehentlich tut, und der Zugang allein
    # trägt sie nicht.
    #
    # Leer heißt **abgeschaltet**, nicht offen - wie bei Verwaltung, Aufsicht
    # und dem Trainerschlüssel und aus demselben Grund: Keine Installation
    # weiß, ob sie eine Entwicklungsinstallation ist. Die Oberfläche fragt den
    # Stand vorher ab und zeigt den Punkt dann gar nicht erst.
    editor_key: str = ""

    # Die Auswertung: welche Erkenner gegeneinander antreten (siehe
    # `services/auswertung.py`). Namen, die faster-whisper versteht, durch
    # Komma getrennt - später darf hier auch der Pfad eines eigenen Standes
    # aus „lernen" stehen. Die Reihenfolge ist zugleich die der Anzeige.
    #
    # Die Vorgabe steht in der Bibliothek, weil „lernen" dieselbe braucht
    # (`wortlaut/einstellungen.py`); warum die Leiter so aussieht, wie sie
    # aussieht, steht dort.
    #
    # Unten steht `small`, und darunter nichts mehr. Erst fiel `tiny`, weil es
    # bei abweichender Aussprache so wenig traf, dass seine Zeile nur noch
    # aussagte, dass ein zu kleines Modell zu klein ist; dann fiel `base`, weil
    # es zwar genug verstand, aber niemand mehr danach fragte. Trainiert wird
    # auf `small` und `medium`, diktiert wird mit einem eigenen Stand oder
    # `small` - eine Sprosse, unter der keine Entscheidung mehr hängt, kostet
    # Rechenzeit und Speicher für eine Spalte, die niemand liest.
    #
    # Oben steht `large-v3`, und das ist die teuerste Zeile der Liste: gut
    # anderthalb Gigabyte zusätzlich im Speicher und je Aufnahme ein
    # Vielfaches der Rechenzeit von `medium`. Sie gehört trotzdem dazu, weil
    # die Frage dieser Ansicht nicht „welches der kleinen Modelle?" ist,
    # sondern „reicht ein fertiges Modell für diese Stimme überhaupt?" - und
    # die beantwortet nur das größte. Bleibt auch `large-v3` deutlich hinter
    # der Vorlage, ist das das Argument für ein eigenes Feintuning; trifft es,
    # war der Weg nicht nötig.
    auswertung_modelle: str = AUSWERTUNG_MODELLE

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
