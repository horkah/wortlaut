# schreiben

Mit dem Modell aus `lernen` diktieren, vorlesen lassen, Fehler neu einsprechen.
Der Entwurf steht im [README des Projekts](../../README.md); hier steht, wie
diese App gebaut ist.

## Ablauf

1. **Sprechen.** Ein großer Knopf, sonst nichts. Whisper liefert Text mit
   Segmentgrenzen; genau an diesen Grenzen wird die Aufnahme zerschnitten, und
   jeder Abschnitt bekommt seine eigene WAV-Datei.
2. **Vorlesen.** Die Ergebnisansicht liest von selbst los und markiert dabei,
   wo sie gerade ist. Gehört wird der Fehler, nicht gelesen — die Zielperson
   kann den Text nicht sicher lesen.
3. **Bessern.** Ein Klick auf einen Abschnitt spricht genau diesen neu ein. Das
   neue Audio ersetzt den alten Ausschnitt, alle anderen bleiben stehen.
4. **Bestätigen.** Jeder Abschnitt geht als Audio-Text-Paar an
   `POST /api/korpus/intake` von `hören`. Der Postausgang puffert, wenn `hören`
   nicht erreichbar ist.

Kein Nutzerkonto (Grundentscheidung 7): Eine Instanz ist auf ein Sprecher-
profil und einen Modellstand konfiguriert. Deshalb gibt es hier auch keine
Einstellungsansicht — Mikrofon, Stimme und Sprechtempo werden in `hören`
eingestellt und gelten mit, weil beide Apps unter derselben Adresse liegen und
sich damit den `localStorage` teilen.

## Aufbau

```
backend/
├── main.py                 FastAPI, Router, Ausliefern des Frontends
├── config.py               Settings aus ENV; auch das Ablage-Layout
├── deps.py                 Datenbank, Ablage, Transkriptor
├── api/
│   ├── sessions.py         Sitzung anlegen, ansehen, bestätigen
│   ├── segments.py         diktieren, Abschnitt neu einsprechen, anhören
│   ├── model.py            welcher Modellstand läuft (für die Kopfzeile)
│   └── outbox.py           Postausgang ansehen und noch einmal senden
├── services/
│   ├── segmenter.py        umwandeln, transkribieren, an Zeitmarken schneiden
│   └── outbox.py           Korrekturen zurück an „hören", mit Wiederholung
└── db/                     models.py und migrations/001_init.sql

frontend/src/
├── lib/                    api.ts, zustand.svelte.ts
└── routes/                 Aufnahme.svelte, Ergebnis.svelte
```

Geteilt mit `hören` und über `$ui` eingebunden: `Kopfleiste`, `Recorder`,
`AudioPlayer`, `SegmentList`, `mikrofon.ts`, `speak.ts`,
`einstellungen.svelte.ts` und `app.css` — alles in `packages/ui/`.

## Endpunkte

```
POST   /schreiben/api/sessions                neue Diktiersitzung
GET    /schreiben/api/sessions/{id}
POST   /schreiben/api/sessions/{id}/segments  multipart: audio → Abschnitte
POST   /schreiben/api/sessions/{id}/bestaetigen   → Postausgang, sofort senden
POST   /schreiben/api/segments/{id}/neu       multipart: audio, ersetzt einen
GET    /schreiben/api/segments/{id}/audio
GET    /schreiben/api/model                   Modellstand für die Kopfzeile
GET    /schreiben/api/outbox
POST   /schreiben/api/outbox/senden           noch einmal versuchen
GET    /gesundheit                            auf der Wurzel, für die Überwachung
```

Alles hängt unter `/schreiben` — dem Ort dieser App unter der gemeinsamen
Domain (`BASIS` in `backend/main.py`). So genügt vor den Containern eine
Regel, die den Weg unverändert durchreicht; ein Proxy, der das Präfix
abschneidet, wird nicht gebraucht.

Kein Token: siehe Grundentscheidung 7 und `docs/datenschutz.md`.

## Konfiguration

| Variable | Bedeutung |
|---|---|
| `WORTLAUT_SPRECHER_ID` | wessen Stimme; steht in jeder Korrektur |
| `WORTLAUT_MODELL_REF` | Stand aus der Registry, `<sprecher_id>/<version>` |
| `WORTLAUT_ASR_MODELL` | Whisper-Modell, solange `MODELL_REF` leer ist (`tiny`) |
| `WORTLAUT_ASR` | `local` (faster-whisper) oder `remote` |
| `WORTLAUT_INTAKE_URL` / `_TOKEN` | wohin die Korrekturen gehen |

**Ohne `lernen` fängt man mit `tiny` an.** Ist `WORTLAUT_MODELL_REF` leer, lädt
faster-whisper das unveränderte `whisper-tiny` — schnell, anspruchslos und für
die Zielgruppe absichtlich noch nicht gut. Genau daran wird später sichtbar,
was das eigene Modell bringt. Die Kopfzeile schreibt deshalb dauerhaft hin,
welcher Stand gerade arbeitet.

## Ablage

```
data/diktate/<sprecher_id>/
├── audio/<abschnitt_id>.wav     16 kHz mono, je ein Abschnitt
└── schreiben.sqlite             Sitzungen, Abschnitte, Postausgang
```

Nach Sprecher gegliedert wie der Korpus, obwohl eine Instanz nur einen kennt:
Sonst fände `scripts/purge_speaker.py` diese Dateien nicht, und eine Löschung
wäre unvollständig.

Bewusst **neben** und nicht **im** Korpus: `hören` ist dessen einziger
Schreiber (Grundentscheidung 6). Was hier liegt, ist Arbeitsstand. Sobald ein
Abschnitt im Korpus angekommen ist, wird seine Audiodatei hier gelöscht —
zweimal braucht sie niemand, und es sind Gesundheitsdaten.

## Entwicklung

```bash
uv sync --extra asr                # faster-whisper dazu (nur für ASR=local)
make dev APP=schreiben             # Backend :8001, Vite :5174
```

Aufgerufen wird `http://localhost:5174/schreiben/`. Beim ersten Diktat lädt
faster-whisper sein Modell herunter; das dauert einmalig und braucht Netz.
`hören` kann daneben weiterlaufen (`:8000` und `:5173`); dann führt auch dort
der Reiter „schreiben" hierher.
