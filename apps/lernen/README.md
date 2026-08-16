# lernen — entworfen, noch nicht implementiert

Aus den Proben von `hören` ein sprecherspezifisches Whisper-Modell feintunen.
Der Entwurf steht im [README des Projekts](../../README.md); hier steht nur,
was beim Bau schon feststeht.

## Nahtstellen, die bereits existieren

| Was | Wo |
|---|---|
| Korpus lesen (nur lesend!) | `data/korpus/<sprecher_id>/` — Layout in `packages/wortlaut/src/wortlaut/corpus.py` |
| Modellstände schreiben | `packages/wortlaut/src/wortlaut/registry.py` |
| Schnappschuss löschbar halten | Datei `sprecher.txt` mit der Sprecher-ID neben dem Manifest ablegen — sonst kann `scripts/purge_speaker.py` ihn nicht zuordnen |

## Noch zu bauen

- `backend/` mit `api/{snapshots,jobs,models}.py` und
  `services/{snapshot,backends,job_worker}.py`
- `frontend/` mit Jobs, Metriken, Modellständen
- `training/` (Dockerfile, `finetune.py`, `evaluate.py`, Rezepte
  `whisper_full.yaml` und `whisper_lora.yaml`) — das, was auf der GPU läuft
- `make train` und `make release` im Makefile ersetzen dort die Platzhalter

Beim Manifest gilt: `quelle` ist `vorlage` oder `korrektur`. Korrekturen
stammen aus `schreiben` und bekommen im Rezept ein niedrigeres Gewicht — wer
sie gleichrangig einspeist, trainiert dem Modell seine eigenen Fehler an. Die
App `hören` liefert die Zahlen dazu bereits unter
`GET /api/progress?sprecher=…` (`nach_modus`, `nach_quelle`).
