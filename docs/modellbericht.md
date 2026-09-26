# Modellbericht: alle trainierten Stände im Vergleich

Ein kurzer Bericht über jeden Trainingslauf, der bis heute Spuren hinterlassen
hat, und die Frage, welche Optionen nach den bisherigen Messungen am besten
abschneiden - mit der Einschränkung, wie weit die Zahlen das tragen.

> **Stand: 26. September 2026.** Grundlage sind die 17 Laufverzeichnisse unter
> `snapshots/`, die 15 Modellstände unter `modelle/` (beides in
> `WORTLAUT_TRAININGSABLAGE`) und die Baseline-Messungen aus den Korpora von
> „hören". Nachrechnen lässt sich alles aus `bewertung.jsonl` je Lauf und der
> Tabelle `erkennungen` des jeweiligen Korpus.
>
> **Datenschutz.** Die Sprecher heißen hier **A** und **B**. Namen und
> Kennungen stehen bewusst nicht im Bericht; die Zuordnung ergibt sich nur für
> den, der ohnehin Zugang zur Trainingsablage hat.

---

## 1. Bestand

Trainiert wurde für zwei Sprecher:

| | Sprecher A | Sprecher B |
|---|---|---|
| gültige Aufnahmen heute | 207 | 43 |
| Gesamtdauer | 37 min | 13 min |
| Läufe | 3 | 14 |
| freigegebener Stand | `ML-A-E-SRP-CI/166` | `ML-E-SRP-CI/43` |

Ein dritter Zugang hat keinen eigenen Stand; für ihn ist das unveränderte
`medium` freigegeben.

Alle Läufe sind LoRA auf `q_proj`/`v_proj` (Rang 32, α 64, Lernrate 1e-3), mit
Early Stopping (`E`), voller Augmentierung (`SRP`) und sechsfacher
Kreuzvalidierung. Sie unterscheiden sich in Grundmodell, Datensatz, Tempo und
Abschluss - lesbar am Optionscode (siehe [lernen.md](lernen.md#der-optionscode)).

**Die zwei Läufe ohne Stand.** `ML-E-SRP-CI/43b` und `/43c` wurden in derselben
Minute beauftragt wie `/43d` und bekamen denselben Versionsnamen; `/43d` hat
ihre Modellstände beim Eintragen überschrieben (behoben in `907892c`). Auftrag,
Zustand und `bewertung.jsonl` liegen noch da, die Messwerte sind also
vollständig - nur die Gewichte fehlen. Für diesen Bericht sind sie wertvoll:
Zusammen mit `/43` und `/43d` sind es **vier Wiederholungen desselben Rezepts
auf denselben Faltungen** (Abschnitt 3).

### Tabelle 1: alle Läufe

WER = mittlere Wortfehlerrate je Messeinheit (Aufnahme × Fassung `original`
und `rauschen`), jede Aufnahme gemessen von der Faltung, die sie nicht kannte.
In Klammern das 95-%-Bootstrap-Intervall über Aufnahmen, wie es der Lauf selbst
gespeichert hat. Die Zahlen gelten nur **innerhalb** eines Sprechers und einer
Aufnahmenzahl; über Zeilen mit verschiedenen Aufnahmen hinweg sind sie kein
Vergleich (Abschnitt 5).

| Sprecher | Lauf | Grundmodell | WER [95 %-KI] | CER | Dauer | Stand |
|---|---|---|---|---|---|---|
| A | `SL-A-E-SRP-CI/132` | small | 0,394 [0,331; 0,479] | 0,212 | 13 min | ja |
| A | `ML-A-E-SRP-CI/134` | medium | 0,294 [0,236; 0,360] | 0,165 | 40 min | ja |
| A | `ML-A-E-SRP-CI/166` | medium | 0,290 [0,237; 0,362] | 0,168 | 51 min | **freigegeben** |
| B | `ML-E-SRP-CI/20` | medium | 0,973 [0,774; 1,233] | 0,651 | 16 min | ja, Prüfung: ausgefranst |
| B | `ML-E-SRP-CI/20b` (Tempo fest 2,0) | medium | 0,928 [0,775; 1,135] | 0,611 | 15 min | ja |
| B | `ML-E-SRP-CI/22` | medium | 1,040 [0,854; 1,246] | 0,645 | 17 min | ja |
| B | `SL-E-SRP-CI/22` | small | 0,949 [0,825; 1,089] | 0,611 | 5 min | ja |
| B | `ML-E-SRP-CI/43` | medium | 0,889 [0,741; 1,070] | 0,504 | 19 min | **freigegeben** |
| B | `ML-E-SRP-CI/43b` | medium | 0,785 [0,683; 0,908] | 0,463 | 19 min | **überschrieben** |
| B | `ML-E-SRP-CI/43c` | medium | 0,890 [0,746; 1,059] | 0,507 | 19 min | **überschrieben** |
| B | `ML-E-SRP-CI/43d` | medium | 0,860 [0,755; 0,985] | 0,493 | 19 min | ja |
| B | `ML-E-SRP-Ts-CI/43` (Tempo 3,0) | medium | 0,940 [0,839; 1,065] | 0,570 | 54 min | ja |
| B | `ML-A-E-SRP-CI/43` | medium | 0,910 [0,760; 1,107] | 0,528 | 21 min | ja |
| B | `ML-A-E-SRP-Ts-CI/43` (Tempo 3,0) | medium | 0,895 [0,811; 0,994] | 0,531 | 55 min | ja |
| B | `SL-E-SRP-CI/43` | small | 0,907 [0,826; 1,005] | 0,540 | 8 min | ja |
| B | `SL-E-SRP-Ts-CI/43` (Tempo 2,0) | small | 1,000 [0,910; 1,103] | 0,594 | 30 min | ja |
| B | `SL-E-SRP-C/43` | small | 0,964 [0,913; 1,021] | 0,675 | 8 min | ja |

Das von der Kreuzvalidierung gewählte WiSE-FT-α lag bei allen Läufen mit
Interpolation zwischen 0,2 und 0,5, meist bei 0,3. Early Stopping hielt bei
Sprecher A nach 2-3 Durchgängen an, bei Sprecher B nach 9-15.

---

## 2. Methode

* **Messung.** Sechsfache Kreuzvalidierung: Jede Aufnahme wird genau einmal von
  einem Modell erkannt, das sie nicht gelernt hat. Zwei Fassungen je Aufnahme
  (`original`, `rauschen` bei 20 dB). WER ist das Mittel der WER je Einheit,
  nicht die WER über den Korpus; deshalb sind Werte über 1 möglich (ein Stand,
  der wiederholt oder weiterredet).
* **Baseline.** Die unveränderten Grundmodelle `small`, `medium`, `large-v3`
  aus der Auswertung von „hören", Tempo 1,0, auf denselben Aufnahmen.
* **Vergleiche** sind gepaart: Differenz je Aufnahme (Mittel beider Fassungen),
  dann Perzentil-Bootstrap über Aufnahmen (10 000 Ziehungen) und als zweiter
  Test ein Vorzeichen-Permutationstest. Verglichen wird nur auf Aufnahmen, die
  alle Beteiligten gemessen haben.
* **Trainingsrauschen** wird aus den vier Wiederholungen geschätzt
  (Abschnitt 3) und dem Bootstrap-Fehler hinzugerechnet, als
  `se_gesamt = √(se_bootstrap² + se_training²)`. Für Sprecher A, wo es keine
  Wiederholungen gibt, wird derselbe relative Wert angenommen
  (Variationskoeffizient 5,8 %). Das ist eine Näherung (Unabhängigkeit beider
  Quellen angenommen), aber ohne sie wäre jeder Einzellauf-Vergleich zu
  optimistisch.

---

## 3. Das wichtigste Ergebnis: dasselbe Rezept streut

Die vier Läufe `ML-E-SRP-CI/43`, `/43b`, `/43c`, `/43d` haben identische
Optionen, identische Faltungen (dieselbe Zuordnung jeder Aufnahme) und
denselben festen Keim (`KEIM = 20260912`). Trotzdem:

| | `/43` | `/43b` | `/43c` | `/43d` | Mittel | SD | Spanne |
|---|---|---|---|---|---|---|---|
| WER | 0,889 | 0,785 | 0,890 | 0,860 | **0,856** | **0,049** | 0,105 |

Die Korrelation je Aufnahme zwischen `/43b` und `/43c` ist nur r = 0,65. Der
feste Keim macht das Training also nicht reproduzierbar - die Streuung kommt
aus nichtdeterministischen GPU-Rechnungen, verstärkt durch das kleine Korpus.

![Sprecher B: alle Stände auf denselben 43 Aufnahmen, mit Baselines](bilder/modellbericht-sprecher-b.svg)

*Abbildung 1.* Das helle Band ist die Spanne der vier Wiederholungen. Fast
jeder andere Stand fällt hinein oder knapp daneben; nur die Baselines liegen
weit entfernt.

Der gepaarte Vergleich `/43b` gegen `/43c` ergibt Δ = −0,105
[−0,234; 0,000], Bootstrap-p ≈ 0,05 - ein „fast signifikanter" Unterschied
**zwischen zwei gleichen Rezepten**. Daraus folgt:

1. Das Bootstrap-Intervall eines Laufs beschreibt nur die Unsicherheit über die
   Aufnahmen, nicht die über das Training. Für Vergleiche einzelner Läufe ist
   es zu schmal.
2. Zwei Einzelläufe auf Sprecher B unterscheiden sich allein durch das
   Training mit einer Standardabweichung von etwa 0,049 · √2 ≈ 0,07. Ein
   Unterschied unter rund 0,14 ist zwischen zwei Einzelläufen **nicht** als
   Wirkung einer Option zu deuten.
3. Die Schätzung selbst ist grob: vier Wiederholungen, drei Freiheitsgrade, ein
   Rezept, ein Sprecher.

Für die Praxis: `/43b`, der beste Einzelwert, ist nicht mehr da - aber er ist
von `/43d` statistisch nicht zu trennen (Δ = −0,075 [−0,177; 0,020]). Verloren
ist damit nichts, was sich belegen ließe.

---

## 4. Welche Optionen wirken?

![Gepaarte Unterschiede je Option, mit und ohne Trainingsrauschen](bilder/modellbericht-kontraste.svg)

*Abbildung 2.* Jede Zeile ein gepaarter Vergleich. Die dünne Linie ist das
Intervall über Aufnahmen allein, das breite Band rechnet das Trainingsrauschen
hinzu. Bei Sprecher B schließt jedes breite Band die Null ein - auch der
Vergleich zweier gleicher Rezepte liegt in derselben Größenordnung wie die
Optionen. Bei Sprecher A liegen zwei Bänder klar neben der Null.

### Tabelle 2: gepaarte Vergleiche

Δ = WER der Option minus WER des Vergleichs; negativ heißt, die Option ist
besser. „Vergleich" bei Sprecher B ist, wo nicht anders genannt, das Mittel
der vier Wiederholungen `ML-E-SRP-CI/43`.

| Vergleich | n | Δ WER | 95 % Bootstrap | 95 % mit Training | z |
|---|---|---|---|---|---|
| B: `small` statt `medium` | 43 | +0,051 | [−0,038; 0,132] | [−0,087; 0,188] | 0,7 |
| B: mit Abwandlungen (`A`) | 43 | +0,054 | [−0,050; 0,193] | [−0,108; 0,217] | 0,7 |
| B: Tempo gesucht, `medium` | 43 | +0,085 | [0,006; 0,168] | [−0,050; 0,220] | 1,2 |
| B: Tempo gesucht, `medium` mit `A` (gegen `ML-A-E-SRP-CI`) | 43 | −0,015 | [−0,178; 0,112] | [−0,214; 0,184] | −0,2 |
| B: Tempo gesucht, `small` (gegen `SL-E-SRP-CI`) | 43 | +0,093 | [0,023; 0,164] | [−0,061; 0,247] | 1,2 |
| B: Abschluss `C` statt `CI` (`small`) | 43 | +0,058 | [−0,029; 0,133] | [−0,101; 0,217] | 0,7 |
| B: gleiches Rezept, `/43b` − `/43c` | 43 | −0,105 | [−0,234; 0,001] | - | - |
| A: `small` statt `medium` | 127 | +0,097 | [0,075; 0,119] | [0,046; 0,147] | **3,8** |
| A: 166 statt 134 Aufnahmen | 127 | +0,006 | [−0,010; 0,021] | [−0,035; 0,046] | 0,3 |
| A: `medium` trainiert − `large-v3` unverändert | 127 | −0,051 | [−0,072; −0,030] | [−0,085; −0,017] | **−3,0** |

### 4.1 Überhaupt trainieren: ja, eindeutig

![Sprecher A: alle Stände auf 127 gemeinsamen Aufnahmen, mit Baselines](bilder/modellbericht-sprecher-a.svg)

*Abbildung 3.* Sprecher A, auf den Aufnahmen, die alle drei Läufe und alle
Baselines gemessen haben.

| Sprecher (Aufnahmen) | Baseline small | medium | large-v3 | bester Stand |
|---|---|---|---|---|
| B (43) | 1,575 | 1,627 | 1,362 | 0,856 (Mittel der vier `ML-E-SRP-CI/43`) |
| A (127 gemeinsame) | 0,518 | 0,403 | 0,287 | 0,231 (`ML-A-E-SRP-CI/134`) |

Jeder einzelne Lauf ist besser als jede Baseline desselben Grundmodells, alle
mit p < 0,001, bei Sprecher B auf 37-41 von 43 Aufnahmen. Bei Sprecher B liegt
der Kern des Gewinns im Ausfransen:

![Sprecher B: Anteil der Einheiten mit WER über 1](bilder/modellbericht-ausfransen.svg)

*Abbildung 4.* Mit `medium` unverändert haben 81 % der Einheiten mehr Fehler als
Wörter, nach dem Training je nach Lauf 16-31 %.

Bemerkenswert: Ein feingetuntes `medium` schlägt das **unveränderte
`large-v3`** - bei Sprecher A um 0,051 (75 Aufnahmen besser, 34 schlechter;
auch mit Trainingsrauschen z ≈ −3,0), bei Sprecher B um 0,506 [0,387; 0,634].
Ein feingetuntes `small` schafft das bei Sprecher A nicht (0,040 schlechter als
`large-v3`, [0,014; 0,067]).

### 4.2 whisper-medium statt small: ja

* **Sprecher A**: Δ = **−0,097** zugunsten `medium`, 91 Aufnahmen besser,
  17 schlechter, Permutation p < 0,001, mit Trainingsrauschen z ≈ 3,8.
  **Belastbar.**
* **Sprecher B**: Δ = −0,051 zugunsten `medium`, z ≈ 0,7. Gleiche Richtung,
  aber nicht nachweisbar.

`medium` braucht etwa die zwei- bis dreifache Rechenzeit (19 statt 8 min bei
Sprecher B, 40 statt 13 min bei Sprecher A).

### 4.3 Tempo gesucht (`Ts`): eher schädlich, sicher teuer

Die Tempowahl fand bei Sprecher B 3,0 (`medium`) und 2,0 (`small`). Keiner der
drei Vergleiche mit und ohne zeigt einen Gewinn, zwei zeigen einen Verlust in
der Größenordnung des Trainingsrauschens (Tabelle 2). Dazu kostet die Suche das
Zwei- bis Dreifache an Zeit (54 statt 19 min).

`SL-E-SRP-Ts-CI/43` ist mit 1,000 der schwächste Stand auf diesen Aufnahmen;
gegen das `ML`-Mittel liegt er 0,144 [0,043; 0,234] zurück. Über Aufnahmen
allein (p ≈ 0,004) hielte das auch einer Holm-Korrektur über die sechs
Optionsvergleiche stand, mit Trainingsrauschen (z ≈ 1,9) nicht mehr. Auch der
ältere Lauf mit fest 2,0 (`/20b`) war nicht besser als ohne (0,795 gegen 0,790
auf 16 gemeinsamen Aufnahmen).

### 4.4 Mit Abwandlungen (`A`): keine messbare Wirkung

Nur bei Sprecher B prüfbar (bei A sind alle Läufe mit `A`):
`ML-A-E-SRP-CI/43` liegt 0,054 **hinter** dem `ML`-Mittel, z ≈ 0,7. Nichts
spricht dafür, nichts klar dagegen; die Rechenzeit ist kaum höher (21 statt
19 min).

### 4.5 Abschluss: `CI` vor `C`, aber schwach

`SL-E-SRP-C/43` (nur Checkpoint-Mittel) liegt 0,058 hinter
`SL-E-SRP-CI/43` (dazu WiSE-FT), z ≈ 0,7 - ein einziger Vergleich auf `small`.
Dass die Kreuzvalidierung in jedem Lauf ein α zwischen 0,2 und 0,5 wählt, also
stets ein Stück Grundmodell zurückholt, deutet in dieselbe Richtung: Etwas
Interpolation schadet nicht und hilft vermutlich.

### 4.6 Mehr Aufnahmen: bisher nicht sichtbar

* **Sprecher A**, 134 gegen 166 Aufnahmen (+24 %), gleiche Optionen:
  Δ = +0,006 [−0,010; 0,021]. Kein Gewinn.
* **Sprecher B**, 20/22 gegen 43: Auf den 16 gemeinsamen Aufnahmen schwankt es
  zwischen 0,69 und 0,98 ohne Ordnung nach Datenmenge. Zwischen diesen Läufen
  wurden 41 der 43 Aufnahmen zugeschnitten und einige geteilt oder verworfen;
  der Ton ist also nicht mehr derselbe, und die Frage bleibt offen.

---

## 5. Grenzen

* **Zwei Sprecher**, und fast jede Option nur bei einem von beiden geprüft.
  Wechselwirkungen (etwa `A` × Grundmodell) lassen sich nicht schätzen.
* **Einzelläufe.** Außer dem einen Rezept mit vier Wiederholungen gibt es je
  Kombination genau einen Lauf. Bei Sprecher A ist das Trainingsrauschen nicht
  gemessen, sondern übertragen; die Aussagen zu 4.1 und 4.2 halten mit diesem
  Aufschlag, wären aber bei deutlich größerem Rauschen neu zu prüfen.
* **Wechselnde Testmengen.** Die Aufnahmenzahlen der Läufe unterscheiden sich,
  und Aufnahmen wurden später zugeschnitten, geteilt oder verworfen. Die
  gespeicherte WER eines älteren Laufs (Tabelle 1) weicht deshalb von der auf
  den heute noch vorhandenen Aufnahmen ab - bei `SL-A-E-SRP-CI/132` etwa 0,394
  gegen 0,328. In Abschnitt 4 wird deshalb nur gepaart verglichen.
* **Baseline nur bei Tempo 1,0.** Stände mit `Ts` spulen beim Erkennen vor;
  ihr Abstand zur Baseline mischt Training und Tempo.
* **Mehrfachvergleiche.** Bei Sprecher B sind es rund zehn Tests; ohne
  Korrektur wäre bei α = 0,05 ein zufälliger Treffer zu erwarten.
* **Das Maß.** Das Mittel je Einheit wird bei Sprecher B von Einheiten mit
  WER > 1 beherrscht. Die CER zeigt dieselbe Reihenfolge der Grundmodelle,
  trennt die Optionen innerhalb eines Grundmodells aber ebenso wenig.

---

## 6. Fazit

| Option | Befund | Stärke |
|---|---|---|
| Feintuning überhaupt | großer Gewinn, bei Sprecher B vor allem gegen Ausfransen | eindeutig |
| `medium` statt `small` | −0,10 WER bei A, gleiche Richtung bei B | belastbar (A) |
| feingetuntes `medium` gegen unverändertes `large-v3` | besser bei beiden | belastbar |
| Tempo gesucht (`Ts`) | nie besser, teils schlechter, 2-3× Rechenzeit | Tendenz: weglassen |
| Mit Abwandlungen (`A`) | kein messbarer Effekt | offen |
| `CI` statt `C` | leicht besser | schwach |
| mehr Aufnahmen (A, +24 %) | kein messbarer Effekt | schwach |

**Was nach heutigem Stand am besten abschneidet: `ML-E-SRP-CI`, also
whisper-medium mit LoRA, Early Stopping, voller Augmentierung, ohne
Tempowahl und mit Checkpoint-Mittel plus WiSE-FT.** Ob mit oder ohne
Abwandlungen, ist nicht entschieden. Beide freigegebenen Stände folgen diesem
Rezept, und keiner der übrigen ist nachweisbar besser.

Für Sprecher B bleibt die absolute Güte das eigentliche Problem: Auch der beste
Stand liegt bei einer WER um 0,85. Keine der geprüften Optionen hat daran
mehr geändert als das Trainingsrauschen.

**Für die nächsten Läufe.** Wer eine Option beurteilen will, braucht
mindestens drei Wiederholungen je Seite; ein einzelner Lauf gegen einen
einzelnen Lauf trägt bei Sprecher B keinen Unterschied unter etwa 0,14. Am
meisten Erkenntnis pro Rechenstunde versprechen jetzt: `A` gegen ohne auf
`medium` mit Wiederholungen, und für Sprecher A ein Lauf ohne `A`, damit die
Option überhaupt einmal bei beiden Sprechern gemessen ist.
