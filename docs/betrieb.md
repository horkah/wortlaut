# Betrieb

## Voraussetzungen

- **ffmpeg** im Pfad - ohne ffmpeg scheitert jeder Aufnahme-Upload
- **tesseract** mit den Sprachdateien des Profils, wenn Vorlagen fotografiert
  werden - sonst fehlt nur dieser Weg (`wortlaut/text/ocr.py`)
- für den Trainer eine NVIDIA-Karte und das NVIDIA Container Toolkit

Im Abbild steht beides. Von Hand, auf Debian oder Ubuntu:

```bash
sudo apt install ffmpeg tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng
uv sync --extra ocr      # pytesseract, pillow, pypdfium2, pillow-heif
```

Die Sprachdateien einzeln, nicht `tesseract-ocr-all` (über ein Gigabyte); es
sind dieselben wie in `sprachen.UNTERSTUETZT` und im `Dockerfile`. Lokale
Entwicklung und Tests stehen in [Entwicklung](entwicklung.md).

---

## Betrieb mit Compose

```bash
docker compose up -d --build
docker compose --profile training up -d --build training
```

**Ein Container für alle drei Apps** (`wortlaut`): ein uvicorn, `hören` auf
der Wurzel, `lernen` unter `/lernen`, `schreiben` unter `/schreiben` -
zusammengesetzt in `apps/gesamt.py`, gebaut vom `Dockerfile` im
Wurzelverzeichnis. Geteilt wird der Prozess, sonst nichts: Jede App behält
Datenbank, Ablage und Zugangsregeln, und die Korrekturen gehen über die API
(`WORTLAUT_INTAKE_URL` auf `http://127.0.0.1:8000/api/korpus/intake`). Die
Frontends werden beim Bauen gebaut und mit ausgeliefert.

**Der Trainer** (`training`) steht hinter `profiles: [training]`: Ohne das
Profil wird er weder gebaut noch gestartet noch gestoppt.
`COMPOSE_PROFILES=training` in der `.env` nimmt ihn immer mit. Er hängt an
keinem Netz und spricht nur mit dem Datenverzeichnis.

**Ollama** (`ollama`) liefert die Textquelle, im internen Netz, auf derselben
Karte.

**Neubauen ist billig**, solange die Schichten stimmen: Backend ~1 s, ein
Frontend ~6 s, `packages/ui` ~7 s, `packages/wortlaut` ~3 s. Nur eine
geänderte `pyproject.toml` baut die Abhängigkeiten neu, aus dem BuildKit-Cache.
`docker buildx du` zeigt den Bauspeicher, `docker buildx prune` räumt ihn.

### Was wo liegt

| Im Container | Auf dem Wirt | Inhalt |
|---|---|---|
| `/srv/wortlaut/data` | Volume `wortlaut-data` | Korpora, Diktate - unersetzlich |
| `/srv/wortlaut/data/modelle`, `…/snapshots` | `WORTLAUT_TRAININGSABLAGE/{modelle,snapshots}` | Stände und Läufe - aus dem Korpus neu zu rechnen |
| `/srv/wortlaut/modellcache` | `WORTLAUT_MODELLCACHE` | Grundmodelle, Stimmen - neu zu laden |
| `/root/.ollama` (Dienst `ollama`) | `WORTLAUT_OLLAMACACHE` | Modelle von Ollama - `ollama pull` |

Im Volume bleibt nur, was sich nicht wiederbeschaffen lässt; alles andere
gehört auf die große Platte. Gesichert wird über die Aufsicht, nicht durch
Kopieren des Volumes (siehe [Sichern](#sichern-und-wiederherstellen)). Der
erste Start lädt Grundmodelle nach; darauf nimmt die `start_period` des
Healthchecks Rücksicht.

**Die Ablagen des Wirts von Hand anlegen.** Die Mounts tragen
`create_host_path: false`: Fehlt die Quelle, startet der Container nicht,
statt still zwanzig Gigabyte auf die Systemplatte zu legen, weil die große
Platte gerade nicht eingehängt ist.

```bash
mkdir -p /pfad/zur/grossen/platte/wortlaut/{huggingface,ollama,training/{modelle,snapshots}}
```

Die Platte gehört vor Docker in den Systemstart, in der `/etc/fstab` über
`LABEL=` oder `UUID=` und mit `x-systemd.before=docker.service`:

```
LABEL=backup  /backup  ext4  defaults,x-systemd.before=docker.service  0  2
```

### Migrationen und Varianten

Ein Update braucht keinen Handgriff: Jede Datenbank holt sich ihr Schema beim
ersten Zugriff. Für alle auf einmal, oder um zu sehen, was offen war:

```bash
docker compose exec wortlaut python scripts/migrate.py
```

Im Container gibt es weder `make` noch `uv`. Daneben:

| Skript | Zweck |
|---|---|
| `scripts/augmentieren.py` | die Variante `rauschen` aller Aufnahmen vorab rechnen (`make augmentieren`) |
| `scripts/varianten_aufraeumen.py` | Dateien von Fassungen entfernen, die `augmentierung.VARIANTEN` nicht mehr nennt; `--wirklich` löscht |
| `scripts/vorlesen.py` | Stimmen holen (`--hole <stimme>`), alle Vorlagen vorab sprechen |
| `scripts/importieren.py` | Paare aus Ton und Text von außerhalb als Textquelle übernehmen |
| `scripts/paare_teilen.py` | zu lange Paare aus Ton und Text vor dem Import an Pausen in Stücke von 15–29 s teilen |
| `scripts/folge_nachtragen.py` | die Folge hinter dem Optionscode für Läufe ohne sie vergeben |
| `scripts/restore.py`, `scripts/purge_speaker.py` | siehe unten |

### Stimmen fürs Vorlesen

```bash
docker compose exec wortlaut python scripts/vorlesen.py --hole de_DE-thorsten-high
docker compose exec wortlaut python scripts/vorlesen.py
```

Die Stimmen liegen unter `WORTLAUT_STIMMEN_DIR` im Modellspeicher
(`de_DE-thorsten-high` 114 MB). Gemessen mit dieser Stimme: 1,7-fache
Echtzeit, rund 24 Sätze je Minute, 265 Vorlagen in etwa 11 Minuten und ~35 MB.
Ein abgebrochener Aufruf holt beim nächsten nur, was fehlt. Mehrere Stimmen
nebeneinander stehen unter „Audio" zur Wahl.

### Der Trainer

```bash
docker compose --profile training up -d training
docker compose logs -f training
```

Der erste Lauf lädt das Grundmodell in den Modellcache. Woran ein Lauf hängt,
steht in seinem Verzeichnis: `zustand.json` sagt, was er tut, `protokoll.txt`,
warum er es nicht mehr tut.

```bash
docker compose exec wortlaut tail -40 data/snapshots/job_01J8…/protokoll.txt
```

Endet ein Lauf mit „CUDA out of memory", hielt entweder jemand anderes die
Karte länger als zehn Minuten (`nvidia-smi` zeigt, wer), oder das Training
passt nicht auf die Karte - dann `stapel` im Rezept herunter und
`akkumulation` hinauf. Den Trainer neu zu starten kostet nur den laufenden
Lauf.

---

## Reverse Proxy und Domain

Eine Adresse für alle drei Apps. Der Proxy reicht jeden Pfad unverändert an
Port 8000 des Containers; die Apps hängen selbst unter ihren Pfaden, eine
Regel, die `/schreiben/` abschneidet, macht die App unerreichbar. Wer eine App
verschiebt, ändert `BASIS` im Backend, `base` in der `vite.config.ts` und den
Pfad in `packages/ui/apps.ts`.

1. **DNS**: A- (und AAAA-)Eintrag auf die Maschine, vor dem ersten Start.
2. **Geheimnisse** in der `.env`, mit `openssl rand -base64 33`, verschieden:
   `WORTLAUT_AUTH_TOKEN`, `WORTLAUT_ADMIN_TOKEN`, bei Bedarf
   `WORTLAUT_TRAINER_KEY` und `WORTLAUT_EDITOR_KEY`.
3. **Ablagen des Wirts** anlegen und in die `.env` (siehe oben).
4. **Proxy.** Die `compose.yaml` hängt den Dienst an das externe Netz `caddy`
   und beschreibt ihn mit Labels für caddy-docker-proxy:

   ```yaml
   labels:
     caddy: wortlaut.example.org
     caddy.reverse_proxy: "{{upstreams 8000}}"
   ```

   Andere containerisierte Proxys (nginx-proxy, Traefik) kommen genauso über
   ein gemeinsames Netz und ihre eigenen Labels. Läuft der Proxy auf dem Wirt,
   veröffentlicht der Dienst stattdessen `127.0.0.1:8000:8000`, und der Proxy
   zeigt darauf:

   ```caddyfile
   wortlaut.example.org {
   	encode gzip
   	reverse_proxy 127.0.0.1:8000
   }
   ```

   ```nginx
   location / {
       proxy_pass http://127.0.0.1:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-Proto $scheme;
       client_max_body_size 64m;
   }
   ```

5. **Prüfen:**

   ```bash
   docker compose ps                              # „healthy"
   curl -I https://wortlaut.example.org/gesundheit
   curl -I https://wortlaut.example.org/schreiben/
   ```

   Kommt unter `/schreiben/` die Seite von „hören", schneidet der Proxy den
   Pfad ab.

**HTTPS ist Pflicht.** `MediaRecorder` gibt der Browser nur in einem sicheren
Kontext frei. `/gesundheit` verlangt keinen Zugang und dient der Überwachung.

**Getrennte Container** gehen auch: die Dockerfiles unter `apps/hoeren/` und
`apps/schreiben/`, je ein Dienst, je eine Proxy-Regel. Am Code ändert das
nichts.

---

## Der erste Sprecher

```bash
curl -X POST https://wortlaut.example.org/api/speakers \
  -H "Authorization: Bearer $WORTLAUT_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Vorname","sprache":"de"}'
# → {"id":"spr_…", …}

curl -X POST https://wortlaut.example.org/api/speakers/spr_…/zugang \
  -H "Authorization: Bearer $WORTLAUT_AUTH_TOKEN"
# → {"zugang":"spr_….…"} - wird zum Link …/#/zugang/<zugang> für die Person
```

Dasselbe geht in der Oberfläche unter „Sprecher". Der Zugang ist nur in
dieser Antwort im Klartext zu sehen und öffnet alle drei Apps.

---

## Sichern und Wiederherstellen

| | Sicherung `.tgz` | Datensatz `.zip` |
|---|---|---|
| Frage | „Der Server ist weg, ich will den Stand zurück." | „Ich will die Paare aus Text und Audio." |
| Inhalt | Datenbanken und Aufnahmen, ohne Gerechnetes | WAV, je Aufnahme ihr Text, `metadaten.csv`/`.jsonl` |
| Umfang | ein Sprecher oder alle | ein Sprecher |
| Zurückspielbar | ja | nein |

Aufbau und Auslassungen beider Formate stehen in
[hören](hoeren.md#zwei-formate-zwei-fragen).

**Ziehen** in der Oberfläche als Aufsicht - „Gesamtsicherung" oder bei einem
Sprecher „Sicherung (.tgz)" -, bei großen Beständen besser mit `curl`:

```bash
curl -OJ https://wortlaut.example.org/api/admin/sicherung \
  -H "Authorization: Bearer $WORTLAUT_ADMIN_TOKEN"
```

Der Dienst darf dabei laufen; die Datenbanken kommen über die
Online-Backup-Schnittstelle von SQLite. Nach dem Zurückspielen sind die Kurven
der Auswertung leer, bis ein Lauf sie füllt.

**Zurückspielen** bei angehaltenem Dienst:

```bash
docker compose stop
uv run python scripts/restore.py wortlaut-gesamt-20260822-174500.tgz --ueberschreiben
docker compose start
```

Ohne `--ueberschreiben` bricht das Skript ab, bevor es etwas schreibt, wenn
eine Datei schon dasteht; `--nur-ansehen` zeigt den Inhalt. Ohne wortlaut geht
es auch: `tar xzf …` und `cp -a daten/. /srv/wortlaut/data/`. Eine ältere
Sicherung holt ihr Schema beim ersten Zugriff nach.

**Löschen** in drei Stufen, als Aufsicht oder auf der Kommandozeile mit
demselben Umfang ([hören](hoeren.md#löschen-drei-stufen)):

```bash
uv run python scripts/purge_speaker.py spr_7f2a               # Probelauf
uv run python scripts/purge_speaker.py spr_7f2a --ja-wirklich
```

---

## Wenn etwas klemmt

| Symptom | Ursache |
|---|---|
| `ffmpeg ist gescheitert` beim Upload | ffmpeg fehlt, oder das Format ist kaputt |
| `Unbekannter Sprecher` (404) | Korpus liegt unter einem anderen `WORTLAUT_DATA_DIR` |
| `Keine Textquelle konfiguriert` | `WORTLAUT_LLM_PROVIDER` ist leer - Upload nutzen oder Anbieter setzen |
| `Textquelle nicht erreichbar` | `WORTLAUT_LLM_BASE_URL` zeigt ins Leere; `docker compose ps` (läuft „ollama"?), `docker compose exec ollama ollama list` |
| `Textquelle antwortete mit 404` | das Modell ist nicht geladen - `docker compose exec ollama ollama pull <modell>` |
| Aufnahmeknopf ohne Wirkung | `MediaRecorder` braucht HTTPS oder `localhost` |
| Aufnahmen durchweg sehr leise | unter „Audio → Mikrofon" **Automatisch einmessen**; sonst [Leises Mikrofon](#leises-mikrofon-unter-linux) |
| Pegelbalken bleibt auf „still" | anderes Gerät geöffnet - im Test ausdrücklich wählen; echte Namen gibt der Browser erst nach der Erlaubnis heraus |
| Vorlesestimme blechern oder stumm | eine Serverstimme holen, oder [Bessere Vorlesestimme](#bessere-vorlesestimme-unter-linux) |
| „schreiben": erstes Diktat hängt | faster-whisper lädt sein Modell; ohne Netz ein schon geladenes in `WORTLAUT_ASR_MODELL` setzen |
| „schreiben": `ModuleNotFoundError: faster_whisper` | `uv sync --extra asr` fehlt |
| „schreiben": „kein Wort verstanden" | Mikrofon einmessen, dann ein größeres Modell freigeben |
| „schreiben": Postausgang bleibt offen | `WORTLAUT_INTAKE_URL` fehlt oder der Zugang wurde ersetzt; nach dem Richten „Noch einmal senden" |
| eine App zeigt „Kein Zugang" | in diesem Browser wurde kein Link geöffnet, oder der Zugang wurde zurückgezogen |
| Reiter „schreiben" landet in „hören" | der Proxy schneidet `/schreiben/` ab; in der Entwicklung läuft „schreiben" nicht |
| `Address already in use` bei `make dev` | ein älterer Lauf hält den Port: `ss -tlnp` |
| Aufsicht: alles antwortet 401 | `WORTLAUT_ADMIN_TOKEN` ist leer; setzen, neu starten |
| Aufsicht: Token eingetragen, Oberfläche zeigt Verwaltung | der Token stimmt nicht; „Speichern und prüfen" unter „Zugangsdaten" zeigt, was der Server sieht |
| „lernen" wartet endlos auf den Trainer | Trainer und App sehen verschiedene `snapshots`-Verzeichnisse - die Bind-Mounts waren beim Start nicht wirksam. `stat -c '%d:%i'` im Container gegen den Wirt vergleichen; `docker compose --profile training up -d --force-recreate training` |
| Download einer großen Sicherung bricht ab | mit `curl -OJ` holen |
| nach dem Zurückspielen fehlen Daten | der Dienst lief dabei; anhalten, erneut einspielen |
| `make frontend` öffnet ein leeres Fenster | `node_modules` fehlt, und `vite` im `$PATH` ist ein fremdes Programm (ViTE, ein Trace-Viewer): `npm install` |

---

## Leises Mikrofon unter Linux

Eingebaute Mikrofone sind unter Linux oft leiser, weil die Verstärkung des
Treibers fehlt - besonders die Arrays von Apple-Geräten am
`snd-hda-macbookpro`-Treiber.

```bash
pactl list sources | grep -A6 'Name: alsa_input'
```

Steht der Regler bei 100 %, liefert der Eingang schlicht wenig. Dann entweder
systemweit über die Vorgabe hinaus (`pactl set-source-volume @DEFAULT_SOURCE@
200%`, bei manchen Treibern nach dem Neustart zurückgesetzt) oder die
**Verstärkung** unter „Audio → Mikrofon", die nur in wortlaut wirkt und bleibt.
Beides verstärkt auch das Raumrauschen; ein Headset bringt mehr.

## Bessere Vorlesestimme unter Linux

Die Browserstimmen kommen aus `speech-dispatcher`, per Vorgabe mit `espeak-ng`.
Für Deutsch sind die mbrola-Stimmen die nächste Stufe:

```bash
sudo apt install espeak-ng mbrola mbrola-de6 mbrola-de7
```

Das Kommandozeilenprogramm `espeak-ng` ist nötig, die Bibliothek allein nicht.
Dann in `/etc/speech-dispatcher/speechd.conf` einschalten, ohne die
vorhandenen Module abzuschalten:

```
AddModule "espeak-ng-mbrola-generic" "sd_generic"   "espeak-ng-mbrola-generic.conf"
```

Das Modul bringt die englische Vorgabestimme `en1` mit, die nicht installiert
ist; geprüft wird deshalb mit Sprache:

```bash
pkill speech-dispatcher
spd-say -o espeak-ng-mbrola-generic -l de -y de6 "Ein Satz zur Probe"
```

Firefox liest die Stimmenliste beim Start; danach neu starten. Eine
Serverstimme (siehe oben) umgeht all das für jedes Gerät.
