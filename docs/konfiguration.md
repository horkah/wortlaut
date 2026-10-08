# Konfiguration

Alles über Umgebungsvariablen, eingelesen in der `config.py` jeder App; der
Fachcode liest keine Umgebung. Was alle Apps gleich lesen, steht als
gemeinsame Grundlage in `wortlaut/einstellungen.py`. Die kommentierte Vorlage
ist [`.env.example`](../.env.example):

```bash
cp .env.example .env
```

---

## Gemeinsam

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `WORTLAUT_DATA_DIR` | `./data` | Korpora, Diktate, Läufe, Modelle; im Container immer `/srv/wortlaut/data` |
| `WORTLAUT_STIMMEN_DIR` | `./modellcache/stimmen` | Piper-Stimmen fürs Vorlesen; ohne Stimme liest der Browser |
| `WORTLAUT_VORLESEN_MOTOR` | `piper` | welcher Motor spricht |
| `WORTLAUT_MODELLCACHE` | `./data/modellcache` | *Compose:* Grundmodelle von Hugging Face auf dem Wirt |
| `WORTLAUT_OLLAMACACHE` | `./data/ollama` | *Compose:* Modelle von Ollama auf dem Wirt |
| `WORTLAUT_TRAININGSABLAGE` | `./data/training` | *Compose:* `modelle/` und `snapshots/` auf dem Wirt |

Die drei mit *Compose* liest keine App: Im Container haben diese Pfade feste
Namen, die Variable sagt nur, wo das auf dem Wirt liegt. Was dort liegt, ist
ersetzbar und gehört nicht ins Volume der Daten
([Betrieb](betrieb.md#was-wo-liegt)).

## Rechenwerk - worauf erkannt wird

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `WORTLAUT_GERAET` | `auto` | `auto` nimmt die Karte, wenn CTranslate2 eine sieht; `cuda` verlangt sie; `cpu` bleibt beim Prozessor |
| `WORTLAUT_RECHENART` | `auto` | `int8_float16` auf der Karte, `int8` auf dem Prozessor; sonst ein fester Wert |

**Eine Einstellung für drei Stellen:** das Diktat in `schreiben`, die
Auswertung in `hören` und die Bewertung eines Laufs im Trainer. Ihre
Rechenzeiten stehen in derselben Tafel; zwischen Karte und Prozessor liegt das
Zehn- bis Zwanzigfache.

**`int8_float16` statt `float16`**, weil die Auswertung alle Modelle
gleichzeitig hält, `large-v3` darunter - in `float16` gut sechs Gigabyte, neben
einem Training und dem Sprachmodell auf derselben Karte.

**Ist die Karte voll**, weicht die Erkennung auf den Prozessor aus und
schreibt das neben jede Messung; die Modelltafel vergleicht dann die
Rechenzeiten nicht. Wer `cuda` verlangt, bekommt stattdessen den Fehler.
Einzelheiten: `wortlaut/rechenwerk.py`.

---

## hören

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `WORTLAUT_AUTH_TOKEN` | leer | **Verwaltung**: Profile anlegen, Zugänge ausgeben. Öffnet keinen Korpus |
| `WORTLAUT_ADMIN_TOKEN` | leer | **Aufsicht**: jeden Korpus einsehen, umbenennen, sichern, löschen |
| `WORTLAUT_EDITOR_KEY` | leer | **Zuschnitt**: Kopfzeile `X-Editor-Key` vor `/api/zuschnitt/…`, neben dem Sprecherzugang |
| `WORTLAUT_LLM_PROVIDER` | leer | Textquelle per LLM: leer = aus, `openai` = jede OpenAI-kompatible Schnittstelle, `anthropic` = Claude |
| `WORTLAUT_LLM_API_KEY` | leer | bei lokalem Ollama leer |
| `WORTLAUT_LLM_MODEL` | `gemma2:9b` | für ein paar Vorlesesätze genügt ein kleines Modell |
| `WORTLAUT_LLM_BASE_URL` | leer | nur bei `openai`, z. B. `http://ollama:11434/v1` |
| `WORTLAUT_AUSWERTUNG_MODELLE` | `small,medium,large-v3` | welche Grundmodelle antreten - in der Auswertung und in der Modelltafel von `lernen` |

Leer heißt bei allen drei Geheimnissen abgeschaltet, nicht offen. Aufsicht und
Verwaltung dürfen nicht denselben Token tragen, sonst bricht der Server beim
Start ab. `WORTLAUT_AUSWERTUNG_MODELLE` steht nur einmal, weil die Zahlen in
`lernen` aus dieser Auswertung stammen; `large-v3` ist teuer, beantwortet aber,
ob überhaupt ein fertiges Modell reicht.

### Das Sprachmodell für die Textquelle

`ollama` läuft als eigener Dienst auf derselben Karte (`compose.yaml`).

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `OLLAMA_KEEP_ALIVE` | `1m` | wie lange das Modell nach einer Anfrage auf der Karte bleibt |

Kurz, weil das Modell gut 5 GB auf der Karte belegt, auf der trainiert wird;
die nächste Textquelle wartet dafür einige Sekunden aufs Laden.

---

## lernen

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `WORTLAUT_TRAINER_KEY` | leer | Kopfzeile `X-Trainer-Key` vor Beauftragen, Neustart und Löschen eines Laufs. Leer = hier trainiert niemand |
| `WORTLAUT_LERNEN_BASISMODELL` | `openai/whisper-small` | die Vorgabe, worauf trainiert wird |
| `WORTLAUT_LERNEN_GRUNDMODELLE` | `openai/whisper-small,openai/whisper-medium,openai/whisper-large-v3` | was zur Wahl steht; jedes auch in `WORTLAUT_AUSWERTUNG_MODELLE`, sonst fehlt seine Baseline. Welche Methode je Modell geht, entscheidet die Karte (`wortlaut/kartenplan.py`) |
| `WORTLAUT_LERNEN_TAKT_S` | `5` | wie oft der Läufer nach Aufträgen sieht |
| `WORTLAUT_LERNEN_RESERVE_MB` | `2000` | was ein Lauf auf der Karte für die Erkenner des Webdienstes übrig lässt; zählt beim Angebot der Methoden und beim Probeschritt |
| `WORTLAUT_OLLAMA_URL` | `http://ollama:11434` | wo der Trainer Ollama vor jedem Lauf die Modelle abnimmt. Leer = kein Ollama |

---

## schreiben

Der Sprecher kommt aus dem Zugang, den der Browser vorlegt.

| Variable | Vorgabe | Was sie tut |
|---|---|---|
| `WORTLAUT_MODELL_REF` | leer | ein Stand für alle, zum Erproben. Leer: die Freigabe je Sprecher |
| `WORTLAUT_ASR_MODELL` | `small` | das Grundmodell, solange nichts freigegeben ist |
| `WORTLAUT_ASR` | `local` | `local` = faster-whisper im Prozess, `remote` = fremder Endpunkt |
| `WORTLAUT_ASR_ENDPOINT` | leer | nur bei `remote` |
| `WORTLAUT_ASR_API_KEY` | leer | nur bei `remote` |
| `WORTLAUT_INTAKE_URL` | leer | wohin die Korrekturen gehen, z. B. `http://127.0.0.1:8000/api/korpus/intake` |

Gesendet wird mit dem Zugang dessen, der bestätigt hat; ein eigenes Geheimnis
für den Intake gibt es nicht.

**Vorsicht bei `remote`:** Jeder entfernte Adapter - ASR wie LLM - schickt
Stimm- oder Textdaten an Dritte ([Datenschutz](datenschutz.md)).
