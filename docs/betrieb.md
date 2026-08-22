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
`http://localhost:8000/api/korpus/intake`) und `WORTLAUT_INTAKE_TOKEN` den
**Zugang des Sprechers** enthalten, den „hören" unter „Sprecher" ausgibt —
nicht den `WORTLAUT_AUTH_TOKEN`. Fehlt beides, sammelt der Postausgang die
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
`diktate/` gehört „schreiben". Gesichert wird nicht durch Kopieren dieses
Volumes, sondern über die Aufsicht: Sie zieht ein Archiv, das den laufenden
Dienst nicht anhält und trotzdem einen in sich stimmigen Stand enthält (siehe
[Sichern und Wiederherstellen](#sichern-und-wiederherstellen)). Wer das Volume
doch von Hand kopiert, hält den Dienst vorher an — SQLite im WAL-Modus mag
keine Kopie mitten im Schreibvorgang. Das Whisper-Modell liegt darin unter `.cache/huggingface`;
ohne das lüde jeder Neustart erneut herunter — der erste Start dauert deshalb
einige Minuten, worauf die `start_period` der Healthcheck-Prüfung Rücksicht
nimmt.

Vite läuft nicht mit — es ist reines Entwicklungswerkzeug. Beide Frontends
werden beim `docker build` einmal gebaut und vom Prozess mit ausgeliefert.

### Bevor die Korrekturen ankommen: der Sprecher

„schreiben" gehört zu genau einer Person. Ihre Kennung vergibt „hören" beim
Anlegen des Sprechers, und ihren Zugang gibt „hören" gesondert aus. Beim ersten
Aufbau also erst den Sprecher anlegen, dann beides in die `.env` schreiben und
den Container neu starten:

```bash
curl -X POST https://wortlaut.example.org/api/speakers \
  -H "Authorization: Bearer $WORTLAUT_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Vorname","sprache":"de","basismodell":"tiny"}'
# → {"id":"spr_…"}  in die .env als WORTLAUT_SPRECHER_ID

curl -X POST https://wortlaut.example.org/api/speakers/spr_…/zugang \
  -H "Authorization: Bearer $WORTLAUT_AUTH_TOKEN"
# → {"zugang":"spr_….…"}  in die .env als WORTLAUT_INTAKE_TOKEN
docker compose up -d
```

Der Zugang ist nur in dieser Antwort im Klartext zu sehen; gespeichert ist nur
sein Prüfwert. Wer ihn verliert, gibt einen neuen aus — der alte gilt dann
nicht mehr, und die `.env` von „schreiben" braucht den neuen.

Fehlt eines von beiden oder passen sie nicht zusammen, sammelt der Postausgang
die Korrekturen, statt sie zu verwerfen — nachzuholen mit „Noch einmal senden"
in der Oberfläche.

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
   WORTLAUT_ADMIN_TOKEN=<eine andere lange Zufallszeichenkette>
   ```

   Beide mit `openssl rand -base64 33` erzeugen, und zwei verschiedene.
   **Ohne den ersten steht die Verwaltung offen im Netz** — jeder mit der
   Adresse kann Sprecher anlegen, deren Zugänge ausgeben und die LLM-Textquelle
   auf deine Rechnung benutzen. An die Aufnahmen kommt er damit nicht: Dorthin
   führt allein der Zugang des jeweiligen Sprechers.

   Der zweite ist der Zugang zur Aufsicht — Einsicht in jeden Korpus,
   Sicherungen und Löschungen. Bleibt er leer, ist die Aufsicht abgeschaltet;
   Sichern geht dann nur noch über das Dateisystem des Wirts.

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

`/gesundheit` verlangt bewusst keinen Zugang und eignet sich als Prüfpunkt für
eine Überwachung.

**HTTPS ist nicht optional.** Der Aufnahmeknopf benutzt `MediaRecorder`, und
das gibt der Browser nur in einem sicheren Kontext frei — über eine
IP-Adresse oder blankes HTTP bleibt die App unbenutzbar.

## Endpunkte

App „hören":

```
Verwaltung — `Authorization: Bearer $WORTLAUT_AUTH_TOKEN`:

```
POST   /api/speakers                              { name, sprache, basismodell }
GET    /api/speakers
GET    /api/speakers/{id}
POST   /api/speakers/{id}/zugang                  neuen Zugang ausgeben
DELETE /api/speakers/{id}/zugang                  Zugang zurückziehen
```

Daten — `Authorization: Bearer <sprecher_id>.<geheimnis>`; der Sprecher steht
im Zugang und in keinem Parameter:

```
POST   /api/sources/llm                           { thema, altersspanne, umfang }
POST   /api/sources/upload                        multipart: datei
GET    /api/sources
GET    /api/sources/{id}/text                     Klartext, eine Einheit je Absatz
PATCH  /api/sources/{id}                          { aktiv }  — abstellen/aufnehmen
DELETE /api/sources/{id}                          409, wenn Aufnahmen daran hängen
POST   /api/sessions
GET    /api/prompts/next?session=…
POST   /api/recordings                            multipart: audio, prompt_id, modus, session
GET    /api/recordings/{id}/audio
DELETE /api/recordings/{id}
GET    /api/progress
POST   /api/korpus/intake                         multipart: audio, text, externe_id
```

Aufsicht — `Authorization: Bearer $WORTLAUT_ADMIN_TOKEN`. Als einzige Wege
dieser App nennen sie ihren Sprecher in der Adresse: Die Aufsicht hat keinen
eigenen, sie sieht über alle hinweg.

```
GET    /api/admin/speakers                        alle Sprecher mit Kennzahlen
GET    /api/admin/speakers/{id}                   Quellen, Sitzungen, Umfang
GET    /api/admin/speakers/{id}/recordings?ab=0   Aufnahmen mit ihrem Text
GET    /api/admin/speakers/{id}/recordings/{r}/audio
PATCH  /api/admin/speakers/{id}                   { name }  — umbenennen
GET    /api/admin/speakers/{id}/sicherung         .tgz, wiederherstellbar
GET    /api/admin/speakers/{id}/datensatz         .zip, Text-Audio-Paare
GET    /api/admin/sicherung                       .tgz über alle Sprecher
DELETE /api/admin/speakers/{id}/recordings/{r}    eine Aufnahme
DELETE /api/admin/speakers/{id}/recordings?bestaetigung={id}
DELETE /api/admin/speakers/{id}?bestaetigung={id}
```

Es gibt hier **keinen** Weg, der mehr als einen Sprecher löscht, und die beiden
löschenden Wege verlangen die Kennung ein zweites Mal als `bestaetigung`. Ein
Versehen soll höchstens eine Person kosten.

Mit jedem der drei erreichbar, weil er die Frage beantwortet, welchen man
vorgelegt hat:

```
GET    /api/zugang                                { art, sprecher_id, name }
GET    /gesundheit                                ohne alles
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

**Warum kein `sprecher=…` mehr:** Das Korpus hat je Sprecher eine eigene
Datenbank (`data/korpus/<sprecher_id>/hoeren.sqlite`), und der Server muss
wissen, welche Datei er öffnen soll. Früher stand die Kennung als Parameter da
— eine Behauptung, die jeder mit dem Token beliebig setzen konnte, versehentlich
auch aus einem alten Reiter. Jetzt trägt der Zugang die Kennung, und der Server
leitet sie daraus ab.

Der Parameter wird trotzdem noch angenommen, aber nur als Behauptung, die
stimmen muss: Weicht sie ab, antwortet der Server mit 403 und nennt beide
Kennungen. Genau davon lebt die Absicherung von „schreiben" — es schickt seinen
`WORTLAUT_SPRECHER_ID` weiter mit und erfährt so, wenn er nicht zum Zugang
in `WORTLAUT_INTAKE_TOKEN` passt.

Die interaktive API-Dokumentation liegt unter `/docs`.

## Authentifizierung

Drei Arten von Zugang, alle als `Authorization: Bearer …`:

**Der Verwaltertoken** ist `WORTLAUT_AUTH_TOKEN`. Er legt Sprecherprofile an
und gibt deren Zugänge aus. Leer → die Verwaltung steht offen, nur für die
lokale Entwicklung gedacht. An die Aufnahmen kommt er nicht.

**Der Sprecherzugang** hat die Form `<sprecher_id>.<geheimnis>` und ist
zugleich die Kennung: „hören" spaltet ihn am Punkt, öffnet die Datenbank dieses
Sprechers und prüft dort den Prüfwert des Geheimnisses. Er ist der einzige Weg
zu den Daten — auch für die Verwaltung.

Ausgegeben wird ein Zugang in der Oberfläche unter „Sprecher"; dabei entsteht
ein Link der Form `https://…/#/zugang/<zugang>`. Den öffnet die Person einmal
auf ihrem Gerät und legt ihn als Lesezeichen ab; danach ist nichts mehr zu
merken und nichts zu tippen (Grundentscheidung 7). Das Geheimnis steht im
Fragment und geht deshalb nie an den Server, landet also in keinem
Zugriffsprotokoll.

Im Klartext gibt es einen Zugang nur genau einmal, beim Ausgeben; gespeichert
ist nur sein Prüfwert (`speakers.zugang_hash`). Ein verlorener Zugang wird
deshalb nicht wiederhergestellt, sondern ersetzt — und damit ist er
zurückgezogen. „Zurückziehen" ohne Ersatz gibt es auch; dann kommt niemand mehr
an diesen Korpus, bis ein neuer Zugang ausgegeben wird.

**Der Aufsichtstoken** ist `WORTLAUT_ADMIN_TOKEN`. Er ist der eine Zugang, der
über allen Korpora steht: einsehen, umbenennen, sichern, ausleiten, löschen. Er
darf zusätzlich alles, was der Verwaltertoken darf — wer jeden Korpus löschen
kann, hätte an einem zweiten Token fürs Anlegen eines Profils nichts gewonnen.

Erreichbar ist die Aufsicht aus **jedem** Browser: Der Token wird unter
„Einstellungen → Zugang" in dasselbe Feld eingetragen wie ein Verwaltertoken,
und der Server sieht am Vorgelegten, welches von beidem es ist. Eine zweite
Adresse oder eine zweite Anmeldung gibt es nicht. Ein Browser trägt allerdings
immer nur einen Zugang: Wer dort vorher den Link eines Sprechers geöffnet
hatte, öffnet ihn danach einmal wieder.

Leer heißt hier — anders als beim Verwaltertoken — **abgeschaltet** und nicht
„offen". Ohne gesetzten Token antwortet jeder Weg unter `/api/admin/…` mit 401,
auch in der Entwicklung: Ein Zugang, der löschen darf, soll nicht
versehentlich offenstehen. Erzeugt wird er wie der andere, etwa mit
`openssl rand -base64 33`. Mit dem Verwaltertoken darf er nicht
übereinstimmen — dann wäre jeder Verwalter zugleich Aufsicht, und der Dienst
bricht beim Start mit einer Meldung ab, statt still mehr zu erlauben.

In der Kopfzeile steht dauerhaft, für wen der Browser gerade eingestellt ist —
und zwar der Name, den der Server zum vorgelegten Zugang nennt, nicht der, den
sich der Browser gemerkt hat. Bei der Aufsicht steht dort „Aufsicht"; sie sieht
in fremde Korpora, und das soll nicht nur dann dastehen, wenn gerade gelöscht
wird.

„schreiben" hat bewusst keinen Zugang (Grundentscheidung 7): Die Zielperson
kann schlecht lesen und schreiben, ein Anmeldefeld wäre eine unüberwindbare
Hürde. Eine solche Instanz gehört deshalb ins private Netz oder hinter einen
Zugang, den jemand anderes einrichtet — etwa eine
Basisauthentifizierung im `/schreiben/`-Block des Proxys oder eine
Beschränkung auf das eigene Netz. In
umgekehrter Richtung braucht „schreiben" den Sprecherzugang von „hören"
(`WORTLAUT_INTAKE_TOKEN`), um seine Korrekturen abliefern zu dürfen.

## Sichern und Wiederherstellen

Es gibt zwei Formate, und sie beantworten zwei verschiedene Fragen.

| | Sicherung `.tgz` | Datensatz `.zip` |
|---|---|---|
| Frage | „Der Server ist weg, ich will den Stand zurück." | „Ich will die Paare aus Text und Audio ansehen oder trainieren." |
| Inhalt | Datenbank und Aufnahmen, wie sie auf der Platte liegen | WAV-Dateien, je Aufnahme ihr Text, `metadaten.csv`/`.jsonl` |
| Umfang | ein Sprecher oder alle | immer genau ein Sprecher |
| Zurückspielbar | ja | **nein** |

Zum Wegtragen also immer die `.tgz`.

### Eine Sicherung ziehen

In der Oberfläche als Aufsicht: unter „Sprecher" der Knopf
**Gesamtsicherung** für alles, oder bei einem Sprecher „Ansehen" →
**Sicherung (.tgz)**. Der Browser hält die Datei dabei kurz im Speicher; bei
einem sehr großen Bestand deshalb lieber über die Kommandozeile:

```bash
curl -OJ https://wortlaut.example.org/api/admin/sicherung \
  -H "Authorization: Bearer $WORTLAUT_ADMIN_TOKEN"

curl -OJ https://wortlaut.example.org/api/admin/speakers/spr_…/sicherung \
  -H "Authorization: Bearer $WORTLAUT_ADMIN_TOKEN"
```

`-OJ` übernimmt den Dateinamen, den der Server nennt — er trägt die Zeitmarke.

**Der Dienst darf dabei laufen.** Die Datenbanken werden nicht kopiert, sondern
über die Online-Backup-Schnittstelle von SQLite gezogen; das Ergebnis ist ein
in sich stimmiger Stand, auch wenn gerade jemand aufnimmt. Ein schlichtes `cp`
der `.sqlite`-Datei wäre das nicht: Im WAL-Modus steht ein Teil der Daten
daneben in `…-wal`.

Nicht in der Sicherung: die Modellstände unter `data/modelle/`. Sie sind groß
und lassen sich aus dem Korpus neu rechnen — die Aufnahmen nicht. Wer sie
trotzdem will, kopiert das Verzeichnis dazu.

### Was drin ist

```
wortlaut-gesamt-20260822-174500.tgz
├── sicherung.json               Zeitpunkt, Sprecher, je Datei Größe und SHA-256
└── daten/
    ├── korpus/spr_…/hoeren.sqlite
    ├── korpus/spr_…/audio/rec_….wav
    └── diktate/spr_…/…          Arbeitsstand von „schreiben"
```

`daten/` bildet `WORTLAUT_DATA_DIR` eins zu eins ab. Das ist Absicht: Eine
Sicherung, die ein laufendes Programm zum Lesen braucht, ist im Ernstfall
keine.

### Zurückspielen

**Erst den Dienst anhalten.** SQLite hält eine laufende Datenbank offen; wer
sie unter dem Prozess austauscht, bekommt einen Mischmasch aus altem
Zwischenspeicher und neuer Datei.

```bash
docker compose stop
uv run python scripts/restore.py wortlaut-gesamt-20260822-174500.tgz --ueberschreiben
docker compose start
make migrate        # falls die Sicherung älter ist als das Schema
```

Ohne `--ueberschreiben` bricht das Skript ab, sobald eine Datei schon dasteht —
und zwar bevor irgendetwas geschrieben wurde. `--nur-ansehen` zeigt nur, was in
der Sicherung steht.

Auf einer Maschine, auf der wortlaut gar nicht installiert ist, geht es auch
ohne das Skript:

```bash
tar xzf wortlaut-gesamt-20260822-174500.tgz
cp -a daten/. /srv/wortlaut/data/
```

### Datensatz zum Arbeiten

Je Sprecher, in der Oberfläche unter „Ansehen" → **Datensatz (.zip)**:

```
spr_…/
├── LIESMICH.txt
├── metadaten.csv        file_name, transcription, dauer_s, modus, quelle, …
├── metadaten.jsonl      dieselben Zeilen als JSON
└── audio/
    ├── rec_….wav        16 kHz mono, PCM 16 bit
    └── rec_….txt        der gesprochene Text zu genau dieser Datei
```

Die Spalten `file_name` und `transcription` heißen so, weil das
`audiofolder`-Format von Hugging Face genau diese Namen erwartet — der
Datensatz lädt damit ohne eine Zeile Anpassungscode. Der Text steht doppelt
darin: in der Tabelle fürs Training, als `.txt` neben dem Audio für jedes
Werkzeug, das nur ein Verzeichnis sieht.

Enthalten sind nur Aufnahmen mit Status `ok`. Verworfene haben kein Audio mehr.

### Löschen

Ebenfalls Sache der Aufsicht, in drei Stufen — jede enger als die vorige:

| | Was verschwindet | Was bleibt |
|---|---|---|
| eine Aufnahme | Audio und Datensatz; die Einheit wird wieder offen | alles andere |
| alle Aufnahmen eines Sprechers | jedes Audio, jede Aufnahmezeile | Profil, Textquellen, Warteschlange |
| ein Sprecher | Korpus, Diktate, Modellstände, Schnappschüsse | nichts |

Eine vierte Stufe „alle Sprecher" gibt es nicht, weder in der Oberfläche noch
in der API. Sie wäre ein Knopf, der einmal im Leben gedrückt wird — und dann
versehentlich. Wer zwei Personen löschen will, tut es zweimal.

Beide großen Stufen verlangen zweimal eine Bestätigung: einen Klick und das
Abschreiben des Namens. Ein zweites „Wirklich?" klickt man weg, ohne es gelesen
zu haben; einen Namen abzuschreiben zwingt dazu hinzusehen, wen es trifft.

Dasselbe geht auf der Kommandozeile, mit demselben Umfang
(`apps/hoeren/backend/services/loeschung.py` ist für beide die eine Wahrheit
darüber, was zu einer Person gehört):

```bash
uv run python scripts/purge_speaker.py spr_7f2a               # Probelauf
uv run python scripts/purge_speaker.py spr_7f2a --ja-wirklich
```

## Wenn etwas klemmt

| Symptom | Ursache |
|---|---|
| `ffmpeg ist gescheitert` beim Upload | ffmpeg fehlt oder das Format ist kaputt |
| `Unbekannter Sprecher` (404) | falsche `sprecher`-ID, oder Korpus liegt unter einem anderen `WORTLAUT_DATA_DIR` |
| `Keine Textquelle konfiguriert` | `WORTLAUT_LLM_PROVIDER` ist leer — Textupload nutzen oder Anbieter setzen |
| `Textquelle nicht erreichbar` | Bei `openai`: `WORTLAUT_LLM_BASE_URL` zeigt ins Leere. Lokal prüfen mit `docker compose ps` (läuft „ollama"?) und `docker exec wortlaut-ollama-1 ollama list` (ist das Modell geladen?). |
| `Textquelle antwortete mit 404` | Das Modell aus `WORTLAUT_LLM_MODEL` ist dort nicht geladen — `docker exec wortlaut-ollama-1 ollama pull <modell>` |
| Aufnahmeknopf ohne Wirkung | `MediaRecorder` braucht HTTPS oder `localhost` |
| Aufnahmen sind durchweg sehr leise (Hinweis „Sehr leise") | Erst unter „Einstellungen → Mikrofon" **Automatisch einmessen** laufen lassen; das hebt den Pegel im Browser an. Bleibt es leise, siehe „Leises Mikrofon unter Linux" unten. |
| Der Pegelbalken im Mikrofontest bleibt auf „still" | Der Browser hat ein anderes Gerät geöffnet als erwartet — im Test das Mikrofon ausdrücklich auswählen. Steht dort nur „Mikrofon 1", war der Test noch nie an; die echten Namen gibt der Browser erst nach erteilter Erlaubnis heraus. |
| „Vorlesen" ohne Stimme | Browser ohne deutsche Stimme für die Web Speech API |
| Vorgelesene Stimme klingt blechern | Siehe „Bessere Vorlesestimme unter Linux" unten. Die Web Speech API nutzt die Stimmen des Betriebssystems; unter Linux ist das per Vorgabe espeak-ng. |
| „schreiben": erstes Diktat hängt lange | faster-whisper lädt beim ersten Aufruf sein Modell herunter. Danach kommt es aus dem Cache. Ohne Netz schlägt es fehl — dann `WORTLAUT_ASR_MODELL` auf ein bereits geladenes Modell setzen. |
| „schreiben": `ModuleNotFoundError: faster_whisper` | `uv sync --extra asr` vergessen (oder `WORTLAUT_ASR=remote` setzen) |
| „schreiben": „Aus der Aufnahme wurde kein Wort verstanden" | Whisper hat nichts erkannt. Mit `tiny` ist das bei leiser Aufnahme oder starker Sprechstörung der Normalfall — erst Mikrofon einmessen (Menüknopf oben rechts → Einstellungen; die Werte gelten für beide Apps), dann ein größeres Modell versuchen. |
| „schreiben": Postausgang bleibt offen | `WORTLAUT_INTAKE_URL` fehlt oder zeigt ins Leere; oder `WORTLAUT_INTAKE_TOKEN` ist kein gültiger Sprecherzugang (401); oder er gehört zu einem anderen Sprecher als `WORTLAUT_SPRECHER_ID` (403, mit beiden Kennungen im Grund). Nichts geht verloren: „Noch einmal senden" nach dem Richten genügt. |
| `localhost:5174` zeigt eine leere Seite | Der Pfad fehlt: `http://localhost:5174/schreiben/` aufrufen. |
| Der Reiter „schreiben" landet wieder in „hören" | Im Betrieb: Der Proxy schneidet `/schreiben/` ab oder zeigt auf den falschen Port. Probe: `curl -I https://<domain>/schreiben/`. In der Entwicklung: „schreiben" läuft nicht mit — `make dev APP=schreiben`. |
| `Address already in use` beim `make dev` | Der Port ist noch belegt, meist von einem älteren Lauf. Nachsehen mit `ss -tlnp \| grep -E "8000\|8001"`, dann die PID beenden. |
| Korrekturen bleiben im Postausgang, Fehler nennt 404 „Unbekannter Sprecher" | `WORTLAUT_SPRECHER_ID` fehlt oder gehört zu keinem Sprecher in „hören" — siehe „Bevor die Korrekturen ankommen". |
| Aufsicht: jeder Weg unter `/api/admin/…` antwortet 401 | `WORTLAUT_ADMIN_TOKEN` ist nicht gesetzt — dann ist die Aufsicht abgeschaltet, absichtlich auch in der Entwicklung. Nach dem Setzen den Dienst neu starten. |
| Aufsicht: Token eingetragen, aber die Oberfläche zeigt weiter die Verwaltung | Der Token stimmt nicht mit dem des Servers überein; der Server fällt dann auf die Verwaltung zurück. Unter „Einstellungen → Zugang" prüft „Speichern und prüfen", was der Server tatsächlich sieht. |
| Der Download einer großen Sicherung bricht ab | Der Browser hält die Datei im Speicher. Über `curl -OJ` mit dem Aufsichtstoken holen (siehe „Sichern und Wiederherstellen"). |
| Nach dem Zurückspielen fehlen Daten oder die Datenbank ist kaputt | Der Dienst lief dabei. Anhalten, noch einmal einspielen, starten — SQLite hält die alte Datei sonst offen. |
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
