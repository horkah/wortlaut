# schreiben — entworfen, noch nicht implementiert

Mit dem Modell aus `lernen` diktieren, vorlesen lassen, Fehler neu einsprechen.
Der Entwurf steht im [README des Projekts](../../README.md); hier steht nur,
was beim Bau schon feststeht.

## Nahtstellen, die bereits existieren

| Was | Wo |
|---|---|
| Transkription (lokal oder entfernt) | `packages/wortlaut/src/wortlaut/whisper/` — ein Protokoll, zwei Umsetzungen |
| Aktiven Modellstand lesen | `packages/wortlaut/src/wortlaut/registry.py` |
| Korrekturen zurückgeben | `POST /api/korpus/intake?sprecher=…` von `hören`, multipart mit `audio`, `text`, `externe_id` |

Die `externe_id` ist die Abschnittskennung aus dieser App. `hören` erkennt
daran eine Wiederholung und legt nichts doppelt an — die Outbox darf also
beliebig oft senden.

## Noch zu bauen

- `backend/` mit `config.py` (`SPRECHER_ID` + `MODELL_REF`, fest),
  `api/{sessions,segments,model}.py`, `services/{segmenter,outbox}.py`
- `frontend/` mit genau zwei Routen: Aufnahme und Ergebnis
- `packages/ui/SegmentList.svelte` — die anklickbare Abschnittsliste

Kein Nutzerkonto (Grundentscheidung 7): Eine Instanz ist auf ein Sprecher-
profil und einen Modellstand konfiguriert. Ein großer Knopf, sonst nichts.
