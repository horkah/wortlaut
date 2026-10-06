# App „hören" - Sprachproben sammeln

Der Einstieg und der Ort, an dem der Korpus entsteht: Textquelle wählen,
äußerungsweise aufnehmen, den Fortschritt sehen - und messen, was die Modelle
daraus machen. Die Grundentscheidungen stehen in
[Der Entwurf](architektur.md#grundentscheidungen).

---

## Ablauf

1. **Sprecherprofil** anlegen: Name und Sprache. Die Sprache gilt für alles am
   Profil - Vorlagen, Aufnahmen, Training, Bewertung, Diktat - und lässt sich
   nicht wechseln ([Andere Sprachen](sprachen.md)). Dazu einen Zugang
   ausgeben; daraus wird ein Link, und der ist alles, was die Person braucht.
2. **Textquelle wählen.** Ein Thema mit Altersspanne, aus dem ein LLM Text
   erzeugt; ein hochgeladener Text; oder ein Foto, das erkannt und geprüft wird.
   Herkunft und Parameter werden gespeichert.
3. **Schneiden.** `chunker.py` zerlegt den Text in Einheiten von grob 3–12
   Sekunden geschätzter Sprechdauer, an Satz- und Teilsatzgrenzen.
4. **Aufnehmen.** Eine Einheit groß, davor und dahinter je eine blass.
   Aufnehmen, anhören, verwerfen, weiter. Die Stelle wird nicht gespeichert,
   sondern abgeleitet: offen ist jede Vorlage ohne gültige Aufnahme. Verwerfen
   macht sie wieder offen und löscht das Audio. Auf Wunsch in zufälliger
   Reihenfolge, fest je Sitzung.
5. **Prüfen.** Serverseitig Pegel, Clipping, Randstille und Dauer gegen die
   geschätzte Sprechdauer. Auffälliges wird angezeigt, nicht erzwungen - bei
   Sprechstörungen sind Ausreißer normal.
6. **Fortschritt.** Die Sprechzeit (`25 min 48 s`, `packages/ui/zeit.ts`)
   gegen zwei Marken: ab etwa 1,5 Stunden wird ein Modell brauchbar, ab etwa
   20 gut. Neben jeder Marke steht, was noch fehlt.

---

## Vorlesen und Nachsprechen

Wer nicht flüssig liest, lässt sich die Einheit vorlesen und spricht sie nach.
Nachsprechen verschiebt Tempo und Satzmelodie zur Vorgabe; solche Aufnahmen
tragen den Modus `nachgesprochen`, damit sich der Effekt messen lässt.

**Vorgelesen wird vom Server, sonst vom Browser.** Die Sätze stehen als
Vorlagen fest, bevor sie jemand hört; einmal gesprochen und abgelegt klingen
sie auf jedem Gerät gleich.

| | |
|---|---|
| Motor | Piper, auf dem Prozessor, MIT |
| Gemessen | 4,34 s Audio in 1,19 s (`de_DE-eva_k-x_low`) |
| Format | 16 kHz, 16 bit, mono |
| Ablage | `korpus/<sprecher>/vorlesen/<vorlage>.<stimme>.wav` |

`wortlaut/vorlesen.py` fragt einen Motor nur zweierlei - welche Stimmen, und
sprich diesen Satz -; ein zweiter Motor kommt daneben. Stimmen liegen im
Modellspeicher, nicht im Abbild, und werden einzeln geholt
(`scripts/vorlesen.py --hole de_DE-thorsten-high`); ohne Argument spricht das
Skript alle Vorlagen vorab. Ohne Stimme, ohne Piper oder bei einem Fehler
liest stumm der Browser vor. Vorgelesenes steht in keiner Sicherung und geht
mit dem Sprecher.

Unter „Audio" stehen „Vom Server" und „Von diesem Gerät" zur Wahl, mit
Stimme, Tempo (Vorgabe 0,9×) und einer Hörprobe an einem festen Satz vom
Server - sonst wäre die Probe ein Weg, beliebigen Text sprechen zu lassen. Wie
die Browserstimmen klingen, entscheidet das Betriebssystem
([Betrieb](betrieb.md#bessere-vorlesestimme-unter-linux)).

---

## Die Oberfläche

Die Kopfzeile hat zwei Reihen: oben die drei Apps, die offene dunkelgrün,
darunter die Ansichten der offenen App - in `hören` **Textquelle**,
**Aufnehmen**, **Fortschritt** und **Auswertung**, in der Reihenfolge der
Arbeit. Rechts steht, wer angemeldet ist - der Name, den der Server zum Zugang
nennt (`GET /api/zugang`).

Kopfzeile, Menü und die Ansichten dahinter gibt es einmal, in
`packages/ui/Rahmen.svelte`; eine App liefert nur ihre eigenen Ansichten. Das
Menü ist in jeder App dasselbe: **Sprecher** (für die Verwaltung) oder
**Meine Daten**, **Zugangsdaten**, **Audio**, **Darstellung**, **System** -
eine Liste (`menuePunkte` in `apps.ts`), kein Satz fester Zeilen. Was eine
Reiterreihe trägt, steht nicht zusätzlich im Menü.

**Die App öffnet, wo zuletzt gearbeitet wurde.** Ohne Route in der Adresse
gilt der zuletzt benutzte Reiter dieses Browsers (`packages/ui/reiter.ts`) -
gemerkt, nicht angesprungen, damit der Zurück-Knopf nirgendwohin führt, wo
niemand war.

**Zugangsdaten** steht immer im Menü, auch ohne gültigen Zugang: Dann ist es
der einzige Weg herein. Mit einem Sprecherzugang zeigt die Seite zuerst,
wessen Zugang im Browser liegt, und darunter **Zugang wechseln** - der Weg zu
Verwaltung und Aufsicht. Alle drei Apps lesen denselben Eintrag
(`packages/ui/zugang.ts`). Darunter stehen die **Rechte dieses Browsers**: was
der Zugang trägt, und je Schlüssel - Trainer und Bearbeitung - ob er gilt,
falsch ist, fehlt oder auf dem Server abgeschaltet ist. Eingetragen werden
beide Schlüssel nur hier (`packages/ui/schluessel.svelte.ts`); geprüft wird
mit derselben Rechnung wie in den Wächtern (`wortlaut/schluessel.py`).

Alle Apps liegen unter einer Adresse: `hören` auf der Wurzel, `lernen` unter
`/lernen/`, `schreiben` unter `/schreiben/` (`packages/ui/apps.ts`). Der Pfad
gehört der App - Oberfläche und API hängen selbst darunter (`BASIS` in
`main.py`, `base` in `vite.config.ts`); der Proxy reicht unverändert weiter.
Auf einem Wirt verteilt `apps/gesamt.py` im Prozess.

Mit dem Verwaltertoken gibt es nur eine Seite - Profile anlegen, Zugänge
ausgeben - und in der Kopfzeile steht „Verwaltung".

### Audio

Mikrofon, Verstärkung, Pegelregelung, Stimme, Tempo und Schriftgröße der
Vorlage, je mit Probe. Sie hängen am Gerät, nicht am Profil, und liegen im
`localStorage` (`wortlaut.mikrofon`, `wortlaut.verstaerkung`,
`wortlaut.autopegel`, `wortlaut.stimme`, `wortlaut.tempo`,
`wortlaut.schrift`).

Der **Mikrofontest** zeigt den Pegel gegen dieselben Grenzen, die der Server
prüft (`services/quality.py`). Zu leise Eingänge lassen sich zweifach heben:

- **Verstärkung**, ein fester Faktor (1–20×) vor der Aufzeichnung. **Automatisch
  einmessen** hört fünf Sekunden zu und setzt die Spitze auf −6 dBFS - auf die
  Spitze, weil ein Wert am Anschlag verloren ist.
- **Pegel automatisch nachregeln**, die Regelung des Browsers. Sie gleicht
  Schwankungen aus, hebt einen durchweg leisen Eingang aber nicht.

Beides steckt in der gespeicherten Aufnahme. Eine nachträgliche Normalisierung
auf dem Server gibt es nicht: Wie laut jemand spricht, gehört zu den Daten.

### Darstellung - und was überhaupt dasteht

Farben, Schriftart und Schriftgrößen, je mit Probe. Die acht Farben stehen als
Raster: Farbfeld zum Antippen, daneben der Hex-Wert als überschreibbares Feld
(`#1b4d3e`, `1b4d3e`, `#abc`); Ungültiges springt zurück. Ein Pfeil am
Zeilenende holt eine Farbe zurück, **Auf Vorgaben zurücksetzen** alles.

Darunter Schalter für alles Sichtbare, im Aufbau der Kopfleiste: die Apps, je
App ihre Ansichten, die Menüpunkte. Wer nur diktiert, blendet `hören` aus; wer
nur aufnimmt, `schreiben`. **Darstellung** und **Meine Daten** bleiben fest
eingeschaltet, damit sich niemand aussperrt. Ausgeblendet heißt unsichtbar,
nicht abgeschaltet: Routen, Zugang und PIN bleiben, wie sie sind. Gespeichert
im `localStorage` (`wortlaut.sichtbar.…`); nur ein ausdrückliches `false`
blendet aus.

---

## Der Zugang ist die Kennung

Mehrere Personen teilen eine Instanz, ohne an die Daten der anderen zu kommen.
Ein Zugang hat die Form

```
spr_01J8ZQ…8K.7f2ac1…            <sprecher_id>.<geheimnis>
```

und geht als `Authorization: Bearer …` mit. Der Server spaltet ihn am Punkt,
öffnet die Datenbank dieses Sprechers und prüft dort den Prüfwert des
Geheimnisses. Die Kennung ist abgeleitet, nicht behauptet.

**Ein Fehlgriff wird laut.** `?sprecher=…` wird nur als Behauptung angenommen,
die stimmen muss; weicht sie ab, antwortet der Server mit 403 und nennt beide
Kennungen.

**Der Zugang kostet die Person nichts.** Beim Ausgeben entsteht ein Link
`…/#/zugang/<zugang>`, einmal geöffnet und als Lesezeichen abgelegt. Das
Geheimnis steht im Fragment und erreicht nie ein Zugriffsprotokoll. Einen
Abmeldeknopf gibt es nicht; ein anderer Link ersetzt den vorhandenen.

**Ein verlorener Zugang wird ersetzt.** Gespeichert ist nur der Prüfwert
(`speakers.zugang_hash`); im Klartext gibt es den Zugang genau einmal. Ein
neuer macht den alten ungültig; Zurückziehen ohne Ersatz sperrt den Korpus.

`WORTLAUT_AUTH_TOKEN` schützt nur die **Verwaltung** - Profile anlegen,
Zugänge ausgeben und zurückziehen - und öffnet keinen Korpus. Wer selbst
aufnehmen will, gibt sich einen Zugang aus wie alle anderen. Ein Link ist ein
Lesezeichen, kein Ausweis: Wer ihn weitergibt, gibt den Korpus weiter.

---

## Die Aufsicht

Ein eigener Token, `WORTLAUT_ADMIN_TOKEN`, sieht über alle Korpora: einsehen,
umbenennen, PIN setzen, sichern, ausleiten, löschen - und alles, was die
Verwaltung darf. Eingetragen wird er unter „Zugangsdaten" wie ein
Verwaltertoken; der Server erkennt die Form (`wortlaut.zugang`). Ein Browser
trägt genau einen Zugang.

Die Wege der Aufsicht nennen als einzige ihren Sprecher in der Adresse
(`/api/admin/…`): Die Aufsicht hat keinen eigenen, geprüft wird ihr Token.
Leer heißt abgeschaltet, auch in der Entwicklung.

### Zwei Formate, zwei Fragen

Die **Sicherung** (`.tgz`, je Sprecher oder über alle) beantwortet „der Server
ist weg, ich will den Stand zurück":

```
wortlaut-gesamt-20260822-174500.tgz
├── sicherung.json               Zeitpunkt, Sprecher, Ausgelassenes, je Datei Größe und SHA-256
└── daten/
    ├── korpus/spr_…/hoeren.sqlite
    ├── korpus/spr_…/audio/rec_….wav
    └── diktate/spr_…/…               Arbeitsstand von „schreiben"
```

`daten/` bildet das Datenverzeichnis ab; Zurückspielen heißt Auspacken an die
richtige Stelle (`scripts/restore.py` oder `tar xzf`). Die Datenbanken kommen
über die Online-Backup-Schnittstelle von SQLite - ein `cp` wäre im WAL-Modus
kein stimmiger Stand -, der Dienst darf also laufen.

Gesichert wird, was ein Mensch hervorgebracht hat. Was eine Maschine daraus
rechnet, bleibt draußen und kommt von selbst zurück:

| | Größe | kommt zurück durch |
|---|---|---|
| Modellstände `modelle/` | ~1 GB je Stand | einen Trainingslauf |
| Laufverzeichnisse `snapshots/` | je Lauf ein Verzeichnis | einen Trainingslauf |
| Varianten `audio/varianten/` | etwa so viel wie das Audio | den nächsten Auswertungslauf |
| vorgelesene Sätze `vorlesen/` | wenige MB | das nächste Vorlesen |
| Tabelle `erkennungen` | wächst mit jedem Modell | denselben Lauf |

Die Datenbank kommt vollständig mit; geleert wird in der Kopie nur
`erkennungen`, und `sicherung.json` nennt das unter `ausgelassen`.

Der **Datensatz** (`.zip`, je Sprecher) ist für Werkzeuge, die von wortlaut
nichts wissen:

```
spr_…/
├── LIESMICH.txt
├── metadaten.csv        file_name, transcription, dauer_s, modus, quelle, …
├── metadaten.jsonl
└── audio/
    ├── rec_….wav        16 kHz mono, PCM 16 bit
    └── rec_….txt        der Text zu genau dieser Datei
```

`file_name` und `transcription` sind die Namen, die das `audiofolder`-Format
von Hugging Face erwartet. Der Datensatz ist keine Sicherung, und die
`LIESMICH.txt` sagt das.

### Löschen: drei Stufen

| | was verschwindet | was bleibt |
|---|---|---|
| eine Aufnahme | Audio samt Varianten und Zeile; die Einheit wird wieder offen | alles andere |
| alle Aufnahmen eines Sprechers | jedes Audio, jede Aufnahmezeile | Profil, Textquellen, Warteschlange |
| ein Sprecher | Korpus, Diktate, Modellstände, Laufverzeichnisse | nichts |

Varianten gehen immer mit: Sie sind dieselbe Stimme und derselbe
Gesundheitsdatensatz. Eine Stufe „alle Sprecher" gibt es nicht. Die beiden
großen Stufen verlangen die Kennung ein zweites Mal (`?bestaetigung=…`); die
Oberfläche lässt dafür den Namen abschreiben. Was zu einer Person gehört,
steht an einer Stelle (`services/loeschung.py`), die auch
`scripts/purge_speaker.py` fragt.

---

## Meine Daten

Dieselben Profildaten, Sitzungen und Aufnahmen, die die Aufsicht sähe
(`api/konto.py`), für den Sprecher selbst - aus dem vorgelegten Zugang, ohne
Kennung in der Adresse. Die Textquellen stehen nur als Summe da (wie viele,
wie viele Einheiten, wie viele aktiv) mit einem Verweis auf den Reiter
„Textquelle"; die Liste selbst führt nur er. Sitzungen stehen hier nur mit
Aufnahmen darin, mit Datum und Uhrzeit in der Zeitzone des Betrachters.
Kurzes zuerst (Name, Kennzahlen, Ausleiten, PIN, Textquellen), die langen
Listen danach.

Gelöscht wird hier nur einzeln - eine Aufnahme verwerfen wie beim Aufnehmen.
`schreiben` verlinkt auf dieselbe Seite.

### Eine Vorlage vom Foto

Ein Zeitungsausschnitt, ein Brief, ein Aushang: fotografiert statt getippt.
Gelesen wird lokal mit Tesseract (`wortlaut/text/ocr.py`); kein Bild verlässt
den Server ([Datenschutz](datenschutz.md)).

**Erkanntes wird geprüft, bevor es Vorlage wird.** Eine Zeichenerkennung rät;
ein Fehler wanderte sonst über die Vorlage in die Aufnahme und ins Training,
wo er als Abweichung des Sprechers zählte. `POST /api/sources/erkennen` gibt
den Text nur zurück; angelegt wird erst mit `POST /api/sources/text`, nachdem
ein Mensch ihn gesehen hat. Die Oberfläche sagt, ob ein Text `gelesen`,
`erkannt` oder `eingefügt` ist. PDFs gehen denselben Weg, damit Kopfzeilen
und Seitenzahlen gestrichen werden können; `txt`, `md`, `epub` und `docx`
gehen unmittelbar durch.

**Aus der Kamera** über das Kamerasymbol (`capture` öffnet die Kamera-App des
Telefons, die besser fokussiert als jeder eigene Sucher), **aus der
Zwischenablage** als Bild oder Text über das `paste`-Ereignis.

**Auf dem Bild:** die lange Seite auf 2400 px begrenzt (größer liest nicht
besser, nur langsamer), dazu eine entrauschte Fassung (3×3-Median, gegen das
Moiré abfotografierter Bildschirme). Beide gehen in drei Seitenarten durch
Tesseract; es gilt der Durchgang mit den meisten Zeichen in Wörtern ab drei
Zeichen.

**Auf dem Text,** nur bei Erkanntem:

- Zeilen aus **mehrheitlich Bruchstücken** fallen weg (Muster, die Tesseract
  für Schrift hält); Ziffern zählen mit, damit `48h` bleibt.
- Zeilen unter einer **mittleren Zuversicht** fallen weg (`image_to_data`) -
  etwa ein Unterstrich, der als Wort gelesen wurde. Die Grenze hängt an der
  Länge des längsten Wortes: bis fünf Zeichen 60, ab sechs 15. Drei zufällig
  passende Formen findet man in jeder Struktur, acht hintereinander nicht.

Was stehen bleibt, streicht ein Mensch im nächsten Schritt; was verschwindet,
sähe er nie. Bei einem PDF wird nichts davon angewandt - ein Scan ist flach
ausgeleuchteter Fließtext, Tesseracts Vorgabefall.

**Erkannt wird in der Sprache des Profils.** Mit dem englischen Wörterbuch
fallen Umlaute ganz aus; das deutsche liest englischen Text mit. Zwei
Wörterbücher zugleich (`deu+eng`) wären möglich, gewinnen aber mal und
verlieren mal, und kein Maß wählt zuverlässig die bessere Fassung - wer
regelmäßig anderssprachiges Material aufnimmt, legt ein zweites Profil an.

**Die Grenze: schräg fotografiert.** Bis etwa zwei Grad trägt Tesseracts
Zeilenausrichtung, ab vier bricht es ein, und eine Drehprobe rät bei kleinen
Winkeln. Ein schräg fotografiertes Plakat ist ein Trapez, das keine Drehung
gerade macht. Die Oberfläche rät deshalb, parallel zu halten, und zeigt die
Vorlage im Prüfschritt neben dem Text: Safari bietet dort Live Text an -
auswählen, kopieren, einfügen.

Ohne Tesseract fehlt der Weg, und `GET /api/sources/erkennung` sagt es, bevor
jemand ein Bild wählt.

### Eine PIN davor

Wer mag, sichert **Meine Daten**, **Darstellung** und **Zugangsdaten** mit
einer vierstelligen PIN (`services/pin.py`) - eine PIN für alle, einmal je
Sitzung eingegeben, über alle Apps (`packages/ui/pin.svelte.ts`), nur im
Speicher der Seite. Sie steht im Korpus, gefragt wird deshalb auch aus
`schreiben` die Konto-API von `hören`.

Die PIN ist eine Hürde gegen den Klick aus Versehen, kein zweites Schloss:
zeitkonstant verglichen, ohne Sperre nach Fehlversuchen, und sie schützt nur
die lesenden Wege unter `/api/konto/…`. Wessen Zugang der Server nicht kennt,
kommt ohne PIN zu den Zugangsdaten - sonst läge der Schlüssel hinter dem
Schloss. Gesetzt wird sie ohne die alte zu kennen, von der Person selbst oder
von der Aufsicht.

---

## Zuschnitt - die Stille an den Rändern

Zwischen Knopfdruck und erstem Laut liegt oft eine Sekunde, am Ende mehr. Über
anderthalb Stunden Korpus summiert sich das zu einer halben Stunde, die
mittrainiert und mitgemessen wird. Der Zuschnitt ist eine Werkbank, erreichbar
über **Meine Daten → Zuschnitt öffnen**.

Je Aufnahme eine Karte, älteste zuerst: der Lautstärkeverlauf mit zwei Linien,
die Vorlage, zwei Knöpfe zum Hören (ganz, oder nur was bliebe). Die Linien
stehen anfangs, wo der Pegel die Stimme vermutet, mit einem Zehntel Sekunde
Luft (`wortlaut/audio.stimmgrenzen`, 20-ms-Fenster, Schwelle relativ zur
Spitze - dieselbe Rechnung wie beim Hochladen). Verschoben wird mit Finger,
Maus oder Pfeiltasten.

**Kein VAD.** Ein Raum, ein Mikrofon vor dem Mund, eine Äußerung - was laut
wird, ist diese Person. Ein Sprachmodell zu fragen, wo abweichende Sprache
anfängt, träfe dieselbe Annahme, an der die Diktierfunktion des Telefons
scheitert; und über dem Vorschlag sitzt ohnehin ein Mensch.

**Geschrieben wird erst nach der Rückfrage**, je Aufnahme:

1. Die Datei entsteht aus dem Original, verlustfrei.
2. Die Grenzen kommen in die Zeile; ab hier gilt der Zuschnitt überall.
3. Die Varianten werden aus der neuen Arbeitsdatei neu gerechnet.
4. Die Messwerte der Aufnahme werden gelöscht, übernommene Faltungen
   eingeschlossen; der nächste Auswertungslauf rechnet neu.

Das Original bleibt; **Zuschnitt zurücknehmen** stellt es wieder her.
Geschnitten wird immer aus dem Original, sonst wanderte die Grenze nach innen.
Bei 16 kHz mono PCM ist ein Rahmen zwei Byte, geschnitten wird auf ganze
Rahmen, nach außen gerundet, ohne Blenden.

### Editieren - teilen oder berichtigen

**Editieren …** an jeder Karte öffnet eine Aufnahme allein: drei Linien in der
Kurve (Anfang, gestrichelte Teilung, Ende), der Text Wort für Wort mit
anklickbaren Lücken, zwei Felder für die Texte der Teile, drei Knöpfe zum
Hören. Die Teilung steht anfangs in der längsten Pause, die Textteilung folgt
ihr an der passendsten Wortgrenze, bis jemand klickt.

Nach der Rückfrage entstehen zwei neue Aufnahmen mit eigener Datei und
eigener Vorlage; Byte für Byte ergeben sie den Bereich des Originals. Liegt die
Teilung auf Anfang oder Ende, entsteht eine einzige Kopie - so wird aus
derselben Ansicht eine Aufnahme mit berichtigtem Text. Das Original bleibt, bis
es jemand löscht. Die Teile tragen sein Datum und einen Sortierschlüssel
(`<id>.1`, `<id>.2`), der sie unter ihm hält.

### Löschen im Zuschnitt

**Löschen** nimmt markierte Aufnahmen ganz aus dem Bestand: Zeile, Original,
Zuschnitt, Varianten, Messwerte - und die Vorlage, wenn keine andere Aufnahme
mehr an ihr hängt. Anders als Verwerfen, das die Vorlage wieder offen macht.
Gedacht für das Original nach dem Teilen.

### Der Schlüssel

Vor allen Wegen des Zuschnitts steht zusätzlich `WORTLAUT_EDITOR_KEY`
(`X-Editor-Key`), auch vor den lesenden: Der Zuschnitt entscheidet für jede
folgende Messung und jedes Training, welcher Ton gilt. Eingetragen wird er
unter „Zugangsdaten"; ob er gilt, sagt `GET /api/zugang` (`bearbeiten`). Nur
dann steht der Weg in den Zuschnitt in „Meine Daten", sonst ein Verweis auf
die Zugangsdaten. Leer heißt abgeschaltet; dann fehlt der Punkt ganz.

---

## Auswertung - wie gut hört welches Modell?

Jede Aufnahme ist eine Prüfaufgabe: durch einen Erkenner schicken, mit der
Vorlage vergleichen (`services/auswertung.py`). Die Zahlen sind die Baseline
für `lernen`. Gemessen wird ein Korpus, der des Zugangs; verworfene Aufnahmen
zählen nicht.

Es treten an die Grundmodelle aus `WORTLAUT_AUSWERTUNG_MODELLE`:

| Modell | wofür |
| --- | --- |
| `small` | der Alltagsfall, die Untergrenze |
| `medium` | was mit mehr Rechenzeit zu holen ist |
| `large-v3` | das größte fertige Modell - reicht überhaupt eines für diese Stimme? |

Jeder Name in der Tabelle der Kennzahlen führt in die Einzelansicht in
`lernen` - ein Grundmodell in seinen Steckbrief, ein Stand in seinen Lauf.

### Die eigenen Stände treten mit an

Jeder trainierte Stand des Sprechers mit Gewichten (`ct2/`) steht daneben.
**Was ein Stand gelernt hat, misst er nie selbst** - das wäre eine Zahl über
sein Gedächtnis:

| woher eine Zeile kommt | für welche Aufnahmen | `herkunft` |
| --- | --- | --- |
| aus den Faltungen seines Laufs | die er im Lauf kannte | `faltung` |
| vom ausgelieferten Stand, hier gerechnet | alle übrigen | `gemessen` |

Beide Male misst die Zeile, wie gut der Stand etwas hört, das er nie gelernt
hat. Die Faltungen werden beim Öffnen der Seite übernommen
(`auswertung.gleiche_ab`), nicht erst beim Druck auf den Knopf.

- **Gekannt** hat ein Stand, was sein Lauf gelernt und gemessen hat -
  bei einem Kernlauf nur den Kern (`_gehoert_im_lauf`) - samt Teilen und
  Kopien davon (`verwandte`).
- **Eine Faltung gilt nur für den Ton, auf dem sie gemessen wurde.** Ist die
  Aufnahme seither zugeschnitten, wird sie nicht übernommen und, wo sie steht,
  weggeräumt (`vergiss_ueberholte_faltungen`); ohne Zuschnitt kommt sie
  zurück. Die Stelle bleibt dann leer und zählt weder als offen noch als
  erledigt.
- **Ohne Gewichte tritt ein Stand nicht an**, und ein gelöschter räumt seine
  Zeilen (`vergiss_verschwundene_staende`, im Lauf `noch_da`).
- **Übernommene Zeilen gelten nie als offen** - ihre Rechenzeit stammt von der
  Trainingsmaschine.

Angezeigt wird ein Stand mit seiner Kurzkennung (`K7M2Q`,
`registry.beschriftung`).

### Zwei Fassungen je Aufnahme

Eine Aufnahme ist ein einzelner Fall - dieser Pegel, dieser Raum. Gemessen
wird deshalb auch eine Abwandlung (`wortlaut/augmentierung.py`):

| Fassung | was sie tut | wonach sie fragt |
| --- | --- | --- |
| `original` | nichts | der Ausgangswert |
| `rauschen` | weißes Rauschen, 20 dB unter der Aufnahme | hält es einem Lüfter, einer Straße stand? |

Liegen beide Zahlen dicht beieinander, versteht das Modell den Sprecher.
Das Rauschen liegt in festem Abstand zur Aufnahme, nicht auf festem Pegel, und
ist mit der Kennung der Aufnahme als Keim gewürfelt - wiederholbar auf jeder
Maschine. Die Fassung liegt unter `audio/varianten/`, entsteht beim Hochladen
oder spätestens, wenn ein Lauf sie braucht (`make augmentieren` zieht es vor),
und geht beim Löschen mit. Womit **trainiert** wird, ist eine andere Frage
(siehe [Das Trainingsverfahren](trainingsverfahren.md#augmentierung-zur-laufzeit)).

### Vier Maße und eine Zahl

`wortlaut/metriken.py`:

| Maß | was es zählt | Grenzen |
| --- | --- | --- |
| **WER** | falsche, fehlende und zusätzliche **Wörter** | 0 bis offen |
| **CER** | dasselbe auf **Zeichen** | 0 bis offen |
| **MER** | Fehler im Verhältnis zu allem Gesagten | 0 bis 1 |
| **WIL** | verlorene Wortinformation | 0 bis 1 |

Darüber die **Genauigkeit**, 0 bis 100, das geometrische Mittel der vier
umgedrehten Raten:

* WER und CER werden **gebogen, nicht gekappt** (`1/(1+x)`) - „jedes Wort
  falsch" und „den Satz dreimal geliefert" bleiben unterscheidbar.
* **Null** heißt, wie bei MER und WIL, dass kein Wort getroffen wurde.
* **Geometrisch**, damit ein durchgefallenes Maß nicht von zwei guten
  aufgerechnet wird.

Verglichen wird auf angeglichenem Text - klein, ohne Satzzeichen, einfache
Leerzeichen. Der Rohtext wird gespeichert und angezeigt.

### Der Lauf

Ein Hintergrundlauf rechnet die offenen Tripel aus Aufnahme, Modell und
Fassung:

* **Von Hand angestoßen**, nie beim Hochfahren.
* **Ist nichts offen, läuft nichts**, und der Knopf sagt „Nichts Neues zu
  rechnen".
* **Modellweise**: Ein Modell rechnet alle offenen Aufnahmen und Fassungen,
  dann kommt das nächste, in der Reihenfolge von `WORTLAUT_AUSWERTUNG_MODELLE`
  und danach die eigenen Stände. So lädt jedes Modell einmal je Lauf.
* **Ein Erkenner auf der Karte.** Kommt das nächste Modell an die Reihe, geht
  das vorige herunter (`transkriptor_fuer`). Mehrere nebeneinander ließen
  einem großen Stand keinen Platz, und einem Training daneben auch nicht.
* **Danach ist die Karte frei.** Endet ein Lauf, gibt er den Erkenner zurück
  (`gib_karte_frei`), denn der Trainer braucht die ganze Karte.
* **Wiederaufnehmbar.** Fertig ist, was in `erkennungen` steht; ein zweiter
  Lauf rechnet nur, was fehlt.
* **Fertig heißt: auf diesem Rechenwerk.** Jede Zeile trägt ihr Rechenwerk;
  eine aus einem anderen gilt als offen, damit die Rechenzeiten vergleichbar
  bleiben.
* **Gezählt wird nur, was gilt** - brauchbare Aufnahmen. Verwerfen räumt die
  Messzeilen einer Aufnahme mit.
* **Auf der Karte, wenn eine da ist**; ist sie voll, weicht der Lauf auf den
  Prozessor aus.
* **Ein Lauf zur Zeit**, über alle Sprecher.

### Die Ansicht

Eine Kurve über die Aufnahmen, lückenlos von 1 an gezählt. Je Aufnahme ein
Wert je Modell, eines als Balken, die übrigen als Punkte; Auswahllisten
wechseln Maß und Balkenmodell. Im Bild steht je Modell der **bessere** Wert
der Fassungen - was es aus der Aufnahme herausholt, wenn der Ton stimmt. Was
noch nicht gerechnet ist, bleibt leer statt null.

Darunter die Bilanz: **Median und Mittel** im gewählten Maß, je Fassung und
für den Bestwert. Liegen sie weit auseinander, verreißt ein Modell einzelne
Aufnahmen, statt gleichmäßig schlechter zu sein.

Ein Tipp in eine Spalte zeigt die Aufnahme: einen Abspieler für die gewählte
Fassung, die Vorlage und je Modell den erkannten Text, eine Fassung zur Zeit.
Unterschiede sind zeichenweise ausgezeichnet - fehlend grau durchgestrichen,
hinzugekommen farbig und fett, als `<del>`/`<ins>` (`packages/ui/diff.ts`); ein
Schalter zeigt den glatten Text.

Gezeichnet wird mit ECharts, nachgeladen mit den eingetragenen Teilen
(`apps/hoeren/frontend/src/lib/diagramm.ts`).

---

## Endpunkte

Verwaltung - hinter `WORTLAUT_AUTH_TOKEN`:

```
POST   /api/speakers                        { name, sprache }
GET    /api/speakers
GET    /api/speakers/{id}
POST   /api/speakers/{id}/zugang            neuen Zugang ausgeben
DELETE /api/speakers/{id}/zugang            Zugang zurückziehen
```

Daten - hinter dem Zugang eines Sprechers, der zugleich sagt, welcher:

```
POST   /api/sources/llm                     { thema, altersspanne, umfang }
POST   /api/sources/upload                  multipart: datei
POST   /api/sources/erkennen                multipart: datei - liest, legt nichts an
POST   /api/sources/text                    { text, titel, herkunft }
GET    /api/sources/erkennung               ob Bilder gelesen werden können
GET    /api/sources
GET    /api/sources/{id}/text               Klartext, eine Einheit je Absatz
PATCH  /api/sources/{id}                    { aktiv }
DELETE /api/sources/{id}                    409, wenn Aufnahmen daran hängen
POST   /api/sessions
GET    /api/prompts/next?session=…
GET    /api/prompts/{id}/vorlesung          die Vorlage als Audio vom Server
GET    /api/vorlesen/stimmen                die Serverstimmen der Profilsprache
GET    /api/vorlesen/probe?stimme=          Hörprobe an einem festen Satz
POST   /api/recordings                      multipart: audio, prompt_id, modus
GET    /api/recordings/{id}/audio?fassung=  Original oder eine Abwandlung
DELETE /api/recordings/{id}
GET    /api/progress
POST   /api/korpus/intake                   ← von „schreiben"
GET    /api/konto                           Profil, Kennzahlen, Textquellen    + X-Pin
GET    /api/konto/sessions?ab=&anzahl=                                         + X-Pin
GET    /api/konto/recordings?ab=&anzahl=                                       + X-Pin
PATCH  /api/konto                           { name } - umbenennen                   + X-Pin
GET    /api/konto/sicherung                 .tgz des eigenen Stands                 + X-Pin
GET    /api/konto/datensatz                 .zip der eigenen Paare                  + X-Pin
GET    /api/konto/pin                       { gesetzt }
GET    /api/konto/pin/pruefung              204, wenn die vorgelegte PIN stimmt
PATCH  /api/konto/pin                       { pin } - vier Ziffern oder null
GET    /api/auswertung                      Kurve und Stand - ohne Texte
GET    /api/auswertung/{aufnahme}           Vorlage und jede erkannte Fassung
POST   /api/auswertung/start
POST   /api/auswertung/stopp                Gerechnetes bleibt
```

Zuschnitt - zusätzlich `X-Editor-Key`:

```
GET    /api/zuschnitt/aufnahmen?ab=&anzahl= Kurve, Vorschlag, bisheriger Schnitt
GET    /api/zuschnitt/aufnahmen/{id}        eine Aufnahme - für „Editieren"
GET    /api/zuschnitt/aufnahmen/{id}/original
POST   /api/zuschnitt/schreiben             { grenzen: [{ id, start_s, ende_s }] }
POST   /api/zuschnitt/zuruecknehmen         { grenzen: [{ id }] }
POST   /api/zuschnitt/teilen                { id, start_s, teilung_s, ende_s, text_vorn, text_hinten } → { ids }
POST   /api/zuschnitt/loeschen              { grenzen: [{ id }] }
```

Aufsicht - hinter `WORTLAUT_ADMIN_TOKEN`:

```
GET    /api/admin/speakers                  alle Sprecher mit Kennzahlen
GET    /api/admin/speakers/{id}
GET    /api/admin/speakers/{id}/sessions?ab=&anzahl=
GET    /api/admin/speakers/{id}/recordings?ab=&anzahl=
GET    /api/admin/speakers/{id}/recordings/{r}/audio
PATCH  /api/admin/speakers/{id}             { name }
PATCH  /api/admin/speakers/{id}/pin         { pin }
GET    /api/admin/speakers/{id}/sicherung   .tgz
GET    /api/admin/speakers/{id}/datensatz   .zip
GET    /api/admin/sicherung                 .tgz über alle
DELETE /api/admin/speakers/{id}/recordings/{r}
DELETE /api/admin/speakers/{id}/recordings?bestaetigung={id}
DELETE /api/admin/speakers/{id}?bestaetigung={id}
```

Mit jedem Zugang (`/api/sprachen` und `/gesundheit` auch ohne):

```
GET    /api/zugang                          { art, sprecher_id, name, sprache, trainieren, bearbeiten }
                                            je Recht aus|fehlt|falsch|gilt, nach X-Trainer-Key und X-Editor-Key
GET    /api/sprachen                        die unterstützten Sprachen
GET    /api/system                          Maschine und Auslastung - für „System"
GET    /gesundheit
```

Die interaktive Dokumentation liegt unter `/docs`.
