# Optionenbericht: Was die neuen Trainingsoptionen bringen

Seit dem 28. September 2026 kennt ein Auftrag sieben weitere Achsen:
Steuergröße, LoRA-Ziele und -Rang, Korrekturgewicht, Selbsttraining, Fenster
und Kontext (siehe [Das Trainingsverfahren](trainingsverfahren.md#6-die-bausteine)).
Dazu ist das Endmodell kein siebtes Training mehr, sondern das Mittel der
Faltungen. Dieser Bericht sammelt, was die Läufe darüber sagen, und wächst mit
jedem Ergebnis.

> **Stand: 28. September 2026.** Sprecher A wie im
> [Modellbericht](modellbericht.md), 237 Aufnahmen, whisper-small mit LoRA.
> Grundlage sind `bewertung.jsonl`, `fortschritt.jsonl` und `protokoll.txt`
> der Läufe und die Tabelle `erkennungen` des Korpus (Baseline `small`). Namen
> und Kennungen stehen bewusst nicht im Bericht. Bisher liegt ein Vergleich
> vor; die übrigen Läufe stehen noch in der Warteschlange.
>
> **Nachtrag 30. September 2026:** Encoder und Decoder allein, dazu dieselben
> Ziele auf whisper-medium (Abschnitt 3). Ab diesem Tag mittelt das
> Checkpoint-Mittel über die besten Zwischenstände statt über den besten und
> die beiden jüngsten (Abschnitt 4); alle Läufe dieses Berichts rechneten noch
> mit der alten Auswahl.

---

## 1. Was gemessen ist

| Achse | Werte | Stand |
|---|---|---|
| LoRA-Ziele | q, v gegen alle Projektionen | ein Paar, Abschnitt 2 |
| LoRA-Ziele | nur Encoder, nur Decoder | small und medium, Abschnitt 3 |
| LoRA-Rang | 64 | beauftragt |
| Steuergröße | WER | beauftragt |
| Kontext | Vokabular | beauftragt |
| Korrekturgewicht, Selbsttraining, Fenster | - | noch nicht beauftragt |

Verglichen wird wie im Modellbericht gepaart auf denselben Aufnahmen, je
Aufnahme von einem Modell gemessen, das sie nicht gelernt hat. Die Bereiche
hier sind vorläufig: 95 % aus 2000 Ziehungen **je Messung**, nicht je
Aufnahme - für einen ersten Blick genug, für eine Aussage nicht.

---

## 2. Alle Projektionen gegen q, v

Zwei Läufe mit denselben Achsen - Mit Abwandlungen, Early Stopping, voller
Augmentierung, Checkpoint-Mittel und WiSE-FT, Rang 32 - und nur einem
Unterschied: der Zusatz an `q_proj`, `v_proj` (3,5 M Gewichte) oder an allen
Projektionen samt Feedforward (13,0 M).

| | Grundmodell | q, v | alle | alle − q, v |
|---|---|---|---|---|
| Original, alle Faltungen (231) | 0,456 | 0,271 | **0,433** | +0,162 [+0,116; +0,214] |
| Original, Faltungen 2-6 (188) | 0,445 | 0,269 | 0,267 | −0,002 [−0,020; +0,016] |
| Rauschen, alle Faltungen (231) | 0,569 | 0,325 | 0,466 | +0,141 [+0,093; +0,193] |
| Rauschen, Faltungen 2-6 (188) | 0,561 | 0,324 | 0,312 | −0,012 [−0,031; +0,007] |

**Der Absturz ist eine einzige Faltung.** Über alle Aufnahmen liegt „alle"
weit hinter q, v (0,433 gegen 0,271). Ohne Faltung 1 sind beide gleichauf -
der Abstand ist null, der Bereich schließt ihn beiderseits ein. Faltung 1 steht
bei WER 1,16, 11 ihrer 43 Originale haben mehr Fehler als Wörter; ihr bester
Stand hat einen Validierungsverlust von 5,92, die übrigen Faltungen beider
Läufe liegen zwischen 0,98 und 1,89.

**Warum: die Lernrate am Ende des Warmlaufs.** Der Trainingsverlust fällt in
allen zwölf Faltungen zunächst gleich, bis die Lernrate nach 50 Schritten ihre
Spitze von 1e-3 erreicht. Dort springt er bei „alle" in zwei von sechs
Faltungen nach oben - von etwa 3 auf 8,2 (Faltung 1) und 9,3 (Faltung 5).
Faltung 5 erholt sich und endet bei WER 0,221, Faltung 1 nicht: Sie lernt 13
Durchgänge lang auf dem entgleisten Stand weiter und kommt nie unter 5,9. Bei
q, v springt keine. Die Lernrate des Rezepts ist für zwei Matrizen an der
Aufmerksamkeit gewählt; mit viermal so vielen Gewichten, darunter die breiten
Feedforward-Schichten, ist sie an der Grenze - mal hält es, mal nicht.

**Was das Endmodell daraus machte.** Faltung 1 blieb als ausgefranst draußen,
gemittelt wurden die übrigen fünf, und die Prüfung fand auf gelernten
Aufnahmen WER 0,00 - der ausgelieferte Stand ist gesund. Die Zahl der Tafel
(0,450) enthält Faltung 1 trotzdem: Sie beschreibt das Verfahren auf diesem
Korpus, und zu dem gehört, dass es jede sechste Faltung verlieren kann. Über
den Stand selbst sagt eher die Zeile „Faltungen 2-6".

**Vorläufig:** Alle Projektionen bringen bei dieser Lernrate nichts - auf den
gesunden Faltungen genau dasselbe wie q, v - und machen das Training
instabil. Das deckt sich mit der Literatur, nach der der Gewinn an der
Aufmerksamkeit sitzt. Offen ist, ob „alle" mit kleinerer Lernrate stabil läuft
und dann mehr bringt; dafür bräuchte es einen Lauf mit angepasstem Rezept.

---

## 3. Nur Encoder, nur Decoder

Alle Projektionen samt Feedforward, Rang 32 - einmal nur im Encoder, einmal
nur im Decoder. Auf small dieselben Achsen wie in Abschnitt 2, auf medium
dieselben, aber nur mit Originalen gelernt. Mittlere WER aller 233 gemessenen
Originale über alle Faltungen, ungepaart und ohne Bereiche - darum weicht
„alle" auf small um ein Tausendstel von Abschnitt 2 ab:

| | q, v | alle | nur Encoder | nur Decoder |
|---|---|---|---|---|
| small | 0,271 | 0,432 | 0,259 | 0,342 |
| medium | 0,209 | 0,352 | 0,208 | **1,732** |

**Nur Decoder auf medium scheitert.** Alle sechs Faltungen blieben als
ausgefranst draußen, der Lauf endete ohne Stand. Median-WER 1,17, 53 % der
Originale haben mehr Fehler als Wörter, die Ausgabe ist im Median fast doppelt
so lang wie die Vorlage - das Modell erzählt weiter, statt zuzuhören. Die
Lernrate springt dabei nicht, anders als bei „alle" in Abschnitt 2: Der
Validierungsverlust ist in fünf Faltungen nach dem zweiten Durchgang am besten
(in einer nach dem dritten) und steigt danach, der Trainingsverlust fällt
weiter. Der Decoder lernt die knapp 200 Lernsätze als Sprachmodell auswendig.
Verstärkt hat es die Auswahl des Checkpoint-Mittels (Abschnitt 4): In
Faltung 1 gingen die Durchgänge 2, 6 und 7 ins Mittel statt 2, 3 und 5.

**Nur Encoder** liegt bei beiden Modellen gleichauf mit q, v, auf small knapp
davor. **Vorläufig:** Der Gewinn sitzt im Encoder, also im Hören; der Decoder
passt sich schneller an die Lerntexte an, als er gewinnt.

---

## 4. Checkpoint-Mittel: die besten, nicht die jüngsten

Gemittelt werden sollen die drei besten Zwischenstände einer Faltung. Auf der
Platte lagen aber nur der beste und die beiden jüngsten: `transformers`
räumt nach `save_total_limit` die ältesten weg und schont nur den besten. Mit
Early Stopping sind die jüngsten die, nach denen die Geduld aufgebraucht war -
die am stärksten überangepassten. Das galt für jeden Lauf mit Checkpoint-Mittel
bis zum 29. September, auch für beide in Abschnitt 2 und alle in Abschnitt 3.

Ab dem 30. September behält der Trainer nach jedem Sichern die besten nach
der Steuergröße (`abschluss.aufraeumer`). Läufe davor und danach sind im
Checkpoint-Mittel darum nicht unmittelbar vergleichbar; Vergleiche innerhalb
dieses Berichts bleiben es, weil beide Seiten dieselbe Auswahl hatten.
