# lernen - aus den Proben ein eigenes Modell

Der Entwurf steht im [README des Projekts](../../README.md); hier steht, wie
die App gebaut ist und wo was liegt.

## Zwei Teile, ein Verzeichnis dazwischen

| Teil | Wo | Was er tut |
|---|---|---|
| **Oberfläche** | `backend/`, `frontend/` | teilt zu, beauftragt, zeigt Kurven und Vergleich - rechnet **nichts** |
| **Trainer** | `training/` | nimmt Aufträge aus der Warteschlange und rechnet sie auf der Karte |

Verbunden sind sie über `data/snapshots/<job_id>/` und nicht über einen
Netzweg (`packages/wortlaut/src/wortlaut/laeufe.py`). Das hat drei Folgen, und
alle drei sind der Grund dafür: Der Webdienst kann neu starten, während ein
Training läuft. Der Trainer kann neu starten, ohne dass ein Auftrag
verlorengeht. Und es gibt keinen Weg, auf dem der eine den anderen zum
Absturz bringt.

Ein Auftragsverzeichnis:

```
data/snapshots/<job_id>/
├── sprecher.txt          nur die Sprecher-ID - die Zusage an die Löschung
├── auftrag.json          wer, welche Methode, welcher Datensatz
├── manifest.jsonl        der Schnappschuss: je Zeile eine Probe
├── zustand.json          was daraus wurde - vom Trainer geschrieben
├── fortschritt.jsonl     je Zeile ein Ereignis: Schritt, Verlust, Stufe
├── bewertung.jsonl       je Zeile eine Testaufnahme, vom fertigen Modell
└── protokoll.txt         die rohe Ausgabe
```

Offen ist ein Auftrag, zu dem es noch keinen `zustand.json` gibt - das ist die
ganze Warteschlange.

Gelöscht wird das Verzeichnis als Ganzes, und mit ihm der Modellstand, der aus
dem Lauf hervorging (`services/auftraege.py`). Ein Stand ohne seinen Lauf wäre
ein Modell, dessen Herkunft niemand mehr nachsehen kann - genau das, wogegen
diese App gebaut ist. Die Aufteilung bleibt: Sie gehört den Aufnahmen, nicht
den Läufen.

## Was feststeht und warum

* **Das Grundmodell ist `whisper-small`.** Nicht wählbar: Es ist die kleinste
  Stufe, die ganze Sätze trifft, es passt in den Speicher einer einzelnen
  Karte, und es ist dieselbe Reihe, gegen die „hören" schon misst. Ohne diesen
  gemeinsamen Nenner wäre der Vergleich mit der Grundlinie keiner.
* **Die Aufteilung ist 2:1** und wird nie umsortiert
  (`backend/services/aufteilung.py`). Eine Aufnahme, die einmal geprüft hat,
  trainiert nie - sonst misst der Test das Auswendiggelernte.
* **Vier Läufe, nicht mehr.** Zwei Methoden (`full`, `lora`) mal zwei
  Datensätze (`original`, `augmentiert`). Alles andere - Lernrate, Durchgänge,
  Stapelgröße - steht in `training/rezepte/*.yaml` und nicht in der Oberfläche:
  Jede Einstellmöglichkeit wäre eine, deren Wirkung später niemand mehr
  zuzuordnen weiß.

## Betrieb

```bash
# Die Oberfläche läuft im Prozess der anderen Apps mit (apps/gesamt.py).
docker compose up -d

# Der Trainer ist ein eigener Dienst und startet nicht von selbst.
docker compose --profile training up -d training
docker compose logs -f training
```

Auf einer Maschine mit Karte und ohne Container: `make trainer`. Dafür müssen
`torch`, `transformers`, `peft` und `accelerate` installiert sein - sie stehen
absichtlich nicht in den Abhängigkeiten des Projekts, sondern im Abbild unter
`training/Dockerfile`.

## Nahtstellen zu den anderen Apps

| Was | Wo | Richtung |
|---|---|---|
| Korpus | `data/korpus/<sprecher_id>/` | **nur lesend** - „hören" ist sein einziger Schreiber |
| Grundlinie | Tabelle `erkennungen` im Korpus | nur lesend; gemessen hat sie „hören" unter „Auswertung" |
| Modellstände | `data/modelle/<sprecher_id>/<version>/` | schreibend; „schreiben" liest sie |
| Aufteilung | `data/lernen/<sprecher_id>/lernen.sqlite` | die einzige eigene Tabelle dieser App |
