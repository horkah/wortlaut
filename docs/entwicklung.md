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

## Wie hier benannt wird

Alles ist deutsch: Bezeichner, Kommentare, Commits, Oberfläche. Das ist keine
Marotte, sondern folgt aus dem Gegenstand - die Menschen, für die diese App
gebaut ist, lesen deutsch, und ein Feld, das in der Ansicht anders heißt als im
Code, ist eine Stelle, an der jemand suchen muss.

**Zwei Ausnahmen, und sie sind beide erlebt.**

**Kein erfundenes Deutsch, wo das englische Wort hier gebräuchlich ist.**
„Basislinie" oder „Grundlinie" für das, was jeder Baseline nennt, ist keine
Übersetzung, sondern eine zweite Vokabel, die der Leser erst auf die erste
zurückführen muss. Dasselbe gälte für LoRA, Token, Commit oder Cache. Die Probe
ist nicht, ob sich ein deutsches Wort bilden lässt - das lässt es sich immer -,
sondern ob es draußen jemand benutzt. Im September 2026 fiel „Grundlinie"
deshalb an 82 Stellen zugunsten von „Baseline".

**Zeitstempel formatiert nur der Browser.** Der Server legt sie als ISO-8601
in UTC ab und schickt sie genauso hinaus; lesbar gemacht werden sie in
`packages/ui/zeit.ts`. Er kennt die Zeitzone des Lesers nicht - auch dann
nicht, wenn er zufällig im selben Land steht. Im September 2026 stand derselbe
Augenblick in der Trainingsliste als 14:38 und im Steckbrief als 12:38, weil
der eine Wert im Browser gerechnet und der andere im Server mit `strftime`
geschrieben wurde. Über Mitternacht springt dabei sogar das Datum.

**Keine Beschriftung, die eine Anzahl festschreibt.** „Beste der vier" stand
über einer Spalte, weil es einmal vier Fassungen einer Aufnahme gab. Dann
fielen zwei Abwandlungen weg, und die Überschrift log - ohne dass ein Test
darauf ansprang, denn sie war richtiger Text an falscher Stelle. Eine
Beschriftung soll sagen, **was** dort steht, nicht wie viele es sind:
„Bestwert". Wo die Zahl wirklich gebraucht wird, kommt sie aus den Daten und
nicht aus dem Satz.

---

## Was allen drei Apps gemeinsam ist

Die drei Oberflächen teilen sich `packages/ui/`. Dort liegt, was in allen
dreien gleich aussehen und gleich heißen muss - und zwar als **eine**
Definition und nicht als drei gleichlautende:

* **Die übergreifenden Menüpunkte** (`uebergreifendePunkte` in `apps.ts`).
  „Meine Daten" oder „Sprecher", je nachdem wer angemeldet ist, und immer die
  „Zugangsdaten". Welche Adresse ein Punkt bekommt, rechnet die Funktion aus:
  In „hören" sind es Hash-Routen, von außen volle Adressen, denn diese
  Ansichten liegen in „hören".
* **Die Regel für „kein Zugang"** (`ohneZugang`). Weist der Browser nichts
  vor, steht überall derselbe eine Satz statt einer Ansicht, deren Anfragen
  sämtlich abgewiesen würden - ausgenommen die Zugangsdaten selbst, denn
  dorthin führt der Hinweis.

**Warum das hier steht.** Bis September 2026 baute sich jede App diese Listen
selbst, und sie waren verschieden: „hören" führte für die Aufsicht „Sprecher",
die anderen beiden nichts; „Meine Daten" hatte in zweien ein `href` und im
dritten nicht; und den Hinweis auf die Zugangsdaten kannten nur zwei - in
„hören" landete man ohne Zugang auf der Verwaltung, deren Anfragen alle
scheiterten.

Keine dieser Abweichungen war je entschieden worden. Sie waren entstanden,
weil dieselbe Überlegung dreimal angestellt wurde und zweimal etwas anders
ausfiel. Das ist die Art Redundanz, die dieses Verzeichnis verhindern soll:
nicht doppelter Code, sondern doppelte **Entscheidungen**.

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
| `apps/lernen/tests/` | Aufteilung und ihre Beständigkeit, Aufträge, der Vergleich mit der Baseline, die Modelltabelle auf gemeinsamen Testaufnahmen, die Freigabe - und dass diese App keinen Weg hat, der in den Korpus schreibt |
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
