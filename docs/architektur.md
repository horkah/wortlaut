# Der Entwurf

Die Festlegungen, an denen sich alles ausrichtet, der Aufbau, die Nahtstellen
zwischen den Apps und die Technikwahl. Die Apps selbst:
[hören](hoeren.md), [lernen](lernen.md), [schreiben](schreiben.md).

---

## Grundentscheidungen

**1. Whisper ist gesetzt.** Laufzeit faster-whisper (CTranslate2), Training
über HF Transformers. Nicht das genaueste Modell, aber das einzige, bei dem
Trainingsrezept, Laufzeit und dokumentierte Ergebnisse für diesen Fall
vollständig vorliegen. MIT-Lizenz. Gemessen wird ab `whisper-small`; darunter
versteht Whisper abweichende Aussprache zu schlecht für einen Vergleich.

**2. Aufgenommen wird äußerungsweise.** `hören` zeigt eine kurze Einheit und
nimmt genau dazu auf. Jedes Paar aus Audio und Text ist damit ausgerichtet -
der größte Komplexitätsgewinn im Entwurf.

**3. Ein Modell gehört genau einem Sprecher.** Kein Mehrsprecher-Training.

**4. Volles Feintuning und LoRA über dieselbe Rezeptdatei.** Bei stark
abweichender Aussprache reicht LoRA oft nicht, bei Dialekt schon; beides ist
eine Achse des Auftrags, kein zweiter Codepfad.

**5. Was Stunden dauert, läuft in einem eigenen Container; was Sekunden
dauert, dort, wo die Anfrage ist - auf der Karte, wenn eine da ist.** Das
Training braucht Gigabyte an Abhängigkeiten und darf keinen Webdienst
aufhalten; es hängt über ein Verzeichnis an (`data/snapshots/`). Die Erkennung
hängt an einer laufenden Anfrage und nimmt die Karte im Webprozess. Worauf
erkannt wird, entscheidet eine Stelle (`wortlaut/rechenwerk.py`) für
„schreiben", die Auswertung in „hören" und die Bewertung eines Laufs - ihre
Rechenzeiten stehen in einer Tafel und sind nur so vergleichbar.

**6. Genau ein Schreiber je Datenbestand.** `hören` schreibt den Korpus,
`lernen` liest ihn. `lernen` schreibt die Registry, `schreiben` liest sie.

**7. Keine Anmeldung - aber ein Sprecher.** Die Zielperson kann schlecht lesen
und schreiben. Jede App leitet den Sprecher aus dem Zugang ab, den der Browser
vorlegt; alle drei liegen unter einer Domain und teilen den `localStorage`,
also genügt ein persönlicher Link, einmal geöffnet.

**8. Jede Entscheidung hat genau einen Ort.** Welches Modell gilt, wird in
`lernen` entschieden - unter **Modelle**, wo die Zahlen stehen, oder mit
`make release`, beides über dieselbe Stelle (`services/freigabe.py`).
`schreiben` liest die Freigabe und zeigt sie an.

**9. Ein Zugang sagt, wem etwas gehört - nicht, was es kosten darf.** Der
Sprecherzugang liegt bei jedem, der aufnimmt. Wo ein Weg mehr kostet als
Zusehen, steht ein zweites Geheimnis davor: der Trainerschlüssel
(`WORTLAUT_TRAINER_KEY`, `X-Trainer-Key`) vor Beauftragen und Neustart eines
Laufs, der Bearbeitungsschlüssel (`WORTLAUT_EDITOR_KEY`, `X-Editor-Key`) vor
jedem Weg des Zuschnitts - dort auch vor den lesenden, denn schon die Ansicht
ist die Werkbank. Leer heißt abgeschaltet, nicht offen.

---

## Projektstruktur

```
wortlaut/
├── Dockerfile                     # ein Abbild für alle drei Apps
├── compose.yaml
├── Makefile                       # test, dev, migrate, augmentieren, trainer, train
├── pyproject.toml
├── conftest.py                    # geteilte Testbausteine
├── .env.example
│
├── apps/
│   ├── gesamt.py                  # alle drei Apps in einem Prozess
│   ├── hoeren/
│   │   ├── Dockerfile             # „hören" allein
│   │   ├── backend/
│   │   │   ├── main.py, config.py, deps.py
│   │   │   ├── api/               # speakers, zugang, admin, konto, sources,
│   │   │   │                      # prompts, recordings, zuschnitt, progress,
│   │   │   │                      # auswertung, intake, sprachen, system
│   │   │   ├── services/          # prompt_queue, quality, zuschnitt, augmentierung,
│   │   │   │                      # auswertung, vorlesen, uebersicht, pin,
│   │   │   │                      # export, ausleitung, loeschung
│   │   │   └── db/                # models.py, migrations/
│   │   ├── frontend/src/routes/   # Verwaltung, Quelle, Aufnahme, Fortschritt,
│   │   │                          # Auswertung, MeineDaten, Einsicht, Zuschnitt,
│   │   │                          # Editieren
│   │   └── tests/
│   │
│   ├── lernen/
│   │   ├── backend/
│   │   │   ├── main.py, config.py, deps.py   # keine eigene Datenbank
│   │   │   ├── api/               # aufteilung, laeufe, modelle
│   │   │   └── services/          # aufteilung, auftraege, kernauswahl,
│   │   │                          # messwerte, vergleich
│   │   ├── frontend/src/routes/   # Aufteilung, Training, Lauf, Modelle
│   │   ├── training/              # was auf der Karte läuft - eigenes Abbild
│   │   │   ├── Dockerfile
│   │   │   ├── laeufer.py         # nimmt Aufträge, einen nach dem anderen
│   │   │   ├── finetune.py        # Kreuzvalidierung, dann Mitteln und Eintragen
│   │   │   ├── daten.py           # Manifest → Merkmale und Marken
│   │   │   ├── klangwandel.py     # Augmentierung zur Laufzeit
│   │   │   ├── tempowahl.py       # Vorspulfaktor schätzen oder suchen
│   │   │   ├── abschluss.py       # Checkpoint-Mittel und WiSE-FT
│   │   │   ├── ausgangsstand.py   # auf einem trainierten Stand aufsetzen
│   │   │   ├── bewerten.py        # Faltungen messen, Kern wählen, Stand eintragen
│   │   │   ├── karte.py           # auf eine belegte Karte warten
│   │   │   ├── endmodell.py       # das Mittel der Faltungen, Ausreißer draußen
│   │   │   └── rezepte/           # whisper_full.yaml, whisper_lora.yaml
│   │   └── tests/
│   │
│   └── schreiben/
│       ├── Dockerfile             # „schreiben" allein
│       ├── backend/
│       │   ├── main.py, config.py, deps.py
│       │   ├── api/               # sessions, segments, model, outbox
│       │   ├── services/          # segmenter, outbox
│       │   └── db/
│       ├── frontend/src/routes/   # Aufnahme, Ergebnis
│       └── tests/
│
├── packages/
│   ├── wortlaut/src/wortlaut/     # Python-Bibliothek aller Apps
│   │   ├── audio.py               # 16 kHz mono, Pegel, Schnitt, Stimmgrenzen
│   │   ├── augmentierung.py       # die gemessenen Fassungen einer Aufnahme
│   │   ├── corpus.py              # Korpus-Layout
│   │   ├── laeufe.py              # Laufverzeichnis, Achsen, Optionscode
│   │   ├── registry.py            # Modellstände und Freigabe
│   │   ├── metriken.py            # WER, CER, MER, WIL, Genauigkeit
│   │   ├── streuung.py            # Bootstrap-Bereiche und gepaarte Vergleiche
│   │   ├── rechenwerk.py          # worauf erkannt wird
│   │   ├── tempo.py               # Vorspulen ohne Tonhöhenänderung
│   │   ├── sprachen.py            # die unterstützten Sprachen
│   │   ├── vorlesen.py            # Sprachsynthese, Motor austauschbar
│   │   ├── zugang.py              # Sprecherzugang: Form, Prüfwert, Prüfung
│   │   ├── einstellungen.py       # was alle Apps gleich aus der Umgebung lesen
│   │   ├── db.py, ids.py, storage.py, sicherung.py, systemlage.py, web.py
│   │   ├── text/                  # llm, upload, ocr, chunker
│   │   └── whisper/               # local (faster-whisper), remote
│   │
│   └── ui/                        # geteilte Svelte-Komponenten
│       ├── Rahmen.svelte          # Kopf, Inhalt, Fuß, Menü jeder App
│       ├── apps.ts                # Apps, Reiter, Menü, was sich ausblenden lässt
│       ├── lage.svelte.ts         # Route und Zugang - ein Zustand für alle
│       ├── zugang.ts, wer.ts, pin.svelte.ts, api.ts, route.ts, reiter.ts
│       ├── Audio.svelte, Darstellung.svelte, System.svelte, Zugangsdaten.svelte
│       ├── Recorder.svelte, Mikrofontest.svelte, mikrofon.ts, speak.ts
│       ├── Pegelverlauf.svelte, ausschnitt.ts, Textvergleich.svelte, diff.ts
│       └── zeit.ts, einstellungen.svelte.ts, app.css, …
│
├── scripts/                       # migrate, augmentieren, varianten_aufraeumen,
│                                  # vorlesen, importieren, paare_teilen,
│                                  # folge_nachtragen, restore, purge_speaker
├── tests/                         # was keine einzelne App betrifft
├── docs/
└── data/                          # nicht im Git
```

---

## Erste Nahtstelle: der Korpus

Ein Verzeichnis je Sprecher, kein Dienst. `hören` schreibt, `lernen` liest;
SQLite im WAL-Modus erlaubt gleichzeitige Leser.

```
data/korpus/<sprecher_id>/
├── hoeren.sqlite                            # Vorlagen, Aufnahmen, Sitzungen, Messwerte
├── audio/
│   ├── <aufnahme_id>.wav                    # was gesprochen wurde, 16 kHz mono PCM
│   ├── varianten/<aufnahme_id>.<fassung>.wav   # abgewandelt, gerechnet
│   └── zuschnitt/<aufnahme_id>.wav          # beschnitten, wenn jemand schnitt
└── vorlesen/<vorlage>.<stimme>.wav          # vom Server vorgelesene Sätze
```

`audio/` enthält genau, was in `recordings.blob` steht - was ein Mensch
gesprochen hat. Alles darunter ist abgeleitet und lässt sich neu rechnen.

**Der Zuschnitt gilt überall.** Gibt es zu einer Aufnahme einen Zuschnitt,
arbeitet jede App mit ihm: Auswertung, Trainingsmanifest, Datensatz, Anhören.
Die Regel steht an einer Stelle (`apps/hoeren/backend/services/zuschnitt.py`,
`arbeitsblob`). Das Original wird nie überschrieben; geschnitten wird immer aus
ihm, verlustfrei auf ganze Abtastwerte, nach außen gerundet.

**Der Zuschnitt steckt in der Sicherung, die Varianten nicht.** Beide ließen
sich neu rechnen, aber nur `hören` darf in den Korpus schreiben. Eine fehlende
Variante holt sich die Auswertung selbst; den Zuschnitt braucht auch `lernen`,
das nichts nachschneiden darf.

Eine Datenbank je Sprecher: `lernen` liest eine Datei, eine Löschung entfernt
ein Verzeichnis, und jeder Weg in `hören` braucht seinen Sprecher.

**Quellen und Gewichte.** `quelle` ist `vorlage` oder `korrektur`. Korrekturen
aus `schreiben` sind abgenickte Maschinenausgaben und gehen mit geringerem
Gewicht ins Training - fest oder aus ihren Anläufen, je nach Auftrag. Im
Manifest eines Laufs kommt `selbst` dazu: unbestätigte Diktate, die der
Trainer selbst beschriftet. **Modi:** `gelesen` und `nachgesprochen` aus `hören`,
`frei` aus `schreiben`; `GET /api/progress` zählt sie getrennt.

---

## Zweite Nahtstelle: das Laufverzeichnis

`lernen` legt je Auftrag ein Verzeichnis an; der Trainer schreibt dort mit.

```
data/snapshots/
├── karte.json                # vom Trainer: seine Karte - „lernen" bietet an, was passt
└── <job_id>/
    ├── sprecher.txt          # die Sprecher-ID - für die Löschung
    ├── manifest.jsonl        # der eingefrorene Korpus: eine Zeile je Probe und Fassung
    ├── kernauswahl.json      # nur bei Kernauswahl
    ├── auftrag.json          # zuletzt geschrieben - erst damit ist der Lauf offen
    ├── zustand.json          # vom Trainer: Status, Stufe, Faltung, Zuschnitt
    ├── fortschritt.jsonl, bewertung.jsonl, protokoll.txt
    └── halt                  # der Wunsch, anzuhalten
```

```json
{"audio":"audio/zuschnitt/rec_01J8….wav","text":"…","quelle":"vorlage","modus":"gelesen",
 "variante":"original","dauer_s":4.8,"gewicht":1.0,"faltung":3,"recording_id":"rec_01J8…"}
```

Der Schnappschuss macht einen Lauf reproduzierbar, während weiter aufgenommen
wird. `sprecher.txt` lässt `scripts/purge_speaker.py` ihn finden, ohne das
Manifest zu deuten. Die Einzelheiten stehen in `wortlaut/laeufe.py`, der
Zuschnitt auf die Karte in `wortlaut/kartenplan.py`. `karte.json` trägt keine
Stimmdaten und gehört keinem Sprecher.

---

## Dritte Nahtstelle: die Registry

Ein Modellstand ist ein Verzeichnis, das sich kopieren und sichern lässt.

```
data/modelle/<sprecher_id>/
├── freigabe.json               # welches Modell dieser Mensch benutzt
└── <version>/
    ├── manifest.json
    └── ct2/                    # für faster-whisper
```

```json
{
  "id": "spr_7f2a/20260912T1420-medium-lora-original-beides-voll-geduldig-2.25x",
  "sprecher_id": "spr_7f2a",
  "basismodell": "openai/whisper-medium",
  "methode": "lora", "daten": "original", "auswahl": "alle",
  "abschluss": "beides", "augmentierung": "voll", "dauer": "geduldig",
  "tempowahl": "optimal", "tempo": 2.25,
  "abschluss_bericht": { "art": "beides", "alpha": 0.2, "…": "…" },
  "kreuzvalidierung": { "durchgaenge": 6.0, "plan": 60.0, "alpha": 0.2, "…": "…" },
  "pruefung": { "stichprobe": 12, "wer_median": 0.21, "auffaellig": false, "…": "…" },
  "metriken": { "wer": 0.146, "cer": 0.061, "genauigkeit": 81.4, "streuung": { "…": "…" } },
  "job_id": "job_01J8…",
  "status": "fertig"
}
```

Die Version nennt Zeit, Grundmodell (außer `small`), Methode und Datensatz,
dahinter jede Achse, die nicht auf ihrer Vorgabe steht, zuletzt das Tempo.
Angezeigt wird ein Stand mit seiner Kurzkennung (`K7M2Q`,
`registry.kurzkennung`) und seinem Optionscode (siehe
[lernen](lernen.md#der-optionscode)).

### Die Freigabe

Höchstens ein Modell je Sprecher ist freigegeben; mit ihm diktiert
`schreiben`. Freigeben lässt sich auch ein unverändertes Grundmodell, deshalb
steht die Freigabe in einer eigenen Datei:

```json
{ "ref": "spr_7f2a/20260912T1420-lora-original" }
```

Eine Standkennung `<sprecher_id>/<version>` oder ein Grundmodellname wie
`medium` - unterscheidbar am Schrägstrich. Leer nimmt die Freigabe zurück. Die
Manifeste führen ihren `status` (`fertig`, `active`, `zurueckgezogen`) mit,
damit ein weggetragenes Verzeichnis zeigt, was es war; gelesen wird die
Freigabedatei.

### Welches Modell `schreiben` lädt

1. `WORTLAUT_MODELL_REF`, falls gesetzt - ein Stand für alle, zum Erproben.
2. Die Freigabe dieses Sprechers.
3. Sonst das Grundmodell aus `WORTLAUT_ASR_MODELL`.

Die Zeile unter dem Aufnahmeknopf nennt dauerhaft, welches Modell arbeitet.

---

## Datenmodell

**hören** (je Sprecher eine Datenbank)

| Tabelle | Zweck |
|---|---|
| `speakers` | Profil, Sprache, Prüfwert von Zugang und PIN - genau eine Zeile |
| `text_sources` | LLM-Auftrag, hochgeladener oder erkannter Text, Korrektur |
| `prompts` | eine Sprecheinheit, fortlaufende Position über alle Quellen |
| `sessions` | Aufnahmesitzung |
| `recordings` | Blob, Messwerte, Modus, Status, Zuschnittgrenzen, Kennung aus „schreiben" |
| `erkennungen` | je Aufnahme, Modell und Fassung eine Messung, mit Rechenwerk und Herkunft |

**lernen** hat keine Datenbank. Läufe und Stände sind Verzeichnisse, die
Faltungen folgen dem Korpus und stehen im Manifest; eine Tabelle daneben wäre
eine zweite Wahrheit über dasselbe.

**schreiben**

| Tabelle | Zweck |
|---|---|
| `sessions` | eine Diktiersitzung |
| `segments` | Text, Reihenfolge, Audio, Herkunft, Anläufe |
| `outbox` | offene Korrekturen mit Wiederholungszähler |

SQLAlchemy 2.0 mit typisierten Modellen, Schemaänderungen als nummerierte
`.sql`-Dateien. Angewendet werden sie beim Anlegen eines Sprechers, beim ersten
Zugriff auf seine Datenbank (`deps.engine_fuer`) und mit `make migrate` für
alle auf einmal. Ein Update braucht also keinen Handgriff.

Spalten mit mehr Bedeutung als ihr Name:

- `prompts.position` läuft über **alle** Quellen eines Sprechers; eine neue
  Quelle hängt hinten an.
- `recordings.externe_id` ist die Abschnittskennung aus `schreiben` und
  eindeutig - der Postausgang darf beliebig oft wiederholen.
- `recordings.anlaeufe`: nur bei Korrekturen, wie oft der Abschnitt in
  `schreiben` gesprochen wurde - 1 heißt unverändert bestätigt. Teile erben
  die Zahl.
- `recordings.zuschnitt_start_s`, `…_ende_s`: Grenzen des Zuschnitts, NULL
  heißt ungeschnitten. Der Pfad folgt aus der Kennung; `dauer_s` bleibt die
  des Originals.
- `recordings.sortierschluessel`: leer, außer bei Teilen einer geteilten
  Aufnahme (`<id des Originals>.1`, `.2`). Sortiert wird nach `erstellt`, dann
  nach `COALESCE(sortierschluessel, id)` - ein Original steht vor seinen
  Teilen, und `zuschnitt.stamm` findet so die Verwandtschaft.

---

## Technologien

| Bereich | Wahl | Warum |
|---|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn | das ML-Ökosystem ist Python |
| Datenbank | SQLite (WAL) | ein Server, ein Sprecher je Datei; Sichern über die Backup-Schnittstelle |
| Frontend | Svelte 5, Vite, TypeScript | kompiliert weg, leicht auf schwachen Geräten |
| Aufnahme | `MediaRecorder` (Opus), serverseitig ffmpeg → 16 kHz mono WAV | Browser liefern kein WAV |
| Vorlesen | Piper auf dem Server, sonst Web Speech API | gleicher Klang auf jedem Gerät; ohne Stimme liest der Browser |
| ASR | faster-whisper, `int8_float16` auf der Karte, sonst `int8` | schnell auf beidem; mehrere Modelle passen gleichzeitig in den Speicher |
| ASR entfernt | OpenAI-kompatibler Endpunkt | ein Adapter für mehrere Anbieter |
| Training | HF Transformers, PEFT, Accelerate | Standardrezept für Whisper |
| Zeichenerkennung | Tesseract, lokal | Vorlagen vom Foto, ohne dass ein Bild das Haus verlässt |
| Diagramme | Apache ECharts, nachgeladen | Finger und Maus, gemischte Reihen, gekoppelte Diagramme |
| Textquelle | LLM über einen Adapter, OpenAI-kompatibel oder Anthropic | bedient ein lokales Ollama wie bezahlte Anbieter |
| Jobs | ein Verzeichnis je Auftrag, ein Läufer | kein Broker für eine Schlange mit selten mehr als einem Eintrag |
| Proxy | der Reverse Proxy des Wirts | TLS und Domain gehören zur Maschine |
| Auth | je Sprecher ein Zugang, der die Kennung trägt; Token für Verwaltung und Aufsicht | die Bindung an den Korpus zieht der Server |
| Tests | pytest, FastAPI-TestClient | echte SQLite-Dateien, echte Endpunkte |
| Werkzeug | uv | eine Abhängigkeitsdatei, ein Befehl |

---

## Bewusst nicht enthalten

- **Phonetisch ausgewogene Vorlagen.** LLM-Text ist flüssig, aber phonetisch
  beliebig. Eine feste, phonetisch abgedeckte Satzliste als dritte Quelle
  wäre für Sprechstörungen wirksamer und steht auf der Liste.
- **Rollen und Mandanten.** Es gibt drei Arten von Aufrufer - Sprecher,
  Verwaltung, Aufsicht - und keine Rechtematrix. Jede ist ein Token, keine
  ein Konto.
- **Streaming-Transkription.** Die Korrekturschleife arbeitet abschnittsweise.
- **Diarisierung, Zeitstempel auf Wortebene.** Ein Sprecher, kurze Abschnitte.
- **Frontend-Tests.** `npm run check` prüft die Typen; den Weg im Browser
  deckt der [manuelle Test](manueller-test.md) ab.
