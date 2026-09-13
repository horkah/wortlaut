# Entwicklung

Voraussetzungen: Python 3.12 mit [uv](https://docs.astral.sh/uv/), Node 20 oder
neuer für das Frontend - und **ffmpeg im Pfad**, sonst schlägt jeder
Aufnahme-Upload fehl.

```bash
cp .env.example .env
uv sync                      # Abhängigkeiten und die Bibliothek `wortlaut`
make test                    # Testlauf, je nach Hardware 5-50 Sekunden
```

`make install APP=<app>` holt die Frontend-Abhängigkeiten; `make dev APP=<app>`
startet Backend und Vite nebeneinander. Alle drei dürfen gleichzeitig laufen:

| App | Backend | Vite | aufgerufen wird |
|---|---|---|---|
| `hoeren` | `:8000` | `:5173` | `http://localhost:5173` |
| `schreiben` | `:8001` | `:5174` | `http://localhost:5174/schreiben/` |
| `lernen` | `:8002` | `:5175` | `http://localhost:5175/lernen/` |

```bash
make install APP=hoeren
make dev APP=hoeren
```

Die Pfade stehen mit in der Adresse, weil die Apps dort liegen - in der
Entwicklung wie im Betrieb. Vite leitet `/api` an das jeweilige Backend weiter,
deshalb gibt es keine CORS-Regeln; `lernen` reicht zusätzlich `/api` an `hören`
durch (der Zugang und die PIN stehen im Korpus) und `/schreiben/api` an
`schreiben` (die Modellübersicht zeigt, was dort geladen ist).

Für `schreiben` braucht es einmal mehr:

```bash
uv sync --extra asr          # zusätzlich faster-whisper (nur für WORTLAUT_ASR=local)
```

Beim ersten Diktat lädt faster-whisper sein Modell herunter; das dauert einmalig
und braucht Netz.

Erkannt wird auf der Karte, wenn eine da ist - `uv sync --extra asr --extra gpu`
legt die CUDA-Bibliotheken dazu, die CTranslate2 dafür braucht. Ohne sie
(oder ohne Karte) fällt die Erkennung auf den Prozessor zurück, und alles
funktioniert unverändert, nur langsamer. Welche Einstellung das steuert, steht
in [Konfiguration](konfiguration.md#rechenwerk---worauf-erkannt-wird).

`make migrate` schreibt alle Korpora auf einmal fort. Es ist kein erster
Schritt: Neue Sprecher bekommen ihre Datenbank beim Anlegen, bestehende werden
beim ersten Zugriff fortgeschrieben. Es ist der Weg, das für alle auf einmal und
vor dem ersten Aufruf zu tun - etwa um zu sehen, was ein Update am Schema
ändert.

---

## Der Trainer

Die Oberfläche von `lernen` teilt zu, beauftragt und zeigt - gerechnet wird
dort nicht. Dafür braucht es den Trainer, und der braucht eine Karte:

```bash
docker compose --profile training up -d training   # im Betrieb
make trainer                                       # auf dieser Maschine
```

`make trainer` setzt voraus, dass `torch`, `transformers`, `peft` und
`accelerate` installiert sind. Sie stehen absichtlich **nicht** in den
Abhängigkeiten dieses Projekts: Drei Gigabyte CUDA in jedem `uv sync`, damit
eine App eine Oberfläche ausliefern kann, wäre der falsche Handel. Sie stehen
im Abbild unter `apps/lernen/training/Dockerfile`.

Ohne Karte lässt sich alles außer dem Rechnen benutzen: Die Aufteilung steht,
Aufträge sammeln sich in der Warteschlange und gehen nicht verloren.

`make train JOB=job_01J8…` rechnet einen einzelnen Auftrag ohne Warteschlange -
zum Nachsehen, woran ein gescheiterter gescheitert ist.

Betrieb, Reverse Proxy und Fehlersuche stehen in [`betrieb.md`](betrieb.md).

---

## Tests

```bash
make test
```

Läuft in gut einer Sekunde: ohne GPU, ohne Netz, ohne Mikrofon.

| Ort | Prüft |
|---|---|
| `packages/wortlaut/tests/` | Chunker, Textformate, Audiomessung und -schnitt, Ablage, Migrationen, Registry, Fehlerraten |
| `apps/hoeren/tests/` | Endpunkte gegen eine echte SQLite-Datei im Temporärverzeichnis; dazu die Trennung: Der Zugang des einen öffnet den Korpus des anderen nicht, und eine fremde Kennung im Parameter endet mit 403 statt mit einem Schreibvorgang. Für die Aufsicht: dass sie ohne Token zu ist, dass ihre Sicherung sich wirklich zurückspielen lässt, und dass es keinen Weg gibt, der mehr als einen Sprecher löscht. Und: dass ein Korpus im ältesten Schemastand beim ersten Zugriff eingeholt wird, statt die Ansicht stillzulegen |
| `apps/hoeren/tests/test_auswertung.py` | Der Auswertungslauf ohne Whisper: was offen ist, was ein Fehlschlag anrichtet, dass ein zweiter Lauf nichts doppelt tut |
| `apps/lernen/tests/` | Aufteilung und ihre Beständigkeit, Aufträge, der Vergleich mit der Grundlinie, die Modelltabelle auf gemeinsamen Testaufnahmen, die Freigabe - und dass diese App keinen Weg hat, der in den Korpus schreibt |
| `apps/schreiben/tests/` | Diktat und Abschnittsersatz, Postausgang, welches Modell geladen wird |

Zwei Regeln halten den Aufwand klein und die Aussagekraft hoch:

**Nachgebaut wird so wenig wie möglich.** Die Tests sprechen mit echtem SQLite,
echten Dateien und den echten Endpunkten. Ersetzt ist nur, was Geld, Netz oder
eine GPU kosten würde: der LLM-Anbieter, ffmpeg, Whisper und der Weg von
`schreiben` zurück zu `hören`.

**ffmpeg wird trotzdem einmal wirklich benutzt.** Ein Test erzeugt eine
Opus-Datei, wie sie ein Browser liefert, schickt sie an `POST /api/recordings`
und prüft, dass im Korpus 16 kHz Mono liegen. Damit ist der Weg vom Browser bis
zur Datei einmal vollständig durchlaufen; die übrigen Aufnahmetests kommen
ohne externes Programm aus. Fehlt ffmpeg, werden diese drei Tests übersprungen
statt zu scheitern.

Was noch fehlt: das Frontend hat keine eigenen Tests. `npm run check`
(svelte-check) prüft dort bislang nur die Typen.

Den kompletten Weg im Browser - Sprecher anlegen, Textquelle, Aufnehmen,
Fortschritt - deckt kein automatisierter Test ab. Dafür gibt es eine
Schritt-für-Schritt-Anleitung zum Selbst-Durchklicken:
[`manueller-test.md`](manueller-test.md).
