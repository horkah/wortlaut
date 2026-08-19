<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/wortlaut-logo-invers.svg" />
  <img src="assets/wortlaut-logo.svg" alt="" width="88" height="88" />
</picture>

# wortlaut

Personalisierte Spracherkennung für Deutsch, wenn die Standardmodelle versagen —
bei Dialekt, starkem Akzent, Dysarthrie oder anderen Sprechstörungen.

Aus dem Laut wird das Wort, und zwar der Wortlaut: was die Person gesagt hat, nicht
das, was ein Sprachmodell für plausibel hält.

Drei Apps, die nacheinander greifen:

| App | Aufgabe | Status |
|---|---|---|
| **hören** | Sprachproben sammeln — zu LLM-erzeugten oder hochgeladenen Texten | läuft, mit Tests |
| **lernen** | aus den Proben ein sprecherspezifisches Whisper-Modell feintunen | entworfen |
| **schreiben** | mit diesem Modell diktieren, vorlesen lassen, Fehler neu einsprechen | entworfen |

`lernen` liest die Dateien von `hören`. `schreiben` liest das Modell von `lernen` und
gibt Korrekturen an `hören` zurück. Sonst berühren sie sich nicht.

---

## Grundentscheidungen

**1. Whisper ist gesetzt.**
Basis ist `openai/whisper-large-v3`, Laufzeit faster-whisper (CTranslate2), Training
über HF Transformers. Nicht weil Whisper das genaueste Modell ist — das ist es seit
2026 nicht mehr — sondern weil es das einzige ist, bei dem Trainingsrezept,
Laufzeit-Ökosystem und dokumentierte Ergebnisse für genau diesen Fall vollständig
vorliegen. MIT-Lizenz, keine Attributionspflicht. Für die Entwicklung ohne GPU
genügt `whisper-small`, für noch weniger Rechenlast `whisper-tiny`.

**2. Aufnahme erfolgt äußerungsweise, nicht am Stück.**
`hören` zeigt immer genau eine kurze Einheit und nimmt genau dazu auf. Jedes
Audio-Text-Paar ist damit von Haus aus ausgerichtet — kein Forced Alignment, keine
Segmentierungsheuristik, kein Timestamp-Drift. Das ist der größte
Komplexitätsgewinn im ganzen Entwurf.

**3. Ein Modell gehört zu genau einem Sprecher.**
Kein Mehrsprecher-Mischtraining. Ein Sprecher, ein Basismodell, eine Versionskette.

**4. Volles Feintuning ist die Voreinstellung, LoRA ein Schalter.**
Bei stark abweichender Aussprache reicht die Kapazität von LoRA oft nicht, bei
Dialekt schon. Beides über dieselbe Rezeptdatei, nicht über zwei Codepfade.

**5. GPU-Arbeit läuft nie im Web-Prozess und ist austauschbar.**
Transkription und Training haben je eine lokale und eine entfernte Implementierung.
Der Server braucht keine GPU; er kann eine haben.

**6. Genau ein Schreiber pro Datenbestand.**
`hören` schreibt den Korpus, `lernen` liest ihn. `lernen` schreibt die
Modell-Registry, `schreiben` liest sie. Keine geteilten Schreibrechte, keine
verteilten Transaktionen.

**7. `schreiben` hat kein Nutzerkonto.**
Die Zielperson kann schlecht lesen und schreiben. Eine Instanz ist auf ein
Sprecherprofil und einen Modellstand konfiguriert. Ein großer Knopf, sonst nichts.

---

## Projektstruktur

Was steht, steht ohne Klammer. Was noch fehlt, ist gekennzeichnet.

```
wortlaut/
├── README.md
├── compose.yaml
├── Caddyfile
├── Makefile                       # test, dev, migrate, train, release
├── pyproject.toml                 # Abhängigkeiten, Test- und Lint-Einstellungen
├── conftest.py                    # geteilte Testbausteine
├── .env.example
│
├── apps/
│   ├── hoeren/                    # App „hören"
│   │   ├── Dockerfile
│   │   ├── backend/
│   │   │   ├── main.py            # FastAPI, Router, Ausliefern des Frontends
│   │   │   ├── config.py          # Settings aus ENV, ein Ort
│   │   │   ├── deps.py            # Token, Datenbank je Sprecher, Ablage
│   │   │   ├── api/
│   │   │   │   ├── speakers.py    # Sprecherprofile
│   │   │   │   ├── sources.py     # LLM-Themen, Textupload
│   │   │   │   ├── prompts.py     # nächste Sprecheinheit, Sitzungen
│   │   │   │   ├── recordings.py  # Upload, Prüfung, Verwerfen
│   │   │   │   ├── progress.py    # gesammelte Minuten, Marken
│   │   │   │   └── intake.py      # Korrekturen von „schreiben"
│   │   │   ├── services/
│   │   │   │   ├── prompt_queue.py    # Reihenfolge, Wiederaufnahme
│   │   │   │   └── quality.py         # Pegel, Clipping, Dauerplausibilität
│   │   │   └── db/
│   │   │       ├── models.py      # typisierte Modelle zum Schema
│   │   │       └── migrations/    # 001_init.sql, 002_…
│   │   ├── frontend/
│   │   │   ├── vite.config.ts     # Alias auf packages/ui, Proxy auf /api
│   │   │   └── src/
│   │   │       ├── lib/           # api.ts, zustand.svelte.ts, einstellungen.svelte.ts
│   │   │       └── routes/        # Start, Quelle wählen, Aufnahme, Fortschritt,
│   │   │                          # Einstellungen
│   │   └── tests/                 # Endpunkte, Warteschlange, Intake
│   │
│   ├── lernen/                    # App „lernen" — entworfen, siehe README dort
│   └── schreiben/                 # App „schreiben" — entworfen, siehe README dort
│
├── packages/
│   ├── wortlaut/                  # eine Python-Bibliothek, von allen genutzt
│   │   ├── src/wortlaut/
│   │   │   ├── audio.py           # 16 kHz mono, Pegel, Dauer
│   │   │   ├── corpus.py          # Korpus-Layout lesen und schreiben
│   │   │   ├── registry.py        # Modellstände lesen und schreiben
│   │   │   ├── storage.py         # Blob-Ablage: lokal (S3 vorbereitet)
│   │   │   ├── db.py              # SQLite-Verbindung, Migrationsläufer
│   │   │   ├── ids.py             # zeitlich sortierbare Kennungen
│   │   │   ├── text/
│   │   │   │   ├── llm.py         # Thema + Altersspanne → Text
│   │   │   │   ├── upload.py      # txt, md, pdf, epub, docx → Reintext
│   │   │   │   └── chunker.py     # Text → sprechbare Einheiten
│   │   │   └── whisper/           # für „schreiben": lokal oder entfernt
│   │   │       ├── local.py       # faster-whisper
│   │   │       └── remote.py      # OpenAI-kompatibler Endpunkt
│   │   └── tests/                 # Chunker, Textformate, Audio, Ablage
│   │
│   └── ui/                        # geteilte Svelte-Komponenten
│       ├── Kopfleiste.svelte      # App-Reiter oben, Ansichten-Reiter darunter
│       ├── apps.ts                # die drei Apps: Name, Pfad, schon da oder nicht
│       ├── Recorder.svelte
│       ├── AudioPlayer.svelte
│       ├── PromptView.svelte      # eine Einheit groß, Kontext blass
│       ├── Mikrofontest.svelte    # Gerät wählen, Pegel sehen, Probe hören
│       ├── Pegelanzeige.svelte    # Pegelbalken, Grenzen wie in quality.py
│       ├── mikrofon.ts            # Aufnahmekette: Gerät, Verstärkung, Messung
│       └── speak.ts               # Vorlesen über Web Speech API, Stimme und Tempo
│
├── training/                      # noch nicht gebaut: das, was auf der GPU läuft
│   ├── Dockerfile
│   ├── finetune.py                # liest Manifest, schreibt Checkpoint + Metriken
│   ├── evaluate.py                # WER/CER auf dem Testsplit
│   └── config/
│       ├── whisper_full.yaml
│       └── whisper_lora.yaml
│
├── data/                          # nicht im Git
├── docs/
│   ├── datenschutz.md
│   └── betrieb.md
└── scripts/
    ├── migrate.py
    └── purge_speaker.py           # Löschung, vollständig
```

---

## App „hören" — der aktuelle Arbeitsstand

### Ablauf

1. **Sprecherprofil** anlegen: Name, Sprache, Basismodell. Sonst nichts.
2. **Textquelle wählen.** Entweder ein Thema oder Stichwort plus Altersspanne, aus
   dem ein LLM Text erzeugt; oder ein hochgeladener Text, aus dem zufällige Proben
   gezogen werden. Beides wird mit Herkunft und Erzeugungsparametern gespeichert,
   damit später nachvollziehbar ist, woher eine Vorlage stammt.
3. **Schneiden.** `chunker.py` zerlegt den Text in Einheiten von grob 3–12 Sekunden
   geschätzter Sprechdauer, an Satz- und Teilsatzgrenzen.
4. **Aufnehmen.** Die App zeigt eine Einheit groß, davor und dahinter je eine blass.
   Aufnehmen, anhören, verwerfen und wiederholen, weiter. Sitzung ist jederzeit
   unterbrechbar und wird an derselben Stelle fortgesetzt. Die Stelle wird
   nirgends gespeichert, sondern abgeleitet: offen ist jede Vorlage ohne gültige
   Aufnahme. Verwerfen macht eine Vorlage damit von selbst wieder offen — und
   löscht die Audiodatei wirklich, statt sie nur zu markieren.
5. **Prüfen.** Serverseitig: Pegel, Clipping, führende und schließende Stille, Dauer
   gegen die geschätzte Sprechdauer. Auffälligkeiten werden angezeigt, nicht
   erzwungen — bei Sprechstörungen sind Ausreißer normal und dürfen nicht
   wegautomatisiert werden.
6. **Fortschritt.** Gesammelte Minuten gegen zwei Marken: ab etwa 1,5 Stunden wird
   ein Modell brauchbar, ab etwa 20 Stunden gut. Danach flacht der Gewinn ab.

### Vorsprechen statt Vorlesen

Die Zielgruppe kann teilweise nicht flüssig lesen — das ist der Grund für das ganze
Projekt und zugleich ein Problem beim Sammeln, denn Sammeln heißt Vorlagen ablesen.
Deshalb hat die Aufnahmeansicht einen Modus, in dem die Einheit erst per Web Speech
API vorgesprochen und dann nachgesprochen wird.

Das hat einen Preis: Nachsprechen verändert Sprechtempo und Satzmelodie in Richtung
der Vorgabe. Die Aufnahme wird deshalb als `nachgesprochen` markiert und im Manifest
getrennt geführt, damit man den Effekt später messen und die Gewichtung anpassen
kann.

Weil dieser Effekt am Sprechtempo der Vorgabe hängt, ist das Tempo einstellbar
(Vorgabe 0,9× — langsamer ist leichter nachzusprechen, ermüdet aber über eine lange
Sitzung). Ebenso die Stimme: welche zur Wahl stehen und wie natürlich sie klingen,
entscheidet allein das Betriebssystem. Dieselbe Seite klingt auf macOS natürlich und
unter Linux mit espeak-ng blechern; die App kann das nur zur Auswahl stellen, nicht
verbessern. Wege zu einer besseren Stimme stehen in `docs/betrieb.md`.

### Menüführung

Die Kopfzeile hat zwei Reihen, weil es zwei Ebenen gibt. Oben die drei Apps —
`hören`, `lernen`, `schreiben` —, die offene dunkelgrün hinterlegt; die beiden
noch nicht gebauten stehen blass daneben und sind nicht anklickbar. Darunter
die Ansichten der offenen App, die aktuelle hell hinterlegt. Beides steht in
`packages/ui/Kopfleiste.svelte`, damit `lernen` und `schreiben` später dieselbe
Leiste bekommen und nicht jede App ihr eigenes Menü erfindet.

Alle drei liegen unter einer Adresse (`wortlaut.example.org`), nicht unter drei
Subdomains: ein Zertifikat, ein Caddy-Block, und der Wechsel zwischen den Apps
ist ein Pfadwechsel. Solange nur `hören` existiert, liegt es auf der Wurzel;
welcher Pfad zu welcher App gehört, steht an einer Stelle in
`packages/ui/apps.ts`.

Ohne gewähltes Sprecherprofil bleibt die zweite Reihe leer — jede Ansicht
führte dort ohnehin nur zurück zur Sprecherwahl.

### Einstellungen

Unter `#/einstellungen` liegen Mikrofon, Stimme, Sprechtempo und Schriftgröße der
Vorlage, je mit Probe. Sie hängen am Gerät und nicht am Sprecherprofil — welche
Stimmen und welche Mikrofone es gibt, bestimmt das Betriebssystem, und wer die App
auf zwei Geräten benutzt, braucht dort verschiedene Werte. Gespeichert wird deshalb
im `localStorage` des Browsers (`wortlaut.mikrofon`, `wortlaut.verstaerkung`,
`wortlaut.autopegel`, `wortlaut.stimme`, `wortlaut.tempo`, `wortlaut.schrift`),
nicht im Korpus.

Die Schriftgröße ist einstellbar, weil die Zielgruppe sehr verschieden gut liest —
dieselbe Vorgabe, die einer Person zu klein ist, drängt bei einer anderen den
Kontext aus dem Bild.

#### Mikrofon

Der Mikrofontest zeigt den Pegel live, gegen dieselben Grenzen, die der Server nach
dem Absenden prüft (`services/quality.py`) — was im Test „guter Pegel" ist, gibt
später keinen Hinweis. Dazu die Wahl unter den vorhandenen Geräten und eine Probe
zum Anhören.

Zu leise Eingänge lassen sich auf zwei Arten heben, und die beiden tun
Verschiedenes:

- **Verstärkung** ist ein fester Faktor (1–20×) vor der Aufzeichnung. Er behebt ein
  Mikrofon, das durchweg zu leise ist — unter Linux der Normalfall bei eingebauten
  Mikrofonen, siehe `docs/betrieb.md`. **Automatisch einmessen** hört fünf Sekunden
  zu und setzt den Faktor so, dass die Spitze bei −6 dBFS landet; eingemessen wird
  auf die Spitze und nicht auf den Mittelwert, weil ein Wert am Anschlag verloren
  ist, ein zu leiser Mittelwert dagegen nur ungünstig.
- **Pegel automatisch nachregeln** ist die Regelung des Browsers (AGC). Sie gleicht
  aus, wenn mal lauter und mal leiser gesprochen wird, hebt einen durchweg zu leisen
  Eingang aber nicht an.

Beides steckt in der gespeicherten Aufnahme — sie ist Trainingsmaterial, und was
hier verstärkt wird, ist später verstärkt. Das ist gewollt: eine Aufnahme knapp über
dem Rauschen nützt dem Training nicht. Was aber *nicht* passiert, ist eine
nachträgliche Normalisierung auf dem Server. Wie laut jemand spricht, gehört zu den
Daten, für die dieses Projekt existiert.

### Endpunkte

```
POST   /api/speakers                        { name, sprache, basismodell }
GET    /api/speakers
GET    /api/speakers/{id}
POST   /api/sources/llm?sprecher=…          { thema, altersspanne, umfang }
POST   /api/sources/upload?sprecher=…       multipart: datei
GET    /api/sources?sprecher=…
POST   /api/sessions?sprecher=…
GET    /api/prompts/next?sprecher=…&session=…
POST   /api/recordings?sprecher=…           multipart: audio + prompt_id + modus
GET    /api/recordings/{id}/audio?sprecher=…
DELETE /api/recordings/{id}?sprecher=…
GET    /api/progress?sprecher=…
POST   /api/korpus/intake?sprecher=…        ← von „schreiben"
GET    /gesundheit                          ohne Token
```

Jeder Endpunkt nennt seinen Sprecher, und zwar immer als Abfrageparameter —
auch die mit Formular- oder JSON-Rumpf. Der Grund steht im nächsten Abschnitt:
Das Korpus hat je Sprecher eine eigene Datenbank, und ohne die Kennung wüsste
der Server nicht, welche Datei er öffnen soll. Ein Parameter an immer derselben
Stelle heißt außerdem: eine einzige Abhängigkeit wertet ihn aus.

Alle `/api`-Endpunkte hängen hinter `WORTLAUT_AUTH_TOKEN`, sofern gesetzt.
Die interaktive Dokumentation liegt unter `/docs`.

---

## Der Korpus — die Nahtstelle zu „lernen"

Ein Verzeichnis, kein Dienst. `hören` ist der einzige Schreiber, `lernen` liest.
Beide laufen auf demselben Server, SQLite im WAL-Modus erlaubt gleichzeitige Leser.

```
data/korpus/<sprecher_id>/
├── audio/<aufnahme_id>.wav     # 16 kHz mono, PCM 16 bit
└── hoeren.sqlite               # Vorlagen, Aufnahmen, Sitzungen
```

Die Datenbank liegt **innerhalb** des Sprecherverzeichnisses, also eine je
Sprecher. Das hat drei Folgen: `lernen` liest genau eine Datei statt einer
gefilterten Tabelle, eine vollständige Löschung ist das Entfernen eines
Verzeichnisses, und jeder Endpunkt von `hören` muss seinen Sprecher nennen.

`lernen` kopiert daraus vor jedem Job einen unveränderlichen Schnappschuss:

```
data/snapshots/<job_id>/
├── manifest.jsonl
└── sprecher.txt                # nur die Sprecher-ID
```

`sprecher.txt` ist die Zusage an die Löschung: `scripts/purge_speaker.py` findet
einen Schnappschuss daran, ohne das Manifest deuten zu müssen. Fehlt die Datei,
meldet das Skript den Schnappschuss zur Prüfung von Hand.

Eine Zeile pro Aufnahme:

```json
{"audio":"audio/rec_01J8….wav","text":"…","quelle":"vorlage","modus":"gelesen",
 "dauer_s":4.8,"gewicht":1.0,"split":"train"}
```

Der Schnappschuss ist der Grund, warum weiter aufgenommen werden kann, während ein
Training läuft, ohne dass das Ergebnis unreproduzierbar wird.

**Quellen und Gewichte.** `quelle` ist `vorlage` oder `korrektur`. Korrekturen
stammen aus `schreiben` und sind schwächere Daten: der Text ist keine Vorgabe,
sondern eine vom Nutzer abgenickte Maschinenausgabe. Wer sie gleichrangig einspeist,
trainiert dem Modell seine eigenen Fehler an. Voreinstellung ist ein niedrigeres
Gewicht, festgelegt im Rezept.

**Modi.** `modus` ist `gelesen`, `nachgesprochen` oder `frei`. Die ersten beiden
kommen aus `hören` (siehe „Vorsprechen statt Vorlesen"), `frei` aus `schreiben`:
dort spricht die Person selbst formulierte Sätze, nicht eine Vorlage.
`GET /api/progress` zählt beides getrennt, damit sich die Gewichtung an Zahlen
statt an Vermutungen ausrichten kann.

---

## Die Modell-Registry — die Nahtstelle zu „schreiben"

Ebenfalls Dateien statt Tabelle. Ein Modellstand ist ein Verzeichnis, das man
kopieren, sichern und per `scp` verschieben kann.

```
data/modelle/<sprecher_id>/<version>/
├── manifest.json
├── ct2/                        # für faster-whisper exportiert
└── checkpoint/                 # Rohgewichte, optional
```

```json
{
  "id": "spr_7f2a/2026-08-15T1420",
  "sprecher_id": "spr_7f2a",
  "basismodell": "openai/whisper-large-v3",
  "methode": "full",
  "erstellt": "2026-08-15T14:20:03Z",
  "daten": { "stunden": 4.7, "einheiten": 1832,
             "quellen": { "vorlage": 1640, "korrektur": 192 } },
  "metriken": { "wer": 0.146, "cer": 0.061, "test_einheiten": 120 },
  "laufzeit": "faster-whisper>=1.1",
  "sha256": "…",
  "status": "active"
}
```

`schreiben` wird über `WORTLAUT_MODELL_REF` auf genau eine `id` festgenagelt und
zeigt Basismodell und Datum dauerhaft in der Kopfzeile. Ein Modellwechsel ist eine
Konfigurationsänderung mit Neustart, kein Laufzeitereignis — sonst weiß hinterher
niemand, welcher Stand welche Ausgabe erzeugt hat.

---

## App „schreiben" — Ablauf

1. Nutzer spricht, Whisper liefert Text mit Segmentgrenzen.
2. Die App liest jeden Abschnitt vor. Jeder Abschnitt ist anklickbar.
3. Klick → nur dieser Abschnitt wird neu eingesprochen und neu transkribiert. Das
   neue Audio ersetzt den alten Ausschnitt, der Rest bleibt stehen.
4. Bestätigt der Nutzer den fertigen Text, geht jeder Abschnitt als Korrekturpaar an
   `POST /api/korpus/intake` von `hören`. Die Outbox puffert, wenn `hören` nicht
   erreichbar ist.

---

## Datenmodell

**hören**

| Tabelle | Zweck |
|---|---|
| `speakers` | Profil, Sprache, Basismodell — genau eine Zeile je Datenbank |
| `text_sources` | LLM-Auftrag, hochgeladener Text oder Korrektur, mit Parametern |
| `prompts` | eine Sprecheinheit, Herkunft, fortlaufende Position |
| `sessions` | Aufnahmesitzung: begonnen, zuletzt aktiv |
| `recordings` | Blob-Referenz, Messwerte, Modus, Status, Kennung aus „schreiben" |

**lernen**

| Tabelle | Zweck |
|---|---|
| `jobs` | Auftrag, Schnappschuss, Rezept, Status, Log-Referenz |

**schreiben**

| Tabelle | Zweck |
|---|---|
| `sessions` | eine Diktiersitzung |
| `segments` | Text, Reihenfolge, Audio, Herkunft (initial/neu) |
| `outbox` | offene Korrekturen mit Wiederholungszähler |

Zugriff über SQLAlchemy 2.0 mit typisierten Modellen. Schemaänderungen als
nummerierte `.sql`-Dateien, angewendet von `scripts/migrate.py`. Kein Alembic — bei
diesem Schemaumfang ist die Migrationsmaschinerie größer als das Schema.

Zwei Spalten tragen mehr Bedeutung, als ihr Name verrät:

- `prompts.position` ist über **alle** Quellen eines Sprechers fortlaufend. Eine
  neue Textquelle hängt hinten an, statt in die laufende Sitzung zu springen.
- `recordings.externe_id` ist die Abschnittskennung aus `schreiben` und
  eindeutig. Die dortige Outbox darf damit beliebig oft wiederholen, ohne dass
  dieselbe Korrektur zweimal im Korpus landet.

---

## Technologien

| Bereich | Wahl | Warum |
|---|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn | ML-Ökosystem ist Python, async für Uploads |
| Datenbank | SQLite (WAL) | ein Server, ein Sprecher; Backup heißt Datei kopieren |
| Frontend | Svelte 5, Vite, TypeScript | kompiliert weg, kein Laufzeit-Framework auf schwachen Geräten |
| Aufnahme | `MediaRecorder` (Opus), serverseitig ffmpeg → 16 kHz mono WAV | Browser liefern kein WAV, Konvertierung an einer Stelle |
| Vorlesen | Web Speech API | deutsche Stimmen fast überall vorhanden, keine Infrastruktur, keine Latenz — dafür schwankt die Qualität je nach Betriebssystem stark, Stimme und Tempo sind deshalb einstellbar |
| ASR | faster-whisper (CTranslate2) | schnellste brauchbare Whisper-Laufzeit auf CPU und kleiner GPU |
| ASR entfernt | OpenAI-kompatibler Endpunkt | ein Adapter deckt mehrere Anbieter ab |
| Training | HF Transformers, Datasets, Accelerate | Standardrezept für Whisper, breit dokumentiert |
| Textquelle | LLM-API über einen Adapter | Thema und Altersspanne als Prompt-Parameter |
| Jobs | `jobs`-Tabelle plus Poll-Worker | keine Broker-Abhängigkeit für eine Warteschlange mit selten mehr als einem Eintrag |
| Proxy | Caddy | TLS ohne Konfigurationsaufwand |
| Auth | `hören` und `lernen` hinter Token, `schreiben` ohne | siehe Grundentscheidung 7 |
| Tests | pytest, FastAPI-TestClient | echte SQLite-Datei, echte Endpunkte, kein Nachbau |
| Werkzeug | uv, ruff | eine Abhängigkeitsdatei, ein Formatierer, keine Diskussion |

---

## Konfiguration

Alles über Umgebungsvariablen, eingelesen in der `config.py` der App, nirgends
`os.environ` im Fachcode. Die Bibliothek liest gar keine Umgebung: Pfade und
Schlüssel werden ihr übergeben. Vorlage ist `.env.example`; im Betrieb bekommt
jede App ihre Werte aus der Umgebung.

```
# gemeinsam
WORTLAUT_DATA_DIR=/srv/wortlaut/data
WORTLAUT_STORAGE=local              # local | s3

# hören
WORTLAUT_LLM_PROVIDER=              # leer = Textquelle „LLM" abgeschaltet
WORTLAUT_LLM_API_KEY=
WORTLAUT_LLM_MODEL=claude-opus-5
WORTLAUT_AUTH_TOKEN=                # leer = offen, nur für die Entwicklung

# lernen
WORTLAUT_TRAINING_BACKEND=local     # local | remote
WORTLAUT_BASE_MODEL=openai/whisper-large-v3

# schreiben
WORTLAUT_SPRECHER_ID=spr_7f2a
WORTLAUT_MODELL_REF=spr_7f2a/2026-08-15T1420
WORTLAUT_ASR=local                  # local | remote
WORTLAUT_ASR_ENDPOINT=
WORTLAUT_ASR_API_KEY=
WORTLAUT_INTAKE_URL=https://hoeren.example.org/api/korpus/intake
WORTLAUT_INTAKE_TOKEN=
```

---

## Entwicklung

Voraussetzungen: Python 3.12 mit [uv](https://docs.astral.sh/uv/), Node 20 oder
neuer für das Frontend — und **ffmpeg im Pfad**, sonst schlägt jeder
Aufnahme-Upload fehl.

```bash
cp .env.example .env
uv sync                      # Abhängigkeiten und die Bibliothek `wortlaut`
cd apps/hoeren/frontend && npm install && cd -

make test                    # Testlauf, gut eine Sekunde
make dev APP=hoeren          # Backend auf :8000, Vite auf :5173
make migrate                 # nur nötig, wenn nach einem Update Migrationen offen sind
```

Aufgerufen wird `http://localhost:5173`; Vite leitet `/api` an das Backend
weiter, deshalb gibt es keine CORS-Regeln. Neue Sprecher bekommen ihre
Datenbank beim Anlegen, `make migrate` ist also kein erster Schritt, sondern
ein späterer.

Noch nicht nutzbar, weil `lernen` fehlt:

```bash
make train SPEAKER=spr_7f2a RECIPE=whisper_full
make release JOB=42
```

Ohne GPU: `WORTLAUT_BASE_MODEL=openai/whisper-small` und
`WORTLAUT_TRAINING_BACKEND=remote`. Die Apps laufen lokal, das Training auf
gemieteter Hardware.

Betrieb, Endpunktliste und Fehlersuche stehen in [`docs/betrieb.md`](docs/betrieb.md).

---

## Tests

```bash
make test
```

Läuft in gut einer Sekunde: ohne GPU, ohne Netz, ohne Mikrofon.

| Ort | Prüft |
|---|---|
| `packages/wortlaut/tests/` | Chunker, Textformate, Audiomessung, Ablage, Migrationen, Registry |
| `apps/hoeren/tests/` | Endpunkte gegen eine echte SQLite-Datei im Temporärverzeichnis |

Zwei Regeln halten den Aufwand klein und die Aussagekraft hoch:

**Nachgebaut wird so wenig wie möglich.** Die Tests sprechen mit echtem SQLite,
echten Dateien und den echten Endpunkten. Ersetzt sind genau zwei Dinge: der
LLM-Anbieter (sonst kostete jeder Testlauf Geld und Netz) und ffmpeg.

**ffmpeg wird trotzdem einmal wirklich benutzt.** Ein Test erzeugt eine
Opus-Datei, wie sie ein Browser liefert, schickt sie an `POST /api/recordings`
und prüft, dass im Korpus 16 kHz Mono liegen. Damit ist der Weg vom Browser bis
zur Datei einmal vollständig durchlaufen; die übrigen Aufnahmetests kommen
ohne externes Programm aus. Fehlt ffmpeg, werden diese drei Tests übersprungen
statt zu scheitern.

Was noch fehlt: das Frontend hat keine eigenen Tests. `npm run check`
(svelte-check) prüft dort bislang nur die Typen.

Den kompletten Weg im Browser — Sprecher anlegen, Textquelle, Aufnehmen,
Fortschritt — deckt kein automatisierter Test ab. Dafür gibt es eine
Schritt-für-Schritt-Anleitung zum Selbst-Durchklicken:
[`docs/manueller-test.md`](docs/manueller-test.md).

---

## Datenschutz

Stimmaufnahmen einer Person mit Sprechstörung sind Gesundheitsdaten nach Art. 9
DSGVO. Das hat Folgen für den Aufbau, nicht nur für einen Hinweistext:

- Audio liegt ausschließlich unter `WORTLAUT_DATA_DIR`, nie im Git, nie in Logs.
- Die entfernten Adapter für ASR und LLM sind bewusste Schalter mit lokaler
  Voreinstellung. Wer sie umlegt, schickt Stimm- oder Textdaten an Dritte.
- Verworfene Aufnahmen werden gelöscht, nicht nur markiert. In der Datenbank
  bleibt der Datensatz als Spur, die Audiodatei ist weg.
- `scripts/purge_speaker.py` entfernt Profil, Aufnahmen, Schnappschüsse und Modelle
  vollständig. Das Recht auf Löschung muss ausführbar sein, nicht dokumentiert.

Einzelheiten in [`docs/datenschutz.md`](docs/datenschutz.md).

---

## Bewusst nicht enthalten

- **Phonetisch ausgewogene Vorlagen.** LLM-Text ist flüssig, aber phonetisch
  beliebig. Eine dritte Textquelle aus einer festen, phonetisch abgedeckten
  Satzliste wäre für Sprechstörungen wirksamer und steht auf der Liste.
- **Mehrsprecher-Betrieb, Rollen, Mandanten.** Erst wenn eine zweite Person
  dieselbe `hören`-Instanz nutzt.
- **Streaming-Transkription.** Die Vorlese-Korrektur-Schleife arbeitet
  abschnittsweise; Live-Erkennung würde das Bedienkonzept nicht verbessern.
- **Diarisierung, Zeitstempel auf Wortebene.** Ein Sprecher, kurze Abschnitte.
