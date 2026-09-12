# Konfiguration

Alles über Umgebungsvariablen, eingelesen in der `config.py` der jeweiligen App,
nirgends `os.environ` im Fachcode. Die Bibliothek `wortlaut` liest gar keine
Umgebung: Pfade und Schlüssel werden ihr übergeben.

Vollständig kommentiert steht alles in [`.env.example`](../.env.example) - das
ist die Vorlage, die kopiert wird. Diese Seite ist die Übersicht dazu.

```bash
cp .env.example .env
```

---

## Gemeinsam

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `WORTLAUT_DATA_DIR` | `./data` | wo alles liegt: Korpora, Diktate, Schnappschüsse, Modelle |
| `WORTLAUT_STORAGE` | `local` | Blob-Ablage; `s3` ist vorbereitet, aber nicht in Betrieb |
| `WORTLAUT_MODELLCACHE` | `./data/modellcache` | wohin die Grundmodelle von Hugging Face geladen werden (Whisper in allen Größen) |
| `WORTLAUT_OLLAMACACHE` | `./data/ollama` | wohin Ollama seine Sprachmodelle legt |
| `WORTLAUT_TRAININGSABLAGE` | `./data/training` | wo `modelle/` und `snapshots/` auf dem Wirt liegen - im Container bleiben sie unter `WORTLAUT_DATA_DIR` |

Im Container ist `WORTLAUT_DATA_DIR` immer `/srv/wortlaut/data`; wo das auf dem
Wirt liegt, entscheidet das Volume in der `compose.yaml`.

Die drei letzten Zeilen sind die Ausnahme dieser Seite: Sie liest **Compose**
und nicht die `config.py` einer App. In keiner Einstellungsklasse kommen sie
vor - im Container heißen diese Pfade immer `/srv/wortlaut/modellcache`,
`/root/.ollama`, `…/data/modelle` und `…/data/snapshots`, und die Variablen
sagen nur, wo das auf dem Wirt liegt. Sie
stehen trotzdem hier, weil sie in derselben `.env` stehen. Was darunter liegt,
ist jederzeit neu zu laden und gehört deshalb nicht ins Volume der Daten
(siehe [Betrieb](betrieb.md#betrieb-mit-compose)).

---

## hören

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `WORTLAUT_AUTH_TOKEN` | leer | **Verwaltung**: Profile anlegen, Zugänge ausgeben. Leer heißt abgeschaltet, auch in der Entwicklung. Öffnet selbst keinen Korpus. |
| `WORTLAUT_ADMIN_TOKEN` | leer | **Aufsicht**: in jeden Korpus sehen, umbenennen, sichern, löschen. Leer heißt abgeschaltet, nicht offen. |
| `WORTLAUT_LLM_PROVIDER` | leer | Textquelle „LLM": leer = aus, `openai` = jede OpenAI-kompatible Schnittstelle (lokales Ollama, Groq, Gemini, Mistral), `anthropic` = Claude |
| `WORTLAUT_LLM_API_KEY` | leer | bei lokalem Ollama leer |
| `WORTLAUT_LLM_MODEL` | `gemma2:9b` | für ein paar Vorlesesätze genügt ein kleines Modell |
| `WORTLAUT_LLM_BASE_URL` | leer | nur bei `openai`, z. B. `http://ollama:11434/v1` |
| `WORTLAUT_AUSWERTUNG_MODELLE` | `base,small,medium,large-v3` | welche Grundmodelle gegeneinander antreten - dieselbe Liste, gegen die in `lernen` die eigenen Stände antreten |

Die beiden Token sind kein Zugang zu den Aufnahmen: Dorthin führt allein der
persönliche Zugang eines Sprechers (siehe [hören](hoeren.md)).

Zur Auswertungsliste: `medium` braucht auf einer CPU je Aufnahme etwa das Drei-
bis Zehnfache ihrer Dauer, `large-v3` noch einmal ein Mehrfaches davon und gut
anderthalb Gigabyte Speicher obendrauf. Sie steht trotzdem in der Vorgabe, denn
nur das größte fertige Modell beantwortet, ob überhaupt eines für diese Stimme
reicht. Wer wenig Maschine hat, kürzt auf `base,small`.

---

## Rechenwerk - worauf erkannt wird

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `WORTLAUT_GERAET` | `auto` | `auto` nimmt die Karte, wenn CTranslate2 eine sieht; `cuda` verlangt sie; `cpu` bleibt beim Prozessor |
| `WORTLAUT_RECHENART` | `auto` | `auto` heißt `int8_float16` auf der Karte, `int8` auf dem Prozessor; sonst ein fester Wert |

**Eine Einstellung und nicht drei, und das ist der Punkt.** Sie gilt für
`schreiben` beim Diktieren, für die Auswertung in `hören` und für den Trainer,
wenn er seinen fertigen Stand auf den Testaufnahmen misst. Diese drei schicken
dieselben Modelle über dieselben Aufnahmen, und ihre Rechenzeiten stehen in der
Modellübersicht von `lernen` nebeneinander - vergleichbar sind sie nur, wenn
sie von derselben Maschine stammen. Zwischen Karte und Prozessor liegt beim
Erkennen das Zehn- bis Zwanzigfache.

Sie standen einmal getrennt, und genau das ging schief: Die Auswertung maß auf
dem Prozessor, der Trainer auf der Karte, und in der Tabelle standen vier
Sekunden neben einer Viertelsekunde für dasselbe Modell.

**Warum `int8_float16` und nicht `float16`.** Speicher. Die Auswertung hält
alle vier Modelle gleichzeitig im Speicher (sie rechnet aufnahmeweise, nicht
modellweise), `large-v3` darunter; in `float16` sind das gut sechs Gigabyte.
Daneben will ein volles Training acht und das Sprachmodell für die Textquelle
weitere sechs - auf einer einzelnen Karte mit elf geht das nicht auf.

**Was passiert, wenn die Karte voll ist.** Die Erkennung weicht auf den
Prozessor aus, statt das Diktat scheitern zu lassen, und schreibt das neben
jede Messung (`erkennungen.rechenwerk`). Die Modellübersicht sieht daran, dass
sie die Rechenzeiten nicht vergleichen darf, und sagt es. Wer `cuda`
ausdrücklich verlangt hat, bekommt dagegen den Fehler zu sehen - sonst sucht er
die verlorene Rechenzeit an der falschen Stelle.

Einzelheiten: `packages/wortlaut/src/wortlaut/rechenwerk.py`.

---

## Das Sprachmodell für die Textquelle

`ollama` läuft als eigener Dienst auf derselben Karte (`compose.yaml`) und legt
sein Modell vollständig darauf, solange der Speicher reicht.

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `OLLAMA_KEEP_ALIVE` | `15m` | wie lange das Modell nach einer Anfrage auf der Karte liegen bleibt |

Ollamas eigene Vorgabe sind fünf Minuten; wer danach eine zweite Textquelle
anlegt, wartet erneut die knapp sechs Sekunden, die das Laden von sechs
Gigabyte dauert. Länger ist nicht umsonst: Solange es liegt, belegt es diese
sechs Gigabyte auf derselben Karte, auf der ein Training acht will. Eine
Viertelstunde ist der Ausgleich.

---

## lernen

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `WORTLAUT_LERNEN_BASISMODELL` | `openai/whisper-small` | worauf trainiert wird - fest und in der Oberfläche nicht wählbar |
| `WORTLAUT_AUSWERTUNG_MODELLE` | `base,small,medium,large-v3` | welche Grundmodelle in der Modelltabelle gegen die eigenen Stände antreten; dieselbe Variable wie oben, und das ist Absicht |
| `WORTLAUT_LERNEN_GERAET` | `cuda` | worauf **trainiert** wird; auf einem Prozessor dauert ein Feintuning Tage statt Stunden. Etwas anderes als `WORTLAUT_GERAET` oben: Dort geht es ums Erkennen, hier ums Lernen, und nur das Erkennen darf ausweichen |
| `WORTLAUT_LERNEN_TAKT_S` | `5` | wie oft der Läufer nach neuen Aufträgen sieht |

`WORTLAUT_AUSWERTUNG_MODELLE` steht bewusst nur einmal in der `.env`: Von der
Auswertung in `hören` stammen die Zahlen, die in `lernen` in der Tabelle
landen. Zwei getrennte Listen wären zwei Gelegenheiten, sie auseinanderlaufen
zu lassen - und eine Tabellenzeile ohne Messung.

---

## schreiben

Wessen Stimme, steht hier **nicht**: Der Sprecher kommt aus dem Zugang, den der
Browser vorlegt - derselbe wie bei `hören`.

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `WORTLAUT_MODELL_REF` | leer | ein fester Stand für alle, zum Erproben. Leer ist der Betriebsfall: Dann gilt die Freigabe je Sprecher. |
| `WORTLAUT_ASR_MODELL` | `small` | das unveränderte Grundmodell, solange nichts freigegeben ist |
| `WORTLAUT_SPRACHE` | `de` | Sprache der Diktate, an Whisper gereicht |
| `WORTLAUT_ASR` | `local` | `local` = faster-whisper im eigenen Prozess, `remote` = fremder Endpunkt |
| `WORTLAUT_ASR_ENDPOINT` | leer | nur bei `remote` |
| `WORTLAUT_ASR_API_KEY` | leer | nur bei `remote` |
| `WORTLAUT_INTAKE_URL` | leer | wohin die Korrekturen gehen, z. B. `http://127.0.0.1:8000/api/korpus/intake` |

Ein Token für den Intake gibt es nicht und braucht es nicht: Gesendet wird mit
dem Zugang dessen, der den Text gerade bestätigt hat. Damit liegt kein
Geheimnis in der Konfiguration, und die Korrektur geht zwingend in den Korpus
desjenigen, der sie abgenickt hat.

**Vorsicht bei `remote`:** Jeder entfernte Adapter - für ASR wie für das LLM -
schickt Stimm- oder Textdaten an Dritte. Beide sind bewusste Schalter mit
lokaler Voreinstellung; siehe [Datenschutz](datenschutz.md).
