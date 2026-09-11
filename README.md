<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/wortlaut-logo-invers.svg" />
  <img src="assets/wortlaut-logo.svg" alt="" width="88" height="88" />
</picture>

# wortlaut

Personalisierte Spracherkennung für Deutsch, wenn die Standardmodelle versagen -
bei Dialekt, starkem Akzent, Dysarthrie oder anderen Sprechstörungen.

Aus dem Laut wird das Wort, und zwar der Wortlaut: was die Person gesagt hat, nicht
das, was ein Sprachmodell für plausibel hält.

Drei Apps, die nacheinander greifen:

| App | Aufgabe | Status |
|---|---|---|
| **hören** | Sprachproben sammeln - zu LLM-erzeugten oder hochgeladenen Texten | läuft, mit Tests |
| **lernen** | aus den Proben ein sprecherspezifisches Whisper-Modell feintunen | entworfen |
| **schreiben** | mit diesem Modell diktieren, vorlesen lassen, Fehler neu einsprechen | läuft, mit Tests |

`lernen` liest die Dateien von `hören`. `schreiben` liest das Modell von `lernen` und
gibt Korrekturen an `hören` zurück. Sonst berühren sie sich nicht.

Solange `lernen` fehlt, läuft `schreiben` mit dem unveränderten `whisper-small`.
Das ist kein Behelf, sondern der Anfang der Messlatte: Was ein Modell von der
Stange mit einer abweichenden Aussprache anstellt, ist der Grund für das ganze
Projekt.

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

**5. GPU-Arbeit läuft nie im Web-Prozess und ist austauschbar.**
Transkription und Training haben je eine lokale und eine entfernte Implementierung.
Der Server braucht keine GPU; er kann eine haben.

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

Aufgehoben hat die alte Fassung, was seither dazugekommen ist: Jeder Sprecher
bekommt aus `lernen` sein **eigenes** Modell (Grundentscheidung 3), und was er
hier diktiert, fließt als Korrektur in **seinen** Korpus zurück. Beides braucht
die Kennung zur Laufzeit; eine Instanz je Person wäre eine Instanz je Modell
und je Korpus gewesen.

---

## Projektstruktur

Was steht, steht ohne Klammer. Was noch fehlt, ist gekennzeichnet.

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
│   ├── gesamt.py                  # beide Apps in einem Prozess (Betrieb)
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
│   ├── lernen/                    # App „lernen" - entworfen, siehe README dort
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
│       │   │   ├── model.py       # welcher Modellstand für diesen Sprecher läuft
│       │   │   ├── outbox.py      # Postausgang ansehen, noch einmal senden
│       │   │   └── zugang.py      # wer ruft - für die Kopfzeile
│       │   ├── services/
│       │   │   ├── segmenter.py   # transkribieren, an Zeitmarken schneiden
│       │   │   └── outbox.py      # Korrekturen zurück an „hören"
│       │   └── db/                # models.py, migrations/
│       ├── frontend/
│       │   └── src/routes/        # Aufnahme, Ergebnis, Zugangsdaten, KeinZugang
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
│       ├── PinSchloss.svelte      # die PIN vor Darstellung und Zugangsdaten
│       ├── pin.svelte.ts          # eine PIN, eine Sitzung, alle Apps
│       ├── Textvergleich.svelte   # Vorlage gegen Erkennung, Zeichen für Zeichen
│       ├── diff.ts                # längste gemeinsame Teilfolge, zeichenweise
│       ├── zugang.ts              # wo der Zugang liegt; ein Eintrag für alle
│       ├── apps.ts                # die drei Apps, die Punkte im Menü, was abschaltbar ist
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
├── training/                      # noch nicht gebaut: das, was auf der GPU läuft
│   ├── Dockerfile
│   ├── finetune.py                # liest Manifest, schreibt Checkpoint + Metriken
│   ├── evaluate.py                # WER/CER auf dem Testsplit
│   └── config/
│       ├── whisper_full.yaml
│       └── whisper_lora.yaml
│
├── data/                          # nicht im Git
├── docs/
│   ├── datenschutz.md
│   └── betrieb.md
└── scripts/
    ├── migrate.py
    ├── augmentieren.py            # abgewandelte Fassungen aller Aufnahmen
    ├── restore.py                 # eine Sicherung zurückspielen
    └── purge_speaker.py           # Löschung, vollständig
```

---

## App „hören" - der aktuelle Arbeitsstand

### Ablauf

1. **Sprecherprofil** anlegen: Name, Sprache, Basismodell. Sonst nichts. Dazu
   einen Zugang ausgeben - daraus wird ein Link, und der ist alles, was die
   Person je braucht (siehe „Der Zugang ist die Kennung").
2. **Textquelle wählen.** Entweder ein Thema oder Stichwort plus Altersspanne, aus
   dem ein LLM Text erzeugt; oder ein hochgeladener Text, aus dem zufällige Proben
   gezogen werden. Beides wird mit Herkunft und Erzeugungsparametern gespeichert,
   damit später nachvollziehbar ist, woher eine Vorlage stammt.
3. **Schneiden.** `chunker.py` zerlegt den Text in Einheiten von grob 3–12 Sekunden
   geschätzter Sprechdauer, an Satz- und Teilsatzgrenzen.
4. **Aufnehmen.** Die App zeigt eine Einheit groß, davor und dahinter je eine blass.
   Aufnehmen, anhören, verwerfen und wiederholen, weiter. Sitzung ist jederzeit
   unterbrechbar und wird an derselben Stelle fortgesetzt. Die Stelle wird
   nirgends gespeichert, sondern abgeleitet: offen ist jede Vorlage ohne gültige
   Aufnahme. Verwerfen macht eine Vorlage damit von selbst wieder offen - und
   löscht die Audiodatei wirklich, statt sie nur zu markieren.
5. **Prüfen.** Serverseitig: Pegel, Clipping, führende und schließende Stille, Dauer
   gegen die geschätzte Sprechdauer. Auffälligkeiten werden angezeigt, nicht
   erzwungen - bei Sprechstörungen sind Ausreißer normal und dürfen nicht
   wegautomatisiert werden.
6. **Fortschritt.** Gesammelte Minuten gegen zwei Marken: ab etwa 1,5 Stunden wird
   ein Modell brauchbar, ab etwa 20 Stunden gut. Danach flacht der Gewinn ab.

### Vorsprechen statt Vorlesen

Die Zielgruppe kann teilweise nicht flüssig lesen - das ist der Grund für das ganze
Projekt und zugleich ein Problem beim Sammeln, denn Sammeln heißt Vorlagen ablesen.
Deshalb hat die Aufnahmeansicht einen Modus, in dem die Einheit erst per Web Speech
API vorgesprochen und dann nachgesprochen wird.

Das hat einen Preis: Nachsprechen verändert Sprechtempo und Satzmelodie in Richtung
der Vorgabe. Die Aufnahme wird deshalb als `nachgesprochen` markiert und im Manifest
getrennt geführt, damit man den Effekt später messen und die Gewichtung anpassen
kann.

Weil dieser Effekt am Sprechtempo der Vorgabe hängt, ist das Tempo einstellbar
(Vorgabe 0,9× - langsamer ist leichter nachzusprechen, ermüdet aber über eine lange
Sitzung). Ebenso die Stimme: welche zur Wahl stehen und wie natürlich sie klingen,
entscheidet allein das Betriebssystem. Dieselbe Seite klingt auf macOS natürlich und
unter Linux mit espeak-ng blechern; die App kann das nur zur Auswahl stellen, nicht
verbessern. Wege zu einer besseren Stimme stehen in `docs/betrieb.md`.

### Menüführung

Die Kopfzeile hat zwei Reihen, weil es zwei Ebenen gibt. Oben die drei Apps -
`hören`, `lernen`, `schreiben` -, die offene dunkelgrün hinterlegt; das noch
nicht gebaute `lernen` steht blass daneben und ist nicht anklickbar. Darunter
die Ansichten der offenen App, die aktuelle hell hinterlegt. Beides steht in
`packages/ui/Kopfleiste.svelte` - deshalb hat `schreiben` dieselbe Leiste
bekommen, ohne ein eigenes Menü zu erfinden. Am rechten Rand der oberen Reihe
ist Platz für eine Randnotiz; `schreiben` schreibt seinen Modellstand hinein.

Marke, App-Reiter, Sprecherzeile und Menüknopf gibt es genau einmal, und keine
App baut sie sich selbst zusammen: `packages/ui/Rahmen.svelte` klammert
Kopfzeile, Inhalt und Fußzeile und beantwortet die gerätebezogenen Menüpunkte
gleich mit. Eine App liefert nur ihre eigenen Ansichten und, was sie darüber
hinaus ins Menü stellt - `hören` den Sprecher (oder, sobald einer spricht,
**Meine Daten** und gleich dahinter die **Auswertung**) und die Zugangsdaten,
`schreiben` **Meine Daten** als Verweis auf dieselbe Seite bei `hören` und die
Zugangsdaten. Was
im Menü steht, ist damit eine Liste (`GERAETE_PUNKTE`
in `apps.ts` und der Durchreichung der App) und keine Folge fester Zeilen mit
Schaltern davor; ein neuer gerätebezogener Punkt ist ein Eintrag und eine
Zeile im Rahmen, statt einer Änderung in jeder App. Weil es eine Liste ist,
lässt sie sich auch kürzen: Welche Apps und welche Menüpunkte tatsächlich
dastehen, schaltet **Darstellung** ein und aus (siehe dort).

Der Punkt **Zugangsdaten** steht in **beiden** Apps immer im Menü, auch und
gerade ohne gültigen Zugang: Dann ist er der einzige Weg herein, und ein Menü,
das ihn erst nach der Anmeldung zeigte, hätte die Tür hinter das Schloss
gelegt. Wer mit dem Zugang eines Sprechers da ist, findet die Seite ebenfalls;
sie sagt ihm zunächst nur, wessen Zugang in diesem Browser liegt, statt ihm ein
Feld hinzustellen, an dem er ihn kaputtmachen kann. Darunter steht **Zugang
wechseln**: Ein Browser trägt genau einen Zugang, und ihn gegen den Verwalter-
oder Aufsichtstoken zu tauschen, ist der einzige Weg in die Verwaltung und in
die Aufsicht - auch von einem Gerät aus, auf dem gerade jemand aufnimmt. Der
persönliche Zugang kommt danach mit einem Klick auf den Link zurück. Die Ansicht selbst gibt es ebenfalls nur einmal
(`packages/ui/Zugangsdaten.svelte`), denn es ist derselbe Zugang: Beide Apps
lesen denselben Eintrag im `localStorage` (`packages/ui/zugang.ts`). Was die
Apps unterscheidet, ist eine Eigenschaft - nur `hören` nimmt in dasselbe Feld
auch Verwalter- und Aufsichtstoken.

Alle drei liegen unter einer Adresse (`wortlaut.example.org`), nicht unter drei
Subdomains: ein Zertifikat, eine Proxy-Regel je App, und der Wechsel zwischen
den Apps ist ein Pfadwechsel. `hören` ist der Einstieg und liegt auf der
Wurzel, `schreiben` unter `/schreiben/`; welcher Pfad zu welcher App gehört,
steht in `packages/ui/apps.ts`.

Der Pfad gehört dabei der App, nicht dem Proxy: `schreiben` hängt seine
Oberfläche *und* seine API selbst unter `/schreiben/` (`BASIS` in seiner
`main.py`, `base` in seiner `vite.config.ts`). Der Proxy reicht den Weg
unverändert weiter und muss nichts abschneiden - als er es einmal gar nicht
verteilte, beantwortete `hören` den Klick auf den Reiter mit der eigenen Seite,
und `schreiben` war nicht erreichbar.

Weil die Pfade so an den Apps hängen, ist der Betrieb frei in der Aufteilung.
Auf einem einzelnen Wirt läuft alles in **einem** Container: `apps/gesamt.py`
verteilt im Prozess, was sonst der Proxy verteilte, und draußen genügt eine
Regel auf einen Port. Wer die Apps trennen will, nimmt die Dockerfiles unter
`apps/` und gibt dem Proxy zwei Regeln - am Code ändert das nichts.

Wer mit dem Verwaltertoken hier ist, sieht keine zweite Reihe: Es gibt für ihn
nur die eine Seite, auf der Profile angelegt und Zugänge ausgegeben werden.
Jede Aufnahmeansicht bräuchte einen Sprecher, und den hat er nicht - er hat
einen Verwaltertoken. In der Kopfzeile steht dann „Verwaltung" statt eines
Namens, damit die fehlende Reiterreihe nicht wie ein Fehler aussieht.

### Einstellungen

Unter `#/einstellungen` liegen Mikrofon, Stimme, Sprechtempo und Schriftgröße der
Vorlage, je mit Probe. Sie hängen am Gerät und nicht am Sprecherprofil - welche
Stimmen und welche Mikrofone es gibt, bestimmt das Betriebssystem, und wer die App
auf zwei Geräten benutzt, braucht dort verschiedene Werte. Gespeichert wird deshalb
im `localStorage` des Browsers (`wortlaut.mikrofon`, `wortlaut.verstaerkung`,
`wortlaut.autopegel`, `wortlaut.stimme`, `wortlaut.tempo`, `wortlaut.schrift`),
nicht im Korpus. Daneben liegt dort der Zugang selbst (`wortlaut.zugang`) -
das Einzige, was dieser Browser über den Sprecher weiß.

Ein Feld für den Zugang steht hier nur, wenn keiner vorliegt oder wenn es der
Verwaltertoken ist. Wer mit dem Zugang eines Sprechers hier ist, sieht es
nicht: Er hat nichts einzutragen, sein Zugang kam über einen Link - ein Feld
daneben wäre bloß ein Weg, ihn kaputtzumachen.

Die Schriftgröße ist einstellbar, weil die Zielgruppe sehr verschieden gut liest -
dieselbe Vorgabe, die einer Person zu klein ist, drängt bei einer anderen den
Kontext aus dem Bild.

#### Mikrofon

Der Mikrofontest zeigt den Pegel live, gegen dieselben Grenzen, die der Server nach
dem Absenden prüft (`services/quality.py`) - was im Test „guter Pegel" ist, gibt
später keinen Hinweis. Dazu die Wahl unter den vorhandenen Geräten und eine Probe
zum Anhören.

Zu leise Eingänge lassen sich auf zwei Arten heben, und die beiden tun
Verschiedenes:

- **Verstärkung** ist ein fester Faktor (1–20×) vor der Aufzeichnung. Er behebt ein
  Mikrofon, das durchweg zu leise ist - unter Linux der Normalfall bei eingebauten
  Mikrofonen, siehe `docs/betrieb.md`. **Automatisch einmessen** hört fünf Sekunden
  zu und setzt den Faktor so, dass die Spitze bei −6 dBFS landet; eingemessen wird
  auf die Spitze und nicht auf den Mittelwert, weil ein Wert am Anschlag verloren
  ist, ein zu leiser Mittelwert dagegen nur ungünstig.
- **Pegel automatisch nachregeln** ist die Regelung des Browsers (AGC). Sie gleicht
  aus, wenn mal lauter und mal leiser gesprochen wird, hebt einen durchweg zu leisen
  Eingang aber nicht an.

Beides steckt in der gespeicherten Aufnahme - sie ist Trainingsmaterial, und was
hier verstärkt wird, ist später verstärkt. Das ist gewollt: eine Aufnahme knapp über
dem Rauschen nützt dem Training nicht. Was aber *nicht* passiert, ist eine
nachträgliche Normalisierung auf dem Server. Wie laut jemand spricht, gehört zu den
Daten, für die dieses Projekt existiert.

#### Darstellung - und was in der Leiste überhaupt dasteht

Unter `#/darstellung` liegen Farben, Schriftart und die beiden Schriftgrößen,
je mit Probe - ein eigener Menüpunkt neben den Einstellungen, weil es ein
anderes Publikum ist: Mikrofon und Stimme misst man einmal ein, an Kontrast
und Schriftgröße darf jeder, der zu wenig sieht, sofort drehen.

Die acht Farben stehen als Raster, eine Farbe je Zeile: Farbfeld, Name,
darunter der Hex-Wert. Das Farbfeld ist der Hauptweg - ein Tippen, dann wählt
das Gerät. Der Hex-Wert daneben sieht aus wie Text und ist doch ein Feld; wer
einen Ton genau treffen muss, überschreibt ihn (`#1b4d3e`, `1b4d3e` und `#abc`
gelten gleichermaßen), alle anderen lesen ihn nur. Was keine Farbe ist, wird
abgewiesen und das Feld springt zurück - vorher landete auch Unsinn im
`localStorage`, und der Browser übergeht eine ungültige CSS-Variable
stillschweigend: Die Farbe blieb scheinbar stehen und war beim nächsten Laden
weg. Weicht eine Farbe von der Vorgabe ab, erscheint am Zeilenende ein
Rückwärtspfeil, der genau diese eine zurückholt; **Auf Vorgaben zurücksetzen**
weiter unten holt alles auf einmal.

Darunter steht, was von der Oberfläche überhaupt sichtbar ist: zwei Listen mit
je einem Schalter rechts, oben die drei Apps der Kopfleiste, darunter die
Punkte im Menüknopf. Der Anlass ist Grundentscheidung 7 - jeder Reiter, den
dieser Mensch nie braucht, ist eine Gelegenheit, sich zu verlaufen. Wer nur
diktiert, blendet `hören` und die Verwaltungspunkte aus; wer nur aufnimmt,
räumt `schreiben` und das noch leere `lernen` weg.

Zwei Punkte bleiben und haben einen festen, nicht bedienbaren Schalter, damit
niemand sich selbst aussperrt: **Darstellung**, weil dort diese Schalter
liegen, und **Meine Daten**, weil dort die PIN vergeben wird, die inzwischen
vor Darstellung und Zugangsdaten steht. Alles andere ist abschaltbar, die
Zugangsdaten eingeschlossen.

Ausgeblendet heißt dabei **unsichtbar, nicht abgeschaltet**: Die Route bleibt,
was sie war, ein Lesezeichen führt weiterhin hin, und der Server prüft
unverändert Zugang und PIN. Die Schalter räumen die Leiste auf, sie sind kein
Rechtemodell - das sind der Zugang (`packages/ui/zugang.ts`) und die PIN. Der
Rückweg ist doppelt gesichert: **Auf Vorgaben zurücksetzen** holt neben Farbe
und Schrift auch jeden ausgeblendeten Punkt zurück.

Gespeichert wird wie Farbe und Schrift im `localStorage` dieses Browsers
(`wortlaut.sichtbar.app.<app>`, `wortlaut.sichtbar.menue.<pfad>`) und gilt
damit in allen Apps darin. Fehlt ein Eintrag, ist der Punkt sichtbar: Nur ein
ausdrückliches `false` blendet aus, sonst stünde nach dem ersten Start eine
leere Leiste da.

### Der Zugang ist die Kennung

Mehrere Personen dürfen dieselbe Instanz benutzen, ohne dass eine an die Daten
einer anderen kommt. Die Trennung dafür liegt längst in der Ablage - je Sprecher
eine eigene Datenbank. Was fehlte, war die Bindung zwischen Aufrufer und
Verzeichnis: Der Sprecher stand als Abfrageparameter da, und ein Parameter ist
eine Behauptung. Wer den Token hatte, konnte jede Kennung hinschreiben, auch
versehentlich aus einem alten Reiter oder einem falschen Lesezeichen - und dann
landeten Aufnahmen im fremden Korpus.

Ein Zugang hat deshalb die Form

```
spr_01J8ZQ…8K.7f2ac1…            <sprecher_id>.<geheimnis>
```

und wird als `Authorization: Bearer …` vorgelegt. Der Server spaltet ihn am
Punkt, öffnet **die** Datenbank dieses Sprechers und prüft dort den Prüfwert des
Geheimnisses. Die Kennung ist damit abgeleitet und nicht behauptet - und der
Nachschlag geht auf dieselbe Datei, die die Anfrage ohnehin öffnet. Dass die
Kennung offen dasteht, kostet nichts: Wer sie in einen fremden Zugang schreibt,
dessen Geheimnis passt dort nicht.

**Ein Fehlgriff wird laut.** `?sprecher=…` wird weiterhin angenommen, aber nur
noch als Behauptung, die stimmen muss. Weicht sie ab, antwortet der Server mit
403 und nennt beide Kennungen, statt still ins falsche Verzeichnis zu schreiben.
Davon lebt die Absicherung von `schreiben`: Es schickt die abgeleitete Kennung
mit dem Zugang mit, mit dem sie abgeleitet wurde - auseinanderfallen können die
beiden damit nicht mehr, und die 403 bleibt als Netz für den Fall, dass doch
einmal jemand daran vorbeibaut.

**Der Zugang kostet die Person nichts.** Ausgegeben wird er in der Verwaltung;
dabei entsteht ein Link `…/#/zugang/<zugang>`. Den öffnet die Person einmal auf
ihrem Gerät und legt ihn als Lesezeichen ab - nichts zu merken, nichts zu
tippen, danach nie wieder (Grundentscheidung 7). Das Geheimnis steht im
Fragment und geht deshalb nie an den Server; es landet in keinem
Zugriffsprotokoll. Einen Abmeldeknopf gibt es nicht: Er wäre für diese
Zielgruppe vor allem ein Weg, den eigenen Zugang zu verlieren. Wechselt ein
Gerät die Person, wird der andere Link geöffnet und ersetzt den vorhandenen.

**Ein verlorener Zugang lässt sich zurückziehen.** Gespeichert ist nur der
Prüfwert (`speakers.zugang_hash`), im Klartext gibt es einen Zugang genau
einmal - beim Ausgeben. Verloren heißt deshalb: einen neuen ausgeben, und damit
ist der alte tot. Ohne Ersatz zurückziehen geht auch; dann kommt niemand mehr
an diesen Korpus.

**Sichtbar ist es auch.** In der Kopfzeile steht dauerhaft, für wen dieser
Browser eingestellt ist - der Name, den der Server zum vorgelegten Zugang nennt
(`GET /api/zugang`), nicht der, den sich der Browser gemerkt hat. Der Sprecher
steht dafür in keinem `localStorage` mehr.

`WORTLAUT_AUTH_TOKEN` schützt damit nicht mehr die Daten, sondern nur noch die
**Verwaltung**: Profile anlegen, Zugänge ausgeben und zurückziehen. An die
Korpora kommt außer den Sprechern nur die Aufsicht - der eine Zugang, der über
ihnen steht (siehe unten). Ist er nicht gesetzt, ist die Verwaltung zu, nicht
offen: Keine Installation weiß, ob sie Entwicklung ist, und ein vergessener
Token darf nicht die großzügigste Einstellung sein.

**Der Preis.** Es gibt genau einen Weg zu den Daten, und der leitet seine
Kennung ab - also kommt auch die Verwaltung nicht an die Korpora. Wer eine
Instanz betreibt und selbst aufnehmen will, gibt sich einen Zugang aus und
öffnet den Link wie alle anderen. Das ist eine Unbequemlichkeit; sie ist die
Gegenleistung dafür, dass es keine zweite Tür gibt, hinter der die Kennung doch
wieder eine Behauptung wäre. Dazu kommt: Ein Zugang liegt im `localStorage`
eines Browsers, und wer den Link weitergibt, gibt den Korpus weiter - das ist
ein Lesezeichen, kein Ausweis. Für die Zielgruppe ist genau das der Punkt.

Und der Umbau ist nicht rückwärtsverträglich. Eine bestehende Installation
braucht einen Handgriff: je Sprecher einen Zugang ausgeben und den Link auf
sein Gerät bringen. (Die neue Spalte holt sich die Datenbank beim ersten
Zugriff selbst; als dieser Abschnitt geschrieben wurde, war dafür noch
`make migrate` nötig.) Derselbe Link öffnet
seither auch `schreiben`; `WORTLAUT_SPRECHER_ID` und `WORTLAUT_INTAKE_TOKEN`
sind dafür ersatzlos entfallen. Bis das geschehen ist, kommt niemand an die
Aufnahmen - was der Sinn der Sache ist, aber eben auch ihr Preis.

### Die Aufsicht - der eine Zugang über allen Korpora

Der Preis des vorigen Abschnitts war, dass niemand mehr über die Korpora
hinwegsieht: Die Verwaltung legt Profile an und kommt an keine Aufnahme. Für
den Alltag ist das richtig. Für den Betrieb fehlte damit alles, was ein Betrieb
braucht - nachsehen, was gesammelt wurde, einen Tippfehler im Namen
richtigstellen, sichern, aufräumen. Nichts davon ging ohne eine SSH-Sitzung und
`sqlite3` von Hand.

Dafür gibt es eine dritte Art von Aufrufer, die **Aufsicht**, hinter einem
eigenen `WORTLAUT_ADMIN_TOKEN`. Sie sieht in jeden Korpus, benennt Sprecher um,
leitet Sicherungen und Datensätze aus und löscht. Sie darf zusätzlich alles,
was die Verwaltung darf; umgekehrt nicht.

**Aus jedem Browser erreichbar, ohne zweite Adresse.** Der Aufsichtstoken wird
unter „Menü → Zugangsdaten" in dasselbe Feld eingetragen wie ein
Verwaltertoken; der Server sieht am Vorgelegten, welches von beidem er vor sich
hat (`wortlaut.zugang` unterscheidet die Formen). Ein Browser trägt dabei
weiterhin genau einen Zugang - wer dort vorher den Link eines Sprechers
geöffnet hatte, öffnet ihn danach einmal wieder. Zwei gleichzeitige Identitäten
in einem Browser wären genau die Doppeldeutigkeit, gegen die der ganze vorige
Abschnitt angetreten ist.

**Der Sprecher steht hier in der Adresse** - als einzige Wege dieser App
(`/api/admin/…`). Das ist kein Rückfall in die alte Behauptung: Die Aufsicht
hat keinen eigenen Sprecher, sie sieht über alle hinweg, und geprüft wird ihr
Token und nicht die Kennung daneben. Damit der Unterschied sichtbar bleibt,
liegen diese Wege unter einem eigenen Präfix und nirgends sonst.

**Leer heißt abgeschaltet, nicht offen.** Beim Verwaltertoken bedeutet ein
leerer Wert „steht offen", was für die lokale Entwicklung bequem ist. Hier
nicht: Ohne gesetzten Token antwortet jeder Weg der Aufsicht mit 401, auch in
der Entwicklung. Ein Zugang, der Korpora löscht, soll nicht versehentlich
offenstehen.

#### Zwei Formate, zwei Fragen

Ausgeleitet wird in zwei Formaten, weil zwei verschiedene Fragen dahinterstehen.

Die **Sicherung** (`.tgz`) beantwortet „Der Server ist weg, ich will den Stand
zurück." Sie enthält die Dateien, wie sie unter `WORTLAUT_DATA_DIR` liegen -
Datenbanken und Aufnahmen -, und ihr Inneres bildet das Datenverzeichnis eins
zu eins ab:

```
wortlaut-gesamt-20260822-174500.tgz
├── sicherung.json               Zeitpunkt, Sprecher, je Datei Größe und SHA-256
└── daten/
    ├── korpus/spr_…/hoeren.sqlite
    ├── korpus/spr_…/audio/rec_….wav
    ├── korpus/spr_…/audio/varianten/rec_….<fassung>.wav
    └── diktate/spr_…/…          Arbeitsstand von „schreiben"
```

Das ist der ganze Trick der Wiederherstellung: Sie ist ein Auspacken an die
richtige Stelle, kein Einspielen. `scripts/restore.py` nimmt einem die
Prüfungen ab, aber `tar xzf` käme genauso weit - eine Sicherung, die ein
laufendes Programm zum Lesen braucht, ist im Ernstfall keine.

Es gibt sie je Sprecher und über alle auf einmal, letztere als **eine** Datei.
Der Dienst darf dabei laufen: Die Datenbanken werden nicht kopiert, sondern
über die Online-Backup-Schnittstelle von SQLite gezogen. Ein `cp` der
`.sqlite`-Datei wäre kein stimmiger Stand, weil im WAL-Modus ein Teil der Daten
daneben in `…-wal` steht.

Der **Datensatz** (`.zip`, nur je Sprecher) beantwortet „Ich will die Paare aus
Text und Audio ansehen oder trainieren, mit Werkzeugen, die von wortlaut nichts
wissen":

```
spr_…/
├── LIESMICH.txt
├── metadaten.csv        file_name, transcription, dauer_s, modus, quelle, …
├── metadaten.jsonl      dieselben Zeilen als JSON
└── audio/
    ├── rec_….wav        16 kHz mono, PCM 16 bit
    └── rec_….txt        der gesprochene Text zu genau dieser Datei
```

Die Spalten `file_name` und `transcription` heißen englisch, weil das
`audiofolder`-Format von Hugging Face genau diese Namen erwartet - der
Datensatz lädt damit ohne eine Zeile Anpassungscode. Der Text steht doppelt
darin: in der Tabelle fürs Training, als `.txt` neben dem Audio für jedes
Werkzeug, das nur ein Verzeichnis sieht. Ein paar Kilobyte gegen den Umweg über
eine Tabelle.

Der Datensatz ist ausdrücklich **keine** Sicherung - Sitzungen und
Warteschlange fehlen -, und die `LIESMICH.txt` sagt das auch demjenigen, der
das Archiv in einem Jahr wiederfindet.

#### Löschen: drei Stufen, und die vierte gibt es nicht

| | Was verschwindet | Was bleibt |
|---|---|---|
| eine Aufnahme | Audio samt abgewandelten Fassungen und Datensatz; die Einheit wird wieder offen | alles andere |
| alle Aufnahmen eines Sprechers | jedes Audio samt Fassungen, jede Aufnahmezeile | Profil, Textquellen, Warteschlange |
| ein Sprecher | Korpus, Diktate, Modellstände, Schnappschüsse | nichts |

Die abgewandelten Fassungen gehen überall mit: Sie sind dieselbe Stimme, nur
lauter oder verrauscht, und damit derselbe Gesundheitsdatensatz. Wer eine
Aufnahme verwirft, hat nicht drei Kopien davon gemeint.

Eine vierte Stufe „alle Sprecher" gibt es nicht, weder in der Oberfläche noch
in der API. Sie wäre ein Knopf, der einmal im Leben gedrückt wird - und dann
versehentlich. Wer zwei Personen löschen will, tut es zweimal und denkt dabei
zweimal nach. Sichern über alle geht; löschen nur einzeln.

Die beiden großen Stufen verlangen die Kennung ein zweites Mal
(`?bestaetigung=…`), und die Oberfläche lässt dafür den Namen abschreiben. Ein
zweites „Wirklich?" klickt man weg, ohne es gelesen zu haben; einen Namen
abzuschreiben zwingt dazu hinzusehen, wen es trifft.

Was zu einer Person gehört, steht an einer Stelle
(`services/loeschung.py`) - dieselbe, die auch `scripts/purge_speaker.py`
fragt. Sonst löschten Oberfläche und Kommandozeile Verschiedenes, und der
Unterschied fiele niemandem auf.

#### Meine Daten - dieselbe Ansicht, für sich selbst

Unter **Meine Daten** sieht ein Sprecher dieselben Profildaten, Textquellen,
Sitzungen und Aufnahmen, die die Aufsicht für ihn sähe (`api/konto.py`,
`MeineDaten.svelte`) - ohne eine Kennung in der Adresse: Sie kommt wie bei
jedem anderen Weg dieser App aus dem vorgelegten Zugang, ein Sprecher kann
also von vornherein nur seine eigene Datenbank öffnen.

Ein Unterschied zur Aufsicht ist geblieben, und er betrifft die Sitzungen:
Hier stehen nur die, in denen auch aufgenommen wurde - Liste wie Kennzahl
(`services/uebersicht.py`, `nur_mit_aufnahmen`). Eine Sitzung entsteht schon
beim Öffnen der Aufnahmeseite, noch bevor jemand gesprochen hat; wer zweimal
hineingesehen und einmal geübt hat, sähe sonst drei Zeilen für einen Abend.
Die Aufsicht bekommt sie weiterhin alle zu sehen: Dort ist gerade der leere
Anlauf eine Auskunft. Jede Sitzung trägt Datum **und** Uhrzeit, in der
Zeitzone des Betrachters umgerechnet (`packages/ui/zeit.ts`) - drei Sitzungen
an einem Tag wären mit dem Datum allein nicht auseinanderzuhalten.

Die drei Löschstufen von oben bleiben der Aufsicht vorbehalten. Was bleibt,
ist die vertraute Grenze aus `api/recordings.py`: eine einzelne Aufnahme
verwerfen, dieselbe Handlung, die während des Aufnehmens schon zur Verfügung
steht. Kein Massenlöschen, kein vollständiges Löschen des eigenen Profils -
ein Versehen soll höchstens eine Aufnahme kosten.

`schreiben` verlinkt auf dieselbe Seite, statt eine eigene Ansicht zu bauen:
Die Daten liegen im Korpus, den nur `hören` schreibt (Grundentscheidung 6).

##### Eine PIN davor

Wer mag - die Person selbst oder die Aufsicht an ihrer Stelle - sichert
**Meine Daten** zusätzlich mit einer vierstelligen PIN (`services/pin.py`,
Spalte `pin_hash`, Migration `004_pin.sql`). Vier Ziffern und keine
Anmeldung mit Text: dieselbe Grundentscheidung 7, die auch `schreiben` einen
Text- statt Passwortfeld erspart.

Dieselbe PIN steht inzwischen auch vor **Darstellung** und **Zugangsdaten**
(`packages/ui/PinSchloss.svelte`) - dieselbe, keine zweite: Es ist derselbe
Mensch, derselbe Browser und dasselbe Bedrohungsmodell, und wer sich eine PIN
je Seite merken müsste, merkte sich am Ende keine. Einmal eingegeben, gilt sie
für die ganze Sitzung und über beide Apps hinweg (`packages/ui/pin.svelte.ts`);
ein Neuladen sperrt wieder zu, denn die PIN liegt allein im Speicher der Seite
und nie im `localStorage`. Beide Ansichten fragen dazu die Konto-API von
`hören`, auch aus `schreiben` heraus: Die PIN gehört zum Sprecher und steht in
seinem Korpus, und den schreibt allein `hören` (Grundentscheidung 6).

Wessen Zugang der Server **nicht** kennt, kommt ohne PIN durch. Das ist kein
Loch, sondern die Bedingung dafür, dass es überhaupt geht: Ohne Sprecher gibt
es keine PIN, nach der zu fragen wäre, und **Zugangsdaten** ist dann der
einzige Weg herein. Ein Schloss, dessen Schlüssel hinter ihm selbst läge, wäre
kein Schutz, sondern ein zugemauerter Eingang.

Es ist ausdrücklich kein zweites Schloss, sondern eine zusätzliche Hürde
gegen den Klick aus Versehen - die eigentliche Kennung bleibt der Zugang.
Eine PIN ist deshalb bewusst leichtgewichtig geprüft (zeitkonstanter
Vergleich, kein Sperren nach Fehlversuchen; siehe `services/pin.py`) und
schützt nur die lesenden Wege unter `/api/konto/…`, nicht das Anhören
oder Verwerfen einer Aufnahme selbst - wer erst einmal drin ist, braucht sie
nicht ein zweites Mal.

Gesetzt und geändert wird sie ohne die alte zu kennen: über `/api/konto/pin`
von der Person selbst oder über `/api/admin/speakers/{id}/pin` von der
Aufsicht - der Rückweg, wenn eine PIN vergessen wurde oder aus Versehen
gesetzt ist.

### Auswertung - wie gut hört welches Modell?

Der Korpus weiß, was gesprochen wurde, und er weiß, was gesprochen werden
*sollte*: Die Vorlage steht daneben. Damit ist jede Aufnahme eine fertige
Prüfaufgabe - man schickt sie durch einen Erkenner und vergleicht, was
herauskommt, mit dem, was dastand. Genau das tut der Menüpunkt **Auswertung**
(`services/auswertung.py`, `api/auswertung.py`).

Gemessen wird immer **ein** Korpus, der des vorgelegten Zugangs. Eine
Auswertung über alle Sprecher hinweg gibt es bewusst nicht: Wie gut ein Modell
hört, hängt an der Stimme, und der Mittelwert über mehrere Menschen wäre eine
Zahl, die für keinen von ihnen gilt. Verworfene Aufnahmen zählen nicht mit -
was der Sprecher selbst weggeworfen hat, ist kein Prüfstück, sondern ein
Fehlversuch, und ginge sonst als schlechte Note eines Modells durch.

Gegeneinander antreten die Modelle aus `WORTLAUT_AUSWERTUNG_MODELLE`. Die
Vorgabe ist eine Leiter mit vier Sprossen:

| Modell | wofür es in der Leiter steht |
| --- | --- |
| `base` | die Untergrenze - wo das Verstehen abzubrechen beginnt |
| `small` | der Alltagsfall, gegen den die anderen zu lesen sind |
| `medium` | was mit mehr Rechenzeit noch zu holen wäre |
| `large-v3` | wo das Verfahren endet - das größte fertige Modell |

Die oberste Sprosse ist die teuerste: gut anderthalb Gigabyte zusätzlich im
Speicher und je Aufnahme ein Vielfaches der Rechenzeit von `medium`. Sie
gehört trotzdem dazu, denn die Frage dieser Ansicht ist nicht „welches der
kleinen Modelle?", sondern „reicht ein fertiges Modell für diese Stimme
überhaupt?" - und die beantwortet nur das größte. Bleibt auch `large-v3`
deutlich hinter der Vorlage, ist genau das das Argument für ein eigenes
Feintuning; trifft es, war der Weg nicht nötig. Wer wenig Maschine hat, kürzt
die Liste - gerechnet wird nur, was darin steht.

#### Vier Fassungen je Aufnahme

Eine Aufnahme ist ein einzelner Fall: diese Stimme, dieses Mikrofon, dieser
Abstand, dieser Raum, dieser Pegel. Ein Modell, das damit zurechtkommt, muss
den Sprecher noch nicht verstanden haben - es kann auch bloß diese eine
Aufnahmesituation gut vertragen. Zu wissen, was von beidem zutrifft, ist der
eigentliche Zweck der Auswertung, denn die nächste Aufnahme entsteht mit
anderem Pegel und anderem Grundgeräusch.

Gemessen wird deshalb nicht die Aufnahme, sondern die Aufnahme und drei
Abwandlungen davon (`packages/wortlaut/src/wortlaut/augmentierung.py`):

| Fassung | was sie tut | wonach sie fragt |
| --- | --- | --- |
| `original` | nichts - die Aufnahme, wie sie gesprochen wurde | der Ausgangswert |
| `pegel` | lauter, bis die Spitze bei −1 dBFS steht | lag es nur daran, dass es zu leise war? |
| `lauter` | alles mal 1,15, für jede Aufnahme derselbe Faktor | was passiert, wenn jemand pauschal aufdreht? |
| `rauschen` | weißes Rauschen, 20 dB unter der Aufnahme | hält es einem Lüfter, einer Straße stand? |

Vier Zahlen je Modell und Aufnahme also, und erst ihr Zusammenhang ist die
Auskunft: Liegen die vier dicht beieinander, versteht das Modell den Sprecher.
Fallen sie auseinander, verträgt es eine bestimmte Aufnahmesituation.

Drei Entscheidungen stecken darin:

* **`pegel` und `lauter` sind nicht dasselbe.** `pegel` schöpft den
  Wertebereich aus - jede Aufnahme landet danach gleich laut, und wer schon am
  Anschlag stand, wird dabei leiser: „optimal ausnutzen" heißt auch, den
  Bereich nicht zu verlassen. `lauter` lässt den Abstand zwischen leisen und
  lauten Aufnahmen stehen und schneidet ab, wo es nicht mehr passt. Das erste
  ist der Regler, den ein Programm stellt, das zweite der, an dem ein Mensch
  dreht.
* **Das Rauschen liegt in festem Abstand zur Aufnahme, nicht auf festem
  Pegel.** Ein absoluter Rauschpegel träfe eine leise Aufnahme viel härter als
  eine laute; die Abwandlung wäre für jede Aufnahme eine andere, und der
  Vergleich zweier Aufnahmen sagte mehr über deren Aussteuerung als über das
  Modell.
* **Das Rauschen ist gewürfelt und trotzdem wiederholbar.** Der Würfel bekommt
  die Kennung der Aufnahme als Keim. Dieselbe Aufnahme ergibt auf jeder
  Maschine dasselbe Rauschen, und eine gelöschte Datei kommt Byte für Byte so
  zurück, wie sie war - sonst wäre eine wiederholte Messung keine Wiederholung.

Die Fassungen werden **aufbewahrt**, nicht im Speicher hergestellt und wieder
vergessen. Damit hat nicht nur die Auswertung etwas davon: Auf der Platte steht
ein viermal so großer Datensatz, den ein späteres Feintuning ohne weiteres
Zutun mitnehmen kann, und der in jeder Sicherung liegt. Sie entstehen beim
Hochladen einer Aufnahme und, falls eine fehlt, spätestens kurz bevor der Lauf
sie braucht - so kommt auch jeder Korpus, der vor dieser Änderung angelegt
wurde, ohne Zutun zu seinen Dateien. `make augmentieren` (im Container
`python scripts/augmentieren.py`) zieht das für alle Korpora auf einmal vor.

Beim Löschen gehen sie mit: Eine abgewandelte Fassung ist dieselbe Stimme, nur
lauter oder verrauscht, und damit derselbe Gesundheitsdatensatz
(Grundentscheidung 6). Wer eine Aufnahme verwirft, hat nicht drei Kopien davon
gemeint.

#### Vier Maße und eine Zahl

Die Fehlerraten stehen in `wortlaut/metriken.py`, weil sie reine Textmathematik
sind und „lernen" sie später ebenso braucht:

| Maß | was es zählt | Grenzen |
| --- | --- | --- |
| **WER** | falsche, fehlende und zusätzliche **Wörter** | 0 bis offen |
| **CER** | dasselbe auf **Zeichen** - feiner, aber blind für den Sinn | 0 bis offen |
| **MER** | Fehler im Verhältnis zu allem Gesagten | 0 bis 1 |
| **WIL** | wie viel Wortinformation verloren ging | 0 bis 1 |

Darüber steht die **Genauigkeit**, 0 bis 100, als geometrisches Mittel der vier
umgedrehten Raten. Drei Entscheidungen stecken darin, und alle drei haben einen
Grund:

* **Die unbeschränkten Raten werden gebogen, nicht gekappt** (`1/(1+x)`). WER
  und CER können über 1 steigen, wenn ein Modell mehr ausgibt, als gesprochen
  wurde - Whisper wiederholt bei Stille gern denselben Satz. Ein Deckel bei 1
  machte „jedes Wort daneben" und „den Satz dreimal geliefert"
  ununterscheidbar, obwohl im zweiten Fall jedes Wort richtig erkannt wurde.
* **Null bleibt der Boden, den MER und WIL setzen.** Die beiden erreichen ihre
  1 genau dann, wenn kein einziges Wort getroffen wurde. Eine Genauigkeit von 0
  heißt damit „nichts davon war richtig" und nicht „irgendeine Rate ist über
  den Deckel gerutscht".
* **Geometrisch, nicht arithmetisch.** Das arithmetische Mittel ließe sich mit
  zwei guten Werten gegen einen katastrophalen aufrechnen; ein Modell, das die
  Zeichen ungefähr trifft und kein einziges Wort, bekäme eine mittlere Note.
  Beim geometrischen Mittel zieht ein durchgefallenes Maß alles mit.

Verglichen wird auf angeglichenem Text - Kleinschreibung, ohne Satzzeichen,
einfache Leerzeichen. Ob ein Modell einen Punkt setzt, hängt an seiner
Nachbearbeitung und nicht daran, ob es den Sprecher verstanden hat. Der Rohtext
bleibt daneben stehen: Er wird gespeichert und angezeigt, damit der Mensch den
echten Unterschied sieht.

#### Der Lauf

Ein Hintergrundlauf arbeitet die offenen Tripel aus Aufnahme, Modell und
Fassung ab, eines nach dem anderen - bei vier Modellen und vier Fassungen also
sechzehn Messungen je Aufnahme. Vier Eigenschaften sind Absicht:

* **Von Hand angestoßen.** Der Lauf startet nicht beim Hochfahren des Servers.
  Whisper rechnet, und zwar auf derselben Maschine, auf der jemand gerade
  aufnimmt; ein Neustart des Containers würde sonst jedes Mal ungefragt Stunden
  Rechenzeit binden.
* **Aufnahmeweise, nicht modellweise.** Erst alle Aufnahmen durch `base`, dann
  durch `small`, dann durch `medium` wäre sparsamer - je Modell einmal laden. Nur zeigte die Kurve
  dann lange eine einzige Reihe, und verglichen werden soll gerade. Bezahlt
  wird das damit, dass alle Erkenner gleichzeitig im Speicher liegen; bei
  `base,small,medium,large-v3` in `int8` gut zweieinhalb Gigabyte.
* **Wiederaufnehmbar.** Fertig ist, was in `erkennungen` steht
  (`005_auswertung.sql`, `007_varianten.sql`). Ein zweiter Lauf rechnet nur,
  was fehlt - nach einem Neustart, nach neuen Aufnahmen, nach einem
  hinzugefügten Modell und nach einer hinzugefügten Fassung. Nichts wird
  doppelt gerechnet, nichts geht verloren, wenn der Lauf mitten darin
  abbricht.
* **Ein Lauf zur Zeit, über alle Sprecher.** Nicht aus Bequemlichkeit: Zwei
  Läufe teilten sich eine CPU und dieselben Modelle im Speicher und wären
  zusammen langsamer als nacheinander.

Was die Modelle sagen, steht mit im Korpus und nicht daneben - es hängt an
genau dieser Aufnahme dieses Sprechers, und wer den Sprecher löscht, löscht es
mit (Grundentscheidung 6).

#### Die Ansicht

Eine Kurve über die Aufnahmen, von 1 an lückenlos durchgezählt. Die Nummer
steht in keiner Tabelle: Sie ergibt sich aus dem, was gerade gilt, damit eine
verworfene Aufnahme keine Lücke in der Achse hinterlässt.

Je Aufnahme ein Wert je Modell - eines davon als Balken, die übrigen als
Punkte darüber. Eine Auswahlliste unter dem Bild wechselt das Maß, eine zweite
das Modell, das den Balken bekommt. Was noch nicht gerechnet ist, bleibt leer
statt auf null zu fallen: Eine Null wäre ein Modell, das nichts verstanden hat.
Der Fortschritt steht darüber, und die Seite fragt im Takt nach, solange
gerechnet wird.

Gemessen sind vier Werte je Modell und Aufnahme, im Bild steht einer davon:
der **beste** der vier. Alle sechzehn Reihen über dieselben Aufnahmen zu legen
hieße, nichts mehr zu sehen; der beste sagt, was ein Modell aus dieser Aufnahme
herausholen kann, wenn der Ton stimmt. „Am besten" heißt dabei je nach Maß
größer oder kleiner - bei den Fehlerraten und der Rechenzeit ist der kleinste
Wert der beste. Eine Kurve, die beim Wechsel des Maßes stillschweigend vom
besten auf den schlechtesten Fall umschaltete, wäre eine Falle.

Unter dem Bild steht die Bilanz: **Median und Mittel** im gewählten Maß, dazu,
über wie viele Aufnahmen sie gehen. Beide, und nicht eines von beiden - das
Mittel nimmt jeden Ausreißer mit, etwa die eine Aufnahme, bei der Whisper in
eine Wiederholungsschleife gerät, während der Median den Normalfall nennt.
Stehen sie weit auseinander, ist das die Auskunft: Das Modell ist nicht
gleichmäßig schlechter, es verreißt einzelne Aufnahmen - welche, steht in der
Kurve darüber. Gerechnet wird das im Browser aus den Zahlen, die die Kurve
ohnehin mitbringt; ein Maßwechsel wartet so auf keine Antwort. Ein Modell, für
das noch nichts gerechnet ist, bekommt keine Zeile: Zwei Nullen wären eine
Behauptung.

Je Modell stehen dort fünf Zeilen: **je Fassung eine** - das ist die Stelle, an
der die vier Zahlen vollständig zu sehen sind - und darüber die beste der vier.
Die letzte ist die Zeile zur Kurve; ohne sie stünde im Bild eine Reihe, zu der
unten keine Zahl gehört, und man suchte sie in den vieren darunter, wo sie nicht
steht: Der Median der besten Werte ist nicht der beste der vier Mediane.

Ein Tipp auf eine Spalte zeigt darunter die Texte, und zwar **eine Fassung zur
Zeit** - vier Schalter wechseln zwischen ihnen, das Original zuerst. Sechzehn
Texte untereinander wären keine Ansicht mehr, sondern eine Liste; gefragt ist
beim Lesen immer „was haben die Modelle aus *dieser* Aufnahme gemacht?".

Getippt wird irgendwo in die Spalte, nicht auf den Balken; auf einem Telefon
ist ein 20 Pixel breiter Balken kein Ziel. Darunter stehen dann die Vorlage und
jede erkannte Fassung, Unterschiede zeichenweise ausgezeichnet:
fehlend grau durchgestrichen, hinzugekommen farbig und fett, wie eine
Textverarbeitung Änderungen nachverfolgt (`packages/ui/diff.ts`,
`Textvergleich.svelte`). Auf Zeichen und nicht auf Wörtern, weil ein
Wortvergleich „Heuser" als ganz falsch markierte, obwohl ein Buchstabe
danebenliegt. Die Auszeichnung trägt nie allein die Farbe - durchgestrichen und
fett sagen dasselbe noch einmal, und `<del>`/`<ins>` sagen es auch einer
Vorlesestimme.

Ein Schalter daneben nimmt die Auszeichnung wieder weg. Sie beantwortet „wo
weicht es ab?", nicht „was hat das Modell eigentlich geschrieben?" - und sobald
viel abweicht, zerfällt der Satz in Schnipsel aus Gestrichenem und Fettem, so
dass ausgerechnet die interessanteste Fassung, die des schlechtesten Modells,
am schlechtesten zu lesen ist. Dann steht der glatte Text da. Am Gemessenen
ändert der Schalter nichts: Verglichen wird immer gegen die Vorlage.

Gezeichnet wird mit **ECharts**, und die Wahl ist für mehr als diese eine Kurve
getroffen: Zeigen, Ziehen und Zwei-Finger-Zoom auf dem Telefon wie mit der
Maus, gemischte Reihen in einem Bild, und `echarts.connect`, das mehrere
Diagramme aneinanderkoppelt - genau der Punkt, an dem die schlankeren
Bibliotheken aufhören und an dem man sie ersetzen müsste. Geladen wird sie erst
beim Öffnen der Ansicht und nur mit den Teilen, die eingetragen sind
(`apps/hoeren/frontend/src/lib/diagramm.ts`); das ist der Unterschied zwischen
190 und 370 Kilobyte.

### Endpunkte

Verwaltung - hinter `WORTLAUT_AUTH_TOKEN`; ohne ihn zu:

```
POST   /api/speakers                        { name, sprache, basismodell }
GET    /api/speakers
GET    /api/speakers/{id}
POST   /api/speakers/{id}/zugang            neuen Zugang ausgeben
DELETE /api/speakers/{id}/zugang            Zugang zurückziehen
```

Daten - hinter dem Zugang eines Sprechers, der zugleich sagt, welcher:

```
POST   /api/sources/llm                     { thema, altersspanne, umfang }
POST   /api/sources/upload                  multipart: datei
GET    /api/sources
GET    /api/sources/{id}/text               Klartext, eine Einheit je Absatz
PATCH  /api/sources/{id}                    { aktiv }  - abstellen/aufnehmen
DELETE /api/sources/{id}                    409, wenn Aufnahmen daran hängen
POST   /api/sessions
GET    /api/prompts/next?session=…
POST   /api/recordings                      multipart: audio + prompt_id + modus
GET    /api/recordings/{id}/audio
DELETE /api/recordings/{id}
GET    /api/progress
POST   /api/korpus/intake                   ← von „schreiben"
GET    /api/konto                           Profil, Kennzahlen, Textquellen - die eigenen
GET    /api/konto/sessions?ab=&anzahl=      seitenweise, zu zehnt
GET    /api/konto/recordings?ab=&anzahl=    seitenweise, mit Text
GET    /api/auswertung                      Kurve und Stand des Laufs - ohne Texte
GET    /api/auswertung/{aufnahme}           Vorlage und jede erkannte Fassung
POST   /api/auswertung/start                Hintergrundlauf anstoßen
POST   /api/auswertung/stopp                abbrechen; Gerechnetes bleibt
GET    /api/konto/pin                       { gesetzt }  - ungeschützt
GET    /api/konto/pin/pruefung              204, wenn die vorgelegte PIN stimmt
PATCH  /api/konto/pin                       { pin }  - vier Ziffern oder null
```

Die drei ersten `/api/konto/…`-Wege verlangen zusätzlich die Kopfzeile
`X-Pin: …`, sobald eine PIN gesetzt ist - und `…/pin/pruefung` tut nichts
anderes als das: Es prüft genau diese Kopfzeile und antwortet mit 204 oder
401. Gedacht für **Darstellung** und **Zugangsdaten**, die im Gegensatz zu
**Meine Daten** nichts abzurufen haben, woran sich die PIN nebenbei prüfen
ließe.

Aufsicht - hinter `WORTLAUT_ADMIN_TOKEN`. Als einzige Wege dieser App nennen
sie ihren Sprecher in der Adresse; die Aufsicht hat keinen eigenen:

```
GET    /api/admin/speakers                  alle Sprecher mit Kennzahlen
GET    /api/admin/speakers/{id}             Quellen, Umfang
GET    /api/admin/speakers/{id}/sessions?ab=&anzahl=   seitenweise, zu zehnt
GET    /api/admin/speakers/{id}/recordings  Aufnahmen mit ihrem Text, seitenweise
GET    /api/admin/speakers/{id}/recordings/{r}/audio
PATCH  /api/admin/speakers/{id}             { name }  - umbenennen
PATCH  /api/admin/speakers/{id}/pin         { pin }  - setzen, ändern, löschen; alte PIN egal
GET    /api/admin/speakers/{id}/sicherung   .tgz, wiederherstellbar
GET    /api/admin/speakers/{id}/datensatz   .zip, Text-Audio-Paare
GET    /api/admin/sicherung                 .tgz über alle Sprecher
DELETE /api/admin/speakers/{id}/recordings/{r}
DELETE /api/admin/speakers/{id}/recordings?bestaetigung={id}
DELETE /api/admin/speakers/{id}?bestaetigung={id}
```

Mit jedem der drei erreichbar, weil er die Frage beantwortet, welcher
vorliegt - und ohne alles:

```
GET    /api/zugang                          { art, sprecher_id, name }
GET    /gesundheit                          ohne Zugang
```

Die interaktive Dokumentation liegt unter `/docs`.

---

## Der Korpus - die Nahtstelle zu „lernen"

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
(siehe „Vier Fassungen je Aufnahme"). Sie liegen ein Stockwerk tiefer und
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
kommen aus `hören` (siehe „Vorsprechen statt Vorlesen"), `frei` aus `schreiben`:
dort spricht die Person selbst formulierte Sätze, nicht eine Vorlage.
`GET /api/progress` zählt beides getrennt, damit sich die Gewichtung an Zahlen
statt an Vermutungen ausrichten kann.

---

## Die Modell-Registry - die Nahtstelle zu „schreiben"

Ebenfalls Dateien statt Tabelle. Ein Modellstand ist ein Verzeichnis, das man
kopieren, sichern und per `scp` verschieben kann.

```
data/modelle/<sprecher_id>/<version>/
├── manifest.json
├── ct2/                        # für faster-whisper exportiert
└── checkpoint/                 # Rohgewichte, optional
```

```json
{
  "id": "spr_7f2a/2026-08-15T1420",
  "sprecher_id": "spr_7f2a",
  "basismodell": "openai/whisper-large-v3",
  "methode": "full",
  "erstellt": "2026-08-15T14:20:03Z",
  "daten": { "stunden": 4.7, "einheiten": 1832,
             "quellen": { "vorlage": 1640, "korrektur": 192 } },
  "metriken": { "wer": 0.146, "cer": 0.061, "test_einheiten": 120 },
  "laufzeit": "faster-whisper>=1.1",
  "sha256": "…",
  "status": "active"
}
```

`schreiben` wird über `WORTLAUT_MODELL_REF` auf genau eine `id` festgenagelt und
zeigt Basismodell und Datum dauerhaft in der Kopfzeile. Ein Modellwechsel ist eine
Konfigurationsänderung mit Neustart, kein Laufzeitereignis - sonst weiß hinterher
niemand, welcher Stand welche Ausgabe erzeugt hat.

---

## App „schreiben"

### Ablauf

1. Nutzer spricht, Whisper liefert Text mit Segmentgrenzen.
2. Die App liest jeden Abschnitt vor. Jeder Abschnitt ist anklickbar.
3. Klick → nur dieser Abschnitt wird neu eingesprochen und neu transkribiert. Das
   neue Audio ersetzt den alten Ausschnitt, der Rest bleibt stehen.
4. Bestätigt der Nutzer den fertigen Text, geht jeder Abschnitt als Korrekturpaar an
   `POST /api/korpus/intake` von `hören`. Die Outbox puffert, wenn `hören` nicht
   erreichbar ist.

### Der Abschnitt ist die Einheit

Was `hören` die Vorlage ist, ist `schreiben` der Abschnitt: die Einheit, an der
alles hängt. Whisper meldet zu jedem Segment Anfang und Ende, und genau dort
wird die Aufnahme zerschnitten (`wortlaut.audio.schneide_ausschnitt`). Jeder
Abschnitt hat deshalb seine eigene WAV-Datei - anders ließe er sich weder
einzeln ersetzen noch einzeln als Audio-Text-Paar zurückgeben.

Die zusammenhängende Aufnahme wird nach dem Schnitt nicht behalten. Sie wäre
eine zweite Kopie derselben Stimmdaten und wird nicht mehr gebraucht.

### Ein großer Knopf

Die Zielperson kann schlecht lesen und schreiben (Grundentscheidung 7). Daraus
folgt mehr als der Verzicht auf ein Anmeldefeld - und der Verzicht bleibt, auch
seit die App einen Sprecher führt: Der Zugang kommt über den persönlichen Link
und liegt danach im Browser, hier wie in `hören`.

- **Zwei Ansichten, keine Menüführung.** Sprechen und Ergebnis; der Weg
  dazwischen ergibt sich, statt gewählt zu werden. Die zweite Reiterreihe der
  Kopfzeile bleibt leer.
- **Vorgelesen wird von selbst.** Wer den Text nicht sicher lesen kann, hört
  den Fehler - deshalb liest die Ergebnisansicht sofort los und markiert
  mitlaufend, wo sie gerade ist.
- **Nichts zu tippen, auch nicht zum Anmelden.** Der Zugang kommt über den
  persönlichen Link und liegt danach im Browser - derselbe Eintrag, den `hören`
  liest, denn beide Apps liegen unter derselben Adresse.
- **Einstellungen nur im Menü.** Mikrofon, Stimme, Tempo und Schriftgröße
  gelten für beide Apps und stehen eingeklappt hinter dem Menüknopf, damit die
  Oberfläche ein großer Knopf bleibt.
- **Bearbeitet wird durch Sprechen.** Der fertige Text ist zum Kopieren da,
  nicht zum Tippen.

### Ohne „lernen" fängt es mit `small` an

Ist `WORTLAUT_MODELL_REF` leer, lädt faster-whisper das unveränderte
`whisper-small`. Die Kopfzeile schreibt dauerhaft hin, was gerade arbeitet
(`whisper-small · unverändert`, später `whisper-large-v3 · Stand 2026-08-15 ·
WER 14,6 %`) - wer eine Ausgabe beurteilt, beurteilt immer ein bestimmtes
Modell.

### Der Postausgang

Zwischen `schreiben` und `hören` liegt eine Tabelle und kein direkter Aufruf:
Dass beide gleichzeitig erreichbar sind, ist nicht zugesichert. Zwei Zusagen
halten das einfach - Wiederholen ist gefahrlos (`hören` erkennt die
Abschnittskennung als `externe_id` wieder), und nichts wird stillschweigend
verworfen: Ein Fehlschlag zählt hoch und schreibt seinen Grund in die Zeile,
der Eintrag bleibt offen.

Erst wenn ein Abschnitt im Korpus angekommen ist, wird seine Audiodatei hier
gelöscht.

### Endpunkte

```
POST   /schreiben/api/sessions              neue Diktiersitzung
GET    /schreiben/api/sessions/{id}
POST   /schreiben/api/sessions/{id}/segments        multipart: audio → Abschnitte
POST   /schreiben/api/sessions/{id}/bestaetigen     → Postausgang, sofort senden
POST   /schreiben/api/segments/{id}/neu     multipart: audio, ersetzt einen
GET    /schreiben/api/segments/{id}/audio
GET    /schreiben/api/model                 Modellstand dieses Sprechers
GET    /schreiben/api/outbox
POST   /schreiben/api/outbox/senden         noch einmal versuchen
GET    /schreiben/api/zugang                wer ruft - für die Kopfzeile
GET    /gesundheit                          ohne Zugang, auf der Wurzel
```

Alles unter `/schreiben` - dem Ort dieser App unter der gemeinsamen Domain.
Nur `/gesundheit` bleibt auf der Wurzel: Eine Überwachung spricht den Container
unmittelbar an.

Kein Sprecherparameter, aber ein Zugang: Jeder Weg außer `/gesundheit` verlangt
den Sprecherzugang aus `hören` und leitet die Kennung daraus ab - dieselbe
Regel wie drüben, aus demselben Grund (die Bindung zieht der Server, nicht der
Aufrufer).

### Ablage

```
data/diktate/<sprecher_id>/
├── audio/<abschnitt_id>.wav     16 kHz mono, je ein Abschnitt
└── schreiben.sqlite             Sitzungen, Abschnitte, Postausgang
```

Nach Sprecher gegliedert wie der Korpus, obwohl eine Instanz nur einen kennt:
Sonst fände `scripts/purge_speaker.py` diese Dateien nicht, und eine Löschung
wäre unvollständig.

Neben und nicht im Korpus: `hören` ist dessen einziger Schreiber
(Grundentscheidung 6). Was hier liegt, ist Arbeitsstand.

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

**lernen**

| Tabelle | Zweck |
|---|---|
| `jobs` | Auftrag, Schnappschuss, Rezept, Status, Log-Referenz |

**schreiben**

| Tabelle | Zweck |
|---|---|
| `sessions` | eine Diktiersitzung |
| `segments` | Text, Reihenfolge, Audio, Herkunft (initial/neu) |
| `outbox` | offene Korrekturen mit Wiederholungszähler |

Zugriff über SQLAlchemy 2.0 mit typisierten Modellen. Schemaänderungen als
nummerierte `.sql`-Dateien. Kein Alembic - bei diesem Schemaumfang ist die
Migrationsmaschinerie größer als das Schema.

Angewendet werden sie an drei Stellen, und die dritte ist die wichtigste: beim
Anlegen eines Sprechers (`api/speakers.py`), beim ersten Zugriff auf dessen
Datenbank (`deps.engine_fuer`) und für alle Korpora auf einmal mit
`make migrate` - im Container `docker compose exec wortlaut python
scripts/migrate.py`, denn dort gibt es weder `make` noch `uv`. Der Zugriff musste dazukommen, nachdem `004_pin.sql` die Spalte
`speakers.pin_hash` mitbrachte: Bestehende Korpora bekamen sie nie, die Modelle
fragten sie ab, und danach scheiterte jedes `SELECT` auf `speakers` - die Liste
der Aufsicht wie die Zugangsprüfung. Ein Update darf nicht davon abhängen, dass
sich jemand an ein Skript erinnert; der Container startet uvicorn, sonst nichts.

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
| ASR | faster-whisper (CTranslate2) | schnellste brauchbare Whisper-Laufzeit auf CPU und kleiner GPU |
| ASR entfernt | OpenAI-kompatibler Endpunkt | ein Adapter deckt mehrere Anbieter ab |
| Training | HF Transformers, Datasets, Accelerate | Standardrezept für Whisper, breit dokumentiert |
| Diagramme | Apache ECharts, nachgeladen und nur mit den eingetragenen Teilen | Finger und Maus gleichermaßen, gemischte Reihen in einem Bild, und `connect` koppelt mehrere Diagramme aneinander - der Punkt, an dem die schlankeren Bibliotheken aufhören |
| Textquelle | LLM über einen Adapter, OpenAI-kompatibel oder Anthropic | Thema und Altersspanne als Prompt-Parameter; derselbe Adapter bedient ein lokales Ollama und die bezahlten Anbieter - für ein paar Vorlesesätze genügt ein kleines Modell auf der eigenen GPU |
| Jobs | `jobs`-Tabelle plus Poll-Worker | keine Broker-Abhängigkeit für eine Warteschlange mit selten mehr als einem Eintrag |
| Proxy | der vorhandene Reverse Proxy des Wirts | TLS und Pfadverteilung gehören zur Maschine, nicht in dieses Projekt |
| Auth | je Sprecher ein Zugang, der zugleich die Kennung ist - derselbe in beiden Apps; der Token davor schützt nur die Verwaltung, ein zweiter die Aufsicht | die Bindung zwischen Aufrufer und Verzeichnis muss der Server ziehen, nicht der Aufrufer; ein Mensch, ein Link, beide Apps |
| Tests | pytest, FastAPI-TestClient | echte SQLite-Datei, echte Endpunkte, kein Nachbau |
| Werkzeug | uv | eine Abhängigkeitsdatei, ein Befehl, keine Diskussion |

---

## Konfiguration

Alles über Umgebungsvariablen, eingelesen in der `config.py` der App, nirgends
`os.environ` im Fachcode. Die Bibliothek liest gar keine Umgebung: Pfade und
Schlüssel werden ihr übergeben. Vorlage ist `.env.example`; im Betrieb bekommt
jede App ihre Werte aus der Umgebung.

```
# gemeinsam
WORTLAUT_DATA_DIR=/srv/wortlaut/data
WORTLAUT_STORAGE=local              # bislang nur local; s3 ist vorbereitet

# hören
WORTLAUT_LLM_PROVIDER=              # leer = Textquelle „LLM" abgeschaltet
                                    # openai = jede OpenAI-kompatible Schnittstelle
                                    #          (lokales Ollama, Groq, Gemini, Mistral)
                                    # anthropic = Claude, braucht einen Schlüssel
WORTLAUT_LLM_API_KEY=               # bei lokalem Ollama leer
WORTLAUT_LLM_MODEL=gemma2:9b
WORTLAUT_LLM_BASE_URL=http://ollama:11434/v1   # nur bei openai
WORTLAUT_AUTH_TOKEN=                # Verwaltung: Profile anlegen, Zugänge
                                    # ausgeben. Leer = abgeschaltet, auch in
                                    # der Entwicklung. Öffnet selbst kein
                                    # Korpus - dorthin führt der Zugang des
                                    # Sprechers.
WORTLAUT_ADMIN_TOKEN=               # Aufsicht: in jeden Korpus sehen,
                                    # umbenennen, sichern, löschen. Leer =
                                    # abgeschaltet (nicht offen).

# lernen - entworfen, noch von keiner config.py gelesen; steht deshalb auch
# nicht in der .env.example.
WORTLAUT_TRAINING_BACKEND=local     # local | remote. Das Basismodell steht
                                    # nicht hier: Es gehört zum Sprecherprofil,
                                    # eines je Sprecher.

# schreiben - wessen Stimme steht hier nicht: Der Sprecher kommt aus dem
# Zugang, den der Browser vorlegt (derselbe wie bei „hören").
WORTLAUT_MODELL_REF=                # leer = je Sprecher sein eigener Stand
WORTLAUT_ASR_MODELL=small           # gilt, solange kein Stand freigegeben ist
WORTLAUT_SPRACHE=de                 # Sprache der Diktate, an Whisper gereicht
WORTLAUT_ASR=local                  # local | remote
WORTLAUT_ASR_ENDPOINT=
WORTLAUT_ASR_API_KEY=
WORTLAUT_INTAKE_URL=https://wortlaut.example.org/api/korpus/intake
                                    # kein Token: gesendet wird mit dem Zugang
                                    # dessen, der den Text bestätigt hat.
```

---

## Entwicklung

Voraussetzungen: Python 3.12 mit [uv](https://docs.astral.sh/uv/), Node 20 oder
neuer für das Frontend - und **ffmpeg im Pfad**, sonst schlägt jeder
Aufnahme-Upload fehl.

```bash
cp .env.example .env
uv sync                      # Abhängigkeiten und die Bibliothek `wortlaut`
cd apps/hoeren/frontend && npm install && cd -

make test                    # Testlauf, je nach Hardware 5-50 Sekunden
make dev APP=hoeren          # Backend auf :8000, Vite auf :5173
make migrate                 # alle Korpora auf einmal fortschreiben
```

Aufgerufen wird `http://localhost:5173`; Vite leitet `/api` an das Backend
weiter, deshalb gibt es keine CORS-Regeln. `make migrate` ist kein erster
Schritt: Neue Sprecher bekommen ihre Datenbank beim Anlegen, bestehende werden
beim ersten Zugriff fortgeschrieben. Es ist der Weg, das für alle Korpora auf
einmal und vor dem ersten Aufruf zu tun - etwa um zu sehen, was ein Update am
Schema ändert.

Für `schreiben` dasselbe mit eigenem Port - beide dürfen nebeneinander laufen:

```bash
uv sync --extra asr          # zusätzlich faster-whisper (nur für WORTLAUT_ASR=local)
cd apps/schreiben/frontend && npm install && cd -
make dev APP=schreiben       # Backend auf :8001, Vite auf :5174
```

Aufgerufen wird `http://localhost:5174/schreiben/` - mit Pfad, weil die App
dort liegt, in der Entwicklung wie im Betrieb. Laufen beide Apps, führt auch
der Reiter auf `http://localhost:5173` hinüber. Beim ersten Diktat lädt faster-whisper sein Modell herunter;
das dauert einmalig und braucht Netz.

Noch nicht nutzbar, weil `lernen` fehlt:

```bash
make train SPEAKER=spr_7f2a RECIPE=whisper_full
make release JOB=42
```

Ohne GPU: `WORTLAUT_TRAINING_BACKEND=remote` und im Sprecherprofil
`openai/whisper-small` als Basismodell. Die Apps laufen lokal, das Training auf
gemieteter Hardware.

Betrieb, Endpunktliste und Fehlersuche stehen in [`docs/betrieb.md`](docs/betrieb.md).

---

## Tests

```bash
make test
```

Läuft in gut einer Sekunde: ohne GPU, ohne Netz, ohne Mikrofon.

| Ort | Prüft |
|---|---|
| `packages/wortlaut/tests/` | Chunker, Textformate, Audiomessung und -schnitt, Ablage, Migrationen, Registry, Fehlerraten |
| `apps/hoeren/tests/` | Endpunkte gegen eine echte SQLite-Datei im Temporärverzeichnis; dazu die Trennung: Der Zugang des einen öffnet den Korpus des anderen nicht, und eine fremde Kennung im Parameter endet mit 403 statt mit einem Schreibvorgang. Für die Aufsicht: dass sie ohne Token zu ist, dass ihre Sicherung sich wirklich zurückspielen lässt, und dass es keinen Weg gibt, der mehr als einen Sprecher löscht. Und, seit `004_pin.sql` es versäumte: dass ein Korpus im ältesten Schemastand beim ersten Zugriff eingeholt wird, statt die Ansicht stillzulegen |
| `apps/hoeren/tests/test_auswertung.py` | Der Auswertungslauf ohne Whisper: was offen ist, was ein Fehlschlag anrichtet, dass ein zweiter Lauf nichts doppelt tut |
| `apps/schreiben/tests/` | Diktat und Abschnittsersatz, Postausgang, Modellauskunft |

Zwei Regeln halten den Aufwand klein und die Aussagekraft hoch:

**Nachgebaut wird so wenig wie möglich.** Die Tests sprechen mit echtem SQLite,
echten Dateien und den echten Endpunkten. Ersetzt ist nur, was Geld, Netz oder
eine GPU kosten würde: der LLM-Anbieter, ffmpeg, Whisper und der Weg von
`schreiben` zurück zu `hören`.

**ffmpeg wird trotzdem einmal wirklich benutzt.** Ein Test erzeugt eine
Opus-Datei, wie sie ein Browser liefert, schickt sie an `POST /api/recordings`
und prüft, dass im Korpus 16 kHz Mono liegen. Damit ist der Weg vom Browser bis
zur Datei einmal vollständig durchlaufen; die übrigen Aufnahmetests kommen
ohne externes Programm aus. Fehlt ffmpeg, werden diese drei Tests übersprungen
statt zu scheitern.

Was noch fehlt: das Frontend hat keine eigenen Tests. `npm run check`
(svelte-check) prüft dort bislang nur die Typen.

Den kompletten Weg im Browser - Sprecher anlegen, Textquelle, Aufnehmen,
Fortschritt - deckt kein automatisierter Test ab. Dafür gibt es eine
Schritt-für-Schritt-Anleitung zum Selbst-Durchklicken:
[`docs/manueller-test.md`](docs/manueller-test.md).

---

## Datenschutz

Stimmaufnahmen einer Person mit Sprechstörung sind Gesundheitsdaten nach Art. 9
DSGVO. Das hat Folgen für den Aufbau, nicht nur für einen Hinweistext:

- Audio liegt ausschließlich unter `WORTLAUT_DATA_DIR`, nie im Git, nie in Logs.
- Wer an einen Korpus kommt, entscheidet der vorgelegte Zugang und nicht die
  Adresse: Bei mehreren Personen an einer Instanz kommt keine an die Aufnahmen
  einer anderen, auch nicht aus Versehen.
- Die entfernten Adapter für ASR und LLM sind bewusste Schalter mit lokaler
  Voreinstellung. Wer sie umlegt, schickt Stimm- oder Textdaten an Dritte.
- Verworfene Aufnahmen werden gelöscht, nicht nur markiert. In der Datenbank
  bleibt der Datensatz als Spur, die Audiodatei ist weg.
- `schreiben` behält kein Audio, das es losgeworden ist: Sobald ein Abschnitt
  im Korpus angekommen ist, wird seine Datei dort gelöscht.
- `scripts/purge_speaker.py` entfernt Profil, Aufnahmen, Schnappschüsse und Modelle
  vollständig. Das Recht auf Löschung muss ausführbar sein, nicht dokumentiert.
- **Meine Daten** zeigt einer Person nur ihre eigenen Aufnahmen, nie fremde -
  aus demselben Grund wie oben, nicht durch eine zweite Prüfung. Eine
  optionale PIN sichert die Ansicht - und ebenso **Darstellung** und
  **Zugangsdaten** - zusätzlich gegen den Klick aus Versehen; sie ist kein
  Ersatz für den Zugang, nur eine Hürde davor (siehe „Eine PIN davor" oben).

Einzelheiten in [`docs/datenschutz.md`](docs/datenschutz.md).

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
