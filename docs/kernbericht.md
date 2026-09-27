# Kernbericht: Wie robust ist das Lernen gegenüber schlechten Daten?

Ein Lauf mit Kernauswahl (`K`) lernt nur auf den besten 70 % der Aufnahmen
(siehe [lernen.md](lernen.md#die-kernauswahl)). Dieser Bericht vergleicht das
erste Kernmodell mit den Läufen auf allen Aufnahmen: auf dem Kern, auf dem
aussortierten Rest und auf beidem zusammen.

> **Stand: 27. September 2026.** Sprecher B wie im
> [Modellbericht](modellbericht.md), 292 Aufnahmen. Grundlage sind
> `bewertung.jsonl` und `kernauswahl.json` der Läufe und die Tabelle
> `erkennungen` des Korpus, den Rest hat das Kernmodell in der Auswertung von
> „hören" gehört. Namen und Kennungen stehen bewusst nicht im Bericht.

---

## 1. Die Frage und der Vergleich

Der Kern sind die 205 Aufnahmen mit der kleinsten WER des bei der Auswahl
freigegebenen `ML-A-E-SRP-CI/292` (Original, aus seiner Kreuzvalidierung).
Die Grenze liegt genau bei WER = 1: Im Kern ist keine Aufnahme schlechter, im
Rest keine besser. Die übrigen 87 Aufnahmen nennt dieser Bericht den **Rest**.

Jede Aufnahme ist von einem Modell gemessen, das sie nicht gelernt hat - beim
Kernmodell auf dem Kern aus seinen Kernfaltungen und auf dem Rest vom
Endmodell in „hören", bei den Läufen auf allen Aufnahmen aus deren
Kreuzvalidierung, bei den unveränderten Grundmodellen aus „hören". Vier
Rest-Aufnahmen sind Teile eines Originals, dessen andere Teile im Kern liegen;
sie gelten dem Kernmodell als gehört und bleiben ungemessen. Der Rest zählt
deshalb in allen Vergleichen 83 Aufnahmen, alle zusammen 288. Maß wie im Modellbericht: WER je Aufnahme als
Mittel der Fassungen `original` und `rauschen`, Vergleiche gepaart, Bootstrap
über Stämme (Teile und Kopien einer Aufnahme ziehen zusammen), dazu der
Aufschlag für das Trainingsrauschen (Variationskoeffizient 5,8 %).

**Warum das die Frage trifft.** In jeder Faltung lernt das Kernmodell rund
171 Kernaufnahmen. Ein Lauf auf allen 292 lernt ebenfalls rund 171
Kernaufnahmen - und dazu rund 72 aus dem Rest. `ML-K-E-SRP-CI/205` gegen
`ML-E-SRP-CI/292` ist also dasselbe Rezept mit und ohne die schlechten Daten
im Training, gemessen auf den guten.

| Stand | gelernt | WER Kern [95 %] | WER > 1 | Dauer |
|---|---|---|---|---|
| **`ML-K-E-SRP-CI/205`** | Kern | **0,672** [0,620; 0,727] | 10 % | 43 min |
| `ML-E-SRP-CI/292` | alle | 0,617 [0,569; 0,674] | 6 % | 57 min |
| `ML-A-E-SRP-CI/292` | alle, mit Abwandlungen | 0,574 [0,536; 0,616] | 3 % | 76 min |
| `SV-E-SRP-CI/292` | alle, `small` voll | 0,674 [0,636; 0,712] | 9 % | 32 min |
| `ML-E-SRP-CI/43` | 43 frühe | 0,910 [0,868; 0,956] | 26 % | - |
| `ML-A-E-SRP-CI/43` | 43 frühe, mit Abwandlungen | 0,988 [0,910; 1,075] | 29 % | - |
| `large-v3` unverändert | - | 1,333 [1,268; 1,405] | 67 % | - |
| `small` unverändert | - | 1,520 [1,448; 1,606] | 89 % | - |
| `medium` unverändert | - | 1,626 [1,533; 1,729] | 87 % | - |

![Alle Stände und Baselines auf den 205 Kernaufnahmen](bilder/kernbericht-kern.svg)

*Abbildung 1.* Das Kernmodell liegt auf seinen eigenen Daten hinter beiden
`medium`-Läufen auf allen Aufnahmen und gleichauf mit dem vollen Feintuning
von `small`.

---

## 2. Ergebnis: Die schlechten Daten schaden nicht

![Kernmodell gegen die anderen, gepaarte Unterschiede](bilder/kernbericht-kontraste.svg)

*Abbildung 2.* Positiv heißt: Das Kernmodell ist schlechter.

| Kernmodell gegen | Δ WER | 95 % Bootstrap | 95 % mit Training | z | Kern besser / schlechter |
|---|---|---|---|---|---|
| `ML-E-SRP-CI/292` | +0,055 | [+0,006; +0,103] | [−0,060; +0,169] | 0,9 | 74 / 94 |
| `ML-A-E-SRP-CI/292` | +0,098 | [+0,054; +0,145] | [−0,013; +0,208] | 1,7 | 67 / 104 |
| `SV-E-SRP-CI/292` | −0,002 | [−0,047; +0,049] | [−0,120; +0,117] | 0,0 | 110 / 69 |
| `ML-E-SRP-CI/43` | −0,238 | [−0,285; −0,189] | [−0,375; −0,100] | **−3,4** | 165 / 33 |
| `ML-A-E-SRP-CI/43` | −0,316 | [−0,403; −0,235] | [−0,476; −0,156] | **−3,9** | 166 / 25 |

* **Gegen dasselbe Rezept auf allen Aufnahmen** ist das Kernmodell 0,055
  schlechter. Über Aufnahmen allein ist das nachweisbar (Permutation
  p ≈ 0,03), mit Trainingsrauschen nicht. Sicher ist die Richtung: Die 87
  schlechten Aufnahmen haben das Lernen auf den guten nicht verschlechtert,
  eher verbessert.
* **Gegen keinen Lauf auf allen Aufnahmen** ist das Kernmodell besser.
* **Mehr Daten wirken, auch unsaubere.** Gegen die Läufe auf den 43 frühen
  Aufnahmen gewinnt das Kernmodell 0,24 bis 0,32, auch mit Trainingsrauschen
  klar. Der große Schritt kommt von der Datenmenge, nicht vom Aussortieren.

### Die Auswahl bevorzugt die anderen

Der Kern wurde nach der WER von `ML-A-E-SRP-CI/292` gewählt, also gerade die
Aufnahmen, auf denen dieser Lauf gut war. Auf ihnen ist er zwangsläufig etwas
zu gut gemessen; sein Vorsprung von 0,098 ist zum Teil Auswahl.

`ML-E-SRP-CI/292` ist davon nicht mehr betroffen als das Kernmodell: Je
Aufnahme hängt er mit dem Auswähler kaum enger zusammen (r = 0,55) als mit dem
Kernmodell (r = 0,57), und vom Mittel über alle 292 zum Mittel über den Kern
fällt er im selben Verhältnis wie der Auswähler (0,66 gegen 0,67). Der
Vergleich mit dem gleichen Rezept ist damit der saubere, und er fällt gegen
das Kernmodell aus.

---

## 3. Auf dem Rest: kein Unterschied

| Stand | vom Rest gelernt | WER Rest [95 %] | Median | WER > 1 |
|---|---|---|---|---|
| **`ML-K-E-SRP-CI/205`** | nichts | **1,696** [1,414; 2,055] | 1,30 | 72 % |
| `ML-E-SRP-CI/292` | rund 69 je Faltung | 1,692 [1,365; 2,096] | 1,25 | 63 % |
| `ML-A-E-SRP-CI/292` | rund 69 je Faltung | 1,508 [1,371; 1,676] | 1,30 | 80 % |
| `SV-E-SRP-CI/292` | rund 69 je Faltung | 1,415 [1,213; 1,676] | 1,17 | 60 % |
| `ML-E-SRP-CI/43` | nichts | 1,659 [1,284; 2,236] | 1,20 | 65 % |
| `ML-A-E-SRP-CI/43` | nichts | 2,257 [1,867; 2,734] | 1,63 | 89 % |
| `large-v3` unverändert | - | 1,972 [1,761; 2,195] | 1,70 | 86 % |
| `small` unverändert | - | 2,218 [1,959; 2,496] | 1,83 | 96 % |
| `medium` unverändert | - | 2,482 [2,159; 2,866] | 2,10 | 93 % |

![Kernmodell gegen die Läufe auf allen Aufnahmen, auf Kern, Rest und allen](bilder/kernbericht-gesamt.svg)

*Abbildung 3.* Auf dem Rest sind die Intervalle breit. Kein Band mit
Trainingsrauschen schließt die Null aus.

| Kernmodell gegen | Δ Rest | 95 % mit Training | z | Δ alle | 95 % mit Training | z |
|---|---|---|---|---|---|---|
| `ML-E-SRP-CI/292` | +0,004 | [−0,327; +0,335] | 0,0 | +0,040 | [−0,126; +0,206] | 0,5 |
| `ML-A-E-SRP-CI/292` | +0,187 | [−0,239; +0,614] | 0,9 | +0,123 | [−0,055; +0,302] | 1,4 |
| `SV-E-SRP-CI/292` | +0,281 | [−0,117; +0,679] | 1,4 | +0,080 | [−0,098; +0,257] | 0,9 |
| `ML-E-SRP-CI/43` | +0,036 | [−0,482; +0,555] | 0,1 | −0,159 | [−0,373; +0,055] | −1,5 |
| `ML-A-E-SRP-CI/43` | −0,562 | [−1,066; −0,057] | **−2,2** | −0,387 | [−0,615; −0,158] | **−3,3** |

* **Gegen dasselbe Rezept auf allen Aufnahmen** liegt das Kernmodell auf dem
  Rest gleichauf: 1,696 gegen 1,692, gleicher Median, 40 Aufnahmen besser,
  37 schlechter. Die Rest-Aufnahmen zu lernen hat auf den übrigen
  Rest-Aufnahmen nichts gebracht.
* **Gegen `SV-E-SRP-CI/292`** fällt es auf dem Rest um 0,28 zurück. Über
  Aufnahmen ist das knapp (p ≈ 0,05), mit Trainingsrauschen nicht
  nachweisbar. Auf dem Kern lagen beide gleichauf.
* **Über alle 288** ist das Kernmodell 0,04 schlechter als dasselbe Rezept,
  nicht nachweisbar (p ≈ 0,23), und 0,12 schlechter als
  `ML-A-E-SRP-CI/292`, nachweisbar über Aufnahmen (p ≈ 0,01), nicht über das
  Trainingsrauschen hinaus. Auf keinem Teil liegt es vor einem Lauf auf allen
  Aufnahmen.

---

## 4. Was „schlecht" hier heißt

![Dieselben Modelle auf Kern und Rest](bilder/kernbericht-rest.svg)

*Abbildung 4.* Der Rest ist für jedes Modell schwer, auch für die
unveränderten und für die beiden Modelle, die keine dieser Aufnahmen gelernt
haben.

Die Rest-Aufnahmen sind so lang wie die Kernaufnahmen (je rund 20 s), tragen
aber nur 5,5 statt 9 Wörter: 4,6 statt 2,5 Sekunden je Wort. Das spricht für
sehr langsames, stockendes Sprechen, lange Pausen oder Aufnahmen, deren Text
nicht ganz zum Gesprochenen passt. Welcher Anteil davon falsch beschriftet
und welcher nur schwer verständlich ist, lässt sich aus Dauer und Wortzahl
allein nicht trennen.

**Der Rest ist kaum lernbar.** Die feinabgestimmten Stände landen dort bei
einem Median von 1,2 bis 1,3, nur `ML-A-E-SRP-CI/43` höher - ob sie keine
Rest-Aufnahme gelernt haben wie das Kernmodell und `ML-E-SRP-CI/43` oder rund
69 wie die Läufe auf allen Aufnahmen. Was ein Modell aus den anderen Rest-Aufnahmen lernt, hilft
ihm bei den ungehörten nicht. Das passt eher zu Text, der nicht zum
Gesprochenen passt, als zu Aufnahmen, die nur schwer zu verstehen sind: An
schwerer Aussprache sollte ein Modell mit Übung zulegen.

---

## 5. Grenzen

* **Der Rest ist klein und streut stark.** 83 Aufnahmen, einzelne mit WER
  über 10; die Intervalle dort sind rund sechsmal so breit wie auf dem
  Kern. Ein kleiner Unterschied auf dem Rest ist damit nicht auszuschließen.
* **Das Kernmodell misst den Rest mit dem Endmodell.** Es hat alle 205
  Kernaufnahmen gelernt, eine Faltung nur rund 171. Das begünstigt das
  Kernmodell auf dem Rest leicht - und doch liegt es dort nicht vorn.
* **Einzelläufe.** Das Trainingsrauschen stammt aus vier Wiederholungen auf
  43 Aufnahmen (Modellbericht, Abschnitt 3). Auf 205 Aufnahmen ist es
  vermutlich kleiner, die Intervalle „mit Training" also eher zu breit.
* **Ein Sprecher, ein Anteil.** Geprüft ist nur der Schnitt bei 70 % und nur
  bei Sprecher B.
* **Schlecht nach dem Urteil eines Modells.** Der Rest ist, was
  `ML-A-E-SRP-CI/292` schlecht erkannt hat. Das mischt schwer Verständliches
  mit womöglich falsch Beschriftetem.

---

## 6. Nebenbefund: Rauschen scheint einem Lauf ohne Rauschtraining zu helfen

In der Modelltafel liegt `ML-E-SRP-CI/292` auf der Fassung `rauschen` besser
als auf dem Original - obwohl er, anders als `ML-A-E-SRP-CI/292`, nie mit
Abwandlungen trainiert hat und die übrigen Stände auf `rauschen` eher
schlechter abschneiden. Die plausibelste Erklärung: **Zufall, getragen von
wenigen Aufnahmen, auf denen das Modell in eine Schleife gerät.** Eine
Robustheit gegen Rauschen ist es nicht.

| Stand | WER Original | WER Rauschen | Δ [95 %] | Median Δ | Rauschen besser / schlechter | Δ ohne \|Δ\| > 2 |
|---|---|---|---|---|---|---|
| `ML-E-SRP-CI/292` | 0,947 | 0,918 | −0,029 [−0,133; +0,071] | 0 | 101 / 104 | −0,013 (7 weg) |
| `ML-A-E-SRP-CI/292` | 0,852 | 0,854 | +0,002 [−0,067; +0,068] | 0 | 78 / 101 | +0,020 (5 weg) |
| `SV-E-SRP-CI/292` | 0,909 | 0,886 | −0,023 [−0,099; +0,039] | 0 | 79 / 107 | +0,014 (2 weg) |
| `ML-E-SRP-CI/43`, zwei Wiederholungen | 0,761 / 0,821 | 0,809 / 0,959 | +0,048 / +0,138 | 0 / +0,07 | 12 / 14, 7 / 23 | −0,010 / +0,133 |

Alle 292 Aufnahmen aus der Kreuzvalidierung der Läufe, gepaart je Aufnahme,
Bootstrap über Stämme.

* **Der Vorteil sitzt im Mittel, nicht in der Masse.** Der Median des
  Unterschieds ist 0, Rauschen hilft auf 101 Aufnahmen und schadet auf 104.
  Ohne die sieben Aufnahmen, auf denen die beiden Fassungen um mehr als 2 WER
  auseinanderliegen, schrumpft der Vorteil von 0,029 auf 0,013. Das Intervall
  schließt die Null weit ein, und das Trainingsrauschen (rund 0,05) ist
  größer als der ganze Effekt.
* **Die Ausreißer sind Schleifen.** Auf dem Original wiederholt das Modell
  eine Silbe oder einen Satz, bis das Fenster voll ist („Gedei-ge-er-ge-er-…",
  „Die Strasse ist sehr flach." dreimal, „Das war's für heute. Bis zum
  nächsten Mal."), auf der verrauschten Fassung bricht es früher ab. Meist
  sind es kurze Aufnahmen: Bei zwei Wörtern Vorlage macht eine Schleife eine
  WER von 5 bis 14, und je Aufnahme ist die WER nach oben offen. Wenige
  solche Fälle bewegen das Mittel mehr als hundert gewöhnliche.
* **Ob eine Fassung in die Schleife gerät, ist fast Münzwurf.** Das
  Rauschen liegt 20 dB unter dem Pegel der ganzen Aufnahme und füllt vor
  allem die langen Pausen dieser Sprecherin - vermutlich genau dort, wo
  Whisper mangels Sprache aus dem eigenen Text weiterschreibt. Eine kleine Änderung im Ton
  kippt eine Schleife in die eine oder die andere Richtung. Dieselbe
  Richtung zeigt deshalb auch `SV-E-SRP-CI/292` im Mittel (−0,023), ebenfalls
  ohne Rauschtraining; dasselbe Rezept auf 43 Aufnahmen zeigt die
  entgegengesetzte (+0,048 und +0,138). Mit oder ohne Rauschtraining sagt
  hier nichts voraus.
* **Nach der Zahl der Aufnahmen** ist `ML-E-SRP-CI/292` am ehesten
  gleichgültig gegen Rauschen (101 / 104), die beiden anderen Läufe auf allen
  Aufnahmen werden eher schlechter (78 / 101 und 79 / 107). Besser auf
  Rauschen ist keiner.

**Die Modelltafel rechnet derzeit auf anderem Boden.** Am selben Tag wurde
der Korpus neu geschnitten und eingelesen: Die neuen Stücke sind dieselben
Buchseiten wie die, auf denen die Läufe gelernt haben, nur anders geteilt.
Für die trainierten Stände sind sie also nicht ungehört. Und die Auswertung
von „hören" misst sie erst nach und nach; beim Schreiben dieses Abschnitts
standen in der Tafel 82 gemeinsame Aufnahmen. Auf diesem Boden wechselt das
Vorzeichen je nach Teilmenge - auf den alten Aufnahmen ist
`ML-E-SRP-CI/292` mit Rauschen 0,010 schlechter, auf den neuen 0,150
besser -, bei einem Median nahe 0 für jeden Stand und jedes Grundmodell.
Für einen Vergleich der Fassungen taugt die Tafel erst wieder, wenn die
Stände auf dem neuen Korpus neu gerechnet sind.

**Folgerung:** Ein Mittel über die WER je Aufnahme ist bei dieser Sprecherin
schleifenanfällig. Für Aussagen über Fassungen zählen Median und die Zahl
besser / schlechter; das Mittel allein trägt einen Unterschied dieser Größe
nicht.

---

## 7. Fazit

**Das Lernverfahren ist robust gegenüber den schlechten Daten dieses
Korpus.** Die 30 % am schlechtesten erkannten Aufnahmen im Training haben das
Ergebnis auf den übrigen 70 % nicht verschlechtert; ohne sie ist dasselbe
Rezept dort 0,055 schlechter, nachweisbar über Aufnahmen, nicht über das
Trainingsrauschen hinaus. Auf dem Rest selbst ändert das Aussortieren nichts:
Das Kernmodell liegt dort gleichauf mit demselben Rezept auf allen
Aufnahmen, und beide bleiben bei einem Median um 1,3. Den großen
Gewinn bringt die Menge: Vom Lauf auf den 43 frühen Aufnahmen zum Kernmodell
sind es auf dem Kern 0,24 WER, zum selben Rezept auf allen 292 0,29.

Für die Praxis: **alle Aufnahmen lernen, nicht aussortieren.** Die
Kernauswahl spart ein Viertel Rechenzeit, bringt weder auf den guten noch auf
den schlechten Daten etwas und liegt über alle 288 hinter jedem Lauf auf
allen Aufnahmen, wenn auch nicht über das Trainingsrauschen hinaus. Bester
Stand bleibt `ML-A-E-SRP-CI/292`: vorn auf dem Kern, mit dem
Vorbehalt, dass sein Vorsprung dort zum Teil aus der Auswahl stammt, und über
alle 288 mit 0,844 gegen 0,967 des Kernmodells. Der Rest verdient
einen Blick im Zuschnitt: Lernen hilft dort nicht.
