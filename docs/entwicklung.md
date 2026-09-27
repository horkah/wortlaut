# Entwicklung

Python 3.12 mit [uv](https://docs.astral.sh/uv/), Node 20 oder neuer und
**ffmpeg im Pfad** - ohne ffmpeg scheitert jeder Aufnahme-Upload.

```bash
cp .env.example .env
uv sync                      # Abhängigkeiten und die Bibliothek `wortlaut`
make test
```

`make install APP=<app>` holt die Frontend-Abhängigkeiten, `make dev APP=<app>`
startet Backend und Vite nebeneinander. Alle drei dürfen gleichzeitig laufen:

| App | Backend | Vite | aufgerufen wird |
|---|---|---|---|
| `hoeren` | `:8000` | `:5173` | `http://localhost:5173` |
| `schreiben` | `:8001` | `:5174` | `http://localhost:5174/schreiben/` |
| `lernen` | `:8002` | `:5175` | `http://localhost:5175/lernen/` |

Der Pfad gehört zur Adresse, weil die App dort liegt; ohne ihn bleibt die
Seite leer. Vite leitet die API an das eigene Backend weiter, es braucht also
keine CORS-Regeln. `schreiben` und `lernen` reichen `/api` an `hören` durch
(Zugang, PIN), `lernen` dazu `/schreiben/api` (was geladen ist), und `hören`
reicht `/schreiben` an dessen Vite.

Für `schreiben`:

```bash
uv sync --extra asr               # faster-whisper
uv sync --extra asr --extra gpu   # dazu die CUDA-Bibliotheken für CTranslate2
```

Ohne Karte erkennt faster-whisper auf dem Prozessor. Das erste Diktat lädt
das Modell herunter. `WORTLAUT_INTAKE_URL` zeigt in der Entwicklung auf
`http://localhost:8000/api/korpus/intake`.

Für Vorlagen vom Foto: `uv sync --extra ocr` und Tesseract im Pfad (siehe
[Betrieb](betrieb.md#voraussetzungen)).

`make migrate` schreibt alle Korpora auf einmal fort; nötig ist es nicht, jede
Datenbank holt sich ihr Schema beim ersten Zugriff.

---

## Konventionen

**Alles ist deutsch:** Bezeichner, Kommentare, Commits, Oberfläche. Die
Menschen, für die die App gebaut ist, lesen deutsch, und ein Feld, das in der
Ansicht anders heißt als im Code, ist eine Stelle, an der jemand suchen muss.

**Kein erfundenes Deutsch.** Wo ein englisches Wort gebräuchlich ist, bleibt
es: Baseline, LoRA, Token, Commit, Cache. Die Probe ist, ob draußen jemand das
deutsche Wort benutzt.

**Zeitstempel formatiert nur der Browser.** Der Server legt sie als ISO-8601
in UTC ab und schickt sie so hinaus; lesbar werden sie in `packages/ui/zeit.ts`.
Der Server kennt die Zeitzone des Lesers nicht.

**Keine Beschriftung, die eine Anzahl festschreibt.** „Bestwert", nicht „Beste
der vier" - die Zahl ändert sich, und die Überschrift lügt dann, ohne dass ein
Test anschlägt. Wo eine Zahl gebraucht wird, kommt sie aus den Daten.

**Nur der aktuelle Stand.** Code, Kommentare, Doku und Oberfläche beschreiben,
was gilt und warum - nicht, wie es vorher war. Die Geschichte steht in der
Commit-History; ausgenommen sind datierte Berichte.

**Eine Entscheidung, ein Ort.** Die drei Oberflächen teilen `packages/ui/`:
das Menü (`menuePunkte` in `apps.ts`), die Ansichten dahinter
(`Rahmen.svelte`), die Reiter (`REITER` in `apps.ts`) und die Regel für „kein
Zugang". Eine App ordnet ihren Pfaden nur ihre Ansichten zu; was sonst in
jeder App gleich sein muss, steht einmal da. Doppelter Code ist lästig,
doppelte Entscheidungen fallen auseinander.

---

## Der Trainer

Die Oberfläche von `lernen` beauftragt und zeigt; gerechnet wird im Trainer,
und der braucht eine Karte:

```bash
docker compose --profile training up -d training   # im Betrieb
make trainer                                       # auf dieser Maschine
make train JOB=job_01J8…                           # einen Auftrag ohne Warteschlange
```

`make trainer` setzt `torch`, `transformers`, `peft` und `accelerate` voraus.
Sie stehen nicht in den Abhängigkeiten des Projekts, sondern im Abbild
`apps/lernen/training/Dockerfile` - Gigabyte an CUDA gehören nicht in jedes
`uv sync`. Ohne Karte lässt sich alles außer dem Rechnen benutzen; Aufträge
sammeln sich und gehen nicht verloren.

---

## Tests

```bash
make test
cd apps/<app>/frontend && npm run check      # Typen im Frontend
```

Ohne GPU, ohne Netz, ohne Mikrofon.

| Ort | prüft |
|---|---|
| `packages/wortlaut/tests/` | Chunker, Textformate, Zeichenerkennung, Audio, Ablage, Migrationen, Registry, Laufverzeichnis, Fehlerraten, Streuung |
| `apps/hoeren/tests/` | Endpunkte gegen echte SQLite-Dateien; die Trennung der Korpora; Aufsicht, Sicherung und Wiederherstellung; Zuschnitt; der Auswertungslauf ohne Whisper |
| `apps/lernen/tests/` | Faltungen, Aufträge, Kernauswahl, Vergleich mit der Baseline, Modelltafel, Freigabe, Anhalten - und dass diese App nicht in den Korpus schreibt |
| `apps/schreiben/tests/` | Diktat und Abschnittsersatz, Postausgang, welches Modell geladen wird |
| `tests/` | was keine einzelne App betrifft, etwa `apps/gesamt.py` |

**Nachgebaut wird so wenig wie möglich.** Echte SQLite-Dateien, echte Dateien,
echte Endpunkte. Ersetzt ist nur, was Geld, Netz oder eine GPU kostet: der
LLM-Anbieter, Whisper, der Weg von `schreiben` zurück zu `hören`.

**ffmpeg wird einmal wirklich benutzt:** Ein Test schickt eine Opus-Datei wie
aus dem Browser an `POST /api/recordings` und prüft 16 kHz mono im Korpus.
Fehlt ffmpeg, werden diese Tests übersprungen. Dasselbe gilt für Tesseract.

Das Frontend hat keine eigenen Tests; den Weg im Browser deckt der
[manuelle Test](manueller-test.md) ab.
