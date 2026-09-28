# Das Trainingsverfahren

Was aus Aufnahmen ein Modell macht - Zielfunktion, Ablauf, Stellen im
Quelltext - und welche Hebel es gibt, aus **demselben Material** mehr
herauszuholen. Aufträge, Warteschlange, Modelltafel und Freigabe stehen in
[App „lernen"](lernen.md).

---

## 1. In einem Absatz

Überwachtes Feintuning eines vortrainierten Sequenz-zu-Sequenz-Modells
(`whisper-small`, `-medium` oder `-large-v3`) auf Paaren aus Log-Mel-Spektrogramm
und Zeichenkette. Zielfunktion ist die Kreuzentropie je Marke unter Teacher
Forcing, je Probe gemittelt und mit einem Gewicht aus dem Manifest versehen.
AdamW, lineares Aufwärmen und Abklingen, halbe Genauigkeit (bf16 oder fp16,
je nach Karte), Gradientenakkumulation bis zum wirksamen Stapel des Rezepts.
Voll oder mit LoRA an den
Aufmerksamkeitsprojektionen. Auf der zurückgehaltenen Faltung wird geprüft
und der beste Stand behalten - nach dem Verlust je Durchgang oder nach der
WER, frei dekodiert je Drittel eines Durchgangs. Wählbar sind außerdem
Augmentierung zur Laufzeit, Early Stopping, Vorspulen, Checkpoint-Mittel und
Interpolation mit dem Grundmodell. Gemessen wird per
sechsfacher Kreuzvalidierung, mit Bootstrap-Bereichen auf jeder Zahl.

---

## 2. Der Weg durch den Quelltext

| # | Schritt | Wo |
|---|---|---|
| 1 | Sechs Faltungen je Stamm | `wortlaut/laeufe.verteile`, `apps/lernen/backend/services/aufteilung.py` |
| 2 | Manifest: Pfad, Text, Herkunft, Gewicht, Faltung je Probe und Fassung | `apps/lernen/backend/services/auftraege.py` (`_manifestzeile`) |
| 3 | Kernauswahl vervollständigen (nur `K`) | `apps/lernen/training/bewerten.py` (`vervollstaendige_kern`) |
| 4 | Lern- und Messzeilen einer Faltung | `apps/lernen/training/daten.py` (`zeilen_fuer_faltung`) |
| 5 | WAV → Log-Mel, Augmentierung, Marken, Stapel | `daten.py` (`Proben`, `Stapler`), `klangwandel.py` |
| 6 | Tempo schätzen oder suchen | `tempowahl.py` |
| 7 | **Der Lernschritt** | `finetune.py` (`trainiere`) |
| 8 | Die gewichtete Verlustrechnung | `finetune.py` (`GewichtetesTraining.compute_loss`) |
| 8a | Prüfplan und WER der Steuergröße | `steuerung.py`, `GewichtetesTraining.prediction_step` |
| 9 | Checkpoint-Mittel, WiSE-FT | `abschluss.py` (`fuehre_aus`) |
| 10 | LoRA verschmelzen, nach CTranslate2 wandeln | `finetune.py` (`wandle_um`) |
| 11 | Faltung messen, Endmodell prüfen, Stand eintragen | `bewerten.py`, `finetune.kreuzvalidiere` |

Wer eine Stelle lesen will, an der aus Daten ein besseres Modell wird, liest
`trainiere`: dort stehen die Hyperparameter, dort wird der Trainer gebaut und
gestartet.

---

## 3. Die Zielfunktion

Sei `x_i` das Spektrogramm der Probe `i` und `y_i = (y_{i,1} … y_{i,T_i})` ihre
Markenfolge:

```
  ℓ_i(θ)  =  − (1 / T_i) · Σ_t  log p_θ( y_{i,t} | y_{i,<t}, x_i )      (Verlust je Probe)

  L(θ)    =  ( Σ_i w_i · ℓ_i(θ) )  /  ( Σ_i w_i )                       (Verlust je Stapel)
```

Zwei Abweichungen von der Vorgabe von `transformers`:

1. **Normiert je Probe, nicht je Marke.** Sonst zählte ein langer Satz mehr
   als ein kurzer, und das Gewicht ginge in der Satzlänge unter.
2. **Gewichtet je Probe.** `w_i = 1,0` für eine Vorlage, `0,5` für eine
   Korrektur aus „schreiben" (`auftraege.GEWICHTE`). Eine Korrektur ist eine
   abgenickte Maschinenausgabe; gleichrangig trainierte sie dem Modell seine
   eigenen Fehler an. Die 0,5 ist begründet, aber ungemessen (**F**).

Die Validierung rechnet denselben gewichteten Verlust.

**Optimiert wird etwas anderes als beurteilt.** `L(θ)` ist ein Markenverlust
unter Teacher Forcing; beurteilt wird die WER nach freier Dekodierung mit Beam
Search in CTranslate2. Beide korrelieren, sind aber nicht dasselbe. Die
Steuergröße `wer` schließt die Lücke dort, wo ausgewählt wird (siehe
[Die Steuergröße](#die-steuergröße)); gelernt wird weiter an `L(θ)`.

---

## 4. Das Verfahren in Pseudocode

### Der Lauf

```
EINGABE:  Laufverzeichnis L (Auftrag, Manifest, ggf. Kernauswahl), Rezept R
AUSGABE:  Modellstand, Messwerte

entlade Ollama, melde die Karte K, warte auf Platz  # finetune.pruefe_karte

WENN Auswahl = kern:
    miss fehlende Werte mit dem freigegebenen Modell, wähle die besten 70 %,
    verteile sie auf eigene Faltungen                 # bewerten.vervollstaendige_kern

FÜR f = 1 … 6:
    D_lern ← Zeilen außerhalb von Faltung f            # je nach Datensatz nur Originale
    D_mess ← Zeilen in Faltung f, alle Fassungen, nur Vorlagen   # Korrekturen lernen nur
    θ_f, ergebnis_f ← TRAINIERE(θ_grund, D_lern, D_mess, R)
    M_f ← nach_CTranslate2(θ_f)
    FÜR jede Zeile z in D_mess:
        schreibe WER/CER/MER/WIL(z.text, dekodiere(M_f, z.audio))   # wortlaut/metriken.py

mitgenommen ← Median über die Faltungen: Plan, bester Durchgang, α, Tempo
θ ← TRAINIERE(θ_grund, alle Zeilen, ∅, R, mitgenommen)    # das Endmodell
prüfe θ an zwölf gelernten Aufnahmen                       # Plausibilität, keine Note
stelle WER/CER des Grundmodells daneben (aus „hören“)     # bewerten.gegen_grundmodell
trage ein mit status = fertig                              # Freigabe bleibt ein Mensch
```

### Die Trainingsschleife

```
FUNKTION TRAINIERE(θ, D_lern, D_mess, R, vorgaben):
    entlade Ollama
    WENN R.methode = lora: θ ← θ halb (bf16|fp16) + LoRA(Rang r, Ziele {q_proj, v_proj}) in fp32
    (s, g) ← erster Kandidat, dessen Probeschritt auf K passt   # finetune.zuschneiden
    a      ← R.stapel / s                           # s Proben je Schritt, g = Gradientensparen
    fixiere Sprache des Profils, Aufgabe = transcribe
    Plan  ← vorgaben.plan  ODER  (geduldig ? R.epochen_hoechstens : R.epochen)
    Warm  ← min(R.warmlauf_schritte, ⌈0,2 · Gesamtschritte⌉)
    Opt   ← AdamW(lr = R.lernrate, weight_decay = R.gewichtsverfall)
    bestes ← (∞, θ)                                 # `wert`: die Steuergröße

    FÜR epoche = 1 … Plan:
        FÜR jeden Stapel B aus mische(D_lern):
            merkmale ← augmentiere(LogMel(B.audio))    # nur Lernproben, gewürfelt
            L ← Σ w_i ℓ_i / Σ w_i                       # compute_loss
            rückwärts, beschneide Gradienten, Schritt alle a Stapel
            WENN D_mess ≠ ∅ und Prüfung fällig:          # je Durchgang, bei `wer` je Drittel
                S ← Steuergröße auf D_mess                # Verlust oder WER, frei dekodiert
                WENN S < bestes.wert: bestes ← (S, θ)
                WENN geduldig und R.geduld Durchgänge ohne Gewinn > R.mindestgewinn: Schluss
            WENN vorgaben.halt erreicht: Schluss        # nur das Endmodell

    θ ← bestes.θ                                        # nicht das letzte θ
    θ ← ABSCHLUSS(θ, R, Auftrag.abschluss)              # mitteln / interpolieren
    GIB ZURÜCK θ
```

Der beste Durchgang statt des letzten ist die wichtigste Entscheidung des
Rezepts: Bei wenigen hundert kurzen Sätzen dreht die Validierungskurve in der
Mitte, und die Epochenzahl wird so zur bloßen Obergrenze.

---

## 5. Die Rezepte

| | Volles Training | LoRA |
|---|---|---|
| trainierbare Gewichte (small) | 244 M (100 %) | ≈ 2,4 M (≈ 1 %) |
| Lernrate | 1e-5 | 1e-3 |
| Aufwärmschritte | 50, höchstens ein Fünftel | 50, höchstens ein Fünftel |
| Epochen fest / geduldig | 8 / 40 | 12 / 60 |
| Geduld, Mindestgewinn | 4, 0,001 | 5, 0,001 |
| Stapel × Akkumulation | 4 × 2 | 8 × 1 |
| Gewichtsverfall | 0,01 | 0,0 |
| Gradientenbegrenzung | 1,0 | 1,0 |
| Rang / Alpha / Ausfall | – | 32 / 64 / 0,05 |
| Ziele | alle | `q_proj`, `v_proj` |
| gemittelte Stände | 3 | 3 |
| WER-Prüfungen je Durchgang | 3 | 3 |
| α-Raster | 0; 0,1; 0,2; 0,3; 0,5 | 0; 0,05; 0,1; 0,2; 0,3; 0,5 |

Der Faktor 100 zwischen den Lernraten ist Absicht: Voll zieht eine hohe
Lernrate dem Modell in wenigen hundert Schritten alles aus, was es konnte; die
LoRA-Matrizen starten bei null. `stapel` ist in beiden der wirksame Stapel;
wie viele Proben je Schritt auf der Karte liegen, ob mit Gradientensparen und
in welcher Genauigkeit, misst der Trainer (`wortlaut/kartenplan.py`). Die
Zahlen stehen in `training/rezepte/` und nicht im Quelltext.

**Einordnung.** Whisper-small, voll und LoRA nebeneinander, je Sprecher - das
ist, was die aktuelle Arbeit zu dysarthrischer Sprache tut. Huber, Kernahan
und Waibel (2026) berichten für einen Sprecher einen Rückgang der WER von
128,4 % auf 15,8 % mit 1,4 Stunden Daten und auf 9,7 % mit Nutzerkorrekturen;
volles Feintuning schnitt dort besser ab als LoRA. Muller, Tóth und Roberts
(2026) finden im Ein-Sprecher-Fall keinen belastbaren Unterschied zwischen
LoRA und DoRA, wohl aber einen Nachteil von QLoRA; Adapter an den
Aufmerksamkeitsprojektionen tragen den Gewinn.

---

## 6. Die Bausteine

Jede Maßnahme ist eine **Achse** des Auftrags, keine stille Änderung des
Rezepts - sonst ist hinterher nicht zu sagen, was gewirkt hat. Die Vorgabe
jeder Achse rechnet ohne die Maßnahme.

### Augmentierung zur Laufzeit

`apps/lernen/training/klangwandel.py`, angewandt beim Laden jeder Lernprobe,
gewürfelt und nirgends abgelegt:

| Wahl | was mit einer Probe geschieht |
|---|---|
| `keine` | nichts |
| `masken` | SpecAugment: je zwei Zeit- und Frequenzmasken |
| `umgebung` | dazu gewürfelter Raum (Nachhall 0,05–0,35 s) und Rauschen (10–35 dB Abstand) |
| `voll` | dazu Tempo 0,9–1,1 |

* **Tempo hat eine eigene Stufe.** Bei dysarthrischer Sprache ist das
  Sprechtempo Merkmal, nicht Störung; `umgebung` gegen `voll` beantwortet, ob
  ±10 % helfen oder schaden.
* **Keine Lautstärke.** Whisper normiert das Log-Mel-Spektrogramm; ein
  Verstärkungsfaktor ändert daran fast nichts.
* **Nur die Lernproben.** Eine Validierung, die in jedem Durchgang anders
  klingt, mäße den Würfel.
* **Die Masken enden beim letzten gesprochenen Rahmen.** Whisper füllt auf
  30 Sekunden auf; ein Balken in der Auffüllung träfe nur Stille, und maskierte
  Bänder allein dort wären ein Merkmal ohne Bezug zur Sprache.

Kosten je Probe von vier Sekunden gegen 9,1 ms für den Merkmalsausleser:
`masken` 0,08 ms, `umgebung` 0,77 ms, `voll` 4,4 ms. Vorbereitet wird in zwei
Ladefäden, während die Karte rechnet.

### Die Steuergröße

`apps/lernen/training/steuerung.py`: woran bester Zwischenstand, Abbruch bei
`geduldig` und das α des Abschlusses gewählt werden.

| Wahl | geprüft | Maß |
|---|---|---|
| `verlust` | je Durchgang | gewichteter Validierungsverlust |
| `wer` | je Drittel eines Durchgangs (`wer_pruefungen_je_durchgang`) | WER nach freier Dekodierung |

* **Dieselbe WER wie die Messung.** Normalisiert mit `wortlaut/metriken.py`
  und je Zeile gemittelt wie in der Bewertung einer Faltung - nur gierig in
  torch statt mit Beam Search in CTranslate2. Die Prüfung soll Stände
  ordnen, nicht die letzte Stelle treffen.
* **Warum überhaupt.** Der Validierungsverlust bestraft Marken, an denen die
  freie Dekodierung längst einen anderen Pfad nähme, und sieht die
  Textangleichung nicht; bei kleinen Korpora fallen beide Kurven regelmäßig
  auseinander.
* **Eigene Dekodierung statt `predict_with_generate`.** Jene reichte die
  Probengewichte an `generate` weiter und rechnete den Verlust ungewichtet;
  `GewichtetesTraining.prediction_step` rechnet den gewichteten Verlust und
  dekodiert daneben, mit höchstens doppelt so vielen Marken wie der längste
  Satz der Validierung.
* **Die Geduld zählt Durchgänge.** Bei drei Prüfungen je Durchgang wartet
  `geduldig` dreimal so viele Prüfungen.
* **Öfter prüfen heißt öfter sichern**, deshalb ohne Optimierer
  (`save_only_model`). Das Endmodell hält auch mitten in einem Durchgang an
  (`_halt_nach`).
* **Mehr Auswahl, mehr Anpassung an die Validierung.** Je feiner an der
  zurückgehaltenen Faltung gewählt wird, desto optimistischer wird ihre Zahl;
  dagegen stehen die Vertrauensbereiche.
* Die Validierungskurve zeigt die WER als dritte Reihe auf eigener Achse.

### Early Stopping (`geduldig`)

Statt der festen Epochenzahl eine weite Obergrenze und Schluss nach `geduld`
Prüfungen ohne Gewinn über `mindestgewinn`. Ausgeliefert wird ohnehin der
beste Durchgang, zu lange zu laufen kostet also nur Zeit. Die Geduld ist
großzügig, weil der Verlust über wenige Aufnahmen selbst streut. Erreicht ein
Lauf die Obergrenze, bevor die Geduld aufgebraucht ist, sagt das Protokoll es.
Ohne Validierungsproben fällt `geduldig` auf `fest` zurück.

Der **Warmlauf** ist auf ein Fünftel der Schritte gedeckelt; ein sehr kleiner
Korpus wäre sonst ganz Rampe.

### Der Abschluss

`apps/lernen/training/abschluss.py`, zwischen `trainer.train()` und dem
Sichern:

| Wahl | was geschieht |
|---|---|
| `bester` | der beste Zwischenstand |
| `mittel` | die besten Zwischenstände elementweise gemittelt („Model Soup") |
| `interpoliert` | θ = α·θ_grund + (1−α)·θ_fein, α an der Validierung gewählt (WiSE-FT) |
| `beides` | erst mitteln, dann interpolieren |

* **α = 0 steht im Raster.** Die Interpolation kann dann nicht verlieren; ein
  gewähltes α = 0 ist ein Ergebnis und steht so am Stand.
* **Nie schlechter als der Anfang.** Der Abschluss merkt sich den Stand, mit
  dem er begann, und stellt ihn wieder her, wenn er am Ende schlechter
  dasteht; der Stand trägt dann „zurückgenommen".
* **Bei LoRA ist die Interpolation eine Multiplikation**: θ_grund + (1−α)·Δ,
  also die B-Matrizen skaliert. Die Mittelung ist bei LoRA eine Näherung, weil
  B·A in B und A nicht linear ist.
* **Wer mittelt, hebt mehr Zwischenstände auf**, dafür ohne Optimierer
  (`save_only_model`) - ein Lauf wird nie fortgesetzt.
* **Das Endmodell wählt nicht**, es übernimmt den Median des α der Faltungen.
* Ohne Validierungsproben fällt der Abschluss auf `bester` zurück.

Das Manifest des Standes trägt `abschluss` und `abschluss_bericht`: gemittelte
Stände, α, die Steuergröße (`mass`) vorher, nach der Mittelung und danach.

### Vorspulen

Siehe [lernen](lernen.md#wie-schnell-gehört-wird). Gesucht wird am
unveränderten Grundmodell auf den Lernzeilen jeder Faltung, nie an Messdaten.

### Vertrauensbereiche

`packages/wortlaut/src/wortlaut/streuung.py`, neben `metriken.py`: Die eine
bewertet ein Paar aus Vorlage und Erkennung, die andere, wie weit ein
Mittelwert über viele trägt.

| | |
|---|---|
| `intervall(bloecke)` | 95-%-Bereich eines Mittelwerts, 2000 Ziehungen |
| `unterschied(bloecke)` | zwei Reihen gepaart: Differenz, Bereich, p-Wert |
| `bilde` / `bilde_paare` | Messungen zu Blöcken bündeln |
| `Verfahren.marke` | das Verfahren als Zeichenkette, gespeichert neben jedem Bereich |

* **Blockweise je Aufnahme.** Die Fassungen einer Aufnahme sind nicht
  unabhängig; der Bereich je Einheit ist auf diesen Daten etwa halb so breit
  wie der richtige (`packages/wortlaut/tests/test_streuung.py`). Er bleibt als
  `einheit` wählbar, weil die Literatur ihn rechnet.
* **Fester Keim.** Dieselbe Messreihe ergibt auf jeder Maschine denselben
  Bereich; gleich viele Blöcke bekommen dieselben Ziehungen, was den
  gepaarten Vergleich erst möglich macht.

Eingeschaltet tritt der Bereich neben die Zahl, nie an ihre Stelle
(`apps/lernen/tests/test_vergleich.py::TestVertrauensbereiche`). Die Bereiche
der Grundmodelle werden beim Zusammenstellen aus den Einzelzeilen in „hören"
gerechnet; ein Stand bringt seine im Manifest mit.

---

## 7. Offene Hebel

Erwartet ist eine Einschätzung, kein Messwert; relativ zur heutigen WER.

| | Maßnahme | erwartet | Aufwand | Risiko |
|---|---|---|---|---|
| **E** | LoRA-Ziele erweitern, Rang prüfen | 0–5 % | gering | gering |
| **F** | Korrekturgewicht messen; Selbsttraining | 5–20 % | hoch | mittel |
| **G** | Encoder auf die tatsächliche Länge kürzen | 2–4× Tempo | mittel | mittel |
| **H** | Kontextverstärkung beim Dekodieren | 3–10 % | gering | gering |

### E - LoRA genauer einstellen

Ziele von `{q_proj, v_proj}` auf `{q,k,v,o_proj, fc1, fc2}` erweitern, Rang 8,
32 und 64 gegeneinander, Encoder und Decoder getrennt. Die
Ein-Sprecher-Vergleiche sagen, dass Adapter an der Aufmerksamkeit den Gewinn
tragen und exotischere Varianten nichts Belastbares bringen. Die getrennte
Betrachtung beantwortete eine inhaltliche Frage: Abweichende Aussprache ist
ein Encoder-, abweichender Wortschatz ein Decoder-Problem.

### F - Die Korrekturen ernst nehmen

1. Das Gewicht 0,5 gegen 0,25, 0,75 und 1,0 stellen.
2. Das Gewicht je Probe aus der Korrekturhistorie ableiten: Eine unverändert
   bestätigte Korrektur ist etwas anderes als eine in drei Anläufen
   umgeschriebene. Die Information liegt in `schreiben` vor; das Manifest
   bräuchte ein Feld.
3. Selbsttraining: unbeschriftetes Audio mit dem aktuellen Modell beschriften,
   nach Konfidenz filtern, gewichtet zurückspeisen.

Die Korrekturschleife ist die Datenquelle, die im Betrieb nicht versiegt; die
zitierte Fallstudie holt dort ihren größten zusätzlichen Gewinn (10,7 % →
9,7 %). Selbsttraining verstärkt eigene Fehler und gehört ans Ende.

### G - Die 30 Sekunden loswerden

Die Positionseinbettungen des Encoders auf etwa 10 s kürzen. Bei Äußerungen
von drei bis fünf Sekunden geht heute rund 80 % der Encoder-Rechnung auf
Stille. CTranslate2 und faster-whisper erwarten aber die 30-Sekunden-Geometrie;
gangbar wäre, gekürzt zu trainieren und für die Auslieferung zurückzubringen,
oder die Kürzung nur für Vorläufe zu nutzen, deren Ergebnis eine Rangfolge ist.
Ein Lauf dauert heute unter einer Stunde; **G** ist nützlich, aber keine
Bedingung.

### H - Die Dekodierseite

Flache Fusion eines kleinen n-Gramm-Modells oder Trie-basierte
Kontextverstärkung, dazu ein Startprompt mit dem einschlägigen Vokabular. Die
einzige Maßnahme ohne Training, und das Textmaterial liegt vor: Vorlagen aus
`hören`, bestätigte Diktate aus `schreiben`. faster-whisper bringt flache
Fusion nicht mit; der billige Einstieg ist der Startprompt in
`LokalerTranskriptor.transkribiere`. Er kann Whisper auch zum Halluzinieren
verleiten und gehört gemessen wie alles andere.

---

## 8. Bewusst nicht vorgeschlagen

* **Ein größeres Grundmodell** beantwortet nicht die Frage dieses Dokuments -
  mehr aus demselben Material bei demselben Grundmodell. `whisper-medium`
  steht als Achse zur Wahl; beides in derselben Tafel zeigt, ob ein Hebel
  auch bei besserem Ausgangspunkt noch trägt.
* **Eine Lernratensuche.** Zwei benachbarte Lernraten unterscheidet eine
  Validierung dieser Größe nicht verlässlich.
* **Synthetische Sprache.** Text-zu-dysarthrischer-Sprache braucht ein zweites
  trainiertes Modell samt Bewertung - ein eigenes Vorhaben.
* **Mehr Aufnahmen.** Der stärkste Hebel, aber kein Trainingsverfahren.

---

## 9. Literatur

Personalisierung für atypische Sprache:

* Huber, Kernahan, Waibel: *Adapting Foundation ASR Models to Dysarthric
  Speech: A Case Study.* arXiv:2606.31722 (2026) -
  <https://arxiv.org/abs/2606.31722>
* Muller, Tóth, Roberts: *Choosing a PEFT Variant for Per-Patient Dysarthric
  ASR.* arXiv:2609.02735 (2026) - <https://arxiv.org/abs/2609.02735>
* Wagner u. a.: *Personalized Fine-Tuning with Controllable Synthetic Speech
  from LLM-Generated Transcripts for Dysarthric Speech Recognition.*
  Interspeech 2025, arXiv:2505.12991 - <https://arxiv.org/abs/2505.12991>
* *The Interspeech 2025 Speech Accessibility Project Challenge.*
  arXiv:2507.22047 - <https://arxiv.org/abs/2507.22047>
* Tomanek u. a.: *Personalizing ASR for Dysarthric and Accented Speech with
  Limited Data.* arXiv:1907.13511 - <https://arxiv.org/abs/1907.13511>
* *Probing Whisper for Dysarthric Speech in Detection and Assessment.*
  arXiv:2510.04219 - <https://arxiv.org/abs/2510.04219>

Verfahren und Augmentierung:

* Radford u. a.: *Robust Speech Recognition via Large-Scale Weak Supervision*
  (Whisper). arXiv:2212.04356 - <https://arxiv.org/abs/2212.04356>
* Hu u. a.: *LoRA: Low-Rank Adaptation of Large Language Models.*
  arXiv:2106.09685 - <https://arxiv.org/abs/2106.09685>
* Park u. a.: *SpecAugment.* arXiv:1904.08779 -
  <https://arxiv.org/abs/1904.08779>
* Ko u. a.: *Audio Augmentation for Speech Recognition.* Interspeech 2015
* *Can speed perturbation plus SpecAugment be outperformed by novel
  combinations of speech data augmentations for ASR? A low-resource
  evaluation.* J. Audio Speech Music Proc. (2026) -
  <https://doi.org/10.1186/s13636-026-00451-8>

Mittelung, Vergessen, Auswahl:

* Wortsman u. a.: *Model Soups.* arXiv:2203.05482 -
  <https://arxiv.org/abs/2203.05482>
* Wortsman u. a.: *Robust Fine-Tuning of Zero-Shot Models* (WiSE-FT).
  arXiv:2109.01903 - <https://arxiv.org/abs/2109.01903>
* *Weight Averaging: A Simple Yet Effective Method to Overcome Catastrophic
  Forgetting in ASR.* arXiv:2210.15282 - <https://arxiv.org/abs/2210.15282>

Selbsttraining und Kontextverstärkung:

* *Consistency Based Unsupervised Self-Training for ASR Personalisation.*
  arXiv:2401.12085 - <https://arxiv.org/abs/2401.12085>
* *Confidence Score Guided Incremental and Speaker Adaptive Pseudo-Labeling
  for Semi-Supervised Elderly Speech Recognition.* arXiv:2606.16546 -
  <https://arxiv.org/abs/2606.16546>
* *NGPU-LM: GPU-Accelerated N-Gram Language Model for Context-Biasing in
  Greedy ASR Decoding.* arXiv:2505.22857 - <https://arxiv.org/abs/2505.22857>
* *Zero-Shot Context Biasing with Trie-Based Decoding.* arXiv:2508.17796 -
  <https://arxiv.org/abs/2508.17796>

Statistik:

* Bisani, Ney: *Bootstrap Estimates for Confidence Intervals in ASR
  Performance Evaluation.* ICASSP 2004
* Liu u. a.: *Statistical Testing on ASR Performance via Blockwise Bootstrap.*
  arXiv:1912.09508 - <https://arxiv.org/abs/1912.09508>
