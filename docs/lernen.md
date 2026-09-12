# App „lernen" - ein Modell für genau diese Stimme

Aus den Aufnahmen von [hören](hoeren.md) ein feingetuntes Whisper - und die
eine Ansicht, auf der entschieden wird, womit [schreiben](schreiben.md)
arbeitet.

Der Entwurf dahinter steht in [Der Entwurf](architektur.md).

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

## Die Aufteilung: 2:1, und sie hält

Zwei Drittel der Aufnahmen trainieren, ein Drittel prüft. Die Zahl ist der
leichte Teil; der schwierige ist, dass die Zuteilung **hält**.

Die naheliegende Lösung wäre, beim Trainieren durchzuzählen: Aufnahme 1 und 2
lernen, Aufnahme 3 prüft. Das ist bis zur ersten gelöschten Aufnahme richtig.
Danach rückt alles dahinter um einen Platz vor - und Aufnahmen, die bisher
geprüft haben, landen im Training eines Modells, das anschließend an ihnen
gemessen wird. Die Zahl, die dabei herauskommt, sieht gut aus und bedeutet
nichts.

Die Zuteilung steht deshalb in einer Tabelle, einmal je Aufnahme, und wird nie
wieder angefasst (`data/lernen/<sprecher_id>/lernen.sqlite` - die einzige
eigene Tabelle dieser App). Verschwindet eine Aufnahme, verschwindet ihre Zeile
mit; die übrigen behalten ihren Platz, und die nächste neue erbt ihn nicht. Das
Verhältnis weicht dadurch leicht von 2:1 ab. Das ist der richtige Preis: Ein
sauberes Verhältnis wäre hier nur zu haben, indem man die Trennung zwischen
Lernen und Prüfen aufweicht, und dann misst niemand mehr etwas.

Zugeteilt wird nach einem festen Muster über sechs Plätze:

| Platz | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Teil | Training | Training | **Test** | Training | Validierung | **Test** |

Vier zum Lernen, zwei zum Prüfen - genau 2:1. Einer der vier ist die
Validierung; sie gehört zum Lernen, weil sie es steuert, ist aber keine
Trainingsprobe: Sonst sagte die Lernkurve nur, wie gut das Modell auswendig
gelernt hat. Ein festes Muster und kein Zufall, weil eine zufällige Auswahl
einen gespeicherten Keim bräuchte, um nachvollziehbar zu sein - also ebenfalls
eine gespeicherte Zuteilung, nur schwerer zu lesen.

Zugeteilt wird beim Hinsehen: Jede Abfrage der Ansicht und jeder Auftrag holt
nach, was noch keine Zeile hat. Ein eigener Knopf dafür wäre einer, den jemand
vergisst - und ein Modell, das ohne die neuen Aufnahmen trainiert, sagt nicht,
dass sie fehlten.

## Vier Läufe, und warum nicht mehr

Zwei Fragen, die sich nicht vermischen lassen, also zwei Achsen:

| | Nur Originale | Mit Abwandlungen |
|---|---|---|
| **Volles Training** | alle Gewichte, eine Probe je Aufnahme | alle Gewichte, vier Proben je Aufnahme |
| **Feintuning (LoRA)** | kleiner Zusatz, eine Probe je Aufnahme | kleiner Zusatz, vier Proben je Aufnahme |

Erst der Vergleich der vier sagt, ob das Mehr an Daten oder das Mehr an
Freiheit geholfen hat. Trainiert wird immer auf `whisper-small`, fest und in
der Oberfläche nicht wählbar: Es ist die kleinste Stufe, die ganze Sätze
trifft, es passt in den Speicher einer einzelnen Karte, und es ist dieselbe
Reihe, gegen die `hören` schon misst. Ohne diesen gemeinsamen Nenner wäre der
Vergleich mit der Grundlinie keiner.

Alles Übrige - Lernrate, Durchgänge, Stapelgröße, LoRA-Rang - steht in
`training/rezepte/*.yaml` und nicht in der Oberfläche. Jede Einstellmöglichkeit
dort wäre eine, deren Wirkung später niemand mehr zuzuordnen weiß.

Ausgeliefert wird **nicht der letzte Durchgang, sondern der beste.** Bei
wenigen hundert kurzen Sätzen dreht die Validierungskurve irgendwo in der Mitte
und steigt danach wieder - das Modell lernt die Trainingssätze auswendig. Wer
den letzten Stand nimmt, liefert genau dieses Modell aus, und die Zahl der
Durchgänge im Rezept wird zu einer Wette, die man je Korpus neu abschließen
müsste. So ist sie nur noch eine Obergrenze: Zu hoch angesetzt kostet sie
Rechenzeit, zu niedrig kostet sie Güte - im Zweifel lieber zu hoch.

Das ist auch die Antwort auf die naheliegende Frage, ob sich aus demselben
Material mehr herausholen ließe, indem man mit mehreren Lernraten trainiert.
Bei knapp hundert Trainingsaufnahmen lohnt sich das nicht: Die Gefahr ist nicht,
zu wenig zu lernen, sondern zu viel, und eine Validierung über zwanzig
Aufnahmen unterscheidet zwei benachbarte Lernraten nicht verlässlich - was man
dann misst, ist Rauschen. Der beste Durchgang statt des letzten holt aus
demselben Material mehr heraus als jede Lernratensuche, und er kostet keinen
zusätzlichen Lauf. Der Hebel, der wirklich zieht, sind mehr Aufnahmen.

Zwei weitere Entscheidungen in den Rezepten sind keine Geschmacksfrage:

* **Volles Training läuft mit 1e-5, LoRA mit 1e-3.** Das ist kein Tippfehler.
  Beim vollen Training zieht eine zu hohe Lernrate dem Modell in wenigen
  hundert Schritten alles aus, was es vorher konnte; die LoRA-Matrizen dagegen
  starten bei null und müssen erst etwas werden.
* **Korrekturen wiegen 0,5.** Sie stammen aus `schreiben`: Ihr Text ist keine
  Vorgabe, sondern eine vom Menschen abgenickte Maschinenausgabe. Wer sie
  gleichrangig einspeist, trainiert dem Modell seine eigenen Fehler an. Das
  Gewicht steht je Zeile im Manifest und wirkt im Verlust je Probe
  (`training/finetune.py`).

## Aufteilung und Training

**Aufteilung** zeigt, wer lernt, steuert und prüft - als Streifen, als Tabelle
und als Liste mit dem Platz im Muster daneben. Es gibt hier keinen Knopf, der
etwas verschiebt: Er wäre der Weg, auf dem eine Testaufnahme ins Training
rutscht. Die Liste steht trotzdem da, weil die Zusage sonst eine Behauptung
wäre - wer wissen will, ob seine Prüfaufnahmen ungesehen sind, muss sie sehen
können.

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

Ein Papierkorb in der Kopfzeile jeder Karte räumt einen Lauf weg. Die
Sicherheitsabfrage nennt vorher, was verschwindet - und das ist mehr als der
Lauf: Ein fertiger hat ein Modell hervorgebracht, und das geht mit. Bliebe es
stehen, zeigte es auf ein Verzeichnis, das es nicht mehr gibt, und die Frage,
worauf es trainiert wurde, wäre nicht mehr zu beantworten; das Manifest, das es
sagt, liegt im gelöschten Lauf. Ist der Stand gerade freigegeben, steht auch
das in der Abfrage: In `schreiben` ändert sich dann, womit diktiert wird - die
Freigabe geht mit, statt auf ein Verzeichnis zu zeigen, das es nicht mehr gibt.

Was **nicht** mitgeht, ist die Aufteilung. Sie hängt an den Aufnahmen und nicht
an einem Lauf; sie mitzulöschen hieße, sie beim nächsten Mal neu zu würfeln -
und damit Testaufnahmen ins Training zu lassen, die vorher geprüft haben. Ein
rechnender Lauf lässt sich nicht löschen: In sein Verzeichnis schreibt gerade
ein anderer Container.

Ein Klick führt in den **einzelnen Lauf**: zwei Kurven über den Schritten. Die
durchgezogene ist der Trainingsverlust, die gestrichelte die Validierung. Zwei
und nicht eine, denn der Trainingsverlust fällt auch dann weiter, wenn das
Modell nur noch auswendig lernt; erst die zweite Reihe zeigt, wann das anfängt -
sie ist die, die wieder steigt, während die andere sinkt.

Darunter, sobald der Lauf durch ist, der **Vergleich mit der Grundlinie**.

## Gegen die Grundlinie, nicht ins Blaue

Die Frage dieser App ist nicht, wie gut ein Modell ist, sondern ob das Training
es besser gemacht hat. Dafür braucht es zwei Zahlen zu denselben Aufnahmen, und
die zweite liegt schon da: `hören` hat in seiner Auswertung jede Aufnahme durch
`base`, `small`, `medium` und `large-v3` geschickt und je Fassung gemessen. Die
Zeilen zu `small` auf den **Testaufnahmen** sind die Grundlinie - dasselbe
Grundmodell, dieselben Aufnahmen, dasselbe Maß, dieselbe Rechnung.

Drei Entscheidungen stecken darin:

* **Nicht neu gemessen.** Eine zweite Messung derselben Sache wäre eine zweite
  Gelegenheit, sie anders zu machen - ein anderes Gerät, eine andere
  Quantisierung, eine andere Textangleichung.
* **Nur die Testaufnahmen.** Auf allem anderen hat das Modell gelernt; eine
  Verbesserung dort ist keine Auskunft, sondern eine Selbstverständlichkeit.
* **Je Fassung.** Geprüft wird immer auf allen vier Fassungen (Original,
  ausgesteuert, lauter, mit Rauschen), auch beim Lauf „nur Originale": Die zu
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

Jede Zeile ist ein Modell - die vier Grundmodelle aus
`WORTLAUT_AUSWERTUNG_MODELLE` und darunter jeder eigene Stand. Vier Spalten
tragen die Zahlen: **Genauigkeit**, **WER**, **CER** und die **Rechenzeit** je
Aufnahme. Der beste Wert jeder Spalte ist hervorgehoben, und ein Klick auf eine
Spaltenüberschrift sortiert danach - bei den Fehlerraten von selbst andersherum,
denn dort ist klein besser.

Gemessen wird an den **Testaufnahmen**: dem Drittel des Korpus, das von der
ersten Aufnahme an zum Prüfen bestimmt ist und nie wieder umsortiert wird. Kein
trainiertes Modell hat sie je gesehen, die Grundmodelle sowieso nicht. Nur an
ihnen darf verglichen werden - auf allem anderen hätte die eine Seite gelernt
und die andere nicht.

**Gemessen wird dabei nichts neu.** Zwei Rechnungen liegen längst vor, und
beide stammen aus derselben Datei (`wortlaut/metriken.py`):

* für die Grundmodelle die **Auswertung** aus `hören` - jede Aufnahme durch
  `base`, `small`, `medium`, `large-v3`, in allen vier Fassungen;
* für jeden eigenen Stand die **Bewertung** seines Laufs - dieselben
  Testaufnahmen, dieselben vier Fassungen, dieselben Maße.

Ein drittes Mal zu messen wäre eine dritte Gelegenheit, es anders zu machen:
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

Eine Auswahlliste wechselt die **Fassung**. Vorgabe sind alle vier zusammen -
die Zahl, die ein Modell in einem Satz beschreibt. Wer wissen will, ob ein
Stand den Sprecher verstanden hat oder bloß seine Aufnahmesituation, schaltet
auf **Original** oder **Rauschen** um; das ist dieselbe Frage wie beim
einzelnen Lauf, nur über alle Modelle auf einmal.

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

Daneben der Schalter für das **Aussteuern** vor dem Erkennen - die zweite
Stellschraube, die nicht ändert, *wer* zuhört, sondern was er zu hören bekommt.

Beides kommt aus der API von `schreiben` und nicht aus dieser App: Dort wird
diktiert, dort liegt der Schalter, und eine zweite Wahrheit darüber wäre eine
zu viel. Antwortet `schreiben` nicht - weil es getrennt betrieben wird und
gerade steht -, entfällt die Karte; die Tabelle darunter steht weiterhin.

---

## Endpunkte

```
GET    /lernen/api/aufteilung               wer lernt, steuert, prüft - teilt dabei zu
GET    /lernen/api/laeufe                   die Liste, ohne Kurven
POST   /lernen/api/laeufe                   einen Lauf beauftragen
GET    /lernen/api/laeufe/{id}              Kurven, Bewertung, Vergleich, Protokoll
POST   /lernen/api/laeufe/{id}/abbruch      einen wartenden zurücknehmen
DELETE /lernen/api/laeufe/{id}              ersatzlos löschen, samt seinem Modell
GET    /lernen/api/modelle                  alle Modelle mit ihren Zahlen
POST   /lernen/api/modelle/freigabe         { ref } - dieses freigeben, jedes andere
                                            zurückziehen; leer nimmt die Freigabe zurück
GET    /gesundheit                          ohne Zugang, auf der Wurzel
```

Alles unter `/lernen` - dem Ort dieser App unter der gemeinsamen Domain. Jeder
Weg außer `/gesundheit` verlangt den Sprecherzugang aus `hören` und leitet die
Kennung daraus ab. Verwaltung und Aufsicht kommen hier **nicht** durch, und das
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
| Grundlinie | Tabelle `erkennungen` im Korpus | nur lesend; gemessen hat sie „hören" unter „Auswertung" |
| Aufteilung | `data/lernen/<sprecher_id>/lernen.sqlite` | die einzige eigene Tabelle dieser App |
| Läufe | `data/snapshots/<job_id>/` | schreibend; der Trainer schreibt dort mit |
| Modellstände | `data/modelle/<sprecher_id>/<version>/` | schreibend; „schreiben" liest sie |
| Freigabe | `data/modelle/<sprecher_id>/freigabe.json` | schreibend; „schreiben" liest sie |
| Was geladen ist | `GET /schreiben/api/model` | lesend über die API von „schreiben" - für die Karte über der Tabelle |

Dass der Korpus hier nur lesend vorkommt, ist keine Zusage auf Papier: Es gibt
in dieser App keinen Weg, der in ihn schreibt, und ein Test hält das fest
(`apps/lernen/tests/test_trennung.py`).
