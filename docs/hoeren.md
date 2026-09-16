# App „hören" - Sprachproben sammeln

Der Einstieg und der Ort, an dem der Korpus entsteht: Textquelle wählen,
äußerungsweise aufnehmen, den Fortschritt sehen - und am Ende messen, was die
unveränderten Modelle daraus machen.

Der Entwurf dahinter steht in [Der Entwurf](architektur.md); die beiden
anderen Apps in [lernen](lernen.md) und [schreiben](schreiben.md).

Die **Grundentscheidungen**, auf die hier verwiesen wird, stehen
[dort](architektur.md#grundentscheidungen).

---

## Ablauf

1. **Sprecherprofil** anlegen: Name und Sprache. Sonst nichts. Die
   Sprache gilt danach für alles, was am Profil hängt - Vorlagen, Aufnahmen,
   Feintuning, Bewertung, Diktat - und lässt sich nicht mehr wechseln; wer
   wortlaut in zwei Sprachen braucht, bekommt zwei Profile
   ([Andere Sprachen](sprachen.md)). Dazu
   einen Zugang ausgeben - daraus wird ein Link, und der ist alles, was die
   Person je braucht (siehe [Der Zugang ist die Kennung](#der-zugang-ist-die-kennung)).
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
6. **Fortschritt.** Gesammelte Sprechzeit gegen zwei Marken: ab etwa 1,5 Stunden
   wird ein Modell brauchbar, ab etwa 20 Stunden gut. Danach flacht der Gewinn
   ab. Neben jeder Marke steht, was noch fehlt - das ist die Frage, mit der
   jemand auf diese Seite kommt.

   Angezeigt wird das als Stunden, Minuten und Sekunden („25 min 48 s") und
   nicht als Dezimalstunden. Hier stand einmal „0,43 Stunden": richtig
   gerechnet und für die Zielperson keine Auskunft - niemand weiß aus dem
   Stand, wie viele Minuten das sind. Gerechnet wird es in `packages/ui/zeit.ts`,
   damit dieselbe Sprechzeit in „Meine Daten" und in der Sprecherliste der
   Verwaltung genauso dasteht.

---

## Vorsprechen statt Vorlesen

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
verbessern. Wege zu einer besseren Stimme stehen in [`betrieb.md`](betrieb.md).

---

## Menüführung

Die Kopfzeile hat zwei Reihen, weil es zwei Ebenen gibt. Oben die drei Apps -
`hören`, `lernen`, `schreiben` -, die offene dunkelgrün hinterlegt. Darunter
die Ansichten der offenen App, die aktuelle hell hinterlegt; in `hören` sind
das **Textquelle**, **Aufnehmen**, **Fortschritt** und **Auswertung**, in
dieser Reihenfolge, denn sie ist der Weg durch die Arbeit. Beides steht in
`packages/ui/Kopfleiste.svelte` - deshalb hat `schreiben` dieselbe Leiste
bekommen, ohne ein eigenes Menü zu erfinden. Am rechten Rand der oberen Reihe
steht, wer gerade angemeldet ist.

Die **Auswertung** stand lange im Menü, mit der Begründung, Auswerten sei ein
Nachsehen und Aufnehmen eine Tätigkeit. Das stimmt nicht: Sie ist der Schritt,
der aus dem Korpus Zahlen macht, und ohne ihn bleibt die Modellübersicht in
`lernen` leer. Sie gehört damit in dieselbe Reihe, ans Ende.

Marke, App-Reiter, Sprecherzeile und Menüknopf gibt es genau einmal, und keine
App baut sie sich selbst zusammen: `packages/ui/Rahmen.svelte` klammert
Kopfzeile, Inhalt und Fußzeile und beantwortet die gerätebezogenen Menüpunkte
gleich mit. Eine App liefert nur ihre eigenen Ansichten und, was sie darüber
hinaus ins Menü stellt - `hören` den Sprecher (oder, sobald einer spricht,
**Meine Daten**) und die Zugangsdaten, `schreiben` dasselbe als Verweis und
ebenfalls die Zugangsdaten. Was im Menü steht, ist damit eine Liste
(`GERAETE_PUNKTE` in `apps.ts` und der Durchreichung der App) und keine Folge
fester Zeilen mit Schaltern davor; ein neuer gerätebezogener Punkt ist ein
Eintrag und eine Zeile im Rahmen, statt einer Änderung in jeder App. Weil es
eine Liste ist, lässt sie sich auch kürzen: Welche Apps, welche Ansichten und
welche Menüpunkte tatsächlich dastehen, schaltet **Darstellung** ein und aus
(siehe dort).

**Die App öffnet dort, wo zuletzt gearbeitet wurde.** Steht in der Adresse
keine Route - die App vom Startbildschirm des Telefons geöffnet, aus einem
alten Lesezeichen, nach einem Neustart des Browsers -, gilt der Reiter, auf dem
dieser Browser zuletzt war (`packages/ui/reiter.ts`, `wortlaut.reiter.<app>`).
Wer eine Woche lang aufnimmt, sieht „Aufnehmen" und nicht jeden Tag wieder
„Textquelle"; wer ein Training beaufsichtigt, sieht „Training" und nicht die
Aufteilung.

Gemerkt, nicht angesprungen: Die Adresse bleibt leer und der Reiter ist nur die
Vorgabe dafür. Ein Sprung schriebe den Hash in den Verlauf, und der
Zurück-Knopf führte dann auf eine Seite, die niemand angesteuert hat. Ein
ausgeblendeter Reiter zählt dabei nicht - sonst sähe es aus, als hätte der
Schalter unter **Darstellung** nichts getan.

**Was eine Reiterreihe trägt, steht nicht zusätzlich im Menü.** „Auswertung"
und „Modelle" standen eine Zeitlang beides - hier als Reiter, drüben als
Menüpunkt mit voller Adresse. Bequem war das nicht, sondern eine Stelle, an der
jemand zweimal sucht. Der Weg zwischen den Apps ist der App-Reiter in der
oberen Reihe; wer aus `schreiben` zu den Modellen will, klickt die Modellzeile
unter dem Aufnahmeknopf an.

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
Wurzel, `lernen` unter `/lernen/`, `schreiben` unter `/schreiben/`; welcher
Pfad zu welcher App gehört, steht in `packages/ui/apps.ts`.

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
`apps/` und gibt dem Proxy je eine Regel - am Code ändert das nichts.

Wer mit dem Verwaltertoken hier ist, sieht keine zweite Reihe: Es gibt für ihn
nur die eine Seite, auf der Profile angelegt und Zugänge ausgegeben werden.
Jede Aufnahmeansicht bräuchte einen Sprecher, und den hat er nicht - er hat
einen Verwaltertoken. In der Kopfzeile steht dann „Verwaltung" statt eines
Namens, damit die fehlende Reiterreihe nicht wie ein Fehler aussieht.

---

## Audio

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

### Mikrofon

Der Mikrofontest zeigt den Pegel live, gegen dieselben Grenzen, die der Server nach
dem Absenden prüft (`services/quality.py`) - was im Test „guter Pegel" ist, gibt
später keinen Hinweis. Dazu die Wahl unter den vorhandenen Geräten und eine Probe
zum Anhören.

Zu leise Eingänge lassen sich auf zwei Arten heben, und die beiden tun
Verschiedenes:

- **Verstärkung** ist ein fester Faktor (1–20×) vor der Aufzeichnung. Er behebt ein
  Mikrofon, das durchweg zu leise ist - unter Linux der Normalfall bei eingebauten
  Mikrofonen, siehe [`betrieb.md`](betrieb.md). **Automatisch einmessen** hört fünf Sekunden
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

### Darstellung - und was in der Leiste überhaupt dasteht

Unter `#/darstellung` liegen Farben, Schriftart und die beiden Schriftgrößen,
je mit Probe - ein eigener Menüpunkt neben „Audio", weil es ein
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

Darunter steht, was von der Oberfläche überhaupt sichtbar ist: Listen mit je
einem Schalter rechts, und sie folgen dem Aufbau der Kopfleiste - zuerst die
drei Apps, dann je App ihre **Ansichten** (die zweite Reihe: Textquelle,
Aufnehmen, Fortschritt, Auswertung in `hören`; Aufteilung, Training, Modelle in
`lernen`), zuletzt die Punkte im Menüknopf. Der Anlass ist Grundentscheidung 7 -
jeder Reiter, den dieser Mensch nie braucht, ist eine Gelegenheit, sich zu
verlaufen. Wer nur diktiert, blendet `hören` und die Verwaltungspunkte aus; wer
nur aufnimmt, räumt `schreiben` weg und lässt in `lernen` nur die Modelle
stehen.

`schreiben` fehlt in den Ansichtslisten, und das ist kein Versehen: Die App hat
keine Reiterreihe. Ihr Weg ist eine Folge - sprechen, hören, bessern,
bestätigen - und keine Auswahl.

Zwei Punkte bleiben und haben einen festen, nicht bedienbaren Schalter, damit
niemand sich selbst aussperrt: **Darstellung**, weil dort diese Schalter
liegen, und **Meine Daten**, weil dort die PIN vergeben wird, die inzwischen
vor Darstellung und Zugangsdaten steht. Alles andere ist abschaltbar, die
Zugangsdaten und jede einzelne Ansicht eingeschlossen: Bleibt von einer
Reiterreihe nichts übrig, entfällt sie, und die App zeigt weiterhin ihre erste
Ansicht. Wer über ein Lesezeichen auf einer ausgeblendeten Ansicht landet,
bekommt in der Kopfleiste den Rückweg ins Menü.

Ausgeblendet heißt dabei **unsichtbar, nicht abgeschaltet**: Die Route bleibt,
was sie war, ein Lesezeichen führt weiterhin hin, und der Server prüft
unverändert Zugang und PIN. Die Schalter räumen die Leiste auf, sie sind kein
Rechtemodell - das sind der Zugang (`packages/ui/zugang.ts`) und die PIN. Der
Rückweg ist doppelt gesichert: **Auf Vorgaben zurücksetzen** holt neben Farbe
und Schrift auch jeden ausgeblendeten Punkt zurück.

Gespeichert wird wie Farbe und Schrift im `localStorage` dieses Browsers
(`wortlaut.sichtbar.app.<app>`, `wortlaut.sichtbar.reiter.<app>.<pfad>`,
`wortlaut.sichtbar.menue.<pfad>`) und gilt
damit in allen Apps darin. Fehlt ein Eintrag, ist der Punkt sichtbar: Nur ein
ausdrückliches `false` blendet aus, sonst stünde nach dem ersten Start eine
leere Leiste da.

---

## Der Zugang ist die Kennung

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

---

## Die Aufsicht - der eine Zugang über allen Korpora

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

### Zwei Formate, zwei Fragen

Ausgeleitet wird in zwei Formaten, weil zwei verschiedene Fragen dahinterstehen.

Die **Sicherung** (`.tgz`) beantwortet „Der Server ist weg, ich will den Stand
zurück." Sie enthält die Dateien, wie sie unter `WORTLAUT_DATA_DIR` liegen -
Datenbanken und Aufnahmen -, und ihr Inneres bildet das Datenverzeichnis ab:

```
wortlaut-gesamt-20260822-174500.tgz
├── sicherung.json               Zeitpunkt, Sprecher, Ausgelassenes, je Datei Größe und SHA-256
└── daten/
    ├── korpus/spr_…/hoeren.sqlite
    ├── korpus/spr_…/audio/rec_….wav
    └── diktate/spr_…/…               Arbeitsstand von „schreiben"
```

Das ist der ganze Trick der Wiederherstellung: Sie ist ein Auspacken an die
richtige Stelle, kein Einspielen. `scripts/restore.py` nimmt einem die
Prüfungen ab, aber `tar xzf` käme genauso weit - eine Sicherung, die ein
laufendes Programm zum Lesen braucht, ist im Ernstfall keine.

**Was nicht darin liegt, und warum nicht.** Gesichert wird, was ein Mensch
hervorgebracht hat: die Aufnahmen, die Vorlagen, die Textquellen, die Diktate,
das Profil, die Zugänge. Was eine Maschine daraus gerechnet hat, bleibt
draußen - es ist aus eben diesen Daten wiederherstellbar, und zwar ohne dass
jemand etwas dafür tun müsste:

| | Größe | Kommt zurück durch |
|---|---|---|
| Modellstände `modelle/` | ~1 GB je Stand | einen Trainingslauf |
| Schnappschüsse `snapshots/` | je Lauf ein Verzeichnis | einen Trainingslauf |
| abgewandelte Fassungen `audio/varianten/` | drei Viertel des Audios | den nächsten Auswertungslauf, dateiweise in Millisekunden |
| Messwerte, Tabelle `erkennungen` | wächst mit jedem Modell | denselben Lauf; er rechnet ohnehin nur, was fehlt |

Die ersten beiden waren nie darin. Die anderen beiden sind es seit Kurzem
nicht mehr: Ein Archiv, das dreimal so viel gerechnetes Audio trägt wie
gesprochenes, trägt man seltener weg - und eine Sicherung, die man seltener
zieht, ist die eigentliche Gefahr. Die Datenbank kommt dabei **vollständig**
mit; geleert wird in der Sicherungskopie nur diese eine Tabelle, und auch das
schreibt `sicherung.json` unter `ausgelassen` hin, damit niemand das Fehlende
für einen Schaden hält.

Hier stand einmal eine Ausnahme: die Aufteilung in Lernen und Prüfen
(`lernen/spr_…/lernen.sqlite`). Sie musste mit, weil sie sich nicht neu rechnen
ließ, sondern nur neu erfinden - und eine andere Aufteilung hätte jeden
Vergleich mit früheren Läufen entwertet. Seit September 2026 gibt es sie nicht
mehr: „lernen“ hat keine eigene Datenbank, und die Faltungen der
Kreuzvalidierung folgen der Reihenfolge des Korpus (siehe
[lernen](lernen.md)). Was aus einer Sicherung zurückkommt, ergibt damit
dieselben Faltungen wie vorher.

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

### Löschen: drei Stufen, und die vierte gibt es nicht

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

### Meine Daten - dieselbe Ansicht, für sich selbst

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

**Kurzes zuerst, Langes ans Ende.** Beide Ansichten - diese und die Einsicht
der Aufsicht - sind gleich sortiert: Name mit dem Knopf zum Umbenennen, die
Kennzahlen, das Ausleiten, die PIN. Erst danach die Listen, die über Seiten
laufen: Textquellen, Sitzungen, Aufnahmen. Was man einmal einstellt, stünde
sonst hinter einem Korpus, dessen Länge niemand vorhersagt. Nur das **Löschen**
steht in der Einsicht bewusst dahinter und ganz unten: Dort ist der weite Weg
der Schutz, und die langen Listen sind es, die ihn weit machen.

#### Eine Vorlage darf auch ein Foto sein

Nicht jeder Text liegt als Datei vor. Ein Zeitungsausschnitt, eine Buchseite,
ein Brief - wer so etwas vorlesen will, fotografiert ihn, und genau das ist der
Weg, der ohne Tastatur auskommt (Grundentscheidung 7). Dasselbe gilt für ein
eingescanntes PDF: eines ohne Textebene ist ein Bild in einem PDF-Umschlag.

Gelesen wird auf dieser Maschine, mit Tesseract (`wortlaut/text/ocr.py`), aus
demselben Grund, aus dem auch Whisper hier läuft: Es verlässt nichts den Server
([Datenschutz](datenschutz.md)). Ein fotografierter Brief ist womöglich das
Persönlichste, was diese App je zu sehen bekommt.

**Der Prüfschritt ist der Punkt.** Was aus einem Foto kommt, ist geraten und
nicht gelesen - eine Zeichenerkennung verwechselt `rn` mit `m` und erfindet an
Knicken Zeichen. Ginge das unmittelbar in den Korpus, wanderte der Fehler in
die Vorlage, von dort in die Aufnahme (der Mensch spricht ja nach, was
dasteht) und von dort ins Training, wo er als Abweichung des *Sprechers*
gezählt würde. Deshalb gibt `POST /api/sources/erkennen` den Text nur zurück;
angelegt wird er erst durch `POST /api/sources/text`, nachdem ein Mensch ihn
gesehen und gebessert hat. Die Oberfläche sagt dazu, ob er `gelesen` oder
`erkannt` wurde - Gelesenes stimmt, Erkanntes ist ein Vorschlag.

PDFs nehmen denselben Umweg, auch wenn sie eine Textebene tragen: Kopfzeilen,
Fußnoten und Seitenzahlen will niemand vorlesen, und wer sie sieht, streicht
sie weg. `txt`, `md`, `epub` und `docx` gehen weiterhin unmittelbar durch -
dort steht der Text schon so da, wie ihn jemand geschrieben hat.

**Unmittelbar aus der Kamera** geht es über das Kamerasymbol neben
„Hochladen": `capture` sagt dem Telefon, dass hier nicht aus der Mediathek
gewählt, sondern aufgenommen werden soll, und Safari öffnet die Kamera-App.
Aufgenommen wird sofort gelesen - wer den Auslöser gedrückt und das Bild
bestätigt hat, hat zweimal ja gesagt; ein drittes „Hochladen" wäre ein Knopf
ohne Frage dahinter.

Kein eigener Sucher über `getUserMedia`: Der müsste Freigabe, Auslöser und das
Abschalten der Kamera selbst mitbringen, und die Kamera-App des Telefons kann
das alles längst besser - sie richtet scharf, hält ruhig, zeigt einen Rahmen,
und die Zielperson kennt sie. Ein selbstgebauter Sucher wäre ein zweiter,
schlechterer.

**Aus der Zwischenablage** geht beides: ein Bild, das dann erkannt wird, und
ein Schnipsel Text, der gleich im Prüffeld landet. Über das `paste`-Ereignis
und nicht über `navigator.clipboard.read()` - Letzteres fragt in Safari jedes
Mal um Erlaubnis und gibt in Firefox keine Bilder heraus, während Einfügen
überall dieselbe Handbewegung ist.

**Zwei vorsichtige Filter, und beide sind gemessen.**

*Auf dem Bild:* Die lange Seite wird auf 2400 Pixel begrenzt und eine
entrauschte Fassung danebengestellt (3×3-Median). Beide gehen in drei
Seitenarten durch Tesseract - Seite, zusammenhängender Block, verstreuter
Text -, der beste der sechs Durchgänge gilt - gewertet
wird, wie viele Zeichen in Wörtern aus mindestens drei Zeichen stehen.

Die Begrenzung ist keine Sparsamkeit, sondern eine Messung: Am Foto eines
Cremedeckels brachten 1200 px 96 Punkte, 2000 px 118, 2576 px 119 und 3200 px
nur noch 114 - bei doppelter Zeit. Ein iPhone-Foto hat 4032 Pixel; ohne die
Grenze dauerten vier Durchgänge 22 Sekunden statt 7, bei gleichem Ergebnis.

Der Median ist der Unterschied zwischen lesbar und gar nichts, sobald jemand
einen **Bildschirm** abfotografiert: Dessen Bildpunktgitter legt sich als
feines Muster über die Schrift (Moiré). Nachgemessen an einem nachgestellten
Bildschirmfoto - **0 Punkte** im Rohbild, der volle Satz nach dem Filter.

*Auf dem Text:* Zwei Regeln, und sie fangen Verschiedenes.

Zeilen, in denen **mehrheitlich Bruchstücke** stehen, fallen weg. Eine
Zeichenerkennung findet auf einem Foto auch dort Schrift, wo Muster sind - der
Wirbel auf einem Cremedeckel wird zu `| x`, `Ye`, `v,`, `ae`. Die Grenze liegt
bei drei Zeichen am Stück und zählt Ziffern mit, damit `48h` und `10/2024`
bleiben. Und mindestens die Hälfte der Brocken einer Zeile muss ein Wort
sein: `k Be #2 I CFrAN` hat eines von fünfen und geht, `Bio-Jojobaöl &` eines
von zweien und bleibt.

Dagegen hilft keine Länge, wenn eine Zeile durchweg wie Wörter aussieht und
trotzdem keine sind - ein **Unterstrich** unter einer Überschrift ist ein
Balken, den Tesseract als Wort lesen muss. So entstand unter „Birchermüsli zum
Frühstück?" die Zeile „a nee heneibneeneschebeißsi". Was fehlt, ist nicht die
Länge, sondern die Sicherheit, und die sagt Tesseract selbst: Gelesen wird
deshalb über `image_to_data`, und eine Zeile unter einer mittleren Zuversicht
von 15 fällt weg. Gemessen an zwei Vorlagen - die Rauschzeile kam auf 6,5, der
echte Text des Plakats ab 75, der des schweren Fotos ab 28. Die Grenze liegt in
dieser Lücke, mit Abstand nach beiden Seiten.

**Für kurze Zeilen gilt eine zweite, viel strengere Grenze.** Ein Foto einer
Stofffläche oder einer genarbten Kunststoffschale liefert
Dreibuchstabenwörter am laufenden Band - `Res`, `RER`, `ber`, `Ser`, `ale`,
`STE`. Sie sind lang genug für den Längenfilter und sicher genug für die 15;
an einem Akku auf einer Hose kamen sie auf bis zu 43.

Die eine Grenze anzuheben ging nicht: `OKO-TEST` steht wirklich auf dem
Cremedeckel und kommt dort auf 28. Was beides trennt, ist die Sicherheit
**zusammen mit der Länge** - wer acht Formen hintereinander zu einem Wort
zusammensetzt, hat etwas gesehen, auch wenn er zögert; drei zufällig passende
Formen findet man in jeder Struktur.

| längstes Wort | Rauschen bis | Echtes ab | Grenze |
|---|---|---|---|
| bis 5 Zeichen | 43 | 74 | **60** |
| ab 6 Zeichen | 6 | 2 | **15** |

Von dem Akkufoto bleibt damit genau eine Zeile: `BOSCH`. Cremedeckel und
Aushang bleiben unverändert.

Das ist die richtige Richtung: Was stehen bleibt, streicht ein Mensch im
nächsten Schritt - was verschwindet, sieht er nie wieder. Gefiltert wird **nur
Erkanntes**, nie ein gelesener oder eingefügter Text.

*Bei einem PDF nichts von alldem.* Ein Scan ist eine Seite Fließtext, flach
ausgeleuchtet und ohne Moiré - genau der Fall, für den Tesseracts Vorgabe
gemacht ist. Ein Bild ist eines, ein PDF sind bis zu zwanzig, und vier
Durchgänge je Seite wären achtzig. Wessen Scan schlecht liest, fotografiert
die Seite; dann greift der andere Weg mit allem, was er hat.

**Erkannt wird in der Sprache des Profils**, und das ist kein Beiwerk. Am
zweisprachigen Aushang gemessen, derselbe Aufnahme, nur ein anderes Wörterbuch:

| Profilsprache | deutsche Zeilen | englische Zeilen | Umlaute/ß |
|---|---|---|---|
| `de` → `deu` | 6 von 6 | 6 von 6 | 8 |
| `en` → `eng` | 3 von 6 | 5 von 6 | **0** |

Mit dem englischen Wörterbuch wird aus „Birchermüsli zum Frühstück?" ein
„Birchermiisli zum Frihstiick?" und aus „Möchtest du eins?" ein „Mdchtest du
eins?": Die Umlaute fallen nicht falsch aus, sie kommen gar nicht vor - das
Modell kennt sie nicht. Bemerkenswert ist die Gegenrichtung: Das **deutsche**
Modell liest den englischen Teil des Aushangs fehlerfrei mit, das englische den
deutschen nicht. Wer also nur eine Sprache wählen kann, wählt die mit den
Sonderzeichen.

Die Sprache erreicht dabei **jeden** Aufruf, auch die Lageprobe. Die lief
einmal fest auf `deu`, während die eigentliche Lesung dem Profil folgte - bei
einer Sprache fällt das nicht auf, bei der zweiten wäre es ein Fehler gewesen,
den niemand sieht: Die Probe misst, ob Tesseract *Wörter* erkennt, und was ein
Wort ist, hängt am Wörterbuch. Ein Test hält das fest.

**Wo die Grenze liegt: schräg fotografiert.** Gemessen an einem Aushang, der
um verschiedene Winkel gedreht wurde - verglichen wird die Ähnlichkeit zum
Ergebnis derselben Aufnahme, gerade gehalten:

| Schräglage | 0° | 2° | 4° | 6° | 10° | 15° |
|---|---|---|---|---|---|---|
| Ähnlichkeit | 100 % | 87 % | 47 % | 35 % | 23 % | 17 % |

Bis etwa zwei Grad trägt Tesseracts eigene Zeilenausrichtung, ab vier bricht es
ein. **Eine Drehungsprobe wie bei den vier Lagen hilft hier nicht**, und das
ist gemessen, nicht vermutet: Bei 90-Grad-Schritten liegt die richtige Lage um
das Vierfache vorn, bei Winkeln zwischen vier und acht Grad liegen alle
Kandidaten innerhalb von fünf Prozent - die Probe rät dann. Sie würde drei
Sekunden je Bild kosten und im Alltagsfall beliebig drehen.

Noch weniger hilft sie bei einem **schräg von der Seite** fotografierten
Bildschirm oder Plakat. Dort laufen die Zeilen nicht nur schief, sondern
zusammen: Das Rechteck ist im Bild ein Trapez, und keine Drehung macht daraus
wieder ein Rechteck. Das ginge nur mit einer Entzerrung über die vier Ecken -
ein eigenes Vorhaben mit einer neuen Abhängigkeit, das an einem Foto, auf dem
eine Ecke fehlt, ohnehin scheitert.

Der praktische Rat steht deshalb in der Oberfläche besser als jede Rechnung:
möglichst parallel zur Vorlage halten. Bis drei Grad merkt man nichts.

**Und für den Rest: das Gerät kann es besser.** Apples Texterkennung („Live
Text") liest auch schräg fotografierte Folien, bei denen die Zeilen
zusammenlaufen - genau der Fall, an dem Tesseract scheitert. Programmatisch
kommt eine Webseite nicht heran: `TextDetector` aus der Shape-Detection-API ist
ausdrücklich **nicht** standardisiert („not stable enough across computing
platforms or character sets"), Safari liefert ihn nicht, und was dort an
Shape Detection existiert, ist seit iOS 18 defekt.

Der Mensch kommt aber heran. Safari bietet Live Text auf **jedem angezeigten
Bild** an. Deshalb steht die Vorlage im Prüfschritt neben dem Text: Sie dient
erstens dem Vergleich - wer Erkanntes bessern soll, braucht das Original
daneben und nicht in einer anderen App - und zweitens als Angriffspunkt. Ein
langer Druck aufs Bild, auswählen, kopieren, ins Feld darunter einfügen; der
eingefügte Text geht dann als `eingefügt` durch und wird nicht gefiltert.

Das ist kein Notbehelf, sondern die richtige Arbeitsteilung: Der Server liest,
was er lesen kann, ohne dass ein Bild das Haus verlässt; wo er an seine Grenze
kommt, steht das bessere Werkzeug schon in der Hand dessen, der fotografiert
hat.

**Ohne Tesseract fehlt der Weg, und die App sagt es.**
`GET /api/sources/erkennung` beantwortet die Frage, bevor jemand ein Bild
auswählt; das Auswahlfeld bietet die Bildformate dann gar nicht erst an.
Dieselbe Regel wie beim Vorlesen: eine fehlende Möglichkeit ist kein Fehler,
sondern ein Weg weniger.

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

---

## Auswertung - wie gut hört welches Modell?

Der Korpus weiß, was gesprochen wurde, und er weiß, was gesprochen werden
*sollte*: Die Vorlage steht daneben. Damit ist jede Aufnahme eine fertige
Prüfaufgabe - man schickt sie durch einen Erkenner und vergleicht, was
herauskommt, mit dem, was dastand. Genau das tut der Reiter **Auswertung**
(`services/auswertung.py`, `api/auswertung.py`).

Die Zahlen, die dabei entstehen, bleiben nicht hier: Sie sind die Baseline,
gegen die in `lernen` jedes selbst trainierte Modell antritt (siehe
[lernen](lernen.md)). Wer dort eine leere Tabelle sieht, hat diesen Lauf noch
nicht angestoßen.

Gemessen wird immer **ein** Korpus, der des vorgelegten Zugangs. Eine
Auswertung über alle Sprecher hinweg gibt es bewusst nicht: Wie gut ein Modell
hört, hängt an der Stimme, und der Mittelwert über mehrere Menschen wäre eine
Zahl, die für keinen von ihnen gilt. Verworfene Aufnahmen zählen nicht mit -
was der Sprecher selbst weggeworfen hat, ist kein Prüfstück, sondern ein
Fehlversuch, und ginge sonst als schlechte Note eines Modells durch.

Gerechnet wird auf der Karte, wenn eine da ist - dieselbe Einstellung wie beim
Diktieren (siehe [Konfiguration](konfiguration.md#rechenwerk---worauf-erkannt-wird)).

Gegeneinander antreten die Modelle aus `WORTLAUT_AUSWERTUNG_MODELLE`. Die
Vorgabe ist eine Leiter mit drei Sprossen:

| Modell | wofür es in der Leiter steht |
| --- | --- |
| `small` | der Alltagsfall und die Untergrenze, gegen den die anderen zu lesen sind |
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

### Vorlesen: vom Server, sonst vom Browser

Wer nicht flüssig liest, lässt sich den Satz vorlesen und spricht ihn nach. Das
lief über die Web Speech API des Browsers - keine Infrastruktur, keine Latenz,
und der Preis war, dass das Betriebssystem entscheidet, wie es klingt. Dieselbe
Seite klingt auf einem iPhone erträglich und unter Linux mit espeak-ng
blechern.

Seit September 2026 kann der Server sprechen. Die Sätze sind keine Eingabe: Sie
stehen als Vorlagen im Korpus, bevor sie jemand hört. Ein Satz, der **einmal**
gesprochen und als Datei abgelegt wird, klingt danach auf jedem Gerät gleich -
und wie gut er klingt, hängt am Modell und nicht am Betriebssystem.

| | |
|---|---|
| Motor | Piper, auf dem Prozessor, frei (MIT) |
| Gemessen | 4,34 s Audio in 1,19 s, also **4× Echtzeit** (`de_DE-eva_k-x_low`) |
| Format | 16 kHz, 16 bit, mono - dasselbe wie überall sonst |
| Ablage | `korpus/<sprecher>/vorlesen/<vorlage>.<stimme>.wav` |

**Der Motor ist austauschbar.** In `wortlaut/vorlesen.py` steht eine
Schnittstelle mit genau zwei Fragen - *welche Stimmen hast du* und *sprich
diesen Satz* - und darunter heute Piper. Ob eine Stimme aus einem Dienst besser
klingt, ist damit nicht beantwortet, aber billig zu beantworten: Der zweite
Motor kommt daneben, nicht an seine Stelle, und alles darüber merkt nichts
davon.

**Stimmen liegen nicht im Abbild.** Je Stimme sind es einige Dutzend Megabyte;
sie kommen in den Modellspeicher, und welche jemand haben will, entscheidet er:

```bash
docker compose exec wortlaut python scripts/vorlesen.py --hole de_DE-thorsten-high
docker compose exec wortlaut python scripts/vorlesen.py   # alle Vorlagen vorab
```

Das zweite ist eine Bequemlichkeit, keine Bedingung: Vorgelesen wird von selbst,
wenn jemand auf den Knopf drückt, und beim zweiten Mal liegt der Satz da. Vorab
gerechnet wartet niemand auf den ersten Satz einer Sitzung.

**Ohne Stimme bleibt alles, wie es war.** Keine abgelegte Stimme, Piper nicht
installiert, die Datei kommt einmal nicht - in jedem Fall liest der Browser
vor. Der Rückfall ist stumm, und das mit Absicht: Wer einen Satz nachsprechen
will, soll ihn hören und keine Fehlermeldung lesen.

**Was abgeleitet ist, wird nicht mitgetragen.** Kein Byte davon ist gesprochen
worden; es steht nicht in der Sicherung und geht mit dem Sprecher
(`services/vorlesen.py`).

Unter „Audio" stehen beide Arten nebeneinander zur Wahl - „Vom Server"
und „Von diesem Gerät" -, mit einer Hörprobe an demselben festen Satz. Der
Probesatz steht auf dem Server und nicht im Browser: Sonst wäre die Hörprobe
ein Weg, beliebigen Text sprechen zu lassen.

### Zwei Fassungen je Aufnahme

Eine Aufnahme ist ein einzelner Fall: diese Stimme, dieses Mikrofon, dieser
Abstand, dieser Raum, dieser Pegel. Ein Modell, das damit zurechtkommt, muss
den Sprecher noch nicht verstanden haben - es kann auch bloß diese eine
Aufnahmesituation gut vertragen. Zu wissen, was von beidem zutrifft, ist der
eigentliche Zweck der Auswertung, denn die nächste Aufnahme entsteht mit
anderem Pegel und anderem Grundgeräusch.

Gemessen wird deshalb nicht die Aufnahme allein, sondern die Aufnahme und eine
Abwandlung davon (`packages/wortlaut/src/wortlaut/augmentierung.py`):

| Fassung | was sie tut | wonach sie fragt |
| --- | --- | --- |
| `original` | nichts - die Aufnahme, wie sie gesprochen wurde | der Ausgangswert |
| `rauschen` | weißes Rauschen, 20 dB unter der Aufnahme | hält es einem Lüfter, einer Straße stand? |

Zwei Zahlen je Modell und Aufnahme also, und erst ihr Zusammenhang ist die
Auskunft: Liegen sie dicht beieinander, versteht das Modell den Sprecher.
Fallen sie auseinander, verträgt es eine bestimmte Aufnahmesituation.

**Hier standen bis September 2026 zwei weitere Fassungen**, und sie sind
verworfen: `pegel` (lauter bis knapp unter den Anschlag) und `lauter` (alles
mal 1,15). Beide änderten allein die Lautstärke, und Whisper hört kein
Wellenfeld, sondern ein Log-Mel-Spektrogramm - eine gleichmäßige Verstärkung
verschiebt darin kaum mehr als einen Summanden. Über Monate haben sie drei
Spalten gefüllt, die sich nicht unterschieden, und zwei Drittel der Rechenzeit
jeder Auswertung gekostet. Ihre Datenbankzeilen sind gelöscht
(`009_ohne_pegelvarianten.sql`), ihre Dateien weggeräumt
(`scripts/varianten_aufraeumen.py`).

Dieselbe Rechnung stand danach noch eine Weile in „schreiben", das ein Diktat
vor dem Erkennen lauter rechnete. Auch das ist weg
(`004_ohne_aussteuern.sql`): Was zwischen zwei Modellen nichts trennt, hilft
auch einem einzelnen nicht messbar - und es kostete eine zweite Datei je
Diktat, einen Schalter und eine Tabelle.

Und wovon das alles zu trennen ist: Womit **trainiert** wird, ist eine andere
Frage. Dort ist die Abwandlung seit September 2026 breit, gewürfelt und
flüchtig - Masken im Spektrogramm, Raum, Rauschen, Tempo, je Durchgang anders
und nirgends abgelegt (siehe [lernen](lernen.md) und
`apps/lernen/training/klangwandel.py`). Die Fassungen hier sind das Gegenteil:
wenige, feste, seit Monaten vergleichbare Messpunkte.

Zwei Entscheidungen stecken in der verbliebenen:

* **Das Rauschen liegt in festem Abstand zur Aufnahme, nicht auf festem
  Pegel.** Ein absoluter Rauschpegel träfe eine leise Aufnahme viel härter als
  eine laute; die Abwandlung wäre für jede Aufnahme eine andere, und der
  Vergleich zweier Aufnahmen sagte mehr über deren Aussteuerung als über das
  Modell.
* **Das Rauschen ist gewürfelt und trotzdem wiederholbar.** Der Würfel bekommt
  die Kennung der Aufnahme als Keim. Dieselbe Aufnahme ergibt auf jeder
  Maschine dasselbe Rauschen, und eine gelöschte Datei kommt Byte für Byte so
  zurück, wie sie war - sonst wäre eine wiederholte Messung keine Wiederholung.

Die Fassung wird **aufbewahrt** - nicht, weil das Rechnen teuer wäre (gemessen
33 ms je Aufnahme, der ganze Korpus in 13 Sekunden), sondern aus zwei anderen
Gründen: Die Ansicht spielt genau diese Datei zum Mithören ab, und das Manifest
eines Trainingslaufs zeigt auf sie - ein Schnappschuss, dessen Dateien es nicht
gibt, wäre keiner. Sie entsteht beim Hochladen einer Aufnahme und, falls
eine fehlt, spätestens kurz bevor der Lauf sie braucht - so kommt auch jeder
Korpus, der vor dieser Änderung angelegt wurde, ohne Zutun zu seinen Dateien.
`make augmentieren` (im Container `python scripts/augmentieren.py`) zieht das
für alle Korpora auf einmal vor.

In der Sicherung liegen sie dagegen **nicht**: Liegenbleiben ist billig,
Wegtragen nicht (siehe [Zwei Formate, zwei Fragen](#zwei-formate-zwei-fragen)).

Beim Löschen gehen sie mit: Eine abgewandelte Fassung ist dieselbe Stimme, nur
lauter oder verrauscht, und damit derselbe Gesundheitsdatensatz
(Grundentscheidung 6). Wer eine Aufnahme verwirft, hat nicht drei Kopien davon
gemeint.

### Vier Maße und eine Zahl

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

### Der Lauf

Ein Hintergrundlauf arbeitet die offenen Tripel aus Aufnahme, Modell und
Fassung ab, eines nach dem anderen - bei drei Modellen und zwei Fassungen also
sechs Messungen je Aufnahme. Vier Eigenschaften sind Absicht:

* **Ist nichts offen, läuft auch nichts.** Ein zweiter Start, bei dem alles
  schon gerechnet ist, legt keine Aufgabe an, sondern gibt den unveränderten
  Stand zurück. Sonst stünde für einen Augenblick „läuft" da, ohne dass etwas
  liefe - und die Ansicht, die genau dann nachfragt, zeigte etwas an, das im
  nächsten Takt wieder verschwindet. Am Knopf **Erneut prüfen** steht dann
  „Nichts Neues zu rechnen"; ein Knopf, der zurückfedert und sonst nichts tut,
  ist von einem kaputten nicht zu unterscheiden.
* **Von Hand angestoßen.** Der Lauf startet nicht beim Hochfahren des Servers.
  Whisper rechnet, und zwar auf derselben Maschine, auf der jemand gerade
  aufnimmt; ein Neustart des Containers würde sonst jedes Mal ungefragt Stunden
  Rechenzeit binden.
* **Aufnahmeweise, nicht modellweise.** Erst alle Aufnahmen durch `small`, dann
  durch `medium`, dann durch `large-v3` wäre sparsamer - je Modell einmal laden. Nur zeigte die Kurve
  dann lange eine einzige Reihe, und verglichen werden soll gerade. Bezahlt
  wird das damit, dass alle Erkenner gleichzeitig im Speicher liegen; bei
  `small,medium,large-v3` gut zweieinhalb Gigabyte in `int8` auf dem
  Prozessor, knapp drei in `int8_float16` auf der Karte. Das ist der Grund für
  die halbe Darstellung: In `float16` wären es gut sechs, und die Karte teilt
  sich die Auswertung mit dem Training und dem Sprachmodell.
* **Wiederaufnehmbar.** Fertig ist, was in `erkennungen` steht
  (`005_auswertung.sql`, `007_varianten.sql`). Ein zweiter Lauf rechnet nur,
  was fehlt - nach einem Neustart, nach neuen Aufnahmen, nach einem
  hinzugefügten Modell und nach einer hinzugefügten Fassung. Nichts wird
  doppelt gerechnet, nichts geht verloren, wenn der Lauf mitten darin
  abbricht.
* **Auf der Karte, wenn eine da ist.** Dieselbe Einstellung wie beim
  Diktieren und beim Trainer (`WORTLAUT_GERAET`, siehe
  [Konfiguration](konfiguration.md#rechenwerk---worauf-erkannt-wird)). Das ist
  der Unterschied zwischen vier Sekunden und einer Viertelsekunde je Aufnahme -
  ein voller Lauf über einen Korpus von 350 Messungen je Modell dauert damit
  Minuten statt Stunden. Ist die Karte voll, weicht der Lauf auf den Prozessor
  aus, statt zu scheitern.
* **Fertig heißt: auf diesem Rechenwerk fertig.** Jede Zeile trägt mit, worauf
  sie gemessen wurde (`erkennungen.rechenwerk`, `008_rechenwerk.sql`). Eine
  Zeile aus einem anderen Rechenwerk gilt als offen und wird neu gerechnet -
  ihre Rechenzeit passt nicht neben die übrigen, und zwar um eine
  Größenordnung. Das kostet nach einem Wechsel einmal einen vollen Lauf; auf
  der Karte sind das Minuten. Die Alternative wäre eine Spalte mit zwei
  Maßstäben darin, und die sagt weniger als keine.
* **Ein Lauf zur Zeit, über alle Sprecher.** Nicht aus Bequemlichkeit: Zwei
  Läufe teilten sich eine CPU und dieselben Modelle im Speicher und wären
  zusammen langsamer als nacheinander.

Was die Modelle sagen, steht mit im Korpus und nicht daneben - es hängt an
genau dieser Aufnahme dieses Sprechers, und wer den Sprecher löscht, löscht es
mit (Grundentscheidung 6).

### Die Ansicht

Eine Kurve über die Aufnahmen, von 1 an lückenlos durchgezählt. Die Nummer
steht in keiner Tabelle: Sie ergibt sich aus dem, was gerade gilt, damit eine
verworfene Aufnahme keine Lücke in der Achse hinterlässt.

Je Aufnahme ein Wert je Modell - eines davon als Balken, die übrigen als
Punkte darüber. Eine Auswahlliste unter dem Bild wechselt das Maß, eine zweite
das Modell, das den Balken bekommt. Die zweite zeigt dabei, was **gilt**, und
nicht, was gewählt wurde: Solange niemand gewählt hat, steht dort die Vorgabe
(`small`, sonst die Mitte der Liste). Sie zeigte eine Zeitlang ein leeres Feld,
weil die leere Wahl auf keine ihrer Optionen passte - während im Bild längst
ein Modell als Balken stand. Was noch nicht gerechnet ist, bleibt leer
statt auf null zu fallen: Eine Null wäre ein Modell, das nichts verstanden hat.
Der Fortschritt steht darüber, und die Seite fragt im Takt nach, solange
gerechnet wird.

Gemessen sind zwei Werte je Modell und Aufnahme, im Bild steht einer davon:
der **bessere** der beiden. Alle Reihen über dieselben Aufnahmen zu legen hieße,
nichts mehr zu sehen; der beste sagt, was ein Modell aus dieser Aufnahme
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

**Die Aufnahme läuft mit.** Unter der Vorlage steht ein Abspieler, und zwar
ohne Knopf davor: Wer hierher gekommen ist, hat schon zweimal geklickt - einmal
auf die Spalte, einmal auf die Fassung -, und ein dritter Klick, um zu hören,
worüber er gerade liest, wäre einer zu viel. In „Meine Daten" steht dort ein
„▶ Hören", und das ist richtig so: Dort liegt eine lange Liste untereinander,
und der Browser zöge sonst Dutzende Aufnahmen in den Speicher.

Abgespielt wird **die gewählte Fassung** und nicht immer das Original
(`GET /api/recordings/{id}/audio?fassung=…`). Gerade beim Rauschen ist das die
eigentliche Frage: Versteht man selbst noch, was das Modell nicht mehr
verstanden hat? Eine Zahl beantwortet das nicht. Gerechnet wird für den
Abspieler nichts - fehlt eine Fassung noch, steht dort kein Abspieler, und die
Texte darunter fehlen ohnehin auch.

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

---

## Endpunkte

Verwaltung - hinter `WORTLAUT_AUTH_TOKEN`; ohne ihn zu:

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
PATCH  /api/sources/{id}                    { aktiv }  - abstellen/aufnehmen
DELETE /api/sources/{id}                    409, wenn Aufnahmen daran hängen
POST   /api/sessions
GET    /api/prompts/next?session=…
POST   /api/recordings                      multipart: audio + prompt_id + modus
GET    /api/recordings/{id}/audio?fassung=  Original oder eine Abwandlung
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
GET    /api/zugang                          { art, sprecher_id, name, sprache }
GET    /gesundheit                          ohne Zugang
```

Die interaktive Dokumentation liegt unter `/docs`.

