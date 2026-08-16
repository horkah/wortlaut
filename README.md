# wortlaut

Personalisierte Spracherkennung für Deutsch, wenn die Standardmodelle versagen —
bei Dialekt, starkem Akzent, Dysarthrie oder anderen Sprechstörungen.

Aus dem Laut wird das Wort, und zwar der Wortlaut: was die Person gesagt hat, nicht
das, was ein Sprachmodell für plausibel hält.

Drei Apps, die nacheinander greifen:

| App | Aufgabe | Status |
|---|---|---|
| **hören** | Sprachproben sammeln — zu LLM-erzeugten oder hochgeladenen Texten | in Entwicklung |
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
genügt `whisper-small`.

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

```
wortlaut/
├── README.md
├── compose.yaml
├── Makefile                       # dev, migrate, train, release
├── .env.example
│
├── apps/
│   ├── hoeren/                    # App „hören"
│   │   ├── backend/
│   │   │   ├── main.py            # FastAPI, Router-Registrierung
│   │   │   ├── config.py          # Settings aus ENV, ein Ort
│   │   │   ├── api/
│   │   │   │   ├── speakers.py    # Sprecherprofile
│   │   │   │   ├── sources.py     # LLM-Themen, Textupload
│   │   │   │   ├── prompts.py     # nächste Sprecheinheit ausliefern
│   │   │   │   ├── recordings.py  # Upload, Prüfung, Verwerfen
│   │   │   │   ├── progress.py    # gesammelte Minuten, Marken
│   │   │   │   └── intake.py      # Korrekturen von „schreiben"
│   │   │   ├── services/
│   │   │   │   ├── prompt_queue.py    # Reihenfolge, Wiederaufnahme
│   │   │   │   └── quality.py         # Pegel, Clipping, Dauerplausibilität
│   │   │   └── db/migrations/     # 001_init.sql, 002_…
│   │   └── frontend/
│   │       └── src/routes/        # Start, Quelle wählen, Aufnahme, Fortschritt
│   │
│   ├── lernen/                    # App „lernen"
│   │   ├── backend/
│   │   │   ├── main.py
│   │   │   ├── api/
│   │   │   │   ├── snapshots.py   # Korpus einfrieren, Splits bilden
│   │   │   │   ├── jobs.py        # Training starten, Status, Log
│   │   │   │   └── models.py      # Registry, Freigabe auf „active"
│   │   │   └── services/
│   │   │       ├── snapshot.py    # Korpus → unveränderliches Manifest
│   │   │       ├── backends.py    # lokaler Prozess oder GPU-Anbieter
│   │   │       └── job_worker.py  # Poll-Schleife über jobs-Tabelle
│   │   └── frontend/
│   │       └── src/routes/        # Jobs, Metriken, Modellstände
│   │
│   └── schreiben/                 # App „schreiben"
│       ├── backend/
│       │   ├── main.py
│       │   ├── config.py          # SPRECHER_ID + MODELL_REF, fest
│       │   ├── api/
│       │   │   ├── sessions.py
│       │   │   ├── segments.py    # transkribieren, neu einsprechen
│       │   │   └── model.py       # aktiver Modellstand für die Kopfzeile
│       │   └── services/
│       │       ├── segmenter.py   # Whisper-Ausgabe → vorlesbare Abschnitte
│       │       └── outbox.py      # Korrekturen an „hören", mit Wiederholung
│       └── frontend/
│           └── src/routes/        # genau zwei: Aufnahme, Ergebnis
│
├── packages/
│   ├── wortlaut/                  # eine Python-Bibliothek, von allen genutzt
│   │   └── src/wortlaut/
│   │       ├── audio.py           # 16 kHz mono, Trimmen, Pegel, Dauer
│   │       ├── corpus.py          # Korpus-Layout lesen und schreiben
│   │       ├── registry.py        # Modellstände lesen und schreiben
│   │       ├── storage.py         # Blob-Ablage: lokal oder S3-kompatibel
│   │       ├── db.py              # SQLite-Verbindung, Migrationsläufer
│   │       ├── text/
│   │       │   ├── llm.py         # Thema + Altersspanne → Text
│   │       │   ├── upload.py      # txt, md, pdf, epub, docx → Reintext
│   │       │   └── chunker.py     # Text → sprechbare Einheiten
│   │       └── whisper/
│   │           ├── local.py       # faster-whisper
│   │           └── remote.py      # OpenAI-kompatibler Endpunkt
│   │
│   └── ui/                        # geteilte Svelte-Komponenten
│       ├── Recorder.svelte
│       ├── AudioPlayer.svelte
│       ├── PromptView.svelte      # eine Einheit groß, Kontext blass
│       ├── SegmentList.svelte
│       └── speak.ts               # Vorlesen über Web Speech API
│
├── training/                      # das, was auf der GPU läuft
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
   unterbrechbar und wird an derselben Stelle fortgesetzt.
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

### Endpunkte

```
POST   /api/speakers
POST   /api/sources/llm          { thema, altersspanne, umfang }
POST   /api/sources/upload       multipart
GET    /api/prompts/next?session=…
POST   /api/recordings           multipart: audio + prompt_id + modus
DELETE /api/recordings/{id}
GET    /api/progress?speaker=…
POST   /api/korpus/intake        ← von „schreiben"
```

---

## Der Korpus — die Nahtstelle zu „lernen"

Ein Verzeichnis, kein Dienst. `hören` ist der einzige Schreiber, `lernen` liest.
Beide laufen auf demselben Server, SQLite im WAL-Modus erlaubt gleichzeitige Leser.

```
data/korpus/<sprecher_id>/
├── audio/<aufnahme_id>.wav     # 16 kHz mono, PCM 16 bit
└── hoeren.sqlite               # Vorlagen, Aufnahmen, Sitzungen
```

`lernen` kopiert daraus vor jedem Job einen unveränderlichen Schnappschuss:

```
data/snapshots/<job_id>/manifest.jsonl
```

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
| `speakers` | Profil, Sprache, Basismodell |
| `text_sources` | LLM-Auftrag oder hochgeladener Text, mit Parametern |
| `prompts` | eine Sprecheinheit, Herkunft, Reihenfolge |
| `sessions` | Aufnahmesitzung, Position in der Warteschlange |
| `recordings` | Blob-Referenz, Dauer, Pegel, Modus, Status |

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

---

## Technologien

| Bereich | Wahl | Warum |
|---|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn | ML-Ökosystem ist Python, async für Uploads |
| Datenbank | SQLite (WAL) | ein Server, ein Sprecher; Backup heißt Datei kopieren |
| Frontend | Svelte 5, Vite, TypeScript | kompiliert weg, kein Laufzeit-Framework auf schwachen Geräten |
| Aufnahme | `MediaRecorder` (Opus), serverseitig ffmpeg → 16 kHz mono WAV | Browser liefern kein WAV, Konvertierung an einer Stelle |
| Vorlesen | Web Speech API | deutsche Stimmen überall vorhanden, keine Infrastruktur, keine Latenz |
| ASR | faster-whisper (CTranslate2) | schnellste brauchbare Whisper-Laufzeit auf CPU und kleiner GPU |
| ASR entfernt | OpenAI-kompatibler Endpunkt | ein Adapter deckt mehrere Anbieter ab |
| Training | HF Transformers, Datasets, Accelerate | Standardrezept für Whisper, breit dokumentiert |
| Textquelle | LLM-API über einen Adapter | Thema und Altersspanne als Prompt-Parameter |
| Jobs | `jobs`-Tabelle plus Poll-Worker | keine Broker-Abhängigkeit für eine Warteschlange mit selten mehr als einem Eintrag |
| Proxy | Caddy | TLS ohne Konfigurationsaufwand |
| Auth | `hören` und `lernen` hinter Token, `schreiben` ohne | siehe Grundentscheidung 7 |

---

## Konfiguration

Eine `.env` pro App, eingelesen in `config.py`, nirgends `os.environ` im Fachcode.

```
# gemeinsam
WORTLAUT_DATA_DIR=/srv/wortlaut/data
WORTLAUT_STORAGE=local              # local | s3

# hören
WORTLAUT_LLM_PROVIDER=
WORTLAUT_LLM_API_KEY=
WORTLAUT_AUTH_TOKEN=

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

```bash
cp .env.example .env
make migrate                 # Datenbanken anlegen
make dev APP=hoeren          # Backend + Vite
make train SPEAKER=spr_7f2a RECIPE=whisper_full
make release JOB=42
```

Ohne GPU: `WORTLAUT_BASE_MODEL=openai/whisper-small` und
`WORTLAUT_TRAINING_BACKEND=remote`. Die Apps laufen lokal, das Training auf
gemieteter Hardware.

---

## Datenschutz

Stimmaufnahmen einer Person mit Sprechstörung sind Gesundheitsdaten nach Art. 9
DSGVO. Das hat Folgen für den Aufbau, nicht nur für einen Hinweistext:

- Audio liegt ausschließlich unter `WORTLAUT_DATA_DIR`, nie im Git, nie in Logs.
- Die entfernten Adapter für ASR und LLM sind bewusste Schalter mit lokaler
  Voreinstellung. Wer sie umlegt, schickt Stimm- oder Textdaten an Dritte.
- `scripts/purge_speaker.py` entfernt Profil, Aufnahmen, Schnappschüsse und Modelle
  vollständig. Das Recht auf Löschung muss ausführbar sein, nicht dokumentiert.

---

## Bewusst nicht enthalten

- **Automatische Tests.** Kommen später, dann als `tests/` je Paket.
- **Phonetisch ausgewogene Vorlagen.** LLM-Text ist flüssig, aber phonetisch
  beliebig. Eine dritte Textquelle aus einer festen, phonetisch abgedeckten
  Satzliste wäre für Sprechstörungen wirksamer und steht auf der Liste.
- **Mehrsprecher-Betrieb, Rollen, Mandanten.** Erst wenn eine zweite Person
  dieselbe `hören`-Instanz nutzt.
- **Streaming-Transkription.** Die Vorlese-Korrektur-Schleife arbeitet
  abschnittsweise; Live-Erkennung würde das Bedienkonzept nicht verbessern.
- **Diarisierung, Zeitstempel auf Wortebene.** Ein Sprecher, kurze Abschnitte.
