# Wirkungsbericht: Nutzen und Schaden der Trainingsoptionen

Was bringt jede Option eines Laufs, was schadet sie, und was kostet sie? Und
wie wird ein Modell besser, wenn mehr Aufnahmen dazukommen? Dieser Bericht
wertet dafür jeden Lauf im Register aus, der einen fairen Vergleich zulässt.

> **Stand: 2. Oktober 2026.** Grundlage ist das Register der Läufe
> (`data/lernen/<sprecher_id>/register.sqlite`, siehe
> [lernen](lernen.md#das-register-der-läufe)): 39 Läufe, 26 von Sprecher A,
> 13 von Sprecher B. Gemessen wird an den Tabellen `daten` und `messungen`;
> Trainingsdauern stammen aus `laeufe`.
>
> **Datenschutz.** Die Sprecher heißen hier **A** und **B** wie im
> [Modellbericht](modellbericht.md). Namen und Kennungen stehen bewusst nicht
> im Bericht. A ist gut zu verstehen (beste WER 0,16), B schwer (beste WER
> 0,48).

---

## 1. Kurzfassung

| Option | Wirkung auf die WER | Kosten | Befund |
|---|---|---|---|
| Grundmodell eine Stufe größer | **−12 %** je Stufe (small → medium, medium → large-v3) | ×3,2 bzw. ×2,1 | **belastbar nützlich** |
| LoRA nur im Decoder | **+26 %** (small), medium vollständig abgestürzt | - | **belastbar schädlich** |
| LoRA an allen Projektionen | ohne Absturz ±0, aber in beiden Läufen eine Faltung abgestürzt | ×1,3 | **schädlich durch Instabilität** |
| LoRA nur im Encoder | −1 % im Mittel, je Sprecher entgegengesetzt (B −11 %, A +14 % auf large-v3) | ×1,6 | sprecherabhängig, offen |
| Rang 8 oder 64 statt 32 | ±0 | ×1,0-1,2 | keine Wirkung; Rang 8 einmal abgestürzt |
| Steuergröße WER | ±0 | ×2,2 | **schädlich durch Kosten** |
| Kontext Vokabular | ±0 | ×1,0 | keine Wirkung |
| Fenster gekürzt | ±0 | ×1,0 | keine Wirkung, keine Ersparnis; einmal abgestürzt |
| Mit Abwandlungen | +3 % (nicht belastbar) | ×1,3 | kein Nutzen erkennbar |
| Korrekturgewicht 1,0 statt 0,5 | ±0 | - | bei 1-4 % Korrekturen kein Hebel |
| Bündel E · SRP · CI | ±0 ohne Absturz, −14 % mit | - | schützt vor Absturz (ein Vergleich) |
| +16 % Aufnahmen (262 → 305) | −1 % [−6 %; +4 %] | ×1,2 | im beobachteten Bereich keine messbare Wirkung |

**Der einzige verlässliche Hebel ist das Grundmodell.** Jede andere Option
verändert die WER um weniger, als zwei Läufe ohne jeden Unterschied
auseinanderliegen - oder sie schadet. Den größten Schaden richten Optionen
nicht im Mittel an, sondern als **Absturz einzelner Faltungen**: In 26 Läufen
des Standardrezepts ist keine Faltung abgestürzt, in 9 Läufen mit
abweichenden Optionen sechsmal eine oder alle.

---

## 2. Vorgehen

### 2.1 Was gemessen wird

Jeder Lauf misst jede Aufnahme mit dem Faltungsmodell, das sie nicht gelernt
hat (sechsfache Kreuzvalidierung, siehe [lernen](lernen.md#sechsfache-kreuzvalidierung)).
Die Faltung einer Aufnahme hängt an ihrer Kennung; zwei Läufe auf denselben
Daten messen also jede Aufnahme in derselben Faltung und lassen sich
**Aufnahme für Aufnahme paaren**. Hauptmaß ist die WER je Aufnahme auf der
Originalfassung, gemittelt über die gemeinsamen Aufnahmen. CER und die
Fassung mit Rauschen dienen als Gegenprobe (Tabelle in Abschnitt 4).

**Relativ statt absolut.** Die beiden Sprecher liegen um den Faktor drei
auseinander. Eine Option, die bei A die WER um 0,02 senkt, senkt sie bei B
eher um 0,06. Verglichen wird deshalb das Verhältnis der Mittel: −10 % heißt,
die Option macht ein Zehntel weniger Fehler.

### 2.2 Vergleichbarkeit

Welche Läufe dieselben Daten sahen, sagt der Fingerabdruck `datensatz`:

| Sprecher | Datensatz | Läufe | Verhältnis zu den anderen |
|---|---|---|---|
| A | 237 Aufnahmen | 23 | - |
| A | 235 Aufnahmen | 3 | Teilmenge der 237, Zeile für Zeile gleich |
| B | 305 Aufnahmen | 5 | enthält die 262 unten Zeile für Zeile, dazu 30 Aufnahmen und 26 Korrekturzeilen |
| B | 262 Aufnahmen | 4 | Teilmenge der 305 |
| B | 262 Aufnahmen, älterer Zuschnitt | 2 | dieselben Aufnahmen, 428 von 524 Zeilen mit anderem Ton |
| B | 43 Aufnahmen | 2 | älterer Bestand, kaum Überschneidung |

Jeder Vergleich trägt eine Stufe:

| Stufe | Bedingung |
|---|---|
| 1 | gleicher Datensatz, genau eine Option verschieden |
| 2 | eine Option verschieden, aber zwei Aufnahmen mehr (235 ⊂ 237) - oder dazu eine zweite Option, deren eigene Wirkung im Rauschen liegt |
| 3 | weitere Unterschiede; nur als Hinweis, geht in keine Zusammenfassung ein |

### 2.3 Unsicherheit

Zwei Quellen, beide berücksichtigt:

* **Welche Aufnahmen gemessen sind.** Bootstrap je Aufnahme, gepaart, 2000
  Ziehungen mit dem Keim aus `wortlaut/streuung.py` - dasselbe Verfahren wie
  unter „Modelle".
* **Welcher Lauf es zufällig wurde.** Zwei Trainings derselben Daten mit
  derselben Option enden nie gleich. Diese Streuung misst der Bootstrap nicht;
  sie kommt aus Abschnitt 3 und geht als `s = 2,2 %` in jede Zusammenfassung
  ein: `z = Wirkung / √(Bootstrap-Fehler² + s²)`.

Je Option werden die Vergleiche der Stufen 1 und 2 auf der logarithmischen
Skala mit inversen Varianzen gemittelt; über die 13 Optionen gilt eine
Holm-Korrektur. **Belastbar** heißt: nach Holm p < 0,05.

### 2.4 Abgestürzte Faltungen

Manchmal läuft eine einzelne Faltung aus dem Ruder: Ihr Modell wiederholt
oder redet weiter, ihre WER liegt beim Mehrfachen der anderen. Das Endmodell
lässt solche Faltungen aus ([lernen](lernen.md#das-endmodell)), die Messung des
Laufs enthält sie. Jede Wirkung steht deshalb zweimal da:

* **robust** - ohne die Faltungen, in denen einer der beiden Läufe abstürzt
  (vom Endmodell ausgelassen, oder sein Verhältnis zum Partner weicht um mehr
  als das Anderthalbfache vom Median der Faltungen ab). Diese Zahl geht in die
  Zusammenfassung ein.
* **über alle Faltungen** - mit dem Absturz. Abschnitt 5 zählt die Abstürze
  eigens, denn sie sind selbst eine Wirkung der Option.

---

## 3. Wie weit Läufe ohne Unterschied auseinanderliegen

Eine Wiederholung desselben Rezepts gibt es nur bei B mit 43 Aufnahmen. Bei A
gibt es drei Paare, die sich nur im Korrekturgewicht unterscheiden - bei 8
von 474 Zeilen, also praktisch nicht:

| Paar | Aufnahmen | Unterschied der WER | 95 % Bootstrap |
|---|---|---|---|
| A: small | 233 | −2,8 % | [−8,7 %; +3,2 %] |
| A: medium | 233 | +1,9 % | [−4,3 %; +8,4 %] |
| A: medium, nur Encoder | 233 | +1,7 % | [−3,9 %; +8,4 %] |
| B: medium, identisches Rezept, 43 Aufnahmen | 43 | +7,9 % (robust −3,9 %) | [−8,9 %; +33,3 %] |

**Bei A trennt zwei gleiche Läufe etwa 2 % (quadratisch gemittelt 2,2 %).**
Das ist weniger als die Breite des Bootstrap-Bereichs, die bei 233 Aufnahmen
um ±6 % liegt. Für Läufe mit einigen Hundert Aufnahmen begrenzt also die Zahl
der gemessenen Aufnahmen die Auflösung, nicht der Zufall des Trainings. Ein
einzelner Vergleich zweier Läufe kann Wirkungen unter etwa 5 % nicht von null
unterscheiden.

Bei 43 Aufnahmen ist das anders: Die beiden Wiederholungen liegen 8 %
auseinander, und **in jeder ist eine Faltung abgestürzt** (WER über 1). Kleine
Datensätze machen das Training selbst unzuverlässig.

---

## 4. Die Optionen im Einzelnen

![Wirkung je Option, alle Vergleiche zusammengefasst](bilder/wirkungsbericht-optionen.svg)

*Abbildung 1.* Gepoolte Wirkung je Option, robust, mit 95-%-Bereich. Das graue
Band ist der Bereich, in dem zwei gleiche Läufe auseinanderliegen (±1,96 · s).

![Jeder Vergleich einzeln](bilder/wirkungsbericht-vergleiche.svg)

*Abbildung 2.* Jeder Vergleich einzeln, je Sprecher. Ein hohler Kreis rechts
vom gefüllten Punkt heißt: Über alle Faltungen gerechnet sieht die Option
schlechter aus, weil eine Faltung abstürzte.

### Alle Vergleiche als Tabelle

Δ = relative Änderung der WER, robust; daneben über alle Faltungen, die CER und
die Fassung mit Rauschen. „besser/schlechter": Zahl der Aufnahmen.

| | St. | Vergleich | n | WER vorher → nachher | Δ robust [95 %] | alle Falt. | CER | Rauschen | besser/schlechter |
|---|---|---|---|---|---|---|---|---|---|
| A | 2 | small → medium | 231 | 0,271 → 0,215 | **−20,7 %** [−28,1; −12,4] | −20,7 % | −21,0 % | −21,2 % | 121/35 |
| A | 1 | medium → large-v3 (Encoder) | 233 | 0,211 → 0,187 | **−11,6 %** [−19,2; −2,5] | −11,6 % | −5,1 % | −18,5 % | 98/41 |
| B | 1 | medium → large-v3 (Encoder) | 292 | 0,542 → 0,480 | **−11,3 %** [−18,6; −3,4] | −11,3 % | −8,8 % | −14,3 % | 142/65 |
| B | 2 | small → medium (Encoder, Rang 64 → 32) | 262 | 0,615 → 0,563 | **−8,4 %** [−13,8; −2,7] | −8,4 % | −7,8 % | −10,2 % | 132/67 |
| A | 3 | medium → large-v3 (q,v; Abwandlungen → Originale) | 231 | 0,215 → 0,163 | −24,2 % [−32,1; −16,2] | −24,2 % | −21,3 % | −21,0 % | - |
| A | 1 | q,v → alle Projektionen (small) | 190 | 0,269 → 0,267 | −0,9 % [−6,9; +5,9] | **+59,1 %** | +94,7 % | +43,3 % | 60/53 |
| A | 1 | q,v → alle Projektionen (medium) | 185 | 0,223 → 0,265 | +19,0 % [+3,2; +38,0] | **+68,5 %** | +113,3 % | +1,6 % | 42/53 |
| A | 1 | q,v → nur Decoder (small) | 233 | 0,271 → 0,342 | **+26,2 %** [+18,3; +35,3] | +26,2 % | +30,0 % | +39,7 % | 46/121 |
| A | 1 | q,v → nur Decoder (medium) | 233 | 0,209 → 1,732 | **+729 %**, gescheitert | +729 % | - | - | 9/194 |
| A | 1 | q,v → nur Encoder (small) | 233 | 0,271 → 0,259 | −4,6 % [−10,4; +1,5] | −4,6 % | −8,2 % | −6,7 % | 75/63 |
| A | 1 | q,v → nur Encoder (medium) | 233 | 0,209 → 0,208 | −0,6 % [−8,1; +7,3] | −0,6 % | −1,7 % | +3,1 % | 64/71 |
| A | 2 | q,v → nur Encoder (large-v3) | 231 | 0,163 → 0,186 | +14,3 % [+4,5; +27,5] | +14,3 % | +15,3 % | +6,6 % | - |
| B | 1 | q,v → nur Encoder (large-v3) | 292 | 0,542 → 0,480 | −11,4 % [−21,7; −1,1] | −11,4 % | −9,8 % | −13,1 % | 121/84 |
| A | 1 | Rang 32 → 8 (small) | 233 | 0,271 → 0,280 | +3,4 % [−2,6; +9,6] | +3,4 % | +6,3 % | +2,4 % | 64/77 |
| A | 1 | Rang 32 → 8 (medium) | 185 | 0,223 → 0,215 | −3,3 % [−10,7; +4,5] | +16,3 % | +33,1 % | +8,4 % | 49/42 |
| A | 1 | Rang 32 → 64 (small) | 233 | 0,271 → 0,263 | −3,1 % [−8,0; +2,0] | −3,1 % | −6,2 % | +0,4 % | 70/61 |
| A | 1 | Rang 32 → 64 (medium) | 233 | 0,209 → 0,204 | −2,6 % [−8,4; +3,3] | −2,6 % | −3,5 % | +4,9 % | 51/53 |
| B | 1 | Rang 32 → 64 (large-v3) | 292 | 0,542 → 0,556 | +2,6 % [−4,0; +9,3] | +2,6 % | +1,2 % | −0,1 % | 90/94 |
| A | 2 | Rang 32 → 64 (small, Encoder) | 233 | 0,259 → 0,281 | +8,8 % [+3,0; +14,9] | +8,8 % | +8,1 % | +12,7 % | 47/83 |
| B | 1 | Korrekturgewicht 0,5 → 1,0 (26 von 610 Zeilen) | 292 | 0,480 → 0,487 | +1,5 % [−6,4; +11,2] | +1,5 % | +1,7 % | +0,6 % | 96/83 |
| A | 1 | Steuergröße Verlust → WER (small) | 233 | 0,264 → 0,269 | +2,1 % [−3,4; +7,8] | +2,1 % | +2,0 % | −2,6 % | 68/74 |
| A | 1 | Steuergröße Verlust → WER (medium) | 233 | 0,213 → 0,207 | −2,7 % [−8,1; +3,0] | −2,7 % | −1,8 % | −0,4 % | 59/53 |
| A | 2 | Steuergröße Verlust → WER (small, Encoder) | 233 | 0,259 → 0,257 | −0,6 % [−6,3; +5,3] | −0,6 % | −0,5 % | +3,4 % | 64/70 |
| A | 1 | Kontext aus → Vokabular (small) | 233 | 0,264 → 0,267 | +1,2 % [−4,4; +7,5] | +1,2 % | +3,8 % | −0,8 % | 72/69 |
| A | 1 | Kontext aus → Vokabular (medium) | 233 | 0,213 → 0,211 | −0,8 % [−6,2; +5,4] | −0,8 % | −1,0 % | +0,6 % | 56/49 |
| A | 1 | Fenster 30 s → gekürzt (medium) | 233 | 0,213 → 0,209 | −1,9 % [−8,1; +4,4] | −1,9 % | −3,8 % | −3,3 % | 54/47 |
| A | 2 | Fenster 30 s → gekürzt (small) | 197 | 0,283 → 0,286 | +1,4 % [−4,0; +7,0] | +16,4 % | +23,2 % | +20,9 % | 49/63 |
| A | 2 | nur Originale → mit Abwandlungen (medium) | 231 | 0,208 → 0,215 | +3,2 % [−5,5; +14,2] | +3,2 % | +2,8 % | +1,8 % | 46/52 |
| B | 1 | Bündel: fest · ohne Augm. · bester → E · SRP · CI (large-v3) | 211 | 0,577 → 0,592 | +2,6 % [−5,1; +11,3] | **−14,0 %** | −17,0 % | −8,3 % | 83/72 |
| B | 3 | small LoRA (Encoder, Rang 64) → small volles Feintuning | 262 | 0,615 → 0,773 | +25,7 % [+17,8; +34,1] | +25,7 % | +36,8 % | +23,2 % | 59/137 |

### 4.1 Grundmodell: der eine Hebel

Jede Stufe größer senkt die WER um rund ein Achtel - bei beiden Sprechern,
in jedem Maß und auf beiden Fassungen: **small → medium −12,5 % [−17,7; −7,1]**,
**medium → large-v3 −11,5 % [−17,5; −5,0]**, beide nach Holm belastbar. Bei A
wiegt der Schritt von small auf medium mehr (−21 %) als bei B (−8 %, dort mit
Rang 64 gegen 32 vermischt). Auf q,v ohne Abwandlungen zeigt der Hinweis bei
A sogar −24 % von medium auf large-v3.

Der Preis ist Rechenzeit: medium braucht das 3,2-Fache von small, large-v3
das 2,1-Fache von medium. Der beste Lauf bei A ist ein large-v3 mit q,v
(WER 0,163), bei B ein large-v3 nur im Encoder (0,480).

### 4.2 LoRA-Ziele: q,v bleibt die sichere Wahl

* **Nur Decoder schadet.** small +26 % [+18; +35], 121 von 233 Aufnahmen
  schlechter. Auf medium ist jede der sechs Faltungen abgestürzt (WER 1,2-2,2),
  der Lauf scheiterte ohne Endmodell. Vermutlich passt der Decoder allein
  das Sprachmodell an, ohne dass der Encoder die Aussprache besser hört.
* **Alle Projektionen sind instabil.** In beiden Läufen (small und medium)
  stürzte genau eine Faltung ab und trieb die WER über alle Faltungen auf
  +59 % und +69 %. Ohne sie: small ±0, medium +19 % [+3; +38]. Mehr Gewichte
  bringen nichts und kosten 30 % Zeit.
* **Nur Encoder hängt am Sprecher.** Bei B auf large-v3 −11,4 % [−21,7; −1,1],
  bei A auf large-v3 +14,3 % [+4,5; +27,5], dazwischen A small −4,6 % und A
  medium −0,6 %. Zusammen −1,3 % [−5,8; +3,4] bei 1,6-facher Rechenzeit.
  Naheliegend, aber nicht gemessen: Bei schwer verständlicher Aussprache (B)
  liegt das Problem im Hören, also im Encoder; bei A ist es klein, und der
  Decoder hat mehr zu sagen. Mit zwei Sprechern lässt sich das nicht trennen
  von der Frage, ob die Wirkung am Grundmodell hängt.

### 4.3 LoRA-Rang: egal

Rang 8, 32 und 64 unterscheiden sich nicht: Rang 64 +1,4 % [−2,2; +5,1] über
vier Vergleiche, Rang 8 +0,7 % [−4,8; +6,5]. Die Rechenzeit ändert sich kaum.
Zwei Auffälligkeiten ohne Gewicht: Rang 8 auf medium hatte eine abgestürzte
Faltung, und Rang 64 nur im Encoder auf small lag 8,8 % zurück (Stufe 2, ein
Vergleich). Rang 32 bleibt die Vorgabe, weil nichts für einen anderen spricht.

### 4.4 Korrekturgewicht: kein Hebel bei so wenigen Korrekturen

Korrekturen aus „schreiben" sind 8 von 474 Zeilen bei A und 26 von 610 bei B.
Doppelt so stark gewichtet ändern sie nichts Messbares: B +1,5 % [−6,4; +11,2],
die drei Paare bei A liegen im Rauschen (Abschnitt 3). Bewertbar wird die
Achse erst, wenn Korrekturen einen nennenswerten Teil der Daten ausmachen.

### 4.5 Steuergröße WER: kein Nutzen, doppelte Zeit

Checkpoint, Abbruch und α nach der WER statt nach dem Verlust zu wählen,
ändert nichts: −0,4 % [−4,3; +3,7] über drei Vergleiche. Es kostet aber das
2,2-Fache an Zeit, weil jede Validierung erkennen muss statt nur zu rechnen.
**Weglassen.**

### 4.6 Kontext Vokabular: wirkungslos

Der Startprompt mit den seltenen Wörtern der Lerntexte ändert nichts:
+0,2 % [−4,9; +5,5]. Er kostet nichts, aber er bringt auch nichts -
vermutlich, weil das feingetunte Modell diese Wörter schon aus dem Training
kennt.

### 4.7 Fenster gekürzt: weder schneller noch besser

Den Encoder auf die längste Aufnahme zu kürzen, ändert die WER nicht
(−0,2 % [−5,2; +5,2]) und spart in diesen Läufen auch keine Zeit (×0,98). Auf
small stürzte im gekürzten Lauf eine Faltung ab (Stufe 2). Kein Grund, es
einzuschalten.

### 4.8 Mit Abwandlungen: kein Nutzen erkennbar

Die gemessenen Fassungen (Rauschen) mitzulernen, ergibt auf medium +3,2 %
[−5,5; +14,2] - auch auf der Fassung mit Rauschen selbst kein Gewinn
(+1,8 %). Dazu 30 % mehr Rechenzeit. Der Modellbericht fand bei B dasselbe.
Vermutlich sorgt die Augmentierung zur Laufzeit (`SRP`) schon für die
Robustheit, die die Abwandlungen bringen sollten.

### 4.9 Das Bündel E · SRP · CI: Schutz vor dem Absturz

Nur ein Vergleich, bei B auf large-v3, und er ändert drei Achsen zugleich:
feste Epochenzahl, keine Augmentierung und bester Checkpoint gegen Early
Stopping, volle Augmentierung und Checkpoint-Mittel mit WiSE-FT. Über alle
Faltungen −14,0 %, ohne die eine abgestürzte Faltung des einfachen Laufs
+2,6 % [−5,1; +11,3]. **Der ganze Gewinn ist der vermiedene Absturz.** Welche
der drei Achsen ihn verhindert, sagt dieser Vergleich nicht.

### 4.10 Volles Feintuning: nur ein Hinweis

Das einzige volle Feintuning (small, B) liegt 25,7 % hinter einem LoRA-Lauf
auf small - aber mit anderem Zuschnitt und LoRA nur im Encoder mit Rang 64.
Das spricht gegen volles Feintuning, belegt es aber nicht.

### 4.11 Mit den Läufen im Register nicht bewertbar

Tempo (`Ts`), Kernauswahl (`K`), Selbsttraining, der Abschluss allein, die
Augmentierung allein und die Dauer allein kommen in keinem vergleichbaren
Paar vor. Zu Tempo und Abschluss siehe den [Modellbericht](modellbericht.md),
zur Kernauswahl den [Kernbericht](kernbericht.md); deren Läufe stehen nicht
im Register.

---

## 5. Stabilität: abgestürzte Faltungen

![Alle Läufe mit ihren sechs Faltungen](bilder/wirkungsbericht-faltungen.svg)

*Abbildung 3.* Jeder Lauf, gruppiert nach Datensatz: die WER jeder Faltung
und ihr Mittel. Faltung 2 ist bei A in fast jedem Lauf die schwerste - das
ist Inhalt, kein Absturz.

Ein Absturz ist hier eine Faltung, die das Endmodell ausließ, oder deren WER
mehr als das Anderthalbfache dessen beträgt, was dieselbe Faltung in den
übrigen Läufen desselben Datensatzes erreicht - gemessen am eigenen Niveau
des Laufs, sonst fiele jedes small gegen die medium-Läufe auf. Gezählt sind
die Datensätze ab 235 Aufnahmen mit mindestens drei Läufen:

| Läufe | Zahl | mit Absturz |
|---|---|---|
| Standardrezept: q,v oder nur Encoder, Rang 32 oder 64, E · SRP · CI, volles Fenster | 26 | **0** |
| alle Projektionen | 2 | 2 (je eine Faltung) |
| nur Decoder | 2 | 1 (medium, alle Faltungen) |
| Rang 8 | 2 | 1 |
| Fenster gekürzt | 2 | 1 |
| ohne E · SRP · CI | 1 | 1 |

Sechs Abstürze in 9 abweichenden Läufen, keiner in 26 des Standardrezepts
(Fisher, einseitig, p ≈ 5 · 10⁻⁵; die Einteilung ist nachträglich, die Zahl
also beschreibend). Dazu hat in beiden Läufen mit 43 Aufnahmen je eine
Faltung mehr Fehler als Wörter.

Ein Absturz kostet die Faltung selbst - das Endmodell mittelt dann fünf statt
sechs - und verdirbt die Zahl des Laufs. **Was vom Standardrezept abweicht,
erkauft sich ein Absturzrisiko, ohne im Mittel etwas zu gewinnen.**

---

## 6. Mehr Aufnahmen

![WER desselben Rezepts mit weniger und mit mehr Aufnahmen](bilder/wirkungsbericht-datenmenge.svg)

*Abbildung 4.* Je Zeile ein Rezept, gemessen auf den Aufnahmen, die beide
Läufe kennen, jeweils von dem Faltungsmodell, das sie nicht lernte.

**Sauber messbar ist ein Schritt: B von 262 auf 305 Aufnahmen (+16 %),** dieselben
262 Aufnahmen Zeile für Zeile in beiden Läufen, in denselben Faltungen:

| Rezept | gemeinsame Aufnahmen | Änderung der WER |
|---|---|---|
| large-v3, q,v | 262 | −2,6 % [−7,9; +3,6] |
| medium, nur Encoder | 262 | −0,3 % [−5,5; +4,7] |
| zusammen | | **−1,4 % [−6,1; +3,6]** |

Eine Verbesserung um mehr als etwa 6 % schließt das aus. Dieselbe Richtung
zeigte der Modellbericht für A: 134 → 166 Aufnahmen (+24 %), Δ WER +0,006
[−0,010; +0,021].

**Von 43 auf 262 Aufnahmen sieht es anders aus** - als Hinweis, denn dazwischen
wurden die Aufnahmen neu zugeschnitten, und die LoRA-Ziele wechselten von
q,v auf nur Encoder: auf den 25 gemeinsamen Aufnahmen −27,7 % [−38,9; −17,0].
Dazu passt Abschnitt 3: Mit 43 Aufnahmen stürzte in jeder Wiederholung eine
Faltung ab, ab 262 in keinem Lauf des Standardrezepts.

Die Lernkurve ist damit vorne steil und wird ab einigen Hundert Aufnahmen
flach - jedenfalls im Bereich, den die Läufe abdecken. 16 % mehr Aufnahmen
brachten im Mittel ein Zehntel dessen, was eine Stufe Grundmodell bringt,
und nach dem 95-%-Bereich höchstens die Hälfte.
Weitere Aufnahmen lohnen dort, wo sie Neues zeigen (andere Wörter, andere
Situationen), mehr als dort, wo sie Bekanntes wiederholen; ob das so ist,
messen die Läufe nicht.

---

## 7. Nutzen gegen Rechenzeit

![Nutzen gegen Rechenzeit](bilder/wirkungsbericht-rechenzeit.svg)

*Abbildung 5.* Jede Option mit ihrer Wirkung und dem Faktor auf die
Trainingsdauer, gemittelt über ihre Vergleiche. Die Dauer reicht vom Beginn
bis zum Ende des Laufs auf derselben Karte.

Nur das Grundmodell liegt unten rechts: teurer, aber deutlich besser. Die
Steuergröße WER kostet mehr als das Doppelte für nichts, nur Encoder und die
Abwandlungen ein Drittel bis zwei Drittel mehr für nichts Verlässliches. Die
Gruppe um ×1 und null - Rang, Kontext, Fenster, Korrekturgewicht - kostet
nichts und bringt nichts.

---

## 8. Grenzen

* **Zwei Sprecher**, und die meisten Optionen sind nur bei einem geprüft, bei
  A. Dass „nur Encoder" je Sprecher entgegengesetzt wirkt, zeigt, wie viel
  davon abhängt.
* **Ein Lauf je Rezept.** Das Trainingsrauschen stammt aus drei Paaren bei A,
  die sich im Korrekturgewicht von 8 Zeilen unterscheiden. Hätte das eine
  Wirkung, wäre `s` zu groß und die Bewertung vorsichtiger als nötig. Für B ab
  262 Aufnahmen ist dasselbe relative Rauschen angenommen, nicht gemessen.
* **Die Messung ist die Kreuzvalidierung**, nicht das ausgelieferte
  Endmodell; sie ist leicht optimistisch (siehe
  [lernen](lernen.md#sechsfache-kreuzvalidierung)), für Vergleiche aber auf
  beiden Seiten gleich.
* **Rechenzeiten** schwanken mit Early Stopping und mit dem, was sonst auf
  der Karte lief; ein Lauf mit früh abgestürzten Faltungen ist kürzer.
* **Mehrfachvergleiche.** Die Holm-Korrektur gilt für die 13 Optionen, nicht
  für die rund 35 Einzelvergleiche der Tabelle.
* **Datenmenge.** Nur ein sauberer Schritt (+16 %); eine Lernkurve über mehr
  Stufen fehlt.

---

## 9. Fazit

| Option | Empfehlung |
|---|---|
| Grundmodell | so groß, wie die Zeit erlaubt: large-v3, sonst medium |
| LoRA-Ziele | q,v; nur Encoder je Sprecher prüfen, nie nur Decoder, nie alle |
| Rang | 32 |
| Steuergröße | Verlust |
| Kontext | aus |
| Fenster | 30 s |
| Datensatz | nur Originale |
| Korrekturgewicht | Vorgabe; erst bei vielen Korrekturen prüfen |
| Bündel | E · SRP · CI beibehalten |

**Das Rezept, das nach diesen Läufen am besten abschneidet: `L3L-E-SRP-CI`,
large-v3 mit LoRA auf q,v, Rang 32, Early Stopping, voller Augmentierung,
Checkpoint-Mittel und WiSE-FT, sonst überall die Vorgabe.** Wo die Zeit
knapp ist, dasselbe auf medium. Jede weitere Option ist nach heutigem Stand
entweder wirkungslos, zu teuer oder ein Absturzrisiko.

**Was als Nächstes am meisten Erkenntnis bringt:**

1. **Eine echte Lernkurve:** bei A dasselbe Rezept auf 25, 50 und 75 % der
   Aufnahmen, gemessen auf den gemeinsamen. Das trennt Datenmenge von allem
   anderen, was sich zwischen den Läufen ändert.
2. **Wiederholungen** des Standardrezepts bei B ab 262 Aufnahmen, damit das
   Trainingsrauschen dort gemessen und nicht übernommen ist.
3. **Nur Encoder auf medium bei B**, damit Sprecher und Grundmodell sich
   trennen lassen.
