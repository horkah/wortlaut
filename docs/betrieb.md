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

## Betrieb mit Compose

```bash
docker compose up -d --build
```

Der Anwendungscontainer liefert API und gebautes Frontend aus, Caddy davor
besorgt TLS. Die Daten liegen im Volume `wortlaut-data`; eine Sicherung ist
das Kopieren dieses Volumes bei angehaltenem Dienst (SQLite im WAL-Modus mag
keine Kopie mitten im Schreibvorgang).

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
| „Vorlesen" ohne Stimme | Browser ohne deutsche Stimme für die Web Speech API |
