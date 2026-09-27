# Kernbericht: Wie robust ist das Lernen gegenüber schlechten Daten?

Ein Lauf mit Kernauswahl (`K`) lernt nur auf den besten 70 % der Aufnahmen
(siehe [lernen.md](lernen.md#die-kernauswahl)). Dieser Bericht vergleicht das
erste Kernmodell mit den Läufen auf allen Aufnahmen - und zwar nur dort, wo
das Kernmodell überhaupt gemessen ist: auf seinem Kern.

> **Stand: 27. September 2026.** Sprecher B wie im
> [Modellbericht](modellbericht.md), 292 Aufnahmen. Grundlage sind
> `bewertung.jsonl` und `kernauswahl.json` der Läufe und die Tabelle
> `erkennungen` des Korpus. Namen und Kennungen stehen bewusst nicht im
> Bericht.

---

## 1. Die Frage und der Vergleich

Der Kern sind die 205 Aufnahmen mit der kleinsten WER des bei der Auswahl
freigegebenen `ML-A-E-SRP-CI/292` (Original, aus seiner Kreuzvalidierung).
Die Grenze liegt genau bei WER = 1: Im Kern ist keine Aufnahme schlechter, im
Rest keine besser. Die übrigen 87 Aufnahmen nennt dieser Bericht den **Rest**.

Verglichen wird auf den 205 Kernaufnahmen, jede gemessen von einer Faltung,
die sie nicht gelernt hat - beim Kernmodell aus seinen Kernfaltungen, bei den
Läufen auf allen Aufnahmen aus deren Kreuzvalidierung, bei den unveränderten
Grundmodellen aus „hören". Maß wie im Modellbericht: WER je Aufnahme als
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

## 3. Was „schlecht" hier heißt

![Dieselben Modelle auf Kern und Rest](bilder/kernbericht-rest.svg)

*Abbildung 3.* Der Rest ist für jedes Modell schwer, auch für die
unveränderten und für `ML-E-SRP-CI/43`, das keine dieser Aufnahmen gelernt
hat.

Die Rest-Aufnahmen sind so lang wie die Kernaufnahmen (je rund 20 s), tragen
aber nur 5,5 statt 9 Wörter: 4,6 statt 2,5 Sekunden je Wort. Das spricht für
sehr langsames, stockendes Sprechen, lange Pausen oder Aufnahmen, deren Text
nicht ganz zum Gesprochenen passt. Welcher Anteil davon falsch beschriftet
und welcher nur schwer verständlich ist, lässt sich aus den Zahlen nicht
trennen.

---

## 4. Grenzen

* **Der Rest ist für das Kernmodell noch nicht gemessen.** Die Auswertung in
  „hören" steht aus; erst sie zeigt, was das Kernmodell auf schweren
  Aufnahmen kostet. Zu erwarten ist dort ein größerer Rückstand als auf dem
  Kern.
* **Einzelläufe.** Das Trainingsrauschen stammt aus vier Wiederholungen auf
  43 Aufnahmen (Modellbericht, Abschnitt 3). Auf 205 Aufnahmen ist es
  vermutlich kleiner, die Intervalle „mit Training" also eher zu breit.
* **Ein Sprecher, ein Anteil.** Geprüft ist nur der Schnitt bei 70 % und nur
  bei Sprecher B.
* **Schlecht nach dem Urteil eines Modells.** Der Rest ist, was
  `ML-A-E-SRP-CI/292` schlecht erkannt hat. Das mischt schwer Verständliches
  mit womöglich falsch Beschriftetem.

---

## 5. Fazit

**Das Lernverfahren ist robust gegenüber den schlechten Daten dieses
Korpus.** Die 30 % am schlechtesten erkannten Aufnahmen im Training haben das
Ergebnis auf den übrigen 70 % nicht verschlechtert; ohne sie ist dasselbe
Rezept dort 0,055 schlechter, nachweisbar über Aufnahmen, nicht über das
Trainingsrauschen hinaus. Den großen Gewinn bringt die Menge: Vom Lauf auf den 43 frühen Aufnahmen
zum Kernmodell sind es 0,24 WER, zum selben Rezept auf allen 292 0,29.

Für die Praxis: **alle Aufnahmen lernen, nicht aussortieren.** Die
Kernauswahl spart ein Viertel Rechenzeit, bringt auf den guten Daten nichts
und lässt das Modell die schweren nie hören. Bester Stand auf dem Kern bleibt
`ML-A-E-SRP-CI/292`, mit dem Vorbehalt, dass sein Vorsprung zum Teil aus der
Auswahl stammt.
