# Durchsicht: toter Code, Redundanz, veraltete Kommentare

Eine Durchsicht von Code, Kommentaren und Dokumentation mit einem Ziel:
weniger Code, der dasselbe sagt, und keiner, der nichts mehr tut - damit das
Projekt kürzer, leichter zu pflegen und leichter zu erweitern wird.

> **Stand: 9. Oktober 2026**, nach dem Wegfall der Fassung mit Rauschen
> (Commits `473a479`, `b17a8d1`) und der Reparatur der Erkennung unter PyAV 19
> (`0fb6890`). Durchgesehen: `packages/wortlaut`, die Backends von „hören",
> „lernen" und „schreiben", der Trainer, `scripts/`, die drei Frontends und
> `packages/ui` (diese mit Werkzeugen und stichprobenweise gelesen), `docs/`,
> Dockerfiles. Hilfsmittel: `ruff` (F, ARG, SIM, B), `vulture`, `svelte-check`,
> ein Abgleich jedes Backend-Wegs gegen seine Aufrufer und jedes exportierten
> TypeScript-Namens gegen seine Verwender, ein Abgleich mit dem Datenbestand
> (welche Achsenwerte Läufe tatsächlich tragen).

Jeder Befund hat eine Kennung: **F** Fehler, **T** toter Code, **R**
Redundanz, **K** Kommentar oder Dokumentation. Die Spalte „Stand" sagt, was
daraus wurde, mit dem Commit der Behebung. Bilanz der Abarbeitung: knapp 1 000
Zeilen weniger (842 dazu, 1 836 weg), die 829 Tests und `svelte-check` aller
drei Frontends ohne Befund; zwei Befunde bleiben bewusst offen (T-07, R-11).

---

## Übersicht

| Kennung | Befund | Gewicht | Stand |
|---|---|---|---|
| F-01 | Merkliste der Auswertung mit falschem Typ | klein | behoben, `ba5306a` |
| F-02 | Warnung von `svelte-check` in „schreiben" | klein | behoben, `c5518d4` |
| T-01 | Weiterlernen auf einem Stand: vorbereitet, nie beauftragt | groß | behoben, `0f7ef62` |
| T-02 | `GET /api/konto/sessions` ohne Aufrufer | mittel | behoben, `24a3868` |
| T-03 | Einzelansicht eines Laufs liefert alle Wahllisten mit | mittel | behoben, `4904418` |
| T-04 | `scripts/folge_nachtragen.py` hat seine Arbeit getan | mittel | behoben, `86ce4f6` |
| T-05 | Spalte `speakers.tempo` ungenutzt | mittel | behoben, `d8a974b` |
| T-06 | Ablage `s3`: vorbereitet, nie gebaut | klein | behoben, `e2a7379` |
| T-07 | Vorlesemotor austauschbar für genau einen Motor | mittel | offen - Entscheidung |
| T-08 | Einzelne unbenutzte Namen | klein | behoben, `fc7f272` |
| R-01 | Jede Trainingsachse an rund zwanzig Stellen aufgezählt | groß | behoben, `b66f63b` |
| R-02 | Die Maße fünfmal definiert | mittel | behoben, `9269954` |
| R-03 | Aufnahme aus Befund: viermal von Hand kopiert | mittel | behoben, `bb0c4ee` |
| R-04 | Zuschnitt: dreimal dieselbe Vorprüfung und Schreibfolge | klein | behoben, `6b970b2` |
| R-05 | Zugang und Schlüssel: dreimal derselbe Vergleich und Kopf | mittel | behoben, `bb95aba` |
| R-06 | Ein Stand über seine Kennung lesen: an fünf Stellen | klein | behoben, `31a1f12` |
| R-07 | Einheiten je Quelle zweimal gezählt | klein | behoben, `3b96403` |
| R-08 | Kommalisten an drei Stellen zerlegt | klein | behoben, `14939c7` |
| R-09 | Konstanten und Hilfen, die es in der Bibliothek schon gibt | klein | behoben, `2fbe8bf` |
| R-10 | Fehlertext im Frontend 48-mal ausgeschrieben | mittel | behoben, `49ac66f` |
| R-11 | „Einsicht" und „Meine Daten" führen dieselbe Logik zweimal | mittel | offen - mit Sichtprüfung |
| R-12 | Bootstrap: zweimal dieselbe Ziehung | klein | behoben, `044ca1d` |
| R-13 | Audio: ffmpeg-Aufruf und Pegelrechnung doppelt | klein | behoben, `09ffa1c` |
| R-14 | Vorlesung und Hörprobe: zwei gleiche Funktionen | klein | behoben, `f56bbc9` |
| R-15 | Auswertung: Erledigt-Bedingung und Gütefelder doppelt | klein | behoben, `6563e39` |
| R-16 | Status `ok`/`verworfen` als Literal an vielen Stellen | klein | behoben, `330a1e2` |
| K-01 | Auswertung: Moduldocstring beschreibt den alten Ablauf | mittel | behoben, `06f355e` |
| K-02 | „Alle Modelle gleichzeitig im Speicher" - stimmt nicht mehr | mittel | behoben, `1abcebe` |
| K-03 | Verzeichnisbäume mit Lücke | klein | behoben, `2eac8b2` |
| K-04 | Dockerfiles erzählen ihre Geschichte | klein | behoben, `bf3f6bd` |
| K-05 | Weitere Kommentare mit Historie oder falscher Auskunft | klein | behoben, `7f5b73f` |
| K-06 | Gliederung von `wortlaut/laeufe.py` | klein | behoben, `e10d315` |

---

## Fehler

### F-01 Merkliste der Auswertung mit falschem Typ

`apps/hoeren/backend/services/auswertung.py`: `_Lauf.uebersprungen` und die
Merkliste in `starte` sind als `set[tuple[str, str, str]]` annotiert, die
Einträge sind `Posten.marke` - ein Paar aus Aufnahme und Modell. Überrest
der Fassung als drittem Glied. Läuft, weil Python die Annotation nicht prüft,
führt aber jeden Leser in die Irre.

**Behebung:** `set[tuple[str, str]]` an beiden Stellen.

### F-02 Warnung von `svelte-check` in „schreiben"

`apps/schreiben/frontend/src/routes/Ergebnis.svelte:234` liest `bestaetigt`
auf oberster Ebene des Skripts; Svelte warnt (`state_referenced_locally`).
Gemeint ist „beim Öffnen einmal"; so geschrieben, liest es sich wie ein
Versehen, und die einzige Warnung der drei Frontends verdeckt jede künftige.

**Behebung:** in `untrack` fassen, damit die Absicht im Code steht.

---

## Toter Code

### T-01 Weiterlernen auf einem Stand: vorbereitet, nie beauftragt

Ein Lauf kann laut Code auf einem trainierten Stand aufsetzen
(`laeufe.AUSGANGSSTAND`, `training/ausgangsstand.py`). `auftraege.bestelle`
setzt `Auftrag.ausgangsstand` nie; kein Weg aus Oberfläche oder Kommandozeile
führt dorthin, und kein Lauf im Datenbestand trägt das Feld. Gebaut wurde
es, weil Weiterlernen erprobt werden sollte; der Kommentar in `laeufe.py`
sagt selbst: „angeboten wird es nicht - weiterzulernen brachte keinen
Gewinn".

Daran hängen: `training/ausgangsstand.py` (270 Zeilen, Rückrechnung aus
CTranslate2), `ausgangsstand.quelle`/`erkenner` in `finetune.py`,
`Auftrag.ausgangsstand` und sein Schreiben in `auftraege.beauftrage`, die
Zweige in `laeufe.optionscode`, `laeufe.grundmodell_aus`,
`bewerten._version`, `bewerten`-Manifest, `api/laeufe.steckbrief` samt
`_sprechername`, `api/modelle._stand_herkunft`, `laeufe.AUSGANG` in den
Zwischenständen, `tests/test_ausgangsstand.py` (bis auf den Test, dass ein
Auftrag kein solches Feld trägt) und zwei Stellen in `docs/`.

**Behebung:** alles entfernen. `LaufAntwort.grundmodell` entfällt mit - es
wiederholte dann nur noch `basismodell`.

### T-02 `GET /api/konto/sessions` ohne Aufrufer

„Meine Daten" zeigt Sitzungen als eine Zeile und einen Kalender; die Liste
der eigenen Sitzungen fragt niemand mehr ab. Übrig sind der Weg
(`api/konto.sitzungen`), sein Schalter `nur_mit_aufnahmen` in
`uebersicht.sitzungen_seite`, `meineSitzungen` in
`apps/hoeren/frontend/src/lib/api.ts`, ein Test und die Zeile in
`docs/hoeren.md`. Die Zählung „nur Sitzungen mit Aufnahmen" in den
Kennzahlen bleibt - sie wird gezeigt.

**Behebung:** Weg, Schalter, Funktion, Test und Dokuzeile entfernen.

### T-03 Einzelansicht eines Laufs liefert alle Wahllisten mit

`EinzelAntwort` (`apps/lernen/backend/api/laeufe.py`) trägt dieselben
fünfzehn Wahllisten wie die Liste - Methoden, LoRA-Ziele, Abschlüsse … -,
`Lauf.svelte` liest keine davon. Nur `Training.svelte` braucht sie, aus
`ListeAntwort`.

**Behebung:** aus `EinzelAntwort` und dem Typ `Einzellauf` entfernen.

### T-04 `scripts/folge_nachtragen.py` hat seine Arbeit getan

Das Skript vergibt die Folge (`/43b`) an Läufe ohne sie. Jeder Lauf und jedes
Manifest im Bestand trägt eine; neue bekommen sie beim Auftrag. Das Skript ist
eine einmalige Nachführung.

**Behebung:** Skript und seine drei Erwähnungen in `docs/` entfernen.

### T-05 Spalte `speakers.tempo` ungenutzt

`db/models.Sprecher.tempo` ist laut eigenem Kommentar „ungenutzt und immer
1,0" - vorgespult wird je Stand. Die Spalte steht trotzdem in Modell und
Schema.

**Behebung:** Migration `022_ohne_sprechertempo.sql` (`ALTER TABLE speakers
DROP COLUMN tempo`), Feld aus dem Modell.

### T-06 Ablage `s3`: vorbereitet, nie gebaut

`storage.oeffne_ablage` kennt `s3` nur, um `NotImplementedError` zu werfen;
`.env.example` und `docs/konfiguration.md` nennen es „vorbereitet, nicht
umgesetzt". Eine Einstellung mit genau einem gültigen Wert ist keine.

**Behebung:** `WORTLAUT_STORAGE` und `oeffne_ablage` entfallen; beide Apps
legen `LokaleAblage(data_dir)` an. Das Protokoll `Ablage` bleibt - es ist die
Naht für Tests und eine spätere Umsetzung.

### T-07 Vorlesemotor austauschbar für genau einen Motor

`wortlaut/vorlesen.py` hat ein `Motor`-Protokoll, `motor_fuer` und die
Einstellung `WORTLAUT_VORLESEN_MOTOR` - für Piper allein. Jeder Aufrufer
reicht `stimmen_dir` und `vorlesen_motor` durch (sechs Stellen in „hören",
drei in „schreiben", `scripts/vorlesen.py`).

**Behebung:** offen. Die Abstraktion ist klein und dokumentiert („ein zweiter
Motor kommt daneben"); ob sie bleibt, ist eine Entscheidung über künftige
Motoren, keine Aufräumfrage. Entfernt werden hier nur die toten Teile darin
(T-08).

### T-08 Einzelne unbenutzte Namen

| Wo | Was |
|---|---|
| `wortlaut/sprachen.py` | `ist_unterstuetzt` |
| `wortlaut/rechenwerk.py` | `GERAETE` |
| `wortlaut/streuung.py` | `BLOCKARTEN` |
| `wortlaut/registry.py` | `aktiver_stand` (nur in Tests) |
| `wortlaut/vorlesen.py` | `RATE`; `except VorlesenFehler: raise` ohne Quelle |
| `apps/lernen/training/klangwandel.py` | `stufe_aus` |
| `apps/lernen/backend/config.py` | `lernen_geraet` |
| `apps/lernen/training/finetune.py`, `laeufer.py` | unbenutzte Importe `json`, `Path` |
| `apps/hoeren/backend/services/vorlesen.py` | `loesche`, Alias `VorlesenFehler` |
| `packages/ui/diff.ts` | `gleichanteil` |
| `apps/schreiben/frontend/src/lib/api.ts` | `postausgang` samt Typ (der Weg selbst ist dokumentierte Auskunft und bleibt) |

**Behebung:** entfernen.

---

## Redundanz

### R-01 Jede Trainingsachse an rund zwanzig Stellen aufgezählt

Eine neue Achse - oder ein neuer Wert - verlangt heute Änderungen an:
`laeufe.py` (Konstanten, Code-Tafel, `*_aus`-Leser, `optionscode`),
`auftraege.Auftrag`, `auftraege.Bestellung`, der Prüfliste in `bestelle`,
dem Aufbau des `Auftrag` dort, dem `inhalt` in `beauftrage`,
`api/laeufe.Bestellung`, dem Feld-für-Feld-Kopieren in `beauftrage`,
`LaufAntwort`, `_als_antwort`, den Wahllisten, `ListeAntwort`,
`EinzelAntwort`, `bewerten._version`, `scripts/trainieren.py`, dem
Frontend-Typ, `trainingswahl.ts` und `Training.svelte`. Vergisst man eine
Stelle, fällt das erst im Lauf oder in der Anzeige auf.

**Behebung:** eine Tafel `laeufe.ACHSEN` - je Achse Feld, Titel, Werte (die
Vorgabe zuerst) und Code - und alles Übrige daraus: `optionscode`, ein Leser
`laeufe.achse(auftrag, feld)` statt neun einzelner, die Prüfung in
`bestelle`, `Auftrag` und `Bestellung` mit einem Wörterbuch der Achsen, das
Schreiben von Auftrag und Manifest, die Felder von `Bestellung` und
`LaufAntwort` in der API (`create_model`) und `make train`. Die Form der API
bleibt, damit das Frontend unverändert weiterläuft. Je Achse bleiben ihre
Beschriftung (`api/laeufe.py`, `Training.svelte`), ihre Wirkung im Trainer
und ihr Teil im Namen eines Standes (`bewerten._version`) - das ist keine
Wiederholung, sondern ihr Inhalt.

### R-02 Die Maße fünfmal definiert

Genauigkeit, WER, CER, MER, WIL und Rechenzeit, mit Namen, Erklärung und
Richtung, stehen in `hoeren/api/auswertung.METRIKEN`,
`lernen/api/modelle.MASSE`, `lernen/services/messwerte.MASSE` und
`HOCH_IST_GUT`, `lernen/services/vergleich.MASSE` und `HOCH_IST_GUT` sowie
`hoeren/services/auswertung._MASSE`. Dazu baut `api/auswertung.uebersicht`
das Messwert-Wörterbuch Feld für Feld, und `_rechne` kopiert die Güte
einzeln.

**Behebung:** `wortlaut/metriken.py` bekommt `MASSE` (die vier Fehlerraten
und die Genauigkeit), `HOCH_IST_GUT` und je Maß Name und Erklärung; die Tafeln
beider Apps und die Listen der Dienste lesen dort.

### R-03 Aufnahme aus Befund: viermal von Hand kopiert

Die sechs Messwerte eines `audio.Befund` werden in `api/recordings.py`,
`api/intake.py`, `api/zuschnitt.teilen` und `services/zuschnitt.schneide`
Feld für Feld in die Zeile geschrieben; Annahme, Umwandlung und Ablage einer
Datei stehen in `recordings` und `intake` gleich.

**Behebung:** `services/aufnahmen.nimm_an(eingang, ablage, relpfad) ->
Befund` für die Annahme; die Felder des Befunds heißen wie die Spalten und
gehen mit `dataclasses.asdict` in die Zeile. Auch `scripts/importieren.py`
nimmt diesen Weg.

### R-04 Zuschnitt: dreimal dieselbe Vorprüfung und Schreibfolge

`services/zuschnitt.schneide`, `teile` und `kopiere` prüfen je für sich, ob
die Datei da ist und das Ende hinter dem Anfang liegt, und schreiben je über
ein eigenes temporäres Verzeichnis.

**Behebung:** `_quelle()` und `_schneide_ab()` - eine Prüfung, ein Weg in
die Ablage.

### R-05 Zugang und Schlüssel: dreimal derselbe Vergleich und Kopf

Den Bearer-Kopf zerlegen alle drei Apps selbst (`_vorgelegt`), den
zeitkonstanten Vergleich über UTF-8 haben `hoeren/deps._gleich` und
`wortlaut/schluessel.Schluessel.stand` je für sich, und die Prüfung „nur ein
Sprecherzugang" steht in `lernen/deps._zugang` und `schreiben/deps._wer_ruft`
fast gleich.

**Behebung:** `wortlaut/zugang.aus_kopf()`, `wortlaut/schluessel.gleich()` und
für „lernen" und „schreiben" der gemeinsame Wächter
`wortlaut/zugang.verlange_sprecher()`.

### R-06 Ein Stand über seine Kennung lesen: an fünf Stellen

`ref.split("/", 1)` → `registry.lies_stand` → `except (OSError, ValueError)`
steht in `hoeren/services/auswertung.tempo_fuer` und `gehoert`,
`schreiben/deps.modellstand`, `modellpfad` und `registry.aktiver_stand`.

**Behebung:** `registry.lies_ref(datenverzeichnis, ref) -> dict` (leer, wo
nichts zu lesen ist) und `registry.tempo_von(datenverzeichnis, ref)` für den
Faktor, der an vier Stellen je eigen gelesen wurde.

### R-07 Einheiten je Quelle zweimal gezählt

`api/sources.liste` und `services/uebersicht.quellen` bauen dieselbe
Unterabfrage „Vorlagen je Quelle".

**Behebung:** eine Funktion in `services/uebersicht.py`, die beide nutzen.

### R-08 Kommalisten an drei Stellen zerlegt

`auswertung.modelle`, `freigabe.grundmodellnamen` und
`Einstellungen.grundmodelle` zerlegen je eine kommagetrennte Einstellung.

**Behebung:** `wortlaut/einstellungen.liste(text)`.

### R-09 Konstanten und Hilfen, die es in der Bibliothek schon gibt

`hoeren/services/loeschung.SCHNAPPSCHUESSE` und `SCHNAPPSCHUSS_MARKE`
wiederholen `laeufe.SCHNAPPSCHUESSE` und `laeufe.SPRECHER_MARKE`;
`lernen/services/vergleich.baseline` rechnet `laeufe.kurzname` nach;
`lernen/services/freigabe.stand_aus_lauf` sucht, was
`registry.stand_zu_lauf` findet.

**Behebung:** die Bibliothek benutzen.

### R-10 Fehlertext im Frontend 48-mal ausgeschrieben

`ursache instanceof Error ? ursache.message : String(ursache)` steht 48-mal
in 17 Dateien; „Einsicht" prüft die PIN mit einem eigenen regulären Ausdruck
neben `gueltigePin` aus `$ui/pin.svelte`; `megabyte` steht zweimal.

**Behebung:** `fehlertext()` in `packages/ui/api.ts`, `gueltigePin` benutzen.
`megabyte` steht nur in den beiden Ansichten von R-11 und geht mit ihm.

### R-11 „Einsicht" und „Meine Daten" führen dieselbe Logik zweimal

`Einsicht.svelte` (die Aufsicht sieht einen Sprecher) und `MeineDaten.svelte`
(der Sprecher sieht sich) haben je eigene Fassungen von Aufnahmenliste mit
Blättern und Anhören, Umbenennen, PIN setzen und entfernen sowie dem
Knopf-Helfer `tue`.

**Behebung:** offen. Eine geteilte Komponente für die Aufnahmenliste ist der
naheliegende Schnitt, verlangt aber, beide Ansichten im Browser
gegenzuprüfen; dafür ist eine eigene Runde mit Sichtprüfung besser als ein
Nebenher.

### R-12 Bootstrap: zweimal dieselbe Ziehung

`streuung.intervall` und `streuung.unterschied` rechnen die gezogenen Mittel
mit denselben fünf Zeilen.

**Behebung:** `_ziehe` und `_bereich` für beide.

### R-13 Audio: ffmpeg-Aufruf und Pegelrechnung doppelt

`tempo.spule_vor` wiederholt den ffmpeg-Aufruf aus `audio.wandle_in_wav`
(mono, 16 kHz, s16, Fehlerbehandlung); `audio.untersuche` und
`audio.verlauf` rechnen Spitze und Fensterpegel je für sich.

**Behebung:** `audio.wandle_in_wav` nimmt eine Filterkette an und ist der eine
Aufruf; `untersuche` und `verlauf` rechnen über `_pegel`.

### R-14 Vorlesung und Hörprobe: zwei gleiche Funktionen

`hoeren/services/vorlesen.stelle_her` und `stelle_probe_her` unterscheiden
sich nur im Pfad.

**Behebung:** eine Funktion mit dem Pfad als Argument.

### R-15 Auswertung: Erledigt-Bedingung und Gütefelder doppelt

`auswertung._fertig` und `auswertung.zaehle` tragen dieselbe Bedingung
„dieses Rechenwerk oder übernommene Faltung" und „nur gültige Aufnahmen".

**Behebung:** `_erledigt(werk)` für die Bedingung. (Die Gütefelder erledigt
R-02.)

### R-16 Status `ok`/`verworfen` als Literal an vielen Stellen

Der Status einer Aufnahme steht als `"ok"` in rund zehn Abfragen, daneben
gibt es `auswertung.GUELTIG = "ok"`.

**Behebung:** `GUELTIG` und `VERWORFEN` in `db/models.py`, alle Stellen dorthin.

---

## Kommentare und Dokumentation

### K-01 Auswertung: Moduldocstring beschreibt den alten Ablauf

`services/auswertung.py` sagt „Aufnahmeweise, nicht modellweise … Alle
Erkenner liegen dafür gleichzeitig im Speicher". Gerechnet wird modellweise,
und auf der Karte liegt einer (`transkriptor_fuer`, `offene_posten`).

**Behebung:** den Punkt auf den heutigen Ablauf setzen.

### K-02 „Alle Modelle gleichzeitig im Speicher" - stimmt nicht mehr

Dieselbe Annahme begründet `int8_float16` in `wortlaut/rechenwerk.py`,
`docs/konfiguration.md` und `docs/architektur.md` (Technikwahl). Die
Begründung ist heute: ein großes Modell neben Training und Sprachmodell auf
einer Karte mit elf Gigabyte.

**Behebung:** an allen drei Stellen.

### K-03 Verzeichnisbäume mit Lücke

`wortlaut/corpus.py` hat eine leere Zeile mitten im Baum (dort stand
`audio/varianten/`), `wortlaut/registry.py` endet mit `├──` statt `└──`.

**Behebung:** Bäume schließen.

### K-04 Dockerfiles erzählen ihre Geschichte

`Dockerfile` (Abhängigkeitsschichten: „Solange die Apps über dem Befehl
standen …", „Danach stand die Bibliothek darüber …", „Deshalb jetzt …") und
`apps/lernen/training/Dockerfile` („Genau dafür steht hier kein
`--no-cache-dir` mehr") beschreiben, wie es früher war. Die Begründung gehört
hinein, die Geschichte in die Commits.

**Behebung:** auf das Warum kürzen.

### K-05 Weitere Kommentare mit Historie oder falscher Auskunft

* `training/laeufer.py`: „gehen wie bisher nur ins Container-Log".
* `wortlaut/db.py`: „bei fünf Tabellen" - es sind sieben, und eine Zahl im
  Text veraltet still.
* `hoeren/services/loeschung.datenverzeichnisse`: `lernen/<sprecher>` heißt
  dort „Aufnahmekennungen ohne Stimme"; es ist das Register der Läufe.
* `hoeren/deps.py`: „Kurzschreibweisen für die Signaturen" steht über
  `_sprache` statt über den Kurzschreibweisen.
* `wortlaut/__init__.py`: `__all__` nennt eine willkürliche Teilmenge der
  Module und wird nirgends gebraucht; ebenso `wortlaut/text/__init__.py`.
* `wortlaut/vorlesen.py`: zwei Abschnittsköpfe „Piper" hintereinander.

**Behebung:** berichtigen bzw. entfernen.

### K-06 Gliederung von `wortlaut/laeufe.py`

`auswahl_aus` steht unter „Selbsttraining", `mittelt` und `interpoliert`
unter „Kontext", vor drei Abschnittsköpfen fehlt die Leerzeile. Erledigt sich
weitgehend mit R-01.

**Behebung:** mit R-01 ordnen.
