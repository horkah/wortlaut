# Der Entwurf

Warum wortlaut so gebaut ist, wie es gebaut ist: die Festlegungen, an denen
sich alles Übrige ausrichtet, der Aufbau des Bestands, die Nahtstellen
zwischen den Apps und die Technikwahl dahinter.

Die Apps selbst stehen je in einer eigenen Datei:
[hören](hoeren.md), [lernen](lernen.md), [schreiben](schreiben.md).

---

## Grundentscheidungen

**1. Whisper ist gesetzt.**
Basis ist `openai/whisper-large-v3`, Laufzeit faster-whisper (CTranslate2), Training
über HF Transformers. Nicht weil Whisper das genaueste Modell ist - das ist es seit
2026 nicht mehr - sondern weil es das einzige ist, bei dem Trainingsrezept,
Laufzeit-Ökosystem und dokumentierte Ergebnisse für genau diesen Fall vollständig
vorliegen. MIT-Lizenz, keine Attributionspflicht. Für die Entwicklung ohne GPU
genügt `whisper-small`; unterhalb von `whisper-base` wird nicht gemessen -
`whisper-tiny` versteht bei abweichender Aussprache zu wenig, um einen
Vergleich zu tragen.

**2. Aufnahme erfolgt äußerungsweise, nicht am Stück.**
`hören` zeigt immer genau eine kurze Einheit und nimmt genau dazu auf. Jedes
Audio-Text-Paar ist damit von Haus aus ausgerichtet - kein Forced Alignment, keine
Segmentierungsheuristik, kein Timestamp-Drift. Das ist der größte
Komplexitätsgewinn im ganzen Entwurf.

**3. Ein Modell gehört zu genau einem Sprecher.**
Kein Mehrsprecher-Mischtraining. Ein Sprecher, ein Basismodell, eine Versionskette.

**4. Volles Feintuning ist die Voreinstellung, LoRA ein Schalter.**
Bei stark abweichender Aussprache reicht die Kapazität von LoRA oft nicht, bei
Dialekt schon. Beides über dieselbe Rezeptdatei, nicht über zwei Codepfade.

**5. Was Stunden dauert, läuft in einem eigenen Container; was Sekunden
dauert, läuft dort, wo die Anfrage ist - auf der Karte, wenn eine da ist.**
*(Überarbeitet. Vorher stand hier: „GPU-Arbeit läuft nie im Web-Prozess.")*

Die alte Fassung zog die Grenze am Gerät, und das war die falsche Achse.
Gemeint war das **Training**: Stunden Rechenzeit, Gigabyte an Abhängigkeiten,
ein Prozess, der einen Webdienst nicht neu starten lassen darf. Das bleibt, wo
es war - eigener Container, eigenes Abbild, verbunden über ein Verzeichnis
(`data/snapshots/`).

Was die Regel mitgenommen hat, ohne es zu meinen, war die **Erkennung**. Die
dauert Sekunden, hängt an einer laufenden Anfrage und hat im selben Rechner
eine Karte ungenutzt liegen lassen: vier Sekunden je Diktat statt einer
Viertelsekunde. Sie läuft deshalb jetzt dort, wo die Anfrage ist, und nimmt die
Karte, wenn eine da ist.

Worauf gerechnet wird, entscheidet **eine** Stelle
(`wortlaut/rechenwerk.py`) - für „schreiben", für die Auswertung in „hören" und
für die Bewertung eines Laufs. Nicht aus Ordnungsliebe: Diese drei messen
dieselben Modelle, und ihre Rechenzeiten stehen in einer Tabelle nebeneinander.
Sie sind nur vergleichbar, wenn sie von derselben Maschine kommen.

Austauschbar bleibt beides: Transkription hat eine lokale und eine entfernte
Umsetzung, und ohne Karte fällt die lokale auf den Prozessor zurück - langsamer
und unverändert richtig.

**6. Genau ein Schreiber pro Datenbestand.**
`hören` schreibt den Korpus, `lernen` liest ihn. `lernen` schreibt die
Modell-Registry, `schreiben` liest sie. Keine geteilten Schreibrechte, keine
verteilten Transaktionen.

**7. `schreiben` verlangt keine Anmeldung - führt aber denselben Sprecher.**
Die Zielperson kann schlecht lesen und schreiben; ein Anmeldefeld wäre eine
unüberwindbare Hürde, und ein großer Knopf bleibt der ganze Zweck der App.
Trotzdem ist eine Instanz nicht mehr auf **einen** Sprecher konfiguriert: Sie
leitet ihn aus dem Zugang ab, den der Browser vorlegt - demselben, den `hören`
ausgibt. Beide Apps liegen unter einer Domain und teilen sich damit den
`localStorage`, also genügt weiterhin ein persönlicher Link, einmal geöffnet,
gleich in welcher der beiden Apps.

Jeder Sprecher bekommt aus `lernen` sein **eigenes** Modell
(Grundentscheidung 3), und was er hier diktiert, fließt als Korrektur in
**seinen** Korpus zurück. Beides braucht die Kennung zur Laufzeit; eine Instanz
je Person wäre eine Instanz je Modell und je Korpus gewesen.

**8. Jede Entscheidung hat genau einen Ort.**
Welches Modell gilt, wird in `lernen` unter **Modelle** entschieden - dort, wo
die Zahlen stehen, an denen sie hängt, und nirgends sonst. `schreiben` liest
diese Freigabe und zeigt sie an. Zwei Ansichten für dieselbe Frage sind keine
doppelte Bequemlichkeit, sondern zwei Gelegenheiten, verschiedene Antworten zu
geben.

**9. Ein Zugang sagt, wem etwas gehört - nicht, was es kosten darf.**
Der Sprecherzugang beantwortet eine Frage: wessen Korpus, wessen Modell, wessen
Diktat. Er beantwortet nicht die zweite, die es nur an einer Stelle gibt - ob
jemand die Karte für Stunden belegen darf. Ein Training kostet Rechenzeit,
Strom und die Wartezeit aller anderen, und der Zugang ist an jeden ausgegeben,
der aufnimmt; wäre er auch die Erlaubnis, wäre jeder Aufnahmelink ein Knopf,
der Geld kostet, so oft wie jemand darauf drückt. Deshalb steht vor
`POST /lernen/api/laeufe` ein zweites Geheimnis (`WORTLAUT_TRAINER_KEY`,
Kopfzeile `X-Trainer-Key`) - und **nur** dort. Zusehen, zurücknehmen, löschen
und freigeben kosten nichts und bleiben beim Sprecher. Leer heißt abgeschaltet,
nicht offen, wie bei Verwaltung und Aufsicht.

---

## Projektstruktur

```
wortlaut/
├── README.md
├── Dockerfile                     # ein Abbild für beide Apps
├── compose.yaml
├── Makefile                       # test, dev, migrate, train, release
├── pyproject.toml                 # Abhängigkeiten und Testeinstellungen
├── conftest.py                    # geteilte Testbausteine
├── .env.example
│
├── apps/
│   ├── gesamt.py                  # alle drei Apps in einem Prozess (Betrieb)
│   ├── hoeren/                    # App „hören"
│   │   ├── Dockerfile
│   │   ├── backend/
│   │   │   ├── main.py            # FastAPI, Router, Ausliefern des Frontends
│   │   │   ├── config.py          # Settings aus ENV, ein Ort
│   │   │   ├── deps.py            # Zugang → Sprecher, Datenbank, Ablage
│   │   │   ├── api/
│   │   │   │   ├── speakers.py    # Sprecherprofile
│   │   │   │   ├── zugang.py      # Zugänge ausgeben, zurückziehen, auskunft
│   │   │   │   ├── admin.py       # Aufsicht: einsehen, sichern, löschen
│   │   │   │   ├── sources.py     # LLM-Themen, Textupload
│   │   │   │   ├── prompts.py     # nächste Sprecheinheit, Sitzungen
│   │   │   │   ├── recordings.py  # Upload, Prüfung, Verwerfen
│   │   │   │   ├── progress.py    # gesammelte Minuten, Marken
│   │   │   │   └── intake.py      # Korrekturen von „schreiben"
│   │   │   ├── services/
│   │   │   │   ├── prompt_queue.py    # Reihenfolge, Wiederaufnahme
│   │   │   │   ├── quality.py         # Pegel, Clipping, Dauerplausibilität
│   │   │   │   ├── export.py          # Datensatz als .zip (Text-Audio-Paare)
│   │   │   │   └── loeschung.py       # was zu einem Sprecher gehört
│   │   │   └── db/
│   │   │       ├── models.py      # typisierte Modelle zum Schema
│   │   │       └── migrations/    # 001_init.sql, 002_…
│   │   ├── frontend/
│   │   │   ├── vite.config.ts     # Alias auf packages/ui, Proxy auf /api
│   │   │   └── src/
│   │   │       ├── lib/           # api.ts, zustand.svelte.ts
│   │   │       └── routes/        # Verwaltung, Quelle wählen, Aufnahme,
│   │   │                          # Fortschritt, Einsicht, Einstellungen
│   │   └── tests/                 # Endpunkte, Warteschlange, Intake, Aufsicht
│   │
│   ├── lernen/                    # App „lernen"
│   │   ├── backend/
│   │   │   ├── main.py            # FastAPI unter /lernen, hinter dem Zugang
│   │   │   ├── config.py          # Grundmodell, Gerät, Takt des Läufers
│   │   │   ├── deps.py            # Zugang, eigene Datenbank, Korpus (lesend!)
│   │   │   ├── api/               # aufteilung.py, laeufe.py, modelle.py
│   │   │   ├── services/
│   │   │   │   ├── aufteilung.py  # 2:1, einmal vergeben und nie umsortiert
│   │   │   │   ├── auftraege.py   # Schnappschuss und Auftrag schreiben
│   │   │   │   ├── messwerte.py   # alle Modelle auf denselben Testaufnahmen
│   │   │   │   └── vergleich.py   # trainierter Stand gegen die Grundlinie
│   │   │   └── db/                # genau eine Tabelle: die Aufteilung
│   │   ├── frontend/              # Aufteilung, Training (Kurven), Modelle
│   │   ├── training/              # das, was auf der GPU läuft - eigenes Abbild
│   │   │   ├── Dockerfile         # pytorch/cuda, ~4 GB, eigener Compose-Dienst
│   │   │   ├── laeufer.py         # wartet auf Aufträge, einer nach dem anderen
│   │   │   ├── finetune.py        # das Training selbst, schreibt die Kurven
│   │   │   ├── bewerten.py        # Testaufnahmen messen, Stand eintragen
│   │   │   ├── daten.py           # Manifest → Merkmale und Marken
│   │   │   └── rezepte/           # whisper_full.yaml, whisper_lora.yaml
│   │   └── tests/                 # Aufteilung, Aufträge, Vergleich, Grenzen
│   │
│   └── schreiben/                 # App „schreiben"
│       ├── Dockerfile
│       ├── backend/
│       │   ├── main.py            # FastAPI hinter dem Zugang des Sprechers
│       │   ├── config.py          # Modellstand, ASR, Intake-Adresse
│       │   ├── deps.py            # Zugang, Datenbank, Ablage, Transkriptor
│       │   ├── api/
│       │   │   ├── sessions.py    # Diktiersitzung, Bestätigen
│       │   │   ├── segments.py    # diktieren, Abschnitt neu einsprechen
│       │   │   ├── model.py       # was geladen ist, und ob ausgesteuert wird
│       │   │   ├── outbox.py      # Postausgang ansehen, noch einmal senden
│       │   │   └── zugang.py      # wer ruft - für die Kopfzeile
│       │   ├── services/
│       │   │   ├── segmenter.py   # transkribieren, an Zeitmarken schneiden
│       │   │   └── outbox.py      # Korrekturen zurück an „hören"
│       │   └── db/                # models.py, migrations/
│       ├── frontend/
│       │   └── src/routes/        # Aufnahme, Ergebnis, Zugangsdaten
│       └── tests/                 # Diktat, Korrekturen, Modell, Zugang
│
├── tests/                         # was keine einzelne App betrifft: gesamt.py
│
├── packages/
│   ├── wortlaut/                  # eine Python-Bibliothek, von allen genutzt
│   │   ├── src/wortlaut/
│   │   │   ├── audio.py           # 16 kHz mono, Pegel, Dauer
│   │   │   ├── corpus.py          # Korpus-Layout lesen und schreiben
│   │   │   ├── registry.py        # Modellstände lesen und schreiben
│   │   │   ├── rechenwerk.py      # worauf gerechnet wird - eine Antwort für alle
│   │   │   ├── storage.py         # Blob-Ablage: lokal (S3 vorbereitet)
│   │   │   ├── sicherung.py       # Sicherungsarchiv schreiben und einspielen
│   │   │   ├── db.py              # SQLite-Verbindung, Migrationen, Sicherungskopie
│   │   │   ├── ids.py             # zeitlich sortierbare Kennungen
│   │   │   ├── metriken.py        # WER, CER, MER, WIL und die Zahl darüber
│   │   │   ├── zugang.py          # Sprecherzugang: Form, Prüfwert, Prüfung
│   │   │   ├── text/
│   │   │   │   ├── llm.py         # Thema + Altersspanne → Text
│   │   │   │   ├── upload.py      # txt, md, pdf, epub, docx → Reintext
│   │   │   │   └── chunker.py     # Text → sprechbare Einheiten
│   │   │   └── whisper/           # für „schreiben": lokal oder entfernt
│   │   │       ├── local.py       # faster-whisper
│   │   │       └── remote.py      # OpenAI-kompatibler Endpunkt
│   │   └── tests/                 # Chunker, Textformate, Audio, Ablage
│   │
│   └── ui/                        # geteilte Svelte-Komponenten und Einstellungen
│       ├── Rahmen.svelte          # Kopf, Inhalt, Fuß - der Rahmen jeder App
│       ├── Kopfleiste.svelte      # Marke, App-Reiter, Sprecher, Menüknopf
│       ├── Fusszeile.svelte       # eine Zeile: welcher Stand hier läuft
│       ├── Einstellungen.svelte   # Mikrofon, Stimme, Tempo - für alle Apps
│       ├── Darstellung.svelte     # Farben, Schrift, was in der Leiste steht
│       ├── Zugangsdaten.svelte    # der Zugang dieses Browsers, in jeder App
│       ├── KeinZugang.svelte      # was dasteht, wenn keiner da ist - dreimal dasselbe
│       ├── PinSchloss.svelte      # die PIN vor Darstellung und Zugangsdaten
│       ├── pin.svelte.ts          # eine PIN, eine Sitzung, alle Apps
│       ├── Textvergleich.svelte   # Vorlage gegen Erkennung, Zeichen für Zeichen
│       ├── diff.ts                # längste gemeinsame Teilfolge, zeichenweise
│       ├── zugang.ts              # wo der Zugang liegt; ein Eintrag für alle
│       ├── api.ts                 # wie eine Anfrage hinausgeht - für alle drei
│       ├── route.ts               # die Route im Hash; derselbe Router überall
│       ├── wer.ts                 # wer ruft: die Antwort des Servers, ausgewertet
│       ├── apps.ts                # die drei Apps, ihre Ansichten, das Menü,
│       │                          # und was davon sich ausblenden lässt
│       ├── reiter.ts              # wo man zuletzt war, je App
│       ├── app.css                # das gemeinsame Aussehen aller Apps
│       ├── Recorder.svelte
│       ├── AudioPlayer.svelte
│       ├── PromptView.svelte      # eine Einheit groß, Kontext blass („hören")
│       ├── SegmentList.svelte     # anklickbare Abschnitte („schreiben")
│       ├── Mikrofontest.svelte    # Gerät wählen, Pegel sehen, Probe hören
│       ├── Pegelanzeige.svelte    # Pegelbalken, Grenzen wie in quality.py
│       ├── mikrofon.ts            # Aufnahmekette: Gerät, Verstärkung, Messung
│       ├── speak.ts               # Vorlesen über Web Speech API, Stimme und Tempo
│       └── einstellungen.svelte.ts # Gerätewerte im localStorage, appübergreifend
│
├── data/                          # nicht im Git
├── docs/                          # dieser Entwurf, die drei Apps, Betrieb,
│                                  # Konfiguration, Entwicklung, Datenschutz
└── scripts/
    ├── migrate.py
    ├── augmentieren.py            # abgewandelte Fassungen aller Aufnahmen
    ├── restore.py                 # eine Sicherung zurückspielen
    └── purge_speaker.py           # Löschung, vollständig
```

---

## Erste Nahtstelle: der Korpus

Ein Verzeichnis, kein Dienst. `hören` ist der einzige Schreiber, `lernen` liest.
Beide laufen auf demselben Server, SQLite im WAL-Modus erlaubt gleichzeitige Leser.

```
data/korpus/<sprecher_id>/
├── audio/
│   ├── <aufnahme_id>.wav                    # 16 kHz mono, PCM 16 bit
│   └── varianten/
│       └── <aufnahme_id>.<fassung>.wav      # abgewandelt, gerechnet
└── hoeren.sqlite                            # Vorlagen, Aufnahmen, Sitzungen
```

Unter `varianten/` liegen die abgewandelten Fassungen jeder Aufnahme
(siehe [hören](hoeren.md#vier-fassungen-je-aufnahme)). Sie liegen ein Stockwerk tiefer und
nicht daneben, und das ist der ganze Schutz gegen Verwechslung: `audio/` ist
genau das, was in `recordings.blob` steht - was ein Mensch gesprochen hat -,
`audio/varianten/` ist das Abgeleitete, das sich jederzeit neu rechnen lässt.
Ein Werkzeug, das über `audio/` läuft, muss den Unterschied nicht am
Dateinamen erraten. Der Name trägt trotzdem beides, erst die Aufnahme, dann
die Fassung: Ein sortiertes Verzeichnis liegt damit nach Aufnahmen geordnet
da, und Aufnahmekennungen enthalten keinen Punkt.

Die Datenbank liegt **innerhalb** des Sprecherverzeichnisses, also eine je
Sprecher. Das hat drei Folgen: `lernen` liest genau eine Datei statt einer
gefilterten Tabelle, eine vollständige Löschung ist das Entfernen eines
Verzeichnisses, und jeder Endpunkt von `hören` muss seinen Sprecher nennen.

`lernen` kopiert daraus vor jedem Job einen unveränderlichen Schnappschuss:

```
data/snapshots/<job_id>/
├── manifest.jsonl
└── sprecher.txt                # nur die Sprecher-ID
```

`sprecher.txt` ist die Zusage an die Löschung: `scripts/purge_speaker.py` findet
einen Schnappschuss daran, ohne das Manifest deuten zu müssen. Fehlt die Datei,
meldet das Skript den Schnappschuss zur Prüfung von Hand.

Eine Zeile pro Aufnahme:

```json
{"audio":"audio/rec_01J8….wav","text":"…","quelle":"vorlage","modus":"gelesen",
 "dauer_s":4.8,"gewicht":1.0,"split":"train"}
```

Der Schnappschuss ist der Grund, warum weiter aufgenommen werden kann, während ein
Training läuft, ohne dass das Ergebnis unreproduzierbar wird.

**Quellen und Gewichte.** `quelle` ist `vorlage` oder `korrektur`. Korrekturen
stammen aus `schreiben` und sind schwächere Daten: der Text ist keine Vorgabe,
sondern eine vom Nutzer abgenickte Maschinenausgabe. Wer sie gleichrangig einspeist,
trainiert dem Modell seine eigenen Fehler an. Voreinstellung ist ein niedrigeres
Gewicht, festgelegt im Rezept.

**Modi.** `modus` ist `gelesen`, `nachgesprochen` oder `frei`. Die ersten beiden
kommen aus `hören` (siehe [dort](hoeren.md#vorsprechen-statt-vorlesen)), `frei` aus `schreiben`:
dort spricht die Person selbst formulierte Sätze, nicht eine Vorlage.
`GET /api/progress` zählt beides getrennt, damit sich die Gewichtung an Zahlen
statt an Vermutungen ausrichten kann.

---

## Zweite Nahtstelle: die Modell-Registry

Ebenfalls Dateien statt Tabelle. Ein Modellstand ist ein Verzeichnis, das man
kopieren, sichern und per `scp` verschieben kann.

```
data/modelle/<sprecher_id>/
├── freigabe.json               # welches Modell dieser Mensch benutzt
└── <version>/
    ├── manifest.json
    ├── ct2/                    # für faster-whisper exportiert
    └── checkpoint/             # Rohgewichte, optional
```

```json
{
  "id": "spr_7f2a/20260912T1420-lora-augmentiert",
  "sprecher_id": "spr_7f2a",
  "basismodell": "openai/whisper-small",
  "methode": "lora",
  "daten": "augmentiert",
  "job_id": "job_01J8…",
  "erstellt": "2026-09-12T14:20:03Z",
  "daten_umfang": { "train": 1832, "validierung": 118, "test": 480 },
  "metriken": { "wer": 0.146, "cer": 0.061, "genauigkeit": 81.4,
                "test_einheiten": 480 },
  "laufzeit": "faster-whisper>=1.1",
  "status": "fertig"
}
```

Die Version nennt Zeit, Methode und Datensatz, und das ist kein Schmuck: Es
liegen vier Stände nebeneinander, die sich in genau diesen Punkten
unterscheiden (zwei Methoden mal zwei Datensätze). Eine Zeitmarke allein ließe
offen, welcher von den vieren gemeint ist.

`status` ist `fertig`, bis jemand den Stand in `lernen` **freigibt** - dann
wird er `active` und jeder andere `zurueckgezogen`.

### Die Freigabe

Freigegeben ist höchstens ein Modell je Sprecher, und es ist das, mit dem
`schreiben` diktiert. Zwei freigegebene Modelle wären keine Freigabe, sondern
eine offene Frage, die irgendwo weiter unten jemand beantworten müsste.

Freigeben lässt sich seit der Zusammenlegung der Modellansichten auch ein
**unverändertes Grundmodell**: „meins ist noch nicht besser als `medium`" ist
eine Antwort, und sie braucht denselben Knopf wie jede andere. Für ein
Grundmodell gibt es hier aber kein Verzeichnis und kein Manifest. Die Freigabe
steht deshalb in einer eigenen, winzigen Datei je Sprecher:

```json
{ "ref": "spr_7f2a/20260912T1420-lora-augmentiert" }
```

Darin steht entweder eine Standkennung `<sprecher_id>/<version>` oder ein
Grundmodellname wie `medium`; unterscheiden lassen sich beide am Schrägstrich,
und genau deshalb dürfen sie in dasselbe Feld. Ein leeres `ref` nimmt die
Freigabe zurück.

Die Manifeste führen ihren `status` weiter mit: Wer ein Verzeichnis wegkopiert,
soll ihm ansehen, was es einmal war. Geschrieben werden beide in einem Zug,
gelesen wird die Freigabedatei - und fehlt sie, zählen die Manifeste, damit ein
Bestand von vorher nach dem Aufspielen nicht stumm auf das Grundmodell
zurückfällt.

### Welches Modell `schreiben` lädt

Zwei Herkünfte, und die Reihenfolge ist die Rangfolge:

1. **`WORTLAUT_MODELL_REF`**, falls gesetzt - der eine Stand für alle, zum
   Erproben, nicht für den Betrieb.
2. **Die Freigabe** dieses Sprechers.

Darunter liegt das unveränderte Grundmodell aus `WORTLAUT_ASR_MODELL`: Damit
fängt eine Installation an, solange nichts freigegeben ist.

`schreiben` wählt nicht mehr selbst (Grundentscheidung 8). Es führte einmal
eine eigene Auswahlliste, in der sich jeder Stand und jedes Grundmodell
ausprobieren ließ - nur stand dort keine einzige Zahl daneben, an der die Wahl
hing. Die Liste ist in `lernen` aufgegangen, wo die Zahlen entstehen; aus
`schreiben` führt ein Klick auf die Modellzeile dorthin.

Was dabei nicht aufgegeben wurde: Zu jeder Ausgabe steht fest, welches Modell
sie erzeugt hat. Die Zeile unter dem Aufnahmeknopf nennt es dauerhaft, samt
Methode und Datensatz - vier Stände vom selben Tag wären sonst nicht
auseinanderzuhalten.

### Aussteuern vor dem Erkennen

Daneben steht ein Schalter, und er ist **an**: Vor dem Erkennen
wird das Diktat lauter gerechnet, bis seine Spitze knapp unter dem Anschlag
steht - dieselbe Abwandlung, die `hören` als `pegel` neben jede Aufnahme legt.
Der Aufnahmepegel eines Browsers hängt am Gerät, am Abstand und an der Stimme;
bei leisen Aufnahmen schöpft Whisper den Wertebereich nicht aus, den seine
Merkmalsberechnung erwartet, und gerade die kleineren Modelle hören mit
Aussteuerung merklich besser. Es ist zugleich das schlichteste denkbare
Verfahren - ein einziger Faktor über die ganze Aufnahme - und ändert nichts
daran, *wie* gesprochen wurde, nur daran, wie weit der Regler aufgedreht war.

Abschaltbar bleibt es trotzdem: Wer eine gut ausgesteuerte Kette hat, gewinnt
nichts mehr und soll die Aufbereitung nicht aufgedrängt bekommen. Der Schalter
steht in der Modellübersicht von `lernen`, bei dem Modell, auf das er wirkt -
er ändert nicht, wer zuhört, sondern was dieser zu hören bekommt.

**Ausgesteuert wird nur, was Whisper hört.** Abgelegt und später als Korrektur
an `hören` gegeben wird die Aufnahme, wie sie gesprochen wurde. Das ist kein
Detail, sondern die Grenze zwischen Hörhilfe und Datensatz: Aus einer
bestätigten Korrektur wird drüben eine Aufnahme im Korpus, und dort entsteht
aus ihr selbst eine ausgesteuerte Fassung. Läge hier schon eine ausgesteuerte
als „Original", wäre die Abwandlung drüben ein Nichts - und der Vergleich der
vier Fassungen für genau diese Aufnahmen stillschweigend entwertet. Die
Zeitmarken, an denen geschnitten wird, passen weiterhin: Das Aussteuern ändert
die Lautstärke jedes Abtastwerts, nicht ihre Zahl.

---

## Datenmodell

**hören**

| Tabelle | Zweck |
|---|---|
| `speakers` | Profil, Sprache, Basismodell, Prüfwert des Zugangs - genau eine Zeile je Datenbank |
| `text_sources` | LLM-Auftrag, hochgeladener Text oder Korrektur, mit Parametern |
| `prompts` | eine Sprecheinheit, Herkunft, fortlaufende Position |
| `sessions` | Aufnahmesitzung: begonnen, zuletzt aktiv |
| `recordings` | Blob-Referenz, Messwerte, Modus, Status, Kennung aus „schreiben" |
| `erkennungen` | je Aufnahme, Modell und Fassung eine Messung - Text, Fehlerraten, Rechenzeit und das Rechenwerk, auf dem sie entstand |

**lernen**

| Tabelle | Zweck |
|---|---|
| `aufteilung` | je Aufnahme: Training, Validierung oder Test - einmal vergeben, nie geändert |

Es ist genau eine Tabelle, und das ist Absicht. Eine Jobtabelle daneben hätte
nahegelegen und wäre eine zweite Wahrheit über denselben Lauf gewesen: Der
Trainer läuft in einem anderen Container und schreibt in Dateien, die Zeile
hier wüsste nichts davon - und irgendwann stünde darin „läuft", während längst
nichts mehr läuft. Ein Lauf ist deshalb ein Verzeichnis
(`data/snapshots/<job_id>/`), ein Modellstand auch (`data/modelle/…`), und der
Korpus gehört ohnehin `hören`. Übrig bleibt die eine Sache, die nirgends sonst
stehen kann.

**schreiben**

| Tabelle | Zweck |
|---|---|
| `sessions` | eine Diktiersitzung |
| `segments` | Text, Reihenfolge, Audio, Herkunft (initial/neu) |
| `outbox` | offene Korrekturen mit Wiederholungszähler |
| `erkennung` | die Aufbereitung dieses Sprechers - genau eine Zeile |

Zugriff über SQLAlchemy 2.0 mit typisierten Modellen. Schemaänderungen als
nummerierte `.sql`-Dateien. Kein Alembic - bei diesem Schemaumfang ist die
Migrationsmaschinerie größer als das Schema.

Angewendet werden sie an drei Stellen, und die dritte ist die wichtigste: beim
Anlegen eines Sprechers (`api/speakers.py`), beim ersten Zugriff auf dessen
Datenbank (`deps.engine_fuer`) und für alle Korpora auf einmal mit
`make migrate` - im Container `docker compose exec wortlaut python
scripts/migrate.py`, denn dort gibt es weder `make` noch `uv`.

Die zweite Stelle ist die wichtigste: Ein Update darf nicht davon abhängen,
dass sich jemand an ein Skript erinnert. Der Container startet uvicorn, sonst
nichts - und ein Korpus im ältesten Schemastand wird beim ersten Zugriff
eingeholt, statt an einer fehlenden Spalte zu scheitern.

Zwei Spalten tragen mehr Bedeutung, als ihr Name verrät:

- `prompts.position` ist über **alle** Quellen eines Sprechers fortlaufend. Eine
  neue Textquelle hängt hinten an, statt in die laufende Sitzung zu springen.
- `recordings.externe_id` ist die Abschnittskennung aus `schreiben` und
  eindeutig. Die dortige Outbox darf damit beliebig oft wiederholen, ohne dass
  dieselbe Korrektur zweimal im Korpus landet.

---

## Technologien

| Bereich | Wahl | Warum |
|---|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn | ML-Ökosystem ist Python, async für Uploads |
| Datenbank | SQLite (WAL) | ein Server, ein Sprecher; Backup heißt Datei kopieren |
| Frontend | Svelte 5, Vite, TypeScript | kompiliert weg, kein Laufzeit-Framework auf schwachen Geräten |
| Aufnahme | `MediaRecorder` (Opus), serverseitig ffmpeg → 16 kHz mono WAV | Browser liefern kein WAV, Konvertierung an einer Stelle |
| Vorlesen | Web Speech API | deutsche Stimmen fast überall vorhanden, keine Infrastruktur, keine Latenz - dafür schwankt die Qualität je nach Betriebssystem stark, Stimme und Tempo sind deshalb einstellbar |
| ASR | faster-whisper (CTranslate2), auf der Karte `int8_float16`, sonst `int8` | schnellste brauchbare Whisper-Laufzeit auf beidem; die halbe Darstellung, weil vier Modelle gleichzeitig im Speicher liegen und sich die Karte mit Training und Sprachmodell teilen |
| ASR entfernt | OpenAI-kompatibler Endpunkt | ein Adapter deckt mehrere Anbieter ab |
| Training | HF Transformers, Datasets, Accelerate | Standardrezept für Whisper, breit dokumentiert |
| Diagramme | Apache ECharts, nachgeladen und nur mit den eingetragenen Teilen | Finger und Maus gleichermaßen, gemischte Reihen in einem Bild, und `connect` koppelt mehrere Diagramme aneinander - der Punkt, an dem die schlankeren Bibliotheken aufhören |
| Textquelle | LLM über einen Adapter, OpenAI-kompatibel oder Anthropic | Thema und Altersspanne als Prompt-Parameter; derselbe Adapter bedient ein lokales Ollama und die bezahlten Anbieter - für ein paar Vorlesesätze genügt ein kleines Modell auf der eigenen GPU |
| Jobs | ein Verzeichnis je Auftrag, ein Läufer, der danach sieht | keine Broker-Abhängigkeit für eine Warteschlange mit selten mehr als einem Eintrag - und keine Tabelle, die „läuft" sagt, während längst nichts mehr läuft |
| Proxy | der vorhandene Reverse Proxy des Wirts | TLS und Pfadverteilung gehören zur Maschine, nicht in dieses Projekt |
| Auth | je Sprecher ein Zugang, der zugleich die Kennung ist - derselbe in allen drei Apps; der Token davor schützt nur die Verwaltung, ein zweiter die Aufsicht | die Bindung zwischen Aufrufer und Verzeichnis muss der Server ziehen, nicht der Aufrufer; ein Mensch, ein Link, drei Apps |
| Tests | pytest, FastAPI-TestClient | echte SQLite-Datei, echte Endpunkte, kein Nachbau |
| Werkzeug | uv | eine Abhängigkeitsdatei, ein Befehl, keine Diskussion |

---

## Bewusst nicht enthalten

- **Phonetisch ausgewogene Vorlagen.** LLM-Text ist flüssig, aber phonetisch
  beliebig. Eine dritte Textquelle aus einer festen, phonetisch abgedeckten
  Satzliste wäre für Sprechstörungen wirksamer und steht auf der Liste.
- **Rollen und Mandanten.** Mehrere Personen an einer `hören`-Instanz gehen,
  seit der Zugang die Kennung trägt - aber es gibt genau drei Arten von
  Aufrufer, den Sprecher, die Verwaltung und die Aufsicht, und keine
  Rechtematrix dazwischen. Jede ist ein Token, keine ist ein Konto. Ein
  Benutzerkonzept wäre größer als das, was es zu trennen gibt.
- **Streaming-Transkription.** Die Vorlese-Korrektur-Schleife arbeitet
  abschnittsweise; Live-Erkennung würde das Bedienkonzept nicht verbessern.
- **Diarisierung, Zeitstempel auf Wortebene.** Ein Sprecher, kurze Abschnitte.
