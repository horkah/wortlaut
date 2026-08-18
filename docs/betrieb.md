# Betrieb

## Voraussetzungen

- Python 3.12 mit [uv](https://docs.astral.sh/uv/)
- Node 20 oder neuer (nur für das Frontend)
- **ffmpeg** im Pfad — ohne das schlägt jeder Aufnahme-Upload fehl

```bash
ffmpeg -version    # muss etwas ausgeben
```

## Entwicklung

```bash
cp .env.example .env
uv sync                      # Abhängigkeiten und die Bibliothek `wortlaut`
cd apps/hoeren/frontend && npm install && cd -
make dev APP=hoeren          # Backend auf :8000, Vite auf :5173
```

Aufgerufen wird `http://localhost:5173`. Vite leitet alles unter `/api` an das
Backend weiter, deshalb gibt es keine CORS-Regeln.

`make migrate` wird nur gebraucht, wenn nach einem Update Migrationen für
bereits bestehende Sprecher offen sind — neue Sprecher bekommen ihre Datenbank
beim Anlegen.

## Tests

```bash
make test                    # oder: uv run pytest
cd apps/hoeren/frontend && npm run check   # Typen im Frontend
```

Der Testlauf braucht weder Netz noch GPU noch Mikrofon. Ohne ffmpeg im Pfad
werden drei Tests übersprungen statt zu scheitern — die übrigen laufen
vollständig durch. Was geprüft wird, steht im
[README](../README.md#tests).

Den Weg im Browser deckt das nicht ab — dafür gibt es
[`docs/manueller-test.md`](manueller-test.md), zum Durchklicken nach jeder
Änderung an Frontend oder Endpunkten.

## Betrieb mit Compose

```bash
docker compose up -d --build
```

Der Anwendungscontainer liefert API und gebautes Frontend aus, Caddy davor
besorgt TLS. Die Daten liegen im Volume `wortlaut-data`; eine Sicherung ist
das Kopieren dieses Volumes bei angehaltenem Dienst (SQLite im WAL-Modus mag
keine Kopie mitten im Schreibvorgang).

Vite läuft dabei nicht mit — es ist reines Entwicklungswerkzeug. Das Frontend
wird beim `docker build` einmal gebaut und vom Backend mit ausgeliefert. Ein
`--host` braucht darum weder Vite noch uvicorn: der Startbefehl im Dockerfile
bindet bereits `0.0.0.0`, erreichbar von außen ist trotzdem nur Caddy.

### Auf eine Subdomain stellen

Eine Adresse für alle drei Apps, nicht eine je App: `wortlaut.example.org`.
Derzeit liegt `hören` allein auf der Wurzel und Caddy reicht alles dorthin
durch. Kommen `lernen` und `schreiben` dazu, bekommt jede App einen Pfad
(`/hoeren/`, `/lernen/`, `/schreiben/`) und der Caddyfile einen `handle_path`
je Dienst; die App-Leiste im Frontend steht schon darauf ein
(`packages/ui/apps.ts`).

1. **DNS**: einen A-Eintrag (bei IPv6 zusätzlich AAAA) von der Subdomain auf
   die öffentliche Adresse der Maschine. Vor dem ersten Start prüfen, sonst
   scheitert die Zertifikatsausstellung und Let's Encrypt drosselt Wiederholungen.

2. **`.env` auf dem Wirt**:

   ```
   WORTLAUT_DOMAIN=wortlaut.example.org
   WORTLAUT_AUTH_TOKEN=<lange Zufallszeichenkette>
   ```

   Den Token mit `openssl rand -base64 32` erzeugen. **Ohne ihn steht die App
   offen im Netz** — jeder mit der Adresse kann Sprecher anlegen, Aufnahmen
   lesen und die LLM-Textquelle auf deine Rechnung benutzen.

3. **Ports 80 und 443** in der Firewall der Maschine und, falls vorhanden, in
   der des Anbieters freigeben. Port 80 wird gebraucht, auch wenn nachher alles
   über HTTPS läuft: darüber läuft die ACME-Prüfung.

4. **Starten und nachsehen:**

   ```bash
   docker compose up -d --build
   docker compose logs -f caddy       # „certificate obtained successfully"
   curl https://wortlaut.example.org/gesundheit
   ```

`/gesundheit` verlangt bewusst keinen Token und eignet sich als Prüfpunkt für
eine Überwachung.

**HTTPS ist nicht optional.** Der Aufnahmeknopf benutzt `MediaRecorder`, und
das gibt der Browser nur in einem sicheren Kontext frei — über eine
IP-Adresse oder blankes HTTP bleibt die App unbenutzbar.

Läuft auf der Maschine bereits ein anderer Reverse Proxy auf 80/443, dann den
`caddy`-Dienst aus `compose.yaml` streichen, beim Dienst `hoeren` `expose`
durch `ports: ["127.0.0.1:8000:8000"]` ersetzen und den vorhandenen Proxy auf
`127.0.0.1:8000` zeigen lassen.

## Endpunkte

```
POST   /api/speakers                              { name, sprache, basismodell }
GET    /api/speakers
GET    /api/speakers/{id}
POST   /api/sources/llm?sprecher=…                { thema, altersspanne, umfang }
POST   /api/sources/upload?sprecher=…             multipart: datei
GET    /api/sources?sprecher=…
POST   /api/sessions?sprecher=…
GET    /api/prompts/next?sprecher=…&session=…
POST   /api/recordings?sprecher=…                 multipart: audio, prompt_id, modus, session
GET    /api/recordings/{id}/audio?sprecher=…
DELETE /api/recordings/{id}?sprecher=…
GET    /api/progress?sprecher=…
POST   /api/korpus/intake?sprecher=…              multipart: audio, text, externe_id
GET    /gesundheit                                ohne Token
```

**Warum überall `sprecher=…`:** Das Korpus hat je Sprecher eine eigene
Datenbank (`data/korpus/<sprecher_id>/hoeren.sqlite`). Ohne die Sprecher-ID
wüsste der Server nicht, welche Datei er öffnen soll. Der Parameter steht immer
in der Abfragezeichenkette — auch bei POST mit Rumpf, damit eine einzige
Abhängigkeit ihn auswerten kann.

Die interaktive API-Dokumentation liegt unter `/docs`.

## Authentifizierung

`WORTLAUT_AUTH_TOKEN` gesetzt → alle `/api`-Endpunkte verlangen
`Authorization: Bearer <token>`. Leer → offen, nur für die lokale Entwicklung
gedacht. Das Frontend fragt den Token einmal ab und legt ihn im
`localStorage` ab.

## Wenn etwas klemmt

| Symptom | Ursache |
|---|---|
| `ffmpeg ist gescheitert` beim Upload | ffmpeg fehlt oder das Format ist kaputt |
| `Unbekannter Sprecher` (404) | falsche `sprecher`-ID, oder Korpus liegt unter einem anderen `WORTLAUT_DATA_DIR` |
| `Keine Textquelle konfiguriert` | `WORTLAUT_LLM_PROVIDER` ist leer — Textupload nutzen oder Anbieter setzen |
| Aufnahmeknopf ohne Wirkung | `MediaRecorder` braucht HTTPS oder `localhost` |
| Aufnahmen sind durchweg sehr leise (Hinweis „Sehr leise") | Erst unter „Einstellungen → Mikrofon" **Automatisch einmessen** laufen lassen; das hebt den Pegel im Browser an. Bleibt es leise, siehe „Leises Mikrofon unter Linux" unten. |
| Der Pegelbalken im Mikrofontest bleibt auf „still" | Der Browser hat ein anderes Gerät geöffnet als erwartet — im Test das Mikrofon ausdrücklich auswählen. Steht dort nur „Mikrofon 1", war der Test noch nie an; die echten Namen gibt der Browser erst nach erteilter Erlaubnis heraus. |
| „Vorlesen" ohne Stimme | Browser ohne deutsche Stimme für die Web Speech API |
| Vorgelesene Stimme klingt blechern | Siehe „Bessere Vorlesestimme unter Linux" unten. Die Web Speech API nutzt die Stimmen des Betriebssystems; unter Linux ist das per Vorgabe espeak-ng. |
| `make frontend` startet ohne Fehlermeldung, aber `localhost:5173` bleibt unerreichbar | `node_modules` fehlt (`npm install` in `apps/hoeren/frontend` vergessen). `npm run dev` sucht `vite` dann über `$PATH` — auf manchen Systemen (z. B. Ubuntu/Debian) existiert dort ein gleichnamiges, aber völlig anderes Paket namens `vite` (ViTE, ein Trace-Viewer), das kommentarlos ein leeres GUI-Fenster statt des Dev-Servers öffnet. Prüfen mit `command -v vite` — zeigt der Pfad nicht auf `apps/hoeren/frontend/node_modules/.bin/vite`, fehlt die Installation. Abhilfe: `npm install` nachholen. |

## Leises Mikrofon unter Linux

Eingebaute Mikrofone sind unter Linux oft deutlich leiser als unter macOS oder
Windows — nicht weil die Hardware schlechter wäre, sondern weil dort im Treiber
eine Verstärkung sitzt, die es hier nicht gibt. Betroffen sind besonders die
Mikrofonarrays von Apple-Geräten am `snd-hda-macbookpro`-Treiber (T2).

Erst nachsehen, ob auf Systemebene überhaupt noch Luft ist:

```bash
pactl get-default-source
pactl list sources | grep -A6 'Name: alsa_input'
```

Steht dort `Volume: … / 100% / 0,00 dB` bei `Base Volume: … / 100% / 0,00 dB`,
ist der Regler bereits am Anschlag — der Eingang liefert schlicht wenig. Zwei
Wege gibt es dann:

```bash
# 1. Über die Vorgabe hinaus verstärken (PipeWire/PulseAudio können das)
pactl set-source-volume @DEFAULT_SOURCE@ 200%
```

Das gilt für alle Programme, nicht nur für wortlaut, und wird bei einigen
Treibern beim Neustart zurückgesetzt.

2. Oder die **Verstärkung** unter „Einstellungen → Mikrofon" benutzen. Sie
   wirkt nur in dieser App, überlebt den Neustart und lässt sich mit
   „Automatisch einmessen" auf die eigene Stimme einstellen.

Beides verstärkt das Rauschen des Raumes mit. Wo Aufnahmen über Stunden
entstehen sollen, bringt ein Headset oder ein Ansteckmikrofon mehr als jede
Verstärkung.

## Bessere Vorlesestimme unter Linux

Die App wählt die Stimme nicht selbst, sie bietet unter „Einstellungen" nur an,
was der Browser meldet. Unter Linux kommt das aus `speech-dispatcher`, der per
Vorgabe `espeak-ng` benutzt — verständlich, aber deutlich blechern. Für Deutsch
gibt es in den Paketquellen von Debian/Ubuntu/Mint keine RHVoice-Stimme; die
nächstbessere Stufe sind die mbrola-Stimmen.

```bash
sudo apt install espeak-ng mbrola mbrola-de6 mbrola-de7
```

`espeak-ng` gehört ausdrücklich dazu: Das Paket `libespeak-ng1` allein genügt
nicht. Das mbrola-Modul ist ein *generisches* Modul, das eine Shell-Pipeline
aufruft (`espeak-ng … | mbrola … | paplay`) und deshalb das Kommandozeilen-
programm braucht, nicht nur die Bibliothek. Fehlt es, bleibt das Modul still,
obwohl `spd-say -O` es als vorhanden anzeigt.

Danach das Modul in `/etc/speech-dispatcher/speechd.conf` einschalten — dort ist
es auskommentiert:

```
AddModule "espeak-ng-mbrola-generic" "sd_generic"   "espeak-ng-mbrola-generic.conf"
```

Zwei Fallen dabei:

* Beim Einschalten müssen die schon genutzten Module (`espeak-ng`) eingeschaltet
  **bleiben**, sonst ist gar keine Stimme mehr da.
* Das Modul bringt `DefaultVoice "en1"` mit, eine englische Stimme, die mit den
  deutschen Paketen nicht installiert wird. Ohne Sprachangabe scheitert es
  deshalb mit `cannot find file en1`. Zum Prüfen die Sprache mitgeben:

```bash
pkill speech-dispatcher                       # lädt die Konfiguration neu
spd-say -o espeak-ng-mbrola-generic -l de -y de6 "Ein Satz zur Probe"
```

Firefox fragt die Stimmenliste beim Start einmal ab: Nach Änderungen an
`speech-dispatcher` muss der Browser neu gestartet werden, ein Neuladen der
Seite genügt nicht.
