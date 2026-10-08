# App „lernen" - ein Modell für genau diese Stimme

Aus den Aufnahmen von [hören](hoeren.md) ein feingetuntes Whisper - und die
eine Ansicht, auf der entschieden wird, womit [schreiben](schreiben.md)
arbeitet. Die Rechnung selbst steht in
[Das Trainingsverfahren](trainingsverfahren.md).

---

## Zwei Teile, ein Verzeichnis dazwischen

| Teil | Wo | Was er tut |
|---|---|---|
| Oberfläche | `backend/`, `frontend/` | beauftragen, zusehen, freigeben |
| Trainer | `training/` | Aufträge nehmen und rechnen |

Der Trainer ist ein eigener Container mit torch und CUDA. Verbunden sind beide
über `data/snapshots/<job_id>/` (`wortlaut/laeufe.py`): Der Webdienst startet
neu, während trainiert wird; der Trainer startet neu, ohne dass ein Auftrag
verloren geht; keiner bringt den anderen zum Absturz.

Offen ist ein Auftrag mit `auftrag.json` und ohne `zustand.json` - das ist die
ganze Warteschlange. Gerechnet wird einer nach dem anderen, über alle
Sprecher: Es gibt eine Karte.

---

## Sechsfache Kreuzvalidierung

Die Aufnahmen gehen auf sechs Faltungen, je Stamm: Teile und Kopien aus
„Editieren" sind derselbe Ton wie ihr Original und teilen dessen Faltung.
**Die Faltung wird mit der ersten Aufnahme eines Stamms vergeben** - in die
Faltung mit der wenigsten Sprache - und steht dann fest in „hören"
(`hoeren/services/faltungen.py`, Tabelle `faltungen`). So bleiben die
Faltungen gleich schwer, Löschen verschiebt nichts, und eine Aufnahme misst
in jedem Lauf in derselben Faltung. Ein Stamm ohne Eintrag liegt in der
Faltung nach seinem Hash (`laeufe.verteile`). Ein Lauf rechnet sechs
Trainings und mittelt sie:

| | lernt auf | gemessen an |
|---|---|---|
| Faltung 1 … 6 | fünf Sechsteln | dem zurückgehaltenen Sechstel |
| Endmodell | - (Mittel der Faltungen) | nichts, nur geprüft |

Danach ist jede Aufnahme genau einmal von einem Modell gehört worden, das sie
nie gelernt hat; diese Messungen sind die Zahl des Laufs. Die Faltung wird bei
jedem Auftrag gerechnet und steht im Manifest.

**Gemessen wird nur an Vorlagen** (`laeufe.zeilen_fuer_faltung`). Eine
Korrektur aus „schreiben" trägt als Text eine abgenickte Maschinenausgabe;
sie lernt in jeder Faltung mit, gewichtet nach der Achse „Korrekturen", und
wird nie gemessen. Ebenso selbst beschriftete Diktate.

**Am Ende steht das Grundmodell daneben.** Protokoll und Manifest
(`grundmodell`) nennen WER und CER des Laufs und des unveränderten
Grundmodells auf denselben Messungen. Die Zahlen des Grundmodells stammen aus
der Auswertung von „hören"; was dort fehlt, wird gezählt, nicht nachgemessen.

**Was die Zahl sagt.** Wie gut das Verfahren auf diesem Korpus arbeitet - kein
unabhängiger Test. Und sie ist leicht optimistisch: Das zurückgehaltene
Sechstel ist zugleich die Validierung der Faltung. An ihm werden der beste
Checkpoint, das α des Abschlusses und bei `geduldig` der Abbruch gewählt -
mit der Steuergröße `wer` dreimal je Durchgang und am selben Maß -, und an ihm
wird gemessen. Sauber wäre eine geschachtelte Kreuzvalidierung; sie
kostet das Quadrat der Rechenzeit.

### Das Endmodell

**Das Endmodell ist das Mittel der Faltungsmodelle** (`training/endmodell.py`),
kein siebtes Training. Die Gewichte der sechs Faltungen werden elementweise
gemittelt („Model Soup"): Alle starten vom selben Grundmodell und lernen mit
kleiner Lernrate kurz, sie liegen in derselben Verlustmulde, und ihr Mittel
ist erfahrungsgemäß mindestens so gut wie die Faltung im Durchschnitt. Jede
Aufnahme steckt in fünf der sechs Modelle.

Ein Training auf allem müsste Haltepunkt und α blind aus den Faltungen
übernehmen, ohne Validierung - und kann dabei entgleisen, ohne dass es vor der
Prüfung am Ende jemand sieht. Das beste Faltungsmodell auszuliefern wäre keine
Lösung: „Beste" hieße meist nur, dass seine zurückgehaltenen Aufnahmen die
leichtesten waren.

**Bei LoRA wird der verschmolzene Stand gemittelt.** Jede Faltung sichert
Grundmodell plus B·A; ihr Mittel ist genau das Grundmodell plus das Mittel der
Änderungen. A und B getrennt zu mitteln wäre falsch - das Produkt der Mittel
ist nicht das Mittel der Produkte.

**Was schiefging, bleibt draußen** (`endmodell.pruefe_faltungen`), gemessen an
den Aufnahmen, die die Faltung zurückhielt:

| Grund | wann |
|---|---|
| **abgebrochen** | die Faltung ist gescheitert; der Lauf rechnet mit den übrigen weiter |
| **ausgefranst** | ein Viertel ihrer Messungen oder mehr, mindestens zwei, hat mehr Fehler als Wörter |
| **Ausreißer** | ihr Verhältnis zum Grundmodell liegt über dem Anderthalbfachen des Medians, und sie ist schlechter als das Grundmodell |

**Ausreißer am Grundmodell gemessen, nicht an der WER.** Die WER einer
Faltung hängt vor allem daran, wie schwer ihre zurückgehaltenen Aufnahmen
sind. Das Verhältnis ihrer WER zu der des Grundmodells auf denselben
Aufnahmen (aus der Auswertung in „hören") rechnet das heraus; eine Faltung,
die besser ist als das Grundmodell, bleibt immer drin. Fehlen die Werte des
Grundmodells, entfällt diese Prüfung, und das Protokoll sagt es. Dieselben
Schwellen wie in der Plausibilitätsprüfung. Erst wenn keine Faltung
übrig bleibt, scheitert der Lauf. Die Messungen einer ausgelassenen Faltung
bleiben in der Zahl des Laufs: Sie beschreibt das Verfahren auf diesem Korpus,
nicht einen einzelnen Stand. In „Modelle" dagegen zählen nur die gemittelten
Faltungen (siehe dort). Der Steckbrief nennt „Mittel aus 5 von 6
Faltungen" und, welche warum fehlt; das Manifest trägt es unter `endmodell`.

Beim Kontext `vokabular` bekommt das Mittel den Startprompt aus allen
Lerntexten. Das α der Tafel ist der Median der gemittelten Faltungen - jede
trägt ihr eigenes.

Dieser Stand wird ausgeliefert. Er kennt jede Aufnahme und lässt sich nicht
mehr ehrlich messen; **die Zahl neben ihm stammt aus den Faltungen.**

**Die Plausibilitätsprüfung.** Vor dem Eintragen hört das Endmodell zwölf
gleichmäßig verteilte Aufnahmen, die es gelernt hat (`pruefe_endmodell`). Das
ist keine Note, sondern die Frage, ob der Stand überhaupt noch zuhört:

| Befund | wann | wogegen |
|---|---|---|
| **schlechter** | Median über dem Anderthalbfachen dessen, was die Faltungen auf Ungehörtem erreichten | ein Stand, der aus der Art schlägt |
| **ausgefranst** | ein Viertel der Stichprobe oder mehr hat mehr Fehler als Wörter | ein Stand, der wiederholt oder weiterredet |

Der zweite Befund gilt ohne Vergleich, denn bei einem schweren Korpus liegen
schon die Faltungen nahe 1,0. Der Befund steht im Manifest und in „Modelle"
neben dem Stand; die Freigabe blockiert er nicht.

---

## Die Achsen eines Auftrags

Jede Achse steht im Auftrag, im Manifest des Standes und als Glied im
Optionscode. Die Vorgabe ist jeweils der erste Wert.

| Achse | Werte | wofür |
|---|---|---|
| Grundmodell | whisper-small, whisper-medium, whisper-large-v3 | welche Methode geht, entscheidet die Karte; API und Trainer weisen ab, was nicht passt |
| Methode | Volles Feintuning, LoRA | wie viel Freiheit das Modell bekommt |
| LoRA-Ziele | q, v; alle Projektionen; nur Encoder; nur Decoder | wo der Zusatz sitzt - nur mit LoRA |
| LoRA-Rang | 32, 8, 64 | wie groß er ist, α wächst mit - nur mit LoRA |
| Auswahl | Alle Aufnahmen, Kernauswahl | siehe [Die Kernauswahl](#die-kernauswahl) |
| Korrekturen | Gewicht 0,5, 0,25, 0,75, 1,0, aus dem Verlauf | womit Korrekturen aus „schreiben" zählen |
| Selbsttraining | aus, unbestätigte Diktate | ob das freigegebene Modell unbestätigte Diktate beschriftet und sie mitlernen |
| Epochen | fest, geduldig | feste Obergrenze oder Early Stopping |
| Steuergröße | Validierungsverlust, WER | woran Checkpoint, Abbruch und α gewählt werden |
| Fenster | 30 Sekunden, gekürzt | Encoder im Training auf die längste Aufnahme gekürzt, ausgeliefert mit 30 s |
| Augmentierung | keine, SpecAugment, + Raum + Rauschen, + Tempo | Abwandlung zur Laufzeit, nur auf den Lernproben |
| Tempo | aus, geschätzt, gesucht | siehe [Wie schnell gehört wird](#wie-schnell-gehört-wird) |
| Abschluss | bester Checkpoint, Checkpoint-Mittel, WiSE-FT, beides | was am Ende mit den Gewichten geschieht |
| Kontext | aus, Vokabular | Startprompt mit den seltenen Wörtern der Lerntexte, beim Dekodieren |

Was welche Wahl im Einzelnen rechnet, steht in
[Das Trainingsverfahren](trainingsverfahren.md). Welche Grundmodelle zur Wahl
stehen, steht in `WORTLAUT_LERNEN_GRUNDMODELLE`; jedes muss auch in
`WORTLAUT_AUSWERTUNG_MODELLE` stehen, sonst fehlt seine Baseline. Auf einem
trainierten Stand weiterzulernen ist im Trainer vorbereitet
(`training/ausgangsstand.py`), wird aber nicht angeboten.

**Welche Methode mit welchem Modell geht, entscheidet die Karte**
(`wortlaut/kartenplan.py`). Der Läufer meldet sie beim Start
(`data/snapshots/karte.json`), vorher gilt die RTX 2080 Ti mit 11 GB: dort
`small` voll und mit LoRA, `medium` und `large-v3` nur mit LoRA. Volles
Feintuning braucht sechzehn Byte je Gewicht (Gewicht, Gradient, Adam); auf
40 GB geht damit auch `large-v3` voll. Gezählt wird mit
`WORTLAUT_LERNEN_RESERVE_MB` Platz für die Erkenner des Webdienstes.

**Ebenso Ziele und Rang von LoRA.** Der Zusatz kostet dieselben sechzehn Byte
je Gewicht, und wie viele es sind, folgt aus Rang, Zielen und den Abmessungen
des Modells (`kartenplan.lora_parameter`). Was nicht passt, bietet die
Oberfläche nicht an, und Bestellung wie Trainer weisen es ab. Auf der 2080 Ti
passt bei `large-v3` jede Wahl - gemessen braucht der größte Zusatz (alle
Projektionen, Rang 64, 115 M Gewichte) im Probeschritt 5,3 GB; auf einer
8-GB-Karte fiele er weg.

**Wie ein Lauf auf die Karte passt, misst der Trainer** vor jedem Training:
Ein Probeschritt mit dem längsten Text zeigt, wie viele Proben je Schritt
Platz haben - erst ohne Gradientensparen, dann mit, dann mit halbem Stapel.
Die Akkumulation holt den wirksamen Stapel des Rezepts zurück. Genauigkeit
bf16 ab Ampere, darunter fp16; die Aufmerksamkeit über `sdpa`; bei LoRA das
eingefrorene Grundmodell in halber Genauigkeit, der Zusatz in float32. Was
gewählt wurde, steht im Protokoll und im Steckbrief (Stapel, Karte).

**Wenn andere die Karte halten.** Auswertung, Diktat und Sprachmodell rechnen
auf derselben Karte. Vor jedem Lauf und jeder Faltung gibt Ollama seine
Modelle ab (`WORTLAUT_OLLAMA_URL`), und der Lauf wartet, bis genug frei ist.
Scheitert ein Training trotzdem am Speicher, räumt der Trainer die Faltung
weg, wartet und beginnt sie neu - bis zu zehn Minuten (`training/karte.py`).
Hält niemand sonst etwas auf der Karte, bricht er sofort ab: Dann passt das
Training nicht.

### Die Kernauswahl

Für einen Korpus mit vielen fehlerhaften oder verrauschten Aufnahmen: Ein Lauf
mit **Kernauswahl** (`K`) lernt nur auf den besten 70 % und soll ein stabiles
Kernmodell werden (`laeufe.KERN_ANTEIL`).

**Die besten nach dem freigegebenen Modell.** Gezählt wird die WER, aus
denselben Quellen wie in der Modelltafel: bei einem trainierten
Stand aus seiner Kreuzvalidierung und für später dazugekommene Aufnahmen aus
der Auswertung in „hören", bei einem Grundmodell allein aus „hören". Teile und
Kopien erben den Wert ihres Originals. Bei gleicher WER entscheidet die
Kennung.

**Wie viele, steht beim Auftrag fest** - 70 % aller Aufnahmen, aufgerundet
(`laeufe.kern_anzahl`). Die Übersicht zeigt von Anfang an, worauf gerechnet
wird: „205 von 292 Aufnahmen".

**Fehlende Werte misst der Trainer vorher nach.** Hat das freigegebene Modell
eine Aufnahme nie gehört, steht sie in der Kernauswahl als `offen`. Vor der
ersten Faltung hört das Modell sie mit seinem Tempo
(Stufe „Kernauswahl", `bewerten.vervollstaendige_kern`); erst dann wird
gewählt. Abgewiesen wird ein Auftrag nur, wenn nichts freigegeben ist oder die
Gewichte des freigegebenen Standes fehlen.

**Der Kern ist für den Lauf der ganze Korpus.** Die übrigen 30 % kommen weder
zum Lernen noch zum Steuern noch in der Messung der Faltungen vor. Die
Kreuzvalidierung läuft auf eigenen Faltungen des Kerns
(`laeufe.verteile_kern`, nach dem Hash des Stamms), die
Plausibilitätsprüfung zieht nur aus dem Kern.

**Den Rest hört erst das Endmodell**, in der Auswertung von „hören": Für einen
Kernstand gelten dort nur die Kernaufnahmen als gehört
(`auswertung._gehoert_im_lauf`), ausgenommen Teile und Kopien einer
Kernaufnahme. Bis diese Auswertung gelaufen ist, hat ein Kernstand Werte nur
für den Kern, und die Modelltafel vergleicht ihn nur dort; danach stammen
seine Werte für den Kern aus den Faltungen, für den Rest vom Endmodell.

`kernauswahl.json` hält alles fest: Modell, Tempo, Anzahl, jede Aufnahme mit
WER und Stamm, die offenen, später die nachgemessenen, den Kern, die Schwelle
und seine Faltungen (`laeufe.mit_kern`). Der Trainer liest davon nur Kern und
Faltungen (`laeufe.kernfaltungen_aus`). Der Steckbrief nennt Umfang, Modell,
Schwelle und Nachgemessenes.

### Der Optionscode

Lauf und Stand heißen nach ihren Optionen, überall mit demselben Code
(`laeufe.optionscode`). Vorn Grundmodell und Methode, dahinter je Achse ein
Glied, wenn sie nicht auf ihrer Vorgabe steht:

| Achse | Werte | Glied |
|---|---|---|
| Grundmodell | small, medium, large-v3 | `S`, `M`, `L3` |
| Methode | Volles Feintuning, LoRA | `V`, `L` |
| LoRA-Ziele | q, v; alle; Encoder; Decoder | –, `Z`, `Ze`, `Zd` |
| LoRA-Rang | 32, 8, 64 | –, `R8`, `R64` |
| Auswahl | Alle Aufnahmen, Kernauswahl | –, `K` |
| Korrekturen | 0,5, 0,25, 0,75, 1,0, Verlauf | –, `Q25`, `Q75`, `Q1`, `Qv` |
| Selbsttraining | aus, an | –, `U` |
| Epochen | fest, geduldig | –, `E` |
| Steuergröße | Verlust, WER | –, `W` |
| Fenster | 30 s, gekürzt | –, `F` |
| Augmentierung | keine, SpecAugment, + Raum + Rauschen, + Tempo | –, `S`, `SR`, `SRP` |
| Tempo | aus, geschätzt, gesucht | –, `Tg`, `Ts` |
| Abschluss | bester, Mittel, WiSE-FT, beides | –, `C`, `I`, `CI` |
| Kontext | aus, Vokabular | –, `X` |

`ML-K-SRP-Ts-C` ist whisper-medium mit LoRA, auf dem Kern, voller
Augmentierung, gesuchtem Tempo und Checkpoint-Mittel.

**`A` tragen Läufe, die auch auf Rauschkopien lernten**: je Aufnahme eine
Kopie mit weißem Rauschen, 20 dB unter dem Signal. Angeboten wird das nicht;
ihre Stände gelten weiter. Gemessen ist nur an den Aufnahmen selbst, gezählt
werden nur sie (`laeufe.aufnahme_selbst`), und ihr Steckbrief nennt die
Rauschkopien.

Hinter dem Code steht die **Folge**: die Zahl der gelernten Aufnahmen - bei
der Kernauswahl die des Kerns, `ML-K-E-SRP-CI/205` - und ein Buchstabe,
sobald es Code und Zahl schon gibt - `/43`, `/43b`, `/43c`, nach
`z` weiter mit `aa` (`laeufe.titel`). Vergeben wird sie beim Auftrag, einer
über dem höchsten noch vorhandenen Buchstaben, und danach nie geändert.
`scripts/folge_nachtragen.py` trägt sie für Läufe ohne Folge nach. Ergebnisse
wie das gefundene Tempo oder α gehören nicht zum Code; sie stehen in der
Nebenzeile und im Steckbrief.

---

## Wie schnell gehört wird

Dysarthrische Sprache ist oft stark verlangsamt, und Whisper versteht sie
vorgespult besser. Der Faktor hängt am Sprecher:

| Wahl | Verfahren | Kosten |
|---|---|---|
| **aus** | nicht vorspulen | – |
| **geschätzt** | Aufnahmedauer ÷ geschätzte Sprechdauer der Texte | nichts |
| **gesucht** (0,75–4,0) | Stützstellen am unveränderten Grundmodell | ~1 Min. je Faltung |

**Die Schätzung** vergleicht je Faltung zwei Summen: die Sprechdauer der Texte
bei gewöhnlichem Tempo (`chunker.dauer`, plus eine Sekunde je Aufnahme für
Ansetzen und Abklingen) und die tatsächliche Dauer. Summen statt eines Mittels
über Quotienten, damit eine lange Pause oder eine kurze Aufnahme nicht
überwiegt. Gerundet auf eine Viertelstufe.

**Die Suche** dekodiert je Faltung bis zu zwei Dutzend Lernaufnahmen an acht
Stützstellen mit dem unveränderten Grundmodell. Gewinnt die oberste, wird
nachgelegt (3,5, dann 4,0). Am Ende werden die sechs Kurven übereinandergelegt
und das Minimum der gemittelten Kurve genommen - der Sieger einer einzelnen
Faltung wäre Zufall. Der Standardfehler steht je Stützstelle daneben.

Beide beantworten verschiedene Fragen - wie weit dieser Mensch von der Norm
abweicht, und wo das Modell ihn am besten versteht - und können weit
auseinanderliegen. Welcher Faktor besser ist, zeigt die Modelltafel. Gewählt
wird je Faltung auf ihren Lernzeilen, nie an Messdaten.

Der Faktor steht im Titel des Laufs, im Namen und Manifest des Standes, und
„schreiben" spult beim Diktieren genauso vor. Das Vorspulen gehört damit zum
Modell: Stände mit verschiedenem Tempo stehen in der Tafel nebeneinander wie
alle anderen.

---

## Die Ansichten

**Wie gemessen wird** erklärt Kreuzvalidierung und Endmodell und zeigt, wie schwer die
Faltungen sind. Die Aufnahmen selbst stehen unter „Meine Daten" in „hören".

**Training** beauftragt und zeigt die Läufe: je Lauf Code, Zustand, Umfang,
ein Balken über die sechs Faltungen samt Mittel und die Stufe. Kommen neue Aufnahmen
dazu, steht es da - „23 Aufnahmen sind dazugekommen, seit zuletzt etwas fertig
trainiert wurde". Von selbst angestoßen wird nichts: Ein Lauf belegt die Karte
und friert einen Stand des Korpus ein, und das soll jemand entscheiden.

**Beauftragen verlangt den Trainerschlüssel.** Eingetragen wird er unter
„Zugangsdaten", wie der Bearbeitungsschlüssel, einmal für alle Apps
(`packages/ui/schluessel.svelte.ts`). Er geht als `X-Trainer-Key` nur mit dem
Auftrag, dem Neustart und dem Löschen hinaus - und mit der Auskunft
`GET /api/zugang`, die sagt, ob er gilt. Danach richtet sich die Ansicht: Gilt
er nicht, ist „Training beauftragen" gesperrt, und ein Satz verweist auf die
Zugangsdaten. Ist `WORTLAUT_TRAINER_KEY` leer, sagt die Ansicht das und zeigt
keine Wahl. **Löschen ebenso nur mit ihm:** Wer trainieren darf, darf auch
wegwerfen. Solange der Server ihn nicht annimmt, zeigt keine Ansicht einen
Papierkorb. Zusehen, anhalten und freigeben verlangen ihn nie.

**Anhalten.** Ein wartender Lauf wird sofort zurückgenommen. Bei einem
rechnenden legt die Ansicht `halt` ins Laufverzeichnis; der Läufer schickt dem
Prozess SIGTERM, nach einer Minute ohne Antwort SIGKILL an die ganze Gruppe,
und trägt den Zustand notfalls selbst ein. Ein hängender Lauf - `laeuft`, aber
eine Viertelstunde ohne geschriebenes Byte - ist sofort angehalten. Fortsetzen
lässt sich ein Lauf nicht.

**Neu starten.** Gescheiterte und angehaltene Läufe bleiben stehen, bis jemand
sie neu startet oder löscht. Der Neustart rechnet denselben Auftrag auf
demselben Schnappschuss, beim Kern mit derselben Kernauswahl; der neue Lauf
bekommt eine eigene Kennung, behält Titel und Folge und ersetzt den alten
(`auftraege.starte_neu`).

**Löschen.** Der Papierkorb einer Karte nimmt den Lauf samt seinem Stand -
ein Stand ohne seinen Lauf könnte nicht mehr sagen, worauf er trainiert wurde.
Die Rückfrage nennt beides und ob der Stand freigegeben ist; die Freigabe geht
dann mit. Ein rechnender Lauf lässt sich nicht löschen, ein hängender schon.

**Der einzelne Lauf** zeigt Steckbrief, Protokoll und zwei Kurven über den
Schritten: Trainingsverlust und Validierung. Erst die zweite zeigt, wann das
Auswendiglernen beginnt. Ist der Lauf fertig, folgt der Vergleich mit der
Baseline.

### Gegen die Baseline

Die Frage ist, ob das Training das Modell besser gemacht hat. Die Baseline
liegt schon da: die Messungen des unveränderten Grundmodells in der
Auswertung von „hören" - dasselbe Modell, dieselben Aufnahmen, dieselbe
Rechnung (`wortlaut/metriken.py`). Verglichen wird nur, was beide Seiten
gemessen haben; jede Aufnahme des Standes stammt aus der Faltung,
die sie nicht kannte.

---

## Modelle - die eine Ansicht, auf der entschieden wird

Eine Tafel: die Grundmodelle aus `WORTLAUT_AUSWERTUNG_MODELLE` und darunter
jeder eigene Stand, mit **Genauigkeit**, **WER**, **CER** und **Rechenzeit**.
Der beste Wert je Spalte ist hervorgehoben; ein Klick auf die Überschrift
sortiert.

**Gemessen wird nichts neu.** Die Zahlen kommen aus der Auswertung in „hören"
(Grundmodelle, dazu jeder Stand auf den Aufnahmen, die er nicht kannte) und
aus der Bewertung jedes Laufs (`services/messwerte.py`).

**Verglichen wird nur, was alle gemessen haben.** Jedes Mittel läuft über die
Aufnahmen, die alle Modelle mit Messungen haben. Die Zeile über der Tafel nennt, wie viele das
sind. Die Zahl eines Modells ist damit keine Eigenschaft dieses Modells
allein: Fällt eine Zeile weg, wächst die Schnittmenge, und jede Zahl ändert
sich. Begrenzt eine einzelne Zeile den Boden um mehr als ein Viertel, nennt
die Tafel sie samt der Zahl, die ohne sie gälte; die Rückfrage beim Löschen
eines Laufs ebenso. Fehlt der gemeinsame Boden ganz, rechnet jede Zeile auf
dem, was sie hat, und die Seite sagt es.

**Ein Stand zählt nur die Faltungen, die in seinem Endmodell stecken.** Die
Tafel dient der Wahl dessen, was ausgeliefert wird, und eine ausgelassene
Faltung hat dazu nichts beigetragen. Ihre Aufnahmen fehlen dann nur in seiner
Zeile; den gemeinsamen Boden der übrigen schmälern sie nicht. Die Zeilen
stehen damit nicht mehr auf genau denselben Aufnahmen - darum steht unter dem
Namen „nur 5 von 6 Faltungen". Die Zahl in der Einzelansicht des Laufs zählt
weiter alle: Sie beschreibt das Training.

**Die Rechenzeit ist eine Eigenschaft der Maschine.** Jede Messung trägt ihr
Rechenwerk. Nennen nicht alle Zeilen dasselbe, vergleicht die Spalte nicht:
keine Bestmarke, jede Zahl mit ihrer Maschine.

### Wie weit die Zahlen tragen

**Sicherheit** schaltet unter jeder Zahl den 95-%-Bereich ein, als Bootstrap
über 2000 Ziehungen je Aufnahme (`wortlaut/streuung.py`). **Gegen** paart
jede Zeile mit einem gewählten Modell und zeigt den Abstand mit p-Wert; das ist schärfer als
zwei überlappende Bereiche. Eingeschaltet ändert sich keine Zahl - der Bereich
tritt daneben. Überlappen sich bester und zweitbester Wert einer Spalte, trägt
sie ein `≈`. Ein fertiger Lauf schreibt seine Bereiche ins Manifest.

### Freigeben

Ein fertiger Stand trägt `status: fertig`; **Freigeben** ist ein Knopf in der
Tafel, kein Automatismus. Freigegeben ist höchstens ein Modell je Sprecher,
auch ein Grundmodell, und `schreiben` diktiert sofort damit (siehe
[Der Entwurf](architektur.md#die-freigabe)).

Über der Tafel steht, was `schreiben` gerade geladen hat - mit denselben
Zahlen wie seine Zeile, aus derselben Rechnung. Die Auskunft kommt aus der API
von `schreiben`; antwortet es nicht, entfällt die Karte.

### Ein Name führt in die Einzelansicht

Jeder Modellname - in der Tafel, auf der Karte darüber und in der Tabelle der
Auswertung von „hören" - öffnet die Einzelansicht: bei einem eigenen Stand
seinen Lauf, bei einem Grundmodell dessen **Steckbrief** (`#/grundmodell/<name>`).

Der Steckbrief eines Grundmodells steht in zwei Teilen. **Was das Modell ist**,
aus der Modellkarte von OpenAI (`services/grundmodelle.py`): Veröffentlichung,
Parameter, Aufbau, Eingang, Sprachen, Trainingsdaten, Lizenz. **Was davon hier
liegt**, aus dem Modellcache gelesen: die CTranslate2-Fassung mit Revision,
Ladezeitpunkt und Größe, das Rechenwerk der Auswertung, ob und wie `lernen`
darauf trainiert, welche eigenen Stände darauf gewachsen sind und ob es
freigegeben ist. Die Parameterzahl wird an den Gewichten gegengeprüft
(float16, zwei Byte je Parameter). Darunter seine Zahlen aus der Tafel, neben
denen des freigegebenen Modells.

---

## Das Register der Läufe

Lauf und Modell liegen auf der Trainingsablage und gehen beim Löschen. Was es
braucht, um einen Lauf wissenschaftlich auszuwerten und neu zu rechnen, bleibt
im Register: `data/lernen/<sprecher_id>/register.sqlite`, eine Datei je
Sprecher (`services/register.py`, Schema mit Erklärung jeder Spalte in
`backend/db/migrations/001_register.sql`).

| Tabelle | Was | woher |
|---|---|---|
| `laeufe` | Auftrag, Zustand samt Metriken und Bootstrap-Intervall, Manifest des Modells (Rezept, Abschluss, Endmodell, Grundmodell daneben, Plausibilitätsprüfung), Kernauswahl, Protokoll, Umgebung, wann gelöscht | Laufverzeichnis, Registry, Läufer |
| `daten` | jede Zeile des Manifests: Aufnahme, Faltung, Gewicht, Herkunft, Text wie damals, SHA-256 der Audiodatei | `manifest.jsonl` |
| `messungen` | was ein Modell aus einer Aufnahme machte: `faltung` aus der Kreuzvalidierung, `endmodell` aus der Auswertung von „hören" | `bewertung.jsonl`, Tabelle `erkennungen` |
| `ereignisse` | Verlust je Schritt, Validierung je Durchgang, Stufen, gescheiterte Faltungen | `fortschritt.jsonl` |

Die Sicht `uebersicht` zeigt je Lauf die Eckdaten ohne JSON.

**Welche Läufe vergleichbar sind, sagt `datensatz`**: ein Fingerabdruck über
Aufnahme, Faltung, Herkunft, Text und Audiodatei jeder Zeile von
`daten` (`register.datensatz`). Gleich heißt: dieselben Daten, dieselben
Faltungen - zwei solche Läufe unterscheiden sich nur in ihren Optionen, und
der gepaarte Vergleich ihrer `messungen` (`streuung.unterschied`) misst deren
Wirkung. Die Zahl hinter dem Optionscode genügt dafür nicht: Gleich viele
Aufnahmen können andere sein. Die Umgebung
nennt den Quellstand (SHA-256 über den Code des Trainers - dieselbe Zahl über
einen Checkout gerechnet findet den Commit), Python, die Bibliotheken, die
Revision des Grundmodells und die Karte.

**Eingetragen wird, wenn ein Lauf endet** (vom Läufer, der die Umgebung
kennt), **bevor er gelöscht wird** (mit dem, was „hören" mit seinem Modell
gemessen hat; scheitert das, bleibt der Lauf), und von Hand mit
`scripts/register.py` für alle vorhandenen. Ein zweites Eintragen ersetzt, was
aus dem Laufverzeichnis kommt; Umgebung, Messungen des Endmodells, Zeitpunkt
des Löschens und der erste Fingerabdruck jeder Audiodatei bleiben.

Auf Aufnahmen und Vorlagen zeigt das Register mit deren Kennung; mit
`ATTACH` an `korpus/<sprecher_id>/hoeren.sqlite` kommt der Rest dazu. Der
Sprecher steht nur als Kennung darin. Kein Weg der Oberfläche führt hierher;
gelesen wird mit `sqlite3`.

---

## Von der Kommandozeile

```
make train SPEAKER=spr_7f2a RECIPE=whisper_lora [MODELL=large-v3] [ACHSEN="dauer=geduldig"]
make release JOB=job_01J8…
```

`scripts/trainieren.py` bestellt über dieselbe Stelle wie die Oberfläche
(`services/auftraege.bestelle`) und liest Zustand und Protokoll mit, bis der
Lauf endet; gerechnet wird im Läufer. Das Rezept (`training/rezepte/`) nennt
die Methode, `MODELL` das Grundmodell, die übrigen Achsen stehen auf ihrer
Vorgabe. `scripts/freigeben.py` gibt den Stand eines Laufs frei wie der Knopf
unter **Modelle** (`services/freigabe.py`). Im Betrieb beide im Container,
siehe [Betrieb](betrieb.md#der-trainer).

---

## Endpunkte

```
GET    /lernen/api/aufteilung               die Faltungen in Zahlen
GET    /lernen/api/laeufe                   die Liste, ohne Kurven
POST   /lernen/api/laeufe                   beauftragen                    + X-Trainer-Key
GET    /lernen/api/laeufe/{id}              Steckbrief, Kurven, Vergleich, Protokoll
POST   /lernen/api/laeufe/{id}/abbruch      anhalten
POST   /lernen/api/laeufe/{id}/neustart     neu starten, ersetzt ihn     + X-Trainer-Key
DELETE /lernen/api/laeufe/{id}              löschen, samt Stand          + X-Trainer-Key
GET    /lernen/api/modelle                  die Tafel
                                            ?intervall=aus|aufnahme&vergleich_mit=<ref>
POST   /lernen/api/modelle/freigabe         { ref } - leer nimmt die Freigabe zurück
GET    /lernen/api/modelle/grundmodell/{n}  Steckbrief eines Grundmodells, seine Zahlen
GET    /gesundheit                          ohne Zugang
```

Jeder Weg außer `/gesundheit` verlangt den Sprecherzugang und leitet die
Kennung daraus ab. Verwaltung und Aufsicht kommen nicht durch: Ein Modell
gehört einem Menschen. Die Liste trägt keine Kurven, denn sie wird im Takt
abgefragt.

---

## Nahtstellen

| Was | Wo | Richtung |
|---|---|---|
| Korpus | `data/korpus/<sprecher_id>/` | nur lesend |
| Baseline | Tabelle `erkennungen` im Korpus | nur lesend |
| Läufe | `data/snapshots/<job_id>/` | schreibend; der Trainer schreibt mit |
| Modellstände | `data/modelle/<sprecher_id>/<version>/` | schreibend; „schreiben" liest |
| Freigabe | `data/modelle/<sprecher_id>/freigabe.json` | schreibend; „schreiben" liest |
| Register der Läufe | `data/lernen/<sprecher_id>/register.sqlite` | schreibend; der Trainer schreibt mit |
| Was geladen ist | `GET /schreiben/api/model` | lesend |

Dass der Korpus nur gelesen wird, hält ein Test fest
(`apps/lernen/tests/test_trennung.py`).
