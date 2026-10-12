# App „hören" - Sprachproben sammeln

Der Einstieg und der Ort, an dem der Korpus entsteht: Textquelle wählen,
äußerungsweise aufnehmen, den Fortschritt sehen - und messen, was die Modelle
daraus machen. Die Grundentscheidungen stehen in
[Der Entwurf](architektur.md#grundentscheidungen).

---

<a id="hilfe-ablauf"></a>

## Ablauf

1. **Sprecherprofil** anlegen: Name und Sprache. Die Sprache gilt für alles am
   Profil - Vorlagen, Aufnahmen, Training, Bewertung, Diktat - und lässt sich
   nicht wechseln ([Andere Sprachen](sprachen.md)). Dazu einen Zugang
   ausgeben; daraus wird ein Link, und der ist alles, was die Person braucht.
2. <a id="hilfe-textquelle"></a>**Textquelle wählen.** Ein Thema mit Altersspanne, aus dem ein LLM Text
   erzeugt; ein hochgeladener Text; oder ein Foto, das erkannt und geprüft wird.
   Herkunft und Parameter werden gespeichert.
3. **Schneiden.** `chunker.py` zerlegt den Text in Einheiten von grob 3–12
   Sekunden geschätzter Sprechdauer, an Satz- und Teilsatzgrenzen.
4. <a id="hilfe-aufnehmen"></a>**Aufnehmen.** Eine Einheit groß, davor und dahinter je eine blass.
   Aufnehmen, anhören, verwerfen, weiter. Die Stelle wird nicht gespeichert,
   sondern abgeleitet: offen ist jede Vorlage ohne gültige Aufnahme. Verwerfen
   macht sie wieder offen und löscht das Audio. Auf Wunsch in zufälliger
   Reihenfolge, fest je Sitzung.
5. **Prüfen.** Serverseitig Pegel, Clipping, Randstille und Dauer gegen die
   geschätzte Sprechdauer. Auffälliges wird angezeigt, nicht erzwungen - bei
   Sprechstörungen sind Ausreißer normal.
6. <a id="hilfe-fortschritt"></a>**Fortschritt.** Die Sprechzeit (`25 min 48 s`, `packages/ui/zeit.ts`)
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
**Aufnehmen** und **Fortschritt**, in der Reihenfolge der Arbeit. Rechts steht, wer angemeldet ist - der Name, den der Server zum Zugang
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

<a id="hilfe-zugangsdaten"></a>

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

<a id="hilfe-audio"></a>

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

<a id="hilfe-darstellung"></a>

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

<a id="hilfe-system"></a>

### System

Worauf wortlaut läuft und wie viel es gerade zu tun hat: oben die
Grafikkarte - läuft das Training noch, ist der Speicher voll, wird sie zu
heiß? -, darunter Prozessor, Arbeitsspeicher und Platten. Die Werte zeigen die
Maschine, nicht den Browser (`GET /api/system`, `wortlaut/systemlage.py`).
Gefragt wird einmal je Sekunde, fünf Minuten lang und nur, solange der Reiter
vorn liegt; ein Knopf fragt weiter.

### Hilfe

Rechts unter dem Menüknopf führt **Hilfe** an die Stelle dieses Handbuchs, die
die offene Ansicht beschreibt (`packages/ui/hilfe.ts`) - in einem neuen Reiter,
auf GitHub. Unter „Darstellung" lässt sie sich ausblenden wie ein Menüpunkt.

---

<a id="hilfe-zugang"></a>

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

<a id="hilfe-aufsicht"></a>

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
| eine Aufnahme | Audio und Zeile; die Einheit wird wieder offen | alles andere |
| alle Aufnahmen eines Sprechers | jedes Audio, jede Aufnahmezeile | Profil, Textquellen, Warteschlange |
| ein Sprecher | Korpus, Diktate, Modellstände, Laufverzeichnisse | nichts |

Eine Stufe „alle Sprecher" gibt es nicht. Die beiden
großen Stufen verlangen die Kennung ein zweites Mal (`?bestaetigung=…`); die
Oberfläche lässt dafür den Namen abschreiben. Was zu einer Person gehört,
steht an einer Stelle (`services/loeschung.py`), die auch
`scripts/purge_speaker.py` fragt.

---

<a id="hilfe-meine-daten"></a>

## Meine Daten

Dieselben Profildaten und Aufnahmen, die die Aufsicht sähe (`api/konto.py`),
für den Sprecher selbst - aus dem vorgelegten Zugang, ohne Kennung in der
Adresse. Die Textquellen stehen nur als Summe da (wie viele, wie viele
Einheiten, wie viele aktiv) mit einem Verweis auf den Reiter „Textquelle";
die Liste selbst führt nur er.

Die Sitzungen sind eine Zeile - wie viele, in welchem Zeitraum, mit wie
vielen Aufnahmen - und darunter ein Kalender (`packages/ui/Kalender.svelte`),
auf dem jeder Tag mit gültigen Aufnahmen markiert ist; die Zahl je Tag steht
im Tooltip. Je nach Breite zeigt er den laufenden Monat oder dazu den
vorigen, geblättert wird mit Pfeilen oder einem Wisch. Der Server liefert
dafür nur die Zeitpunkte (`GET /api/konto/aufnahmezeiten`); auf welchen Tag
eine Aufnahme fällt, rechnet der Browser in der Zeitzone des Betrachters.

Kurzes zuerst (Name, Kennzahlen, Ausleiten, PIN, Textquellen, Sitzungen),
die lange Liste der Aufnahmen danach.

Jede Aufnahme ist eine Karte (`packages/ui/Aufnahmekarte.svelte`, dieselbe
wie in der Auswertung von `lernen`): Text, Dauer, Modus, Tag, Hinweise. Ein
Klick oder Tippen irgendwo auf die Karte klappt sie auf, ein zweites klappt sie zu;
offen ist immer nur eine. Aufgeklappt stehen dort die Wellenform, der
Papierkorb und - nur wenn der Bearbeitungsschlüssel gilt - der Stift, der die
Aufnahme in **Editieren** öffnet. Die Wellenform ist dieselbe wie im Editor,
ohne Linien und Zahlen (`packages/ui/Abspieler.svelte`): Ein Tippen spielt,
ein zweites hält an, der Cursor läuft mit; das Audio lädt erst das erste
Tippen.

Rechts in der Kennzeile steht ein Ring mit der **Genauigkeit**, mit der das
Modell von „schreiben" die Aufnahme gehört hat (0 bis 100). Die Farbe läuft
von Rot über Orange, Gelb und Hellgrün nach Dunkelgrün, gemessen an den 10-
und 90-%-Quantilen dieses Sprechers; Rot liegt nie über 50, Dunkelgrün nie
unter 85 (`uebersicht.skala`). Ungemessene Aufnahmen tragen keinen Ring.
An seiner Stelle steht bei einer **editierten** Aufnahme grün und fett
„editiert": in „Editieren" gespeichert, und das Modell von „schreiben" hat
seitdem nicht auf ihr gelernt (`uebersicht.ist_editiert`). Lernt ein neuer
Stand auf ihr und wird er freigegeben, steht wieder der Ring.

Über der Liste klappt eine Zeile die **Wahl der Liste** auf, gemerkt im
Browser:

* **Sortieren** nach dem letzten Speichern in „Editieren" („Editiert",
  Vorgabe, neueste zuerst; nie editiert zählt das Datum der Aufnahme), nach
  dem Datum der Aufnahme oder nach der Genauigkeit - ungemessene zählen still
  als 0, editierte still als 100. Ein zweites Tippen auf die gewählte Sortierung kehrt
  die Richtung um (Pfeil).
* **Art** - überschneidungsfrei, jede Aufnahme gehört zu genau einer, und
  jede ist für sich an- und abwählbar, mit ihrer Zahl: gelesen,
  nachgesprochen, frei, Korrektur geprüft, Korrektur ungeprüft, verworfen.
  Verworfen ist eine Art für sich, gleich wie gesprochen wurde; eine gültige
  Korrektur aus „schreiben" zählt nach ihrer Prüfung, jede andere gültige
  Aufnahme nach ihrem Modus. Anfangs ist alles an außer „verworfen".
* **Quelle** - eine Textquelle oder alle.
* **Je Seite** 10, 20, 50 oder 100.

Der Editor blättert in dieser Reihenfolge, wie sie beim Öffnen galt
(`GET /api/konto/recordings/reihenfolge`); neu sortiert wird erst beim
Zurückkommen. Sortiert die Liste nach „Editiert" oder „Genauigkeit", geht sie
dann zur neuen Stelle der zuletzt bearbeiteten Aufnahme.

Gelöscht wird hier nur einzeln und nur die Aufnahme - Ton und Messwerte,
nach einer Rückfrage mit Warnzeichen. Der Text bleibt und steht wieder zum
Aufnehmen an (dasselbe Verwerfen wie beim Aufnehmen, `DELETE
/api/recordings/{id}`). `schreiben` verlinkt auf dieselbe Seite.

Jede Rückfrage vor dem Löschen - hier wie in **Editieren** - nennt in kurzen
Worten, was gelöscht wird.

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

<a id="hilfe-editieren"></a>

## Editieren - kürzen, teilen, berichtigen

Eine Aufnahme allein, erreichbar über den Stift an einer aufgeklappten Karte
in „Meine Daten" (`#/editieren/<id>`): der Lautstärkeverlauf mit zwei Linien
für Anfang und Ende, darunter ihr Text zum Mitlesen und ein Feld, in dem er
berichtigt wird. Verschoben wird mit Finger, Maus oder Pfeiltasten. Beim
Abspielen läuft ein Cursor mit; die Leertaste (außerhalb der Eingabefelder)
oder ein Tippen auf die Kurve startet und stoppt, was zwischen den Linien
liegt.

**Beim Öffnen ist nichts geändert.** Die Linien stehen ganz außen, Teilen ist
aus, „Speichern" gesperrt, und es gibt einen Knopf zum Hören. Jede Änderung
schaltet „Speichern" frei; sein Tooltip und die Rückfrage sagen, was sich
ändert - gekürzt, geteilt, Text geändert, bei einer ungeprüften Korrektur
dazu: als geprüft übernommen. Sind die Linien verschoben, kommt ein Knopf für
den Ausschnitt dazu. Über der Kurve stehen Art (gelesen, nachgesprochen, …),
Datum der Aufnahme und des letzten Speicherns, die Dauer und rechts wie in
„Meine Daten" der Ring der Genauigkeit oder die Marke „editiert".

**Zurück nach „Meine Daten"** steht die Seite, wie sie war: dieselbe Seite der
Liste, dieselbe Karte offen, dieselbe Stelle im Fenster. Wer mit
ungespeicherten Änderungen geht - über „Abbrechen", einen Reiter oder den
Zurück-Knopf -, wird gefragt.

### Auto - die Grenzen der Stimme

Zwischen Knopfdruck und erstem Laut liegt oft eine Sekunde, am Ende mehr. Über
anderthalb Stunden Korpus summiert sich das zu einer halben Stunde, die
mittrainiert und mitgemessen wird.

„Auto" setzt Anfang und Ende dorthin, wo der Pegel die Stimme vermutet
(`wortlaut/audio.stimmgrenzen`). Dieselbe Rechnung meldet beim Hochladen die
Randstille (`services/quality.py`) - der Editor bietet keine Grenze an, die die
Prüfung danach als Stille meldet:

* RMS in 20-ms-Fenstern;
* die Schwelle liegt in dB in der Mitte zwischen dem Rauschboden der Datei -
  dem Median der leisesten 10 % der Fenster - und ihrem lautesten Fenster.
  Nicht feste dBFS: Die Verstärkung beim Aufnehmen (bis 20×) verschiebt
  Stimme und Raum gleichermaßen. Mindestens 8 dB über dem Boden, damit
  Rauschen bei schlechtem Abstand nicht als Stimme zählt, und mindestens
  6 dB unter dem lautesten Fenster, damit eine Aufnahme ohne Pause nicht als
  Stille gilt;
* Luft nach außen: 150 ms vor dem ersten, 200 ms nach dem letzten lauten
  Fenster, an den Dateigrenzen gestutzt. Lieber zu viel Rand als zu wenig -
  bei Dysarthrie sind leise An- und Auslaute häufig.

Die Werte stehen als Konstanten am Kopf von „Wo die Stimme ist" in
`wortlaut/audio.py`.

**Kein VAD.** Ein Raum, ein Mikrofon vor dem Mund, eine Äußerung - was laut
wird, ist diese Person. Ein Sprachmodell zu fragen, wo abweichende Sprache
anfängt, träfe dieselbe Annahme, an der die Diktierfunktion des Telefons
scheitert; und über dem Vorschlag sitzt ohnehin ein Mensch.

### Split - in zwei Aufnahmen

„Split" ist ein Schalter. Gedrückt steht eine dritte, gestrichelte Linie in
der längsten Pause der mittleren Hälfte; es gibt drei Knöpfe zum Hören (ganz,
A, B), der Text bekommt anklickbare Lücken, und das Feld wird zu zweien. Die
Textteilung folgt der Linie an der passendsten Wortgrenze, bis jemand eine
Lücke anklickt; die Felder folgen der Textteilung, bis jemand darin schreibt.
Wieder gelöst, verschmelzen beide Felder zu einem - was darin geändert wurde,
bleibt.

### Speichern

**Bis zum Speichern hat nichts eine Folge**; abgespielt wird aus der geladenen
Datei, ohne vorläufige Dateien auf dem Server. Gespeichert wird in einem
Schritt (`POST /api/zuschnitt/speichern`), nach einer Rückfrage mit
Warnzeichen - rückgängig machen lässt es sich nicht. Danach lässt sich nur
weiter kürzen, teilen und berichtigen, nicht verlängern.

**Der Text steht an der Aufnahme** (`recordings.text`), die Vorlage bleibt
unberührt. Bei einer Korrektur aus „schreiben" steht in der Vorlage damit
weiter, was das Modell schrieb, an der Aufnahme, was wirklich gesagt wurde.
Wo `recordings.text` leer ist, gilt der Text der Vorlage (`Aufnahme.text_zu`) -
für Anzeige, Datensatz, Auswertung und Trainingsmanifest.

**Gespeichert heißt editiert und geprüft.** Jede gespeicherte Aufnahme trägt
das Datum (`recordings.geaendert`) und gilt als geprüft
(`recordings.validiert`) - gleich, ob sie gelesen, nachgesprochen oder aus
„schreiben" kam; eine Korrektur auch mit unverändertem Text. Eine geprüfte
Korrektur zählt in Training und Messung wie eine Vorlage. Beim Sortieren nach
Genauigkeit zählt eine editierte Aufnahme still als 100
(`uebersicht.EDITIERT_QUALITAET`) - ein Mensch hat sie gehört und berichtigt;
angezeigt wird statt einer Zahl die Marke „editiert".

Ohne Split:

1. Die Datei wird verlustfrei auf Anfang und Ende gekürzt und ersetzt das
   Original.
2. Dauer, Pegel, Stille und Hinweise der Zeile kommen aus der neuen Datei.
3. Ändern sich Ton oder Text, werden die Messwerte der Aufnahme gelöscht,
   übernommene Faltungen eingeschlossen; der nächste Auswertungslauf rechnet
   neu. Blieb der Ton, kommt eine Faltung beim nächsten Abgleich wieder,
   gemessen am neuen Text (siehe „Die eigenen Stände treten mit an").

Danach steht die neue Fassung im Editor, die Linien wieder außen.

Mit Split entstehen zwei neue Aufnahmen mit eigener Datei und eigenem Text,
**an derselben Vorlage**; Byte für Byte ergeben sie den Bereich des Originals.
Das Original geht ganz: Zeile, Datei, Messwerte. Die Vorlage bleibt - ihre
gültigen Aufnahmen sind jetzt die Teile, sie steht nicht wieder in der
Warteschlange und zählt im Fortschritt nicht als offen. Die Teile tragen das
Datum des Originals und einen Sortierschlüssel (`<id>.1`, `<id>.2`), der sie
an seiner Stelle hält und über den Stamm in seiner Faltung (`zuschnitt.stamm`).
Danach geht es zurück nach „Meine Daten".

**Jeder Teil trägt seine Vorfahren** (`recordings.vorfahren`): die Kennung
des Originals, und wird ein Teil wieder geteilt, auch seine - über alle
Generationen. Ein Stand, der einen Vorfahren im Training hatte, wird an
keinem Nachfahren gemessen, auch wenn alle Vorfahren gelöscht sind
(`auswertung.verwandte`). Teile desselben Originals untereinander sperren
sich nicht; sie sind verschiedener Ton.

Bei 16 kHz mono PCM ist ein Rahmen zwei Byte, geschnitten wird auf ganze
Rahmen, nach außen gerundet, ohne Blenden.

**Das Audio hängt an seinem Stand.** Ein Schnitt überschreibt die Datei unter
demselben Pfad; der Editor holt sie mit ihrer Version in der Adresse
(`?v=`), und jeder Weg zum Audio antwortet mit `no-cache` - der Browser fragt
mit dem ETag nach, statt die alte Fassung zu spielen.

Ältere Bestände können geteilte Originale noch neben ihren Teilen führen;
`scripts/alte_originale.py` zeigt sie und nimmt sie mit `--loeschen` heraus.
Die Teile gelten danach als Originale.

### Der Schlüssel

Vor allen Wegen unter `/api/zuschnitt/…` steht zusätzlich
`WORTLAUT_EDITOR_KEY` (`X-Editor-Key`), auch vor den lesenden: Speichern
ersetzt Aufnahmen. Eingetragen wird er unter „Zugangsdaten"; ob er gilt,
sagt `GET /api/zugang` (`bearbeiten`). Nur dann steht der Stift an den
Aufnahmen in „Meine Daten". Leer heißt abgeschaltet.

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
GET    /api/recordings/{id}/audio           die eigene Aufnahme
GET    /api/recordings/{id}/verlauf         ihr Lautstärkeverlauf - die Wellenform zum Anhören
DELETE /api/recordings/{id}
GET    /api/progress
POST   /api/korpus/intake                   ← von „schreiben"
GET    /api/konto                           Profil, Kennzahlen, Textquellen    + X-Pin
GET    /api/konto/recordings?ab=&anzahl=&sortierung=&richtung=&quelle=&arten=  + X-Pin
GET    /api/konto/recordings/reihenfolge    Kennungen in derselben Wahl - für den Editor + X-Pin
GET    /api/konto/aufnahmezeiten            Zeitpunkte gültiger Aufnahmen      + X-Pin
PATCH  /api/konto                           { name } - umbenennen                   + X-Pin
GET    /api/konto/sicherung                 .tgz des eigenen Stands                 + X-Pin
GET    /api/konto/datensatz                 .zip der eigenen Paare                  + X-Pin
GET    /api/konto/pin                       { gesetzt }
GET    /api/konto/pin/pruefung              204, wenn die vorgelegte PIN stimmt
PATCH  /api/konto/pin                       { pin } - vier Ziffern oder null
GET    /api/auswertung                      Kurve und Stand - ohne Texte (Ansicht in „lernen")
GET    /api/auswertung/{aufnahme}           Vorlage, der erkannte Text je Modell und die Karte
POST   /api/auswertung/start
POST   /api/auswertung/stopp                Gerechnetes bleibt
```

Zuschnitt - zusätzlich `X-Editor-Key`:

```
GET    /api/zuschnitt/aufnahmen/{id}        Kurve und Vorschlag einer Aufnahme
GET    /api/zuschnitt/aufnahmen/{id}/original
POST   /api/zuschnitt/speichern             { id, start_s, ende_s, teilung_s | null, texte } → { ids }
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
GET    /api/fehlerlog                       die letzten sieben Tage - Verwaltung, Aufsicht
                                            oder X-Trainer-Key
GET    /gesundheit
```

Die interaktive Dokumentation liegt unter `/docs`.
