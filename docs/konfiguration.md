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

Im Container ist `WORTLAUT_DATA_DIR` immer `/srv/wortlaut/data`; wo das auf dem
Wirt liegt, entscheidet das Volume in der `compose.yaml`.

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
| `WORTLAUT_AUSWERTUNG_GERAET` | `auto` | `auto`, `cpu` oder `cuda` |
| `WORTLAUT_AUSWERTUNG_RECHENART` | `int8` | `int8` spart Speicher; `float16` nur auf der GPU |

Die beiden Token sind kein Zugang zu den Aufnahmen: Dorthin führt allein der
persönliche Zugang eines Sprechers (siehe [hören](hoeren.md)).

Zur Auswertungsliste: `medium` braucht auf einer CPU je Aufnahme etwa das Drei-
bis Zehnfache ihrer Dauer, `large-v3` noch einmal ein Mehrfaches davon und gut
anderthalb Gigabyte Speicher obendrauf. Sie steht trotzdem in der Vorgabe, denn
nur das größte fertige Modell beantwortet, ob überhaupt eines für diese Stimme
reicht. Wer wenig Maschine hat, kürzt auf `base,small`.

---

## lernen

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `WORTLAUT_LERNEN_BASISMODELL` | `openai/whisper-small` | worauf trainiert wird - fest und in der Oberfläche nicht wählbar |
| `WORTLAUT_AUSWERTUNG_MODELLE` | `base,small,medium,large-v3` | welche Grundmodelle in der Modelltabelle gegen die eigenen Stände antreten; dieselbe Variable wie oben, und das ist Absicht |
| `WORTLAUT_LERNEN_GERAET` | `cuda` | auf der CPU dauert ein Feintuning Tage statt Stunden |
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
