# App „lernen" - ein Modell für genau diese Stimme

Aus den Aufnahmen von [hören](hoeren.md) ein feingetuntes Whisper - und die
eine Ansicht, auf der entschieden wird, womit [schreiben](schreiben.md)
arbeitet.

Der Entwurf dahinter steht in [Der Entwurf](architektur.md), das Verfahren
selbst - Zielfunktion, Pseudocode, Verbesserungsoptionen - in
[Das Trainingsverfahren](trainingsverfahren.md).

---

## Zwei Teile, ein Verzeichnis dazwischen

Die App zerfällt in zwei Teile, und dazwischen liegt ein Verzeichnis statt
eines Aufrufs.

| Teil | Wo | Was er tut |
|---|---|---|
| Oberfläche | `backend/`, `frontend/` | zuteilen, beauftragen, zusehen, freigeben |
| Trainer | `training/` | Aufträge von der Warteschlange nehmen und rechnen |

Der Trainer ist ein eigener Container mit torch und CUDA - gut vier Gigabyte
Abbild und eine Karte. Der Webdienst braucht davon nichts und soll in Sekunden
neu starten. Verbunden sind beide über `data/snapshots/<job_id>/`
(`wortlaut/laeufe.py`), und das ist dasselbe Muster wie zwischen `schreiben`
und `hören`: etwas Liegendes statt einer Aufrufkette. Drei Folgen, und alle
drei sind der Grund dafür:

* Der Webdienst kann neu starten, während ein Training läuft.
* Der Trainer kann neu starten, ohne dass ein Auftrag verlorengeht.
* Es gibt keinen Weg, auf dem der eine den anderen zum Absturz bringt.

Ein Auftragsverzeichnis trägt alles, was zu diesem Lauf gehört: die Marke für
die Löschung, den Auftrag, das Manifest (den Schnappschuss), den Zustand, den
Fortschritt, die Bewertung und das Protokoll. Offen ist ein Auftrag, zu dem es
noch keinen `zustand.json` gibt - das ist die ganze Warteschlange. Eine
zusätzliche Warteschlangendatei wäre ein zweiter Ort, an dem dasselbe steht,
und der erste, der bei einem Abbruch nicht mehr stimmt.

Gerechnet wird einer nach dem anderen, über alle Sprecher hinweg: Es gibt eine
Karte, und zwei Läufe darauf wären zusammen langsamer als nacheinander -
dieselbe Überlegung wie beim Lauf der Auswertung in `hören`.

## Sechsfache Kreuzvalidierung über alles

Jede Aufnahme bekommt der Reihe nach eine Faltung - die erste in Faltung 1, die
zweite in Faltung 2, nach der sechsten geht es wieder von vorn los. Ein
Trainingslauf rechnet dann **sieben** Trainings:

| | Lernt auf | Gemessen an |
|---|---|---|
| Faltung 1 … 6 | fünf Sechsteln | dem zurückgehaltenen Sechstel |
| Endmodell | allem | nichts |

Nach den sechs Faltungen ist **jede einzelne Aufnahme** genau einmal von einem
Modell gehört worden, das sie nie gesehen hat. Diese Messungen zusammen sind
die Zahl, die in der Modelltabelle steht - sie steht damit auf dem ganzen
Korpus statt auf einem Drittel davon.

### Was hier vorher stand, und warum es weg ist

Bis September 2026 gab es ein festes Testdrittel: zwei Drittel lernen, ein
Drittel prüft, einmal zugeteilt und nie wieder umsortiert. Der Gedanke war
richtig - ungesehene Aufnahmen, an denen gemessen wird -, die Ausführung trug
nicht. Bei einem Korpus von neun Aufnahmen bestand der Test aus dreien und die
Validierung aus **einer**. Eine Fehlerrate über drei Aufnahmen ist keine
Auskunft, sondern ein Würfelwurf, und eine Abbruchentscheidung über eine
Aufnahme erst recht.

Die Kreuzvalidierung beantwortet dieselbe Frage über alle Aufnahmen. Sie ist
dabei ausdrücklich **kein Ersatz für einen unabhängigen Test**: Sie sagt, wie
gut das Verfahren auf diesem Korpus arbeitet, nicht, wie gut es auf der
nächsten Aufnahme arbeiten wird. Wirklich unabhängige Testaufnahmen werden
eigens aufgenommen werden; bis dahin steht hier keiner, und das ist ehrlicher,
als ein Sechstel so zu nennen.

### Warum die Faltung nirgends gespeichert ist

Die alte Zuteilung **musste** in einer Tabelle stehen. Hätte man beim
Trainieren durchgezählt, wäre nach der ersten gelöschten Aufnahme alles
dahinter um einen Platz vorgerückt - und Aufnahmen, die bisher geprüft haben,
wären im Training eines Modells gelandet, das anschließend an ihnen gemessen
wird.

Diese Gefahr gibt es nicht mehr: In fünf von sechs Faltungen trainiert jede
Aufnahme ohnehin. Welche Faltung sie trägt, entscheidet nur, in welchem der
sechs Läufe sie gemessen wird. Die Faltung folgt deshalb schlicht der
Reihenfolge des Korpus, wird bei jedem Auftrag neu gerechnet und im
Schnappschuss festgehalten. Eine Tabelle daneben wäre eine zweite Wahrheit über
dieselbe Sache - und die erste, die nicht mehr stimmt, sobald jemand eine
Aufnahme löscht.

Verglichen werden deshalb **Läufe**, nicht Faltungen: Jeder Lauf misst über
alle Aufnahmen, die er kennt, und trägt sein Manifest bei sich.

### Das Modell, das am Ende benutzt wird

Nach den sechs Messläufen wird ein siebtes Mal trainiert - auf **allen**
Aufnahmen, mit den Einstellungen, die sich in den Faltungen bewährt haben: der
Median der Durchgangszahl und der Median des α (siehe
[Die dritte Achse](#die-dritte-achse-was-am-ende-zählt)). Dieser Stand wird
gespeichert und steht in „Modelle" zur Freigabe für „schreiben".

Er hat mehr gesehen als jedes der sechs Messmodelle und ist deshalb sehr
wahrscheinlich besser als sie - und genau deshalb lässt er sich nicht mehr
ehrlich messen: Er kennt jede Aufnahme, an der man ihn prüfen könnte. **Die
Zahl neben ihm ist die vorsichtige aus der Kreuzvalidierung, nicht seine
eigene.** Das ist der Preis dafür, dass das ausgelieferte Modell alles gesehen
hat, was da war - und bei kleinen Korpora ist das der Preis wert.

## Vier Läufe, und warum nicht mehr

Zwei Fragen, die sich nicht vermischen lassen, also zwei Achsen:

| | Nur Originale | Mit Abwandlungen |
|---|---|---|
| **Volles Training** | alle Gewichte, eine Probe je Aufnahme | alle Gewichte, vier Proben je Aufnahme |
| **Feintuning (LoRA)** | kleiner Zusatz, eine Probe je Aufnahme | kleiner Zusatz, vier Proben je Aufnahme |

Erst der Vergleich der vier sagt, ob das Mehr an Daten oder das Mehr an
Freiheit geholfen hat.

### Worauf trainiert wird

Seit September 2026 ist auch das Grundmodell eine Wahl:

| | | Mit vollem Training | Mit LoRA |
|---|---|---|---|
| **whisper-small** | 244 M Gewichte, die Vorgabe | ja | ja |
| **whisper-medium** | 769 M Gewichte | **nein** | ja |

`small` bleibt die Vorgabe: die kleinste Stufe, die ganze Sätze trifft, bequem
im Speicher einer einzelnen Karte, und dieselbe Reihe, gegen die `hören` schon
misst.

`medium` ist der stärkste Hebel, den dieses Projekt hat - dreimal so viele
Gewichte und ein deutlich besserer Ausgangspunkt. **Nur mit LoRA**: Volles
Feintuning von `medium` sprengt den Speicher einer 11-GB-Karte. Die
Kombination wird deshalb gar nicht erst angeboten und zusätzlich in der API
und im Trainer abgewiesen - nach zwei Stunden am Speicher zu scheitern wäre
die schlechteste aller Auskünfte. Mit LoRA passt es: Das Grundmodell bleibt
eingefroren, gelernt wird ein kleiner Zusatz.

Der Platz reicht trotzdem nur mit einem zweiten Griff, und der erste war der
falsche. Zunächst fiel der Stapel von acht auf vier bei doppelter Akkumulation
- dieselbe wirksame Stapelgröße in zwei Portionen. Gemessen blieben damit
9,3 GB von 10,75 GB nutzbaren belegt. Das Training lief, aber danach will der
**Erkenner** auf dieselbe Karte, um die Faltung zu messen, und der fand nichts
mehr vor: Ein Lauf im September 2026 scheiterte mitten in der Auswertung der
ersten Faltung mit `CUDA failed with error out of memory`.

Seitdem rechnet `medium` seine Aktivierungen beim Rückwärtsgang neu, statt sie
aufzuheben (`gradientensparsam` in `je_grundmodell`,
`training/rezepte/whisper_lora.yaml`). Dieselben Gradienten, ein Viertel des
Platzes: 2,3 GB statt 9,3 GB. Der Stapel darf deshalb wieder auf acht stehen
wie bei `small` - und es wurde dabei nicht langsamer, sondern schneller
(68 statt 125 ms je Probe), weil ein Vorrat, der an die Decke stößt, mehr
kostet als die zweite Rechnung.

## Warum sich Zahlen ändern, wenn ein Modell verschwindet

Die Modelltafel rechnet **jede** Zahl über die Messeinheiten, die alle Modelle
gemeinsam haben. Das ist ihr Zweck: Zwei Wortfehlerraten über verschiedene
Aufnahmen sind kein Vergleich, sondern zwei Zahlen nebeneinander.

Die Folge erwartet nur niemand, solange sie nicht dasteht: **Die Zahl eines
Modells ist damit keine Eigenschaft dieses Modells allein.** Fällt eine Zeile
weg - gelöscht, oder weil ein Lauf mit ihr verschwindet -, wächst die
Schnittmenge, und jede übrige Zahl ändert sich.

Gemessen an einem echten Korpus: Ein Stand, der nur 40 der 264 Einheiten
gehört hatte, hielt die ganze Tafel auf diesen 40. Nach seinem Löschen stiegen
alle Wortfehlerraten um rund 0,15 - nicht weil ein Modell schlechter wurde,
sondern weil plötzlich über 264 statt über 40 Aufnahmen gemittelt wurde.

Deshalb sagt die Tafel es **vorher**: Begrenzt eine einzelne Zeile den Boden
um mehr als ein Viertel, steht ihr Name über der Tabelle, samt der Zahl, die
ohne sie gälte. Und die Sicherheitsabfrage beim Löschen eines Laufs nennt es
ebenfalls.

Wer stabile Zahlen will, hält den Bestand gleichmäßig: Ein erneuter Lauf der
Auswertung in „hören" misst die Grundmodelle über den heutigen Korpus, und ein
neuer Trainingslauf misst seinen Stand ebenso.

---

## Stände einer anderen Geschwindigkeit

Sie stehen in der Tafel wie jeder andere und werden verglichen wie jeder
andere. Eine Weile standen sie grau und außerhalb des gemeinsamen Bodens -
aus Sorge, ihre Zahlen seien mit den übrigen nicht zu halten.

Die Sorge war unbegründet, und der Grund wurde erst beim Nachsehen klar: Ein
Stand **bringt sein Tempo mit**. Es steht in seinem Manifest, und „schreiben"
liest es dort und spult beim Diktieren genauso vor. Das Vorspulen ist damit
kein Teil der Prüfbedingungen, sondern ein Teil des Modells - und jede Zeile
der Tafel beantwortet dieselbe Frage: Was macht dieses Ding aus dieser
Aufnahme? Genau die Frage, für die eine Vergleichstafel da ist.

Mit welcher Geschwindigkeit ein Stand gelernt hat, steht in seinem Namen
(`…-2.25x`) und vollständig in seinem Steckbrief unter „Details".

---

## Wie schnell gehört wird

Dysarthrische Sprache ist oft stark verlangsamt, und Whisper versteht sie
vorgespult messbar besser. Wieviel, hängt am Sprecher. Drei Wege:

| Wahl | Verfahren | Kosten |
|---|---|---|
| **Aus** | gar nicht vorspulen | – |
| **Aus den Dauern geschätzt** | Aufnahmedauer ÷ geschätzte Sprechdauer der Texte | nichts |
| **Gesucht (0,75–4,0)** | Stützstellen am unveränderten Grundmodell | ~1 Min. je Faltung |

**Die Schätzung** rechnet je Faltung zwei Summen: wie lange die Texte bei
gewöhnlichem Sprechtempo dauern würden (`chunker.dauer`, 13 Zeichen je
Sekunde, plus eine Sekunde je Aufnahme für Ansetzen und Abklingen) und wie
lange sie wirklich gedauert haben. Ihr Verhältnis ist der Faktor, gerundet auf
eine Viertelstufe. Über Summen und nicht je Aufnahme: Ein einzelner Satz kann
eine lange Pause enthalten, und ein Mittel über Quotienten gewichtete kurze
Aufnahmen so stark wie lange. Das Endmodell nimmt das Mittel der sechs
Faltungen, wieder auf eine Viertelstufe.

**Die Suche** dekodiert je Faltung eine Stichprobe von bis zu zwei Dutzend
Lernaufnahmen bei acht Stützstellen mit dem **unveränderten Grundmodell** und
nimmt den kleinsten WER. Gewinnt die oberste Stützstelle, wird nachgelegt
(3,5, dann 4,0): Ein Optimum am Rand ist keines, sondern die Auskunft, dass zu
kurz gesucht wurde.

Am Ende werden die sechs Kurven **übereinandergelegt** und das Minimum der
gemittelten Kurve genommen - nicht der Median der sechs Sieger. Eine einzelne
Faltung hört zu wenige Aufnahmen, als dass ihr Sieger mehr wäre als Zufall;
zusammengelegt sind dieselben Kurven glatt. Der Standardfehler steht je
Stützstelle daneben, und Faktoren innerhalb eines Fehlers vom besten gelten
als nicht unterscheidbar.

**Beide Verfahren beantworten verschiedene Fragen.** Die Schätzung sagt, wie
weit dieser Mensch von der Norm abweicht; die Suche sagt, bei welcher
Geschwindigkeit das Modell ihn am besten versteht. An einem echten Korpus
gingen sie deutlich auseinander - geschätzt 4,4 (auf 4,0 gestutzt), gesucht
3,0. Welches der bessere Faktor ist, sagt der Vergleich in der Modelltafel;
dafür stehen beide als eigene Achse darin und nicht eines im Quelltext.

**Je Faltung und nicht einmal für den Lauf.** Sonst sähe die Wahl Daten, an
denen später gemessen wird.

Der gefundene Faktor steht in der Überschrift des Laufs, im Namen des Standes
und in seinem Manifest - und „schreiben" liest ihn von dort, um beim Diktieren
genauso vorzuspulen.

## Wie gemessen wird, und Training

**Wie gemessen wird** erklärt die Kreuzvalidierung: wie die Aufnahmen auf die
sechs Faltungen fallen, was in den sieben Trainings geschieht und warum die
Zahl neben dem Endmodell nicht seine eigene ist. Dazu ein Blick darauf, wie
schwer die Faltungen sind - bei einem Korpus, der nicht durch sechs teilbar
ist, sind sie es nicht ganz.

Die Aufnahmen selbst stehen dort **nicht**. Sie stehen unter „Meine Daten",
einmal und vollständig, mit Text, Dauer und zum Anhören; die Ansicht verlinkt
dorthin. Zwei Listen über dieselbe Sache sind eine zu viel - die zweite ist
die, die irgendwann nicht mehr stimmt.

**Training** beauftragt und zeigt den Stand. Je Lauf ein Balken und die Stufe
daneben (laden, training, umwandeln, bewerten). Der Balken bleibt leer, solange
der Trainer die Schrittzahl nicht genannt hat: Ein Balken bei null, der nicht
weiß wovon, ist eine Behauptung. Vier Felder darunter zeigen, welche der vier
Kombinationen schon gerechnet sind - gesperrt wird keine, ein zweiter Lauf nach
fünfzig neuen Aufnahmen ist ein gutes Recht.

Kommen neue Aufnahmen dazu, sagt die Ansicht es - als Zahl, nicht als
Automatik: „23 Aufnahmen sind dazugekommen, seit zuletzt etwas fertig
trainiert wurde." Einen Lauf von selbst anzustoßen wäre falsch, und zwar aus
demselben Grund, aus dem auch die Auswertung in `hören` von Hand angestoßen
wird: Ein Training belegt die Karte für Minuten bis Stunden und friert einen
Stand des Korpus ein. Liefe es von allein, wüsste hinterher niemand mehr,
welche Aufnahmen in welchem Modell stecken - und genau das zu wissen ist der
Zweck des Schnappschusses. Sichtbar zu machen, wann es sich lohnt, ist die
halbe Automatik und die richtige Hälfte.

**Beauftragen verlangt den Trainerschlüssel.** Über den Wahlmöglichkeiten
steht ein Feld, und ohne Eintrag bleibt der Knopf stumpf; gesendet wird der
Schlüssel als Kopfzeile `X-Trainer-Key` und nur mit dieser einen Anfrage. Der
Grund ist derselbe, aus dem es keine Automatik gibt, nur strenger: Ein Lauf
belegt die Karte für Minuten bis Stunden. Der Sprecherzugang sagt, wessen
Modell entsteht - er sagt nicht, dass dieser Mensch die Maschine dafür
beschäftigen darf, und er ist an jeden ausgegeben, der aufnimmt. Wäre er auch
die Erlaubnis, wäre jeder Aufnahmelink ein Knopf, der Rechenzeit kostet, so
oft wie jemand darauf drückt.

Der Schlüssel steht in `WORTLAUT_TRAINER_KEY`, und **leer heißt abgeschaltet**
- wie bei Verwaltung und Aufsicht in `hören` und aus demselben Grund: Keine
Installation weiß, ob sie eine Entwicklungsinstallation ist. Dann sagt die
Ansicht es und zeigt die Wahl gar nicht erst; die Läufe von früher bleiben
sichtbar. Zusehen, zurücknehmen, löschen und freigeben verlangen ihn nie - das
kostet nichts und gehört dem, dessen Stimme im Modell steckt. Der Browser merkt
sich einen Schlüssel, der funktioniert hat; ein falscher wird nicht gemerkt,
sonst verdächtigte man ihn beim nächsten Mal nicht mehr.

Ein Papierkorb in der Kopfzeile jeder Karte räumt einen Lauf weg. Die
Sicherheitsabfrage nennt vorher, was verschwindet - und das ist mehr als der
Lauf: Ein fertiger hat ein Modell hervorgebracht, und das geht mit. Bliebe es
stehen, zeigte es auf ein Verzeichnis, das es nicht mehr gibt, und die Frage,
worauf es trainiert wurde, wäre nicht mehr zu beantworten; das Manifest, das es
sagt, liegt im gelöschten Lauf. Ist der Stand gerade freigegeben, steht auch
das in der Abfrage: In `schreiben` ändert sich dann, womit diktiert wird - die
Freigabe geht mit, statt auf ein Verzeichnis zu zeigen, das es nicht mehr gibt.

Was **nicht** mitgeht, ist der Korpus. Er gehört „hören" und nicht diesem
Lauf; die Faltungen hängen an seiner Reihenfolge und werden beim nächsten
Auftrag ohnehin neu gerechnet. Ein rechnender Lauf lässt sich nicht löschen: In sein Verzeichnis schreibt gerade
ein anderer Container.

Ein Klick führt in den **einzelnen Lauf**: zwei Kurven über den Schritten. Die
durchgezogene ist der Trainingsverlust, die gestrichelte die Validierung. Zwei
und nicht eine, denn der Trainingsverlust fällt auch dann weiter, wenn das
Modell nur noch auswendig lernt; erst die zweite Reihe zeigt, wann das anfängt -
sie ist die, die wieder steigt, während die andere sinkt.

Darunter, sobald der Lauf durch ist, der **Vergleich mit der Baseline**.

## Gegen die Baseline, nicht ins Blaue

Die Frage dieser App ist nicht, wie gut ein Modell ist, sondern ob das Training
es besser gemacht hat. Dafür braucht es zwei Zahlen zu denselben Aufnahmen, und
die zweite liegt schon da: `hören` hat in seiner Auswertung jede Aufnahme durch
`small`, `medium` und `large-v3` geschickt und je Fassung gemessen. Die
Zeilen zu `small` über **alle Aufnahmen** sind die Baseline - dasselbe
Grundmodell, dieselben Aufnahmen, dasselbe Maß, dieselbe Rechnung.

Drei Entscheidungen stecken darin:

* **Nicht neu gemessen.** Eine zweite Messung derselben Sache wäre eine zweite
  Gelegenheit, sie anders zu machen - ein anderes Gerät, eine andere
  Quantisierung, eine andere Textangleichung.
* **Jede Aufnahme aus der Faltung, die sie nicht kannte.** Auf allem, was ein
  Modell gelernt hat, ist eine Verbesserung keine Auskunft, sondern eine
  Selbstverständlichkeit. Die Kreuzvalidierung macht genau das für den ganzen
  Korpus möglich - ohne ein Sechstel dauerhaft stillzulegen.
* **Je Fassung.** Geprüft wird immer auf allen Fassungen (Original und mit
  Rauschen), auch beim Lauf „nur Originale": Die zu
  vergleichenden Modelle sollen sich in ihren Trainingsdaten unterscheiden und
  in nichts sonst - schon gar nicht in dem, woran sie gemessen werden. Ein
  Stand, der auf dem Original gewinnt und beim Rauschen verliert, hat etwas
  anderes gelernt als einer, der überall gleichmäßig zulegt.

Verglichen wird nur, was beide Seiten gemessen haben. Steht in `hören` für eine
Aufnahme noch keine Zeile, fällt sie aus beiden Mittelwerten - sonst stünde ein
Mittel über zwanzig gegen eines über achtzehn, und der Unterschied läge an der
Auswahl statt am Modell.

## Modelle - die eine Ansicht, auf der entschieden wird

Hier läuft alles zusammen: Wer diesem Menschen zuhören kann, wie gut, und
womit `schreiben` arbeiten soll.

Es waren einmal zwei Ansichten. In `lernen` stand eine Liste der eigenen
Stände mit einem Freigabeknopf, in `schreiben` daneben eine zweite, in der
sich zusätzlich ein unverändertes Grundmodell auswählen ließ. Zwei Ansichten,
zwei Begriffe, dieselbe Entscheidung - und in keiner von beiden stand die
Frage, um die es geht: **Ist das selbst trainierte Modell besser als das, was
Whisper von sich aus mitbringt?** Diese Frage beantwortet nur eine Tabelle, in
der beide Sorten nebeneinander stehen.

### Eine Tabelle, ein gemeinsamer Boden

Jede Zeile ist ein Modell - die Grundmodelle aus
`WORTLAUT_AUSWERTUNG_MODELLE` und darunter jeder eigene Stand. Vier Spalten
tragen die Zahlen: **Genauigkeit**, **WER**, **CER** und die **Rechenzeit** je
Aufnahme. Der beste Wert jeder Spalte ist hervorgehoben, und ein Klick auf eine
Spaltenüberschrift sortiert danach - bei den Fehlerraten von selbst andersherum,
denn dort ist klein besser.

Gemessen wird über **alle Aufnahmen**. Kein Modell wird dabei an etwas
gemessen, das es kennt: Die Grundmodelle haben ohnehin nie etwas gelernt, und
bei einem trainierten Stand kommt jede Zahl aus der Faltung, die diese Aufnahme
zurückgehalten hat.

**Gemessen wird dabei nichts neu.** Die Rechnungen liegen längst vor, und alle
stammen aus derselben Datei (`wortlaut/metriken.py`):

* für die Grundmodelle die **Auswertung** aus `hören` - jede Aufnahme durch
  `small`, `medium` und `large-v3`, in allen Fassungen;
* für jeden eigenen Stand die **Bewertung** seines Laufs - dieselben
  Aufnahmen, dieselben Fassungen, dieselben Maße, jede aus der Faltung, die sie
  nicht kannte;
* und seit September 2026 für einen Stand zusätzlich die Aufnahmen, die es zur
  Zeit seines Trainings **noch nicht gab**. Sie stehen in keiner Faltung, weil
  sie in keinem Lauf waren; die Auswertung in `hören` lässt sie deshalb vom
  ausgelieferten Stand hören und legt sie zu den übrigen
  (siehe [hören](hoeren.md#die-eigenen-stände-treten-mit-an)). Für ihn sind
  sie dasselbe unbekannte Prüfstück wie für ein Grundmodell.

Der Boden wächst damit mit dem Korpus statt beim Trainingstag stehenzubleiben -
und er bleibt für alle Zeilen derselbe.

Ein weiteres Mal zu messen wäre eine weitere Gelegenheit, es anders zu machen:
anderes Gerät, andere Quantisierung, andere Textangleichung.

**Die Rechenzeit ist eine Eigenschaft der Maschine, nicht des Modells.** Sie
stand hier eine Zeitlang als vergleichbare Zahl und war es nicht: Die
Grundmodelle wurden auf dem Prozessor gemessen, die eigenen Stände im Trainer
auf der Karte, und in der Spalte standen vier Sekunden neben einer
Viertelsekunde für dasselbe whisper-small. Beide Zahlen stimmten.

Seitdem entscheidet **eine** Stelle, worauf erkannt wird
(`wortlaut/rechenwerk.py`), und jede Messung trägt mit, worauf sie entstand.
Nennen nicht alle Zeilen dasselbe Rechenwerk - weil ein Lauf auf den Prozessor
ausweichen musste oder weil noch alte Zeilen dastehen -, vergleicht die Spalte
nicht: Es gibt keine Bestmarke, jede Zahl trägt ihre Maschine als Marke, und
über der Tabelle steht, warum.

**Verglichen wird nur, was alle gemessen haben.** Die Einheit ist nicht die
Aufnahme, sondern das Paar aus Aufnahme und Fassung; aus allen Modellen, die
überhaupt etwas gemessen haben, wird die Schnittmenge dieser Paare gebildet,
und jedes Mittel läuft über genau sie. Sonst stünde ein Mittel über zwanzig
gegen eines über achtzehn, und der Unterschied läge an der Auswahl statt am
Modell. Die Zeile über der Tabelle nennt, wie viele Messungen das sind.

Fehlt der gemeinsame Boden - weil die Auswertung in `hören` noch nie gelaufen
ist -, sagt die Seite das und rechnet jede Zeile auf dem, was sie hat. Eine
leere Tabelle wäre die schlechtere Auskunft: Sie verschwiege, dass überhaupt
gemessen wurde.

Eine Auswahlliste wechselt die **Fassung**. Vorgabe sind alle zusammen -
die Zahl, die ein Modell in einem Satz beschreibt. Wer wissen will, ob ein
Stand den Sprecher verstanden hat oder bloß seine Aufnahmesituation, schaltet
auf **Original** oder **Rauschen** um; das ist dieselbe Frage wie beim
einzelnen Lauf, nur über alle Modelle auf einmal.

### Wie weit die Zahlen tragen

Sechzig gemessene Aufnahmen ergeben ein 95-%-Intervall, das mehrere Prozentpunkte
breit ist - breiter als die meisten Unterschiede, um die es hier geht. Eine
Tabelle, die 0,142 neben 0,138 stellt und die kleinere Zahl hervorhebt,
behauptet dann etwas, das sie nicht gemessen hat.

Über der Tabelle steht deshalb die Auswahl **Sicherheit**. Eingeschaltet
erscheint unter jeder Zahl der Bereich, in dem sie liegen dürfte - gerechnet
als Bootstrap über zweitausend Ziehungen (`wortlaut/streuung.py`). Gezogen wird
dabei je **Aufnahme** und nicht je Messung: Vier Fassungen einer Aufnahme sind
vier Messungen an einem Gegenstand, und wer sie einzeln zieht, bekommt einen
etwa halb so breiten Bereich heraus. Die naive Ziehung steht trotzdem zur Wahl,
weil sie das in der Literatur übliche Verfahren ist.

Die Auswahl **Gegen** nennt ein Modell, gegen das jede andere Zeile gepaart
antritt: Statt des Bereichs steht dann der Abstand zu ihm, mit p-Wert. Das ist
die schärfere Frage. Zwei Bereiche nebeneinander überlappen sich auch dann oft,
wenn der Abstand belastbar ist - beide tragen den gemeinsamen Anteil mit, den
eine schwer verständliche Aufnahme bei jedem Modell verursacht. In der
Differenz fällt er heraus.

**Die Vorgabe ist „aus", und das ist Absicht.** Was in dieser Tabelle steht,
wird mit dem verglichen, was vor Monaten darin stand; eine Ansicht, die ihre
Zahlen von sich aus anders rechnet, macht das zunichte. Eingeschaltet ändert
sich deshalb keine Zahl - der Bereich tritt daneben, nicht an ihre Stelle.
Geändert hat sich genau eine Kleinigkeit: Überlappen sich der beste und der
zweitbeste Wert einer Spalte, trägt sie ein `≈` mit dem Hinweis, dass der
Vorsprung nicht belegt ist.

Beim einzelnen Lauf gibt es dieselbe Auswahl; dort kommt eine Spalte **Belegt?**
neben den Unterschied zur Baseline. Ein fertiger Lauf schreibt seine Bereiche
außerdem gleich mit ins Manifest seines Standes (`metriken.streuung`) - Stände
von vor September 2026 haben sie nicht, und die Ansicht kommt mit beidem
zurecht.

Was hier bewusst **nicht** steht: die vollständige Aufschlüsselung je Aufnahme
mit den erkannten Texten daneben. Die gehört dorthin, wo sie entstanden ist -
in die Auswertung von `hören` und zum einzelnen Lauf. Hier wird entschieden,
nicht geforscht.

### Freigeben ist ein eigener Schritt

Ein durchgelaufenes Training ist noch kein Modell, das jemand benutzen soll.
Zwischen „hat gerechnet" und „damit diktiere ich" liegt der Blick auf die
Zahlen, und den nimmt einem nichts ab. Ein fertiger Lauf trägt deshalb
`status: fertig`; **Freigeben** ist ein Knopf in dieser Tabelle und keine Folge
des Fertigwerdens.

Freigegeben ist höchstens eines je Sprecher, und es ist das, mit dem
`schreiben` diktiert - sofort, ohne Neustart. Die übrigen bleiben stehen: Vier
Stände nebeneinander, und welcher der beste ist, beantwortet man nicht, indem
man drei wegwirft.

Freigeben lässt sich auch ein **Grundmodell**. „Mein eigenes ist noch nicht
besser als `medium`" ist eine Antwort, und sie braucht denselben Knopf wie jede
andere. Wie das abgelegt wird, steht in
[Der Entwurf](architektur.md#die-freigabe).

### Und was gerade arbeitet

Über der Tabelle steht eine Karte: das Modell, das `schreiben` in diesem
Augenblick geladen hat, mit vollem Namen - und mit **denselben Zahlen wie seine
Zeile in der Tabelle**, aus derselben Rechnung und über dieselben
Messeinheiten; sie folgen deshalb auch der Fassungswahl.

Das war einmal anders und war eine Falle: Die Karte nannte die Wortfehlerrate
aus dem Manifest des Standes, also das Mittel über die Testeinheiten *seines*
Laufs, die Tabelle darunter das Mittel über die Einheiten, die alle Modelle
gemeinsam haben. Zwei Zahlen zum selben Modell, beide richtig - und wer sie
untereinander sah, musste an einen Fehler glauben. Wie gut ein Modell ist,
steht jetzt an genau einer Stelle.

Die Auskunft kommt aus der API von `schreiben` und nicht aus dieser App: Dort
wird diktiert, und eine zweite Wahrheit darüber wäre eine zu viel. Antwortet `schreiben` nicht - weil es getrennt betrieben wird und
gerade steht -, entfällt die Karte; die Tabelle darunter steht weiterhin.

---

## Endpunkte

```
GET    /lernen/api/aufteilung               wer lernt, steuert, prüft - teilt dabei zu
GET    /lernen/api/laeufe                   die Liste, ohne Kurven
POST   /lernen/api/laeufe                   einen Lauf beauftragen
                                            + X-Trainer-Key - der einzige Weg,
                                            der ein zweites Geheimnis verlangt
GET    /lernen/api/laeufe/{id}              Kurven, Bewertung, Vergleich, Protokoll
                                            ?intervall=aus|aufnahme|einheit
POST   /lernen/api/laeufe/{id}/abbruch      einen wartenden zurücknehmen
DELETE /lernen/api/laeufe/{id}              ersatzlos löschen, samt seinem Modell
GET    /lernen/api/modelle                  alle Modelle mit ihren Zahlen
                                            ?intervall=aus|aufnahme|einheit
                                            ?vergleich_mit=<ref> - gepaart gegen dieses
POST   /lernen/api/modelle/freigabe         { ref } - dieses freigeben, jedes andere
                                            zurückziehen; leer nimmt die Freigabe zurück
GET    /gesundheit                          ohne Zugang, auf der Wurzel
```

Alles unter `/lernen` - dem Ort dieser App unter der gemeinsamen Domain. Jeder
Weg außer `/gesundheit` verlangt den Sprecherzugang aus `hören` und leitet die
Kennung daraus ab; `POST /lernen/api/laeufe` verlangt zusätzlich den
Trainerschlüssel (siehe oben). Verwaltung und Aufsicht kommen hier **nicht** durch, und das
ist kein Versehen: Ein Modell gehört einem Menschen, und wer keines hat, hat
hier nichts zu sehen.

Die Liste trägt bewusst keine Kurven: Sie wird abgefragt, solange die Seite
offen ist, und bei zwölf Läufen mit je tausend Schritten wäre das bei jedem
Takt ein Vielfaches dessen, was gemeint ist.

---

## Nahtstellen zu den anderen Apps

| Was | Wo | Richtung |
|---|---|---|
| Korpus | `data/korpus/<sprecher_id>/` | **nur lesend** - „hören" ist sein einziger Schreiber |
| Baseline | Tabelle `erkennungen` im Korpus | nur lesend; gemessen hat sie „hören" unter „Auswertung" |
| (keine) | — | „lernen“ hat keine eigene Datenbank mehr; die Faltungen folgen dem Korpus, die Läufe sind Verzeichnisse |
| Läufe | `data/snapshots/<job_id>/` | schreibend; der Trainer schreibt dort mit |
| Modellstände | `data/modelle/<sprecher_id>/<version>/` | schreibend; „schreiben" liest sie |
| Freigabe | `data/modelle/<sprecher_id>/freigabe.json` | schreibend; „schreiben" liest sie |
| Was geladen ist | `GET /schreiben/api/model` | lesend über die API von „schreiben" - für die Karte über der Tabelle |

Dass der Korpus hier nur lesend vorkommt, ist keine Zusage auf Papier: Es gibt
in dieser App keinen Weg, der in ihn schreibt, und ein Test hält das fest
(`apps/lernen/tests/test_trennung.py`).
