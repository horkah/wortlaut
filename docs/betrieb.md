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

Für „schreiben" dasselbe mit eigenen Ports — beide dürfen nebeneinander laufen:

```bash
uv sync --extra asr          # zusätzlich faster-whisper (nur bei WORTLAUT_ASR=local)
cd apps/schreiben/frontend && npm install && cd -
make dev APP=schreiben       # Backend auf :8001, Vite auf :5174
```

Aufgerufen wird `http://localhost:5174/schreiben/` — **mit Pfad**, weil die App
dort liegt, in der Entwicklung wie im Betrieb (`base` in ihrer
`vite.config.ts`, `BASIS` in ihrer `main.py`). Ohne den Pfad antwortet Vite mit
einer leeren Seite, das ist kein Fehler der App.

Laufen beide Apps, führt auch der Reiter „schreiben" auf `http://localhost:5173`
hinüber: Vite von „hören" reicht `/schreiben` an den Nachbarn auf 5174 durch,
wie im Betrieb der Reverse Proxy. Läuft „schreiben" nicht, steht dort ein
Verbindungsfehler — dann fehlt `make dev APP=schreiben`.

Beim ersten Diktat lädt faster-whisper sein Modell aus dem Netz; das dauert
einmalig und landet im Cache von huggingface. `WORTLAUT_ASR_MODELL=tiny` ist
die Vorgabe und läuft auch auf schwacher Hardware.

Damit die Korrekturen ankommen, muss in der `.env` `WORTLAUT_INTAKE_URL` auf
die laufende „hören"-Instanz zeigen (in der Entwicklung
`http://localhost:8000/api/korpus/intake`) und `WORTLAUT_INTAKE_TOKEN` deren
`WORTLAUT_AUTH_TOKEN` enthalten. Fehlt beides, sammelt der Postausgang die
Korrekturen, statt sie zu verwerfen.

`make migrate` wird nur gebraucht, wenn nach einem Update Migrationen für
bereits bestehende Sprecher offen sind — neue Sprecher bekommen ihre Datenbank
beim Anlegen.

## Tests

```bash
make test                    # oder: uv run pytest
cd apps/hoeren/frontend && npm run check      # Typen im Frontend
cd apps/schreiben/frontend && npm run check   # dasselbe für „schreiben"
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

**Ein Container für alles.** Darin ein uvicorn für beide Apps: „hören" auf der
Wurzel, „schreiben" unter `/schreiben` — zusammengesetzt in `apps/gesamt.py`,
gebaut vom `Dockerfile` im Wurzelverzeichnis. Compose bindet ihn an
`127.0.0.1:8000`; aus dem Netz erreichbar ist allein der Reverse Proxy des
Wirts, und der braucht genau eine Regel auf diesen Port.

Geteilt wird der Prozess, sonst nichts: Jede App behält ihre Datenbank, ihre
Ablage und ihre Zugangsregeln — die `/api`-Wege von „hören" hinter dem Token,
„schreiben" ohne (Grundentscheidung 7). Auch der Weg der Korrekturen bleibt die
API und nicht das Dateisystem (Grundentscheidung 6); er zeigt nur auf
`127.0.0.1` statt in ein Containernetz, deshalb steht `WORTLAUT_INTAKE_URL` in
der `compose.yaml` auf `http://127.0.0.1:8000/api/korpus/intake`. Verklemmen
kann das nicht: Der Postausgang sendet in einem Arbeitsfaden, während die
Ereignisschleife die eingehende Lieferung annimmt.

Die Daten liegen im Volume `wortlaut-data` — `korpus/` gehört „hören",
`diktate/` gehört „schreiben". Eine Sicherung ist das Kopieren dieses Volumes
bei angehaltenem Dienst (SQLite im WAL-Modus mag keine Kopie mitten im
Schreibvorgang). Das Whisper-Modell liegt darin unter `.cache/huggingface`;
ohne das lüde jeder Neustart erneut herunter — der erste Start dauert deshalb
einige Minuten, worauf die `start_period` der Healthcheck-Prüfung Rücksicht
nimmt.

Vite läuft nicht mit — es ist reines Entwicklungswerkzeug. Beide Frontends
werden beim `docker build` einmal gebaut und vom Prozess mit ausgeliefert.

### Bevor die Korrekturen ankommen: der Sprecher

„schreiben" gehört zu genau einer Person, und ihre Kennung vergibt „hören"
beim Anlegen des Sprechers. Beim ersten Aufbau also erst den Sprecher anlegen,
dann seine Kennung in die `.env` schreiben und den Container neu starten:

```bash
curl -X POST https://wortlaut.example.org/api/speakers \
  -H "Authorization: Bearer $WORTLAUT_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Vorname","sprache":"de","basismodell":"tiny"}'
# → {"id":"spr_…"}  in die .env als WORTLAUT_SPRECHER_ID
docker compose up -d
```

Fehlt die Kennung, sammelt der Postausgang die Korrekturen, statt sie zu
verwerfen — nachzuholen mit „Noch einmal senden" in der Oberfläche.

### Getrennte Container

Wer die Apps auseinanderhalten will — eigene Neustarts, ein schlankes Abbild
für „hören" ohne CTranslate2 —, nimmt statt dessen die beiden Dockerfiles
unter `apps/`, je einen Dienst daraus, und gibt dem Proxy zwei Regeln
(`/schreiben/` → „schreiben", `/` → „hören"). Am Code ändert das nichts: Die
Pfade bringen die Apps selbst mit, `apps/gesamt.py` fügt sie nur zusammen.

### Auf eine Subdomain stellen

Eine Adresse für alle drei Apps, nicht eine je App: `wortlaut.example.org`.
`hören` ist der Einstieg und liegt auf der Wurzel, `schreiben` unter
`/schreiben/`. Für `lernen` kommt später ein weiterer Pfad nach demselben
Muster dazu.

**Der Proxy schneidet nichts ab.** Jede App hängt selbst unter ihrem Pfad —
Oberfläche *und* API (`BASIS` in `apps/schreiben/backend/main.py`, `base` in
ihrer `vite.config.ts`). Der Proxy reicht den Weg unverändert weiter; eine
Regel, die `/schreiben/` entfernt, macht die App unerreichbar.

Wer eine App verschiebt, ändert drei Stellen zusammen: `BASIS` im Backend, das
`base` in der `vite.config.ts` und den Pfad in `packages/ui/apps.ts`.

1. **DNS**: einen A-Eintrag (bei IPv6 zusätzlich AAAA) von der Subdomain auf
   die öffentliche Adresse der Maschine. Vor dem ersten Start prüfen, sonst
   scheitert die Zertifikatsausstellung und Let's Encrypt drosselt Wiederholungen.

2. **`.env` auf dem Wirt**:

   ```
   WORTLAUT_AUTH_TOKEN=<lange Zufallszeichenkette>
   ```

   Den Token mit `openssl rand -base64 32` erzeugen. **Ohne ihn steht die App
   offen im Netz** — jeder mit der Adresse kann Sprecher anlegen, Aufnahmen
   lesen und die LLM-Textquelle auf deine Rechnung benutzen.

3. **Den Reverse Proxy** auf `127.0.0.1:8000` zeigen lassen — eine Regel für
   die ganze Domain, die Verteilung macht die App selbst. Mit Caddy:

   ```caddyfile
   wortlaut.example.org {
   	encode gzip
   	reverse_proxy 127.0.0.1:8000
   }
   ```

   Mit nginx:

   ```nginx
   location / {
       proxy_pass http://127.0.0.1:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-Proto $scheme;
       client_max_body_size 64m;   # Aufnahmen sind größer als die Vorgabe
   }
   ```

   **Läuft der Proxy selbst als Container** (nginx-proxy, Traefik und
   Verwandte), dann nicht auf `127.0.0.1` veröffentlichen, sondern beide in ein
   gemeinsames Docker-Netz stellen — sonst sieht der Proxy den Dienst nicht.
   In der `compose.yaml` die `ports` streichen und statt dessen:

   ```yaml
   services:
     wortlaut:
       networks: [proxy]
       environment:
         # nginx-proxy/acme-companion lesen das; bei Traefik sind es Labels.
         VIRTUAL_HOST: wortlaut.example.org
         VIRTUAL_PORT: "8000"
         LETSENCRYPT_HOST: wortlaut.example.org

   networks:
     proxy:
       external: true
   ```

   Der Name `proxy` ist der des vorhandenen Netzes (`docker network ls`).

4. **Starten und nachsehen:**

   ```bash
   docker compose up -d --build
   docker compose ps                            # „healthy"
   curl http://127.0.0.1:8000/gesundheit
   curl -I https://wortlaut.example.org/schreiben/
   ```

   Die letzte Zeile ist die Probe auf die Verteilung: Kommt dort die Seite von
   „hören" statt der von „schreiben", zeigt der Proxy nicht auf diesen Port
   oder schneidet den Pfad ab.

`/gesundheit` verlangt bewusst keinen Token und eignet sich als Prüfpunkt für
eine Überwachung.

**HTTPS ist nicht optional.** Der Aufnahmeknopf benutzt `MediaRecorder`, und
das gibt der Browser nur in einem sicheren Kontext frei — über eine
IP-Adresse oder blankes HTTP bleibt die App unbenutzbar.

## Endpunkte

App „hören":

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

App „schreiben" (kein Token, kein Sprecherparameter — beides steht in der
Konfiguration der Instanz):

```
POST   /schreiben/api/sessions                    neue Diktiersitzung
GET    /schreiben/api/sessions/{id}
POST   /schreiben/api/sessions/{id}/segments      multipart: audio → Abschnitte
POST   /schreiben/api/sessions/{id}/bestaetigen   → Postausgang, sofort senden
POST   /schreiben/api/segments/{id}/neu           multipart: audio
GET    /schreiben/api/segments/{id}/audio
GET    /schreiben/api/model                       Modellstand für die Kopfzeile
GET    /schreiben/api/outbox
POST   /schreiben/api/outbox/senden               noch einmal versuchen
GET    /gesundheit                                auf der Wurzel, für die Überwachung
```

Der Pfad `/schreiben` gehört zur App und nicht zum Proxy: Er steht als `BASIS`
in ihrer `main.py`, damit vor dem Container eine Regel genügt, die den Weg
unverändert durchreicht.

Im gemeinsamen Container (`apps/gesamt.py`) gibt es nur eine Wurzel, also auch
nur ein `/gesundheit` — das von „hören". Für eine Überwachung genügt es: Der
Prozess ist derselbe.

**Warum überall `sprecher=…`:** Das Korpus hat je Sprecher eine eigene
Datenbank (`data/korpus/<sprecher_id>/hoeren.sqlite`). Ohne die Sprecher-ID
wüsste der Server nicht, welche Datei er öffnen soll. Der Parameter steht immer
in der Abfragezeichenkette — auch bei POST mit Rumpf, damit eine einzige
Abhängigkeit ihn auswerten kann.

Die interaktive API-Dokumentation liegt unter `/docs`.

## Authentifizierung

`WORTLAUT_AUTH_TOKEN` gesetzt → alle `/api`-Endpunkte von „hören" verlangen
`Authorization: Bearer <token>`. Leer → offen, nur für die lokale Entwicklung
gedacht. Das Frontend fragt den Token einmal ab und legt ihn im
`localStorage` ab.

„schreiben" hat bewusst keinen Zugang (Grundentscheidung 7): Die Zielperson
kann schlecht lesen und schreiben, ein Anmeldefeld wäre eine unüberwindbare
Hürde. Eine solche Instanz gehört deshalb ins private Netz oder hinter einen
Zugang, den jemand anderes einrichtet — etwa eine
Basisauthentifizierung im `/schreiben/`-Block des Proxys oder eine
Beschränkung auf das eigene Netz. In
umgekehrter Richtung braucht „schreiben" den Token von „hören"
(`WORTLAUT_INTAKE_TOKEN`), um seine Korrekturen abliefern zu dürfen.

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
| „schreiben": erstes Diktat hängt lange | faster-whisper lädt beim ersten Aufruf sein Modell herunter. Danach kommt es aus dem Cache. Ohne Netz schlägt es fehl — dann `WORTLAUT_ASR_MODELL` auf ein bereits geladenes Modell setzen. |
| „schreiben": `ModuleNotFoundError: faster_whisper` | `uv sync --extra asr` vergessen (oder `WORTLAUT_ASR=remote` setzen) |
| „schreiben": „Aus der Aufnahme wurde kein Wort verstanden" | Whisper hat nichts erkannt. Mit `tiny` ist das bei leiser Aufnahme oder starker Sprechstörung der Normalfall — erst Mikrofon einmessen (in „hören" unter Einstellungen), dann ein größeres Modell versuchen. |
| „schreiben": Postausgang bleibt offen | `WORTLAUT_INTAKE_URL` fehlt oder zeigt ins Leere, oder der Token passt nicht zum `WORTLAUT_AUTH_TOKEN` von „hören". Nichts geht verloren: „Noch einmal senden" nach dem Richten genügt. |
| `localhost:5174` zeigt eine leere Seite | Der Pfad fehlt: `http://localhost:5174/schreiben/` aufrufen. |
| Der Reiter „schreiben" landet wieder in „hören" | Im Betrieb: Der Proxy schneidet `/schreiben/` ab oder zeigt auf den falschen Port. Probe: `curl -I https://<domain>/schreiben/`. In der Entwicklung: „schreiben" läuft nicht mit — `make dev APP=schreiben`. |
| `Address already in use` beim `make dev` | Der Port ist noch belegt, meist von einem älteren Lauf. Nachsehen mit `ss -tlnp \| grep -E "8000\|8001"`, dann die PID beenden. |
| Korrekturen bleiben im Postausgang, Fehler nennt 404 „Unbekannter Sprecher" | `WORTLAUT_SPRECHER_ID` fehlt oder gehört zu keinem Sprecher in „hören" — siehe „Bevor die Korrekturen ankommen". |
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
