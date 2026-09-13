# Das Trainingsverfahren

Was heute aus Aufnahmen ein Modell macht - die Zielfunktion, der Ablauf, die
Stellen im Quelltext - und welche Hebel es gibt, aus **demselben Material**
mehr herauszuholen.

Die Umgebung drumherum steht in [App „lernen"](lernen.md): Aufteilung,
Aufträge, Warteschlange, Modelltabelle, Freigabe. Hier geht es allein um die
Rechnung.

> **Stand: September 2026.** Die Abschnitte 1 bis 5 beschreiben, was läuft.
> Ab Abschnitt 6 wird vorgeschlagen. Umgesetzt sind davon bisher **Stufe 0**
> (Vorschlag **I**, Vertrauensbereiche), die erste Hälfte von **Stufe 1**
> (Vorschlag **D**, Gewichtsmittelung und Interpolation) und **A** - alles so,
> dass es abwählbar bleibt: Wer nichts einschaltet und nichts wählt, bekommt
> Zahl für Zahl und Gewicht für Gewicht dasselbe wie vorher.
>
> Mit **A** ist zugleich der Befund 1 unten eingelöst worden, und zwar in beide
> Richtungen: Die beiden Amplitudenfassungen `pegel` und `lauter` sind nicht
> ergänzt, sondern **verworfen** - samt ihren Dateien und Datenbankzeilen.

---

## 1. Was heute gerechnet wird, in einem Absatz

Überwachtes Feintuning eines vortrainierten Sequenz-zu-Sequenz-Modells
(`whisper-small`, 244 M Parameter) auf Paaren aus Log-Mel-Spektrogramm und
Zeichenkette. Zielfunktion ist die Kreuzentropie je Marke unter Teacher
Forcing, also gewöhnliche Maximum-Likelihood-Schätzung des autoregressiven
Dekoders; je Probe kommt ein Gewicht aus dem Manifest darauf. Optimiert wird
mit AdamW, linearem Aufwärmen und linearem Abklingen, in halber Genauigkeit mit
Verlustskalierung und mit Gradientenakkumulation auf eine wirksame Stapelgröße
von acht. Trainiert wird entweder voll (alle Gewichte) oder mit LoRA (zwei
Niedrigrangmatrizen je Aufmerksamkeitsprojektion). Nach jedem Durchgang wird auf
der Validierung geprüft; ausgeliefert wird der Durchgang mit dem kleinsten
Validierungsverlust, nicht der letzte. Datenseitig liegt davor eine
Vervierfachung des Korpus durch drei Abwandlungen, die alle drei an der
**Amplitude** ansetzen.

Was es **nicht** gibt: Augmentierung im Merkmalsraum, Veränderung von
Sprechtempo oder Raum, Curriculum, Label Smoothing, Kreuzvalidierung,
Modellauswahl nach Wortfehlerrate, Gewichtsmittelung, ein Sprachmodell beim
Dekodieren, und keine Streuungsangabe auf irgendeiner der gemessenen Zahlen.
Das ist der Ausgangspunkt, und die Liste ist zugleich die Tagesordnung ab
Abschnitt 7.

---

## 2. Der Weg, mit Verweisen

| # | Schritt | Wo |
|---|---|---|
| 1 | Sechs Faltungen, der Reihe nach vergeben | `wortlaut/laeufe.py` (`faltung_fuer`), `apps/lernen/backend/services/aufteilung.py` |
| 2 | Manifest schreiben: je Probe Pfad, Text, Herkunft, Gewicht, Teil | `apps/lernen/backend/services/auftraege.py:_manifestzeile` |
| 3 | WAV → Log-Mel, Text → Marken, Stapel bilden | `apps/lernen/training/daten.py:63` (`Proben.__getitem__`), `:77` (`Stapler`) |
| 4 | **Modell aus Daten** - der eigentliche Lernschritt | `apps/lernen/training/finetune.py:205` (`trainiere`), `:341` (`trainer.train()`) |
| 5 | Die Verlustrechnung, die dieses Projekt von der Vorgabe abweichen lässt | `apps/lernen/training/finetune.py:174` (`GewichtetesTraining.compute_loss`) |
| 6 | LoRA verschmelzen, sichern | `finetune.py:357` ff. (`bericht.stufe("sichern")`) |
| 7 | Umwandlung nach CTranslate2 float16 | `finetune.py:381` (`wandle_um`) |
| 8 | Messung je Faltung, Endmodell auf allem, Eintrag in die Registry | `apps/lernen/training/bewerten.py`, `finetune.kreuzvalidiere` |

Wer nur **eine** Stelle lesen will, an der aus Trainingsdaten ein verbessertes
Modell wird, liest `finetune.py:282-341`: dort stehen die Hyperparameter, dort
wird der Trainer gebaut, dort läuft er.

**Die Aufteilung in Zahlen** *(Stand vor September 2026; heute wird
kreuzvalidiert, siehe **C**)*. Das Muster über sechs Plätze
(`train, train, test, train, validierung, test`) ergibt genau: 1/2 Training,
1/6 Validierung, 1/3 Test. Bei den anderthalb Stunden, von denen der
Projekttext ausgeht - grob 180 Aufnahmen - sind das etwa **90 Trainings-,
30 Validierungs- und 60 Testaufnahmen**. Diese drei Zahlen sind der wichtigste
Kontext für alles Weitere: Jeder Vorschlag muss sich daran messen lassen, dass
die Validierung aus 30 kurzen Sätzen besteht.

---

## 3. Die Zielfunktion, formal

Sei `x_i` das Spektrogramm der Probe `i` und `y_i = (y_{i,1} … y_{i,T_i})` ihre
Markenfolge. Der Dekoder ist autoregressiv, trainiert wird mit Teacher Forcing:

```
  ℓ_i(θ)  =  − (1 / T_i) · Σ_t  log p_θ( y_{i,t} | y_{i,<t}, x_i )      (Verlust je Probe)

  L(θ)    =  ( Σ_i w_i · ℓ_i(θ) )  /  ( Σ_i w_i )                       (Verlust je Stapel)
```

Zwei Abweichungen von dem, was `transformers` von sich aus täte, und beide sind
Absicht (`finetune.py:174`):

1. **Normiert je Probe, nicht je Marke.** Die Vorgabe mittelt über alle Marken
   des Stapels; ein langer Satz zählte dann mehr als ein kurzer. Hier wird erst
   je Probe über deren Marken gemittelt, dann über die Proben. Ohne das ginge
   das Gewicht `w_i` in der Satzlänge unter.
2. **Gewichtet je Probe.** `w_i = 1,0` für eine vorgelesene Vorlage, `w_i = 0,5`
   für eine Korrektur aus „schreiben" (`auftraege.py:46`). Der Text einer
   Korrektur ist keine Vorgabe, sondern eine abgenickte Maschinenausgabe; sie
   gleichrangig einzuspeisen hieße, dem Modell seine eigenen Fehler
   anzutrainieren.

Die 0,5 ist ein begründeter, aber ungemessener Wert - siehe Vorschlag **F**.

**Was optimiert wird und was zählt, ist nicht dasselbe.** `L(θ)` ist ein
Markenverlust unter Teacher Forcing. Beurteilt wird das Modell an der
Wortfehlerrate nach freier, autoregressiver Dekodierung mit Beam Search in
CTranslate2 - eine andere Größe, in einem anderen Rechenwerk. Zwischen beiden
besteht eine Korrelation, keine Identität. Genau in dieser Lücke sitzt
Vorschlag **B**.

---

## 4. Das Verfahren in Pseudocode

### Der Lauf als Ganzes

```
EINGABE:  Laufverzeichnis L           (Auftrag + Manifest, eingefroren)
          Rezept R                    (rezepte/whisper_{full,lora}.yaml)
AUSGABE:  Modellstand + Messwerte

θ ← Gewichte von whisper-small                      # vortrainiert, eingefroren erst mal nichts
fixiere Sprache = de, Aufgabe = transcribe          # keine Spracherkennung nebenher
lösche forced_decoder_ids                           # stünden sonst doppelt in den Marken

WENN R.methode = lora:
    θ_basis ← θ                                     # bleibt unverändert
    θ ← θ_basis + LoRA(Rang r, Ziele {q_proj, v_proj})   # ~1 % trainierbar

D_train ← Manifestzeilen(L, split = train)
D_val   ← Manifestzeilen(L, split = validierung)

θ* ← TRAINIERE(θ, D_train, D_val, R)                # ↓ unten
WENN R.methode = lora: θ* ← verschmelze(θ_basis, θ*)

M ← nach_CTranslate2(θ*, float16)
FÜR jede Zeile z in Manifestzeilen(L, split = test):    # alle vier Fassungen
    ŷ ← dekodiere(M, z.audio)
    schreibe WER/CER/MER/WIL(z.text, ŷ)             # wortlaut/metriken.py, dieselbe Datei wie „hören"
trage ein in Registry mit status = fertig           # Freigabe bleibt eine Menschenentscheidung
```

### Die Trainingsschleife

```
FUNKTION TRAINIERE(θ, D_train, D_val, R):
    Opt   ← AdamW(θ, lr = R.lernrate, weight_decay = R.gewichtsverfall,
                  β = (0.9, 0.999), ε = 1e-8)                    # Vorgabe von transformers
    Plan  ← linear_aufwärmen(R.warmlauf_schritte) dann linear_abklingen_auf_0
    Skala ← GradScaler()                                         # fp16, Turing kann kein bf16
    bestes ← (∞, θ)

    FÜR epoche = 1 … R.epochen:                                  # Obergrenze, keine Vorgabe
        FÜR jeden Stapel B aus mische(D_train):                  # Stapelgröße R.stapel
            merkmale ← LogMel80x3000(B.audio)                    # immer 30 s, gefüllt
            marken   ← zerteile(B.text), Füllstellen ← −100      # −100 = von der Rechnung ausgenommen
            mit fp16:
                logits ← θ(merkmale, marken_verschoben)
                ℓ_i    ← mittlere_Markenkreuzentropie je Probe
                L      ← Σ w_i ℓ_i / Σ w_i                       # ← finetune.py:174
            Skala.backward(L)
            WENN Schritt ≡ 0 (mod R.akkumulation):               # wirksame Stapelgröße 8
                beschneide_Gradienten(‖g‖ ≤ R.gradientenbegrenzung)
                Skala.step(Opt); Plan.step(); Opt.zero_grad()
            alle 10 Schritte: schreibe (Schritt, L, lr) nach fortschritt.jsonl

        L_val ← Σ_{D_val} ℓ_i / |D_val|                          # Teacher Forcing, ohne Gewichte
        sichere Zwischenstand
        WENN L_val < bestes.verlust: bestes ← (L_val, θ)         # ← load_best_model_at_end

    GIB ZURÜCK bestes.θ                                          # nicht das letzte θ
```

Die letzte Zeile ist die wichtigste Entscheidung des ganzen Rezepts. Bei
wenigen hundert kurzen Sätzen dreht die Validierungskurve irgendwo in der
Mitte; wer den letzten Durchgang nimmt, liefert ein auswendig gelerntes Modell
aus und macht die Epochenzahl zu einer Wette, die man je Korpus neu abschließen
müsste. So ist sie nur eine Obergrenze.

---

## 5. Die beiden Rezepte

| | Volles Training | LoRA |
|---|---|---|
| trainierbare Gewichte | 244 M (100 %) | ≈ 2,4 M (≈ 1 %) |
| Lernrate | 1e-5 | 1e-3 |
| Aufwärmschritte | 50 | 50 |
| Epochen (Obergrenze) | 8 | 12 |
| Stapel × Akkumulation | 4 × 2 | 8 × 1 |
| Gewichtsverfall | 0,01 | 0,0 |
| Gradientenbegrenzung | 1,0 | 1,0 |
| Rang / Alpha / Ausfall | - | 32 / 64 / 0,05 |
| Ziele | alle | `q_proj`, `v_proj` |

Der Faktor 100 zwischen den Lernraten ist kein Tippfehler: Beim vollen Training
zieht eine zu hohe Lernrate dem Modell in wenigen hundert Schritten alles aus,
was es vorher konnte; die LoRA-Matrizen starten dagegen bei null und müssen
erst etwas werden.

**Einordnung in die Literatur.** Die Wahl „whisper-small, voll und LoRA
nebeneinander, je Sprecher" ist genau das, was die aktuelle Arbeit zu
dysarthrischer Sprache tut. Huber, Kernahan und Waibel (2026) berichten für
einen einzelnen Sprecher einen Rückgang der Wortfehlerrate von 128,4 % auf
15,8 % mit **1,4 Stunden** Anpassungsdaten und auf 9,7 % mit dem vollen
Material einschließlich Nutzerkorrekturen - und dass volles Feintuning dort
besser abschnitt als LoRA. Muller, Tóth und Roberts (2026) vergleichen sieben
Verfahren der LoRA-Familie im Ein-Sprecher-Fall und finden keinen belastbaren
Unterschied zwischen LoRA und DoRA, wohl aber einen deutlichen Nachteil von
QLoRA; Adapter an den Aufmerksamkeitsprojektionen - dieselbe Wahl wie hier -
tragen den Gewinn. Beides stützt den bestehenden Aufbau. Die Zahl 1,4 Stunden
ist dabei die eigentliche Nachricht: Die Größenordnung dieses Projekts genügt.

---

## 6. Wo dieses Verfahren heute Leistung liegen lässt

Acht Punkte, nach Hebel sortiert, jeweils mit Verweis auf den Vorschlag, der
sie aufgreift.

1. ~~**Die Augmentierung fasst nur die Amplitude an.**~~ **Erledigt**
   (September 2026). `pegel`, `lauter` und `rauschen` veränderten alle drei die
   Lautstärke, und zwei davon fast nur diese; der Merkmalsausleser von Whisper
   rechnet ein Log-Mel-Spektrogramm mit anschließender Normierung und ist
   gegenüber einem reinen Verstärkungsfaktor weitgehend unempfindlich. Der
   Datensatz war vervierfacht, die Varianz nicht. Die beiden reinen
   Amplitudenfassungen sind deshalb **verworfen**, und an ihre Stelle ist eine
   gewürfelte Abwandlung zur Laufzeit getreten: siehe **A**.
2. **Ausgewählt wird nach dem falschen Maß.** `metric_for_best_model` ist
   `eval_loss`, also Markenkreuzentropie unter Teacher Forcing. Entschieden
   wird aber nach WER nach freier Dekodierung. → **B**
3. **Ausgewählt wird zu grob und auf zu wenig.** Geprüft wird einmal je
   Durchgang, also acht- bzw. zwölfmal im ganzen Lauf, auf 30 Aufnahmen. Beide
   Zahlen sind klein; das Minimum der Kurve ist damit selbst eine Zufallsgröße.
   → **B**, **C**
   
   Teilweise erledigt (September 2026): Dass **überhaupt ein Minimum** in der
   Kurve liegt, war bei einem sehr kleinen Korpus nicht der Fall - sie fiel bis
   zum letzten Durchgang. Dagegen steht jetzt die Wahl `geduldig`, siehe **J**.
4. ~~**Der Endstand ist ein einzelner Zwischenstand.**~~ **Wählbar seit
   September 2026.** Weder wurden Zwischenstände gemittelt noch wurde gegen das
   Grundmodell interpoliert - dabei sind genau diese beiden Handgriffe in der
   Literatur die billigste bekannte Absicherung gegen katastrophales Vergessen
   und gegen Überanpassung. Beides steht jetzt als dritte Achse beim
   Beauftragen; die Vorgabe bleibt der einzelne beste Zwischenstand. Siehe
   **D**.
5. ~~**Kein Maß für Zufall.**~~ **Erledigt** (September 2026). `bewerten.py`
   lieferte Mittelwerte über 60 Testaufnahmen mal vier Fassungen, und ob 14,2 %
   gegen 13,8 % ein Unterschied war oder Rauschen, sagte keine Zahl im Projekt.
   Seitdem schon: siehe **I**.
6. **Das Gewicht 0,5 ist gesetzt, nicht gemessen** - und Korrekturen sind die
   Datenquelle, die im Betrieb als einzige von selbst wächst. → **F**
7. **Die Dekodierseite ist unberührt.** Kein Sprachmodell, keine
   Kontextverstärkung, kein Startprompt. Das ist die einzige Gruppe von
   Maßnahmen, die ohne jedes Training wirkt - und die Vorlagen dieses Projekts
   liefern das Vokabular dafür frei Haus. → **H**
8. **Jede Probe kostet 30 Sekunden Rechenzeit.** Whisper füllt jede Aufnahme
   auf 30 s; bei Äußerungen von drei bis fünf Sekunden geht der weitaus größte
   Teil der Encoder-Rechnung auf Stille. Das kostet keine Güte, aber ein
   Vielfaches der Zeit - und Zeit ist hier die Währung, in der man
   Kreuzvalidierung und Wiederholungsläufe bezahlt. → **G**

---

## 7. Verbesserungsoptionen

Erwarteter Effekt ist eine Einschätzung, kein Messwert; „relativ" heißt
relativ zur heutigen Wortfehlerrate.

| | Maßnahme | Erwartet | Aufwand | Risiko | |
|---|---|---|---|---|---|
| **A** | SpecAugment + Tempo-/Raumvariation statt reiner Amplitude | 5-15 % rel. | mittel | gering | ✅ |
| **B** | Auswahl nach WER, häufiger geprüft | 3-8 % rel. | mittel | gering | |
| **C** | k-fache Kreuzvalidierung über alle Daten | indirekt | mittel | keins | ✅ |
| **D** | Gewichtsmittelung / Interpolation mit dem Grundmodell | 2-6 % rel. | gering | gering | ✅ |
| **E** | LoRA-Ziele erweitern, Rang prüfen | 0-5 % rel. | gering | gering | |
| **F** | Korrekturgewicht messen statt setzen; Selbsttraining | 5-20 % rel. | hoch | mittel | |
| **G** | Encoder auf die tatsächliche Länge kürzen | 2-4× Tempo | mittel | mittel | |
| **H** | Kontextverstärkung beim Dekodieren | 3-10 % rel. | gering | gering | |
| **I** | Vertrauensbereiche auf allen Messwerten | 0 % | gering | keins | ✅ |
| **J** | Geduldiges Training statt fester Durchgangszahl | 0-20 % rel. | gering | keins | ✅ |

### A - Augmentierung dorthin, wo sie wirkt ✅ umgesetzt

**Was war geplant.** Die drei Amplitudenfassungen ergänzen (nicht ersetzen) um:
*SpecAugment* (Zeit- und Frequenzmasken direkt auf dem Log-Mel, zur Laufzeit,
also ohne eine einzige zusätzliche Datei), *Tempoveränderung* mit den
klassischen Faktoren 0,9 / 1,0 / 1,1, und *Raum* per Faltung mit
Impulsantworten.

**Warum.** Die Kombination aus Tempoveränderung und SpecAugment ist seit Jahren
die Bezugsgröße für Augmentierung in ressourcenarmer Spracherkennung, und neuere
Vergleichsarbeiten finden sie schwer zu schlagen. SpecAugment ist dabei
besonders passend: Es ist Regularisierung im Merkmalsraum, kostet keinen
Speicherplatz und greift genau die Überanpassung an, die hier laut
Validierungskurve nach vier bis acht Durchgängen einsetzt.

**Vorsicht - und das ist der Punkt, an dem dieses Projekt anders liegt als die
Literatur.** Tempoveränderung bei dysarthrischer Sprache ist zweischneidig:
Sprechtempo, Pausenstruktur und Rhythmus sind hier nicht Störung, sondern
Merkmal. Ein Modell, das auf ±10 % Tempo unempfindlich gemacht wird, verliert
möglicherweise genau die Unterscheidung, für die es gebaut wurde. Das ist eine
empirische Frage, und dieses Projekt kann sie beantworten: als fünfte und
sechste Achse in der bestehenden Vierfelder-Tafel.

**Was daraus geworden ist.** Ergänzt wurde nicht, sondern ersetzt: `pegel` und
`lauter` sind weg (Befund 1), und die Abwandlung ist von der Platte in den
Trainer gewandert. Gerechnet wird in `apps/lernen/training/klangwandel.py`,
angewandt in `daten.py:Proben.__getitem__` - zur Laufzeit, gewürfelt, und
nichts davon wird abgelegt.

Die Stufen sind eine **vierte Achse** des Auftrags, neben Methode, Datensatz
und Abschluss:

| Wahl | Was mit einer Probe geschieht |
|---|---|
| `keine` | nichts - die Vorgabe und das Verfahren von vorher |
| `masken` | SpecAugment: Zeit- und Frequenzbalken im Spektrogramm |
| `umgebung` | dazu ein gewürfelter Raum und ein gewürfeltes Grundgeräusch |
| `voll` | dazu Tempo |

**Fünf Entscheidungen darin.**

* **Tempo hat eine eigene Stufe.** Das ist die Vorsicht von oben, in Code
  gegossen: Sprechtempo ist bei dysarthrischer Sprache Merkmal und nicht
  Störung. Ob ±10 % helfen oder schaden, ist eine Frage - und `umgebung` gegen
  `voll` ist genau der Versuch, der sie beantwortet.
* **Die Lautstärke fehlt mit Absicht.** Sie wäre der billigste Griff und ist
  der einzige, von dem wir wissen, dass er nichts bringt.
* **Nur die Lernproben.** Der Wandler hängt allein am Datensatz `train`
  (`finetune.py`). Die Validierung steuert den Lauf - sie sagt, welcher
  Durchgang der beste war und welches α gewinnt (**D**); eine Validierung, die
  in jedem Durchgang anders klingt, misst den Würfel und nicht das Modell. Das
  zurückgehaltene Faltung wird nicht mitgelernt.
* **Die Masken enden beim letzten gesprochenen Rahmen.** Whisper füllt jede
  Aufnahme auf 30 Sekunden auf; bei einem Satz von vier Sekunden sind 2600 von
  3000 Rahmen Stille. Ein Balken an zufälliger Stelle träfe fast immer die
  Auffüllung - und ein Frequenzbalken über die ganze Zeitachse machte die
  Auffüllung zur einzigen Stelle mit maskierten Bändern, also zu einem Merkmal,
  das mit Sprache nichts zu tun hat.
* **Nichts wird abgelegt, und das ist gemessen.** Eine Datei je Aufnahme wäre
  in jedem Durchgang dieselbe - gerade das soll sie nicht sein. Die Kosten
  sprechen ebenfalls nicht dafür (siehe unten).

**Was es kostet.** Gemessen im Trainer-Abbild, je Probe von vier Sekunden,
gegen die 9,1 ms, die der Merkmalsausleser ohnehin verlangt:

| Stufe | Aufwand | Anteil an der Vorbereitung |
|---|---|---|
| `masken` | 0,08 ms | +1 % |
| `umgebung` | 0,77 ms | +8 % |
| `voll` | 4,4 ms | +49 % |

Auch die teuerste Stufe ist damit umsonst zu haben: Vorbereitet wird in zwei
Ladefäden, während die Karte rechnet, und ein Trainingsschritt dauert ein
Vielfaches davon. Der Raum ist der Brocken darin (4,7 ms) und wäre ohne
Faltung über die Fourier-Transformation hundertmal so teuer.

### B - Auswählen nach dem, worauf es ankommt

**Was.** `compute_metrics` mit `predict_with_generate=True` und WER als
`metric_for_best_model`; dazu `eval_strategy="steps"` mit einem Takt von etwa
einem Drittel Durchgang statt einmal je Durchgang.

**Warum.** Der Validierungsverlust ist ein Stellvertreter. Er bestraft eine
falsche Marke an einer Stelle, an der die freie Dekodierung längst einen
anderen Pfad genommen hätte, und er sieht nichts von der Textangleichung, mit
der am Ende gemessen wird (`wortlaut/metriken.py`). Bei kleinen Korpora fallen
beide Kurven regelmäßig auseinander: Der Verlust steigt, während die WER noch
fällt - und dann wird der falsche Durchgang ausgeliefert.

**Kosten.** Freie Dekodierung von 30 Aufnahmen je Prüfpunkt, in torch statt
CTranslate2, also merklich langsamer als der jetzige Verlustdurchgang. Bei
dreimal so vielen Prüfpunkten ist das die Hauptkostenstelle dieses Vorschlags.
Gegenrechnung: Es ist der einzige Vorschlag, der die Lücke zwischen
Trainingsziel und Auslieferungskriterium direkt schließt.

**Sauber bleiben.** Die Validierung darf dabei nicht zur zweiten Testmenge
werden. Je feiner geprüft und je öfter ausgewählt wird, desto mehr passt man
sich an 30 Aufnahmen an. Das ist der Grund, warum **C** und **I**
dazugehören.

### C - Kreuzvalidierung statt einer festen Sechstelmenge ✅ umgesetzt

**Was geplant war.** Training und Validierung (zusammen zwei Drittel) in k = 5
Faltungen teilen und k Läufe rechnen; der Test bleibt unangetastet.

**Was daraus geworden ist - und es ist mehr.** Das Testdrittel ist ganz
weggefallen. Kreuzvalidiert wird über **alle** Aufnahmen, sechsfach, und die
Faltung folgt schlicht der Reihenfolge des Korpus: 1, 2, 3, 4, 5, 6, 1, 2, …

Der Anlass war ein Korpus von neun Aufnahmen. Darin bestand der Test aus
dreien, die Validierung aus **einer**. Eine Fehlerrate über drei Aufnahmen ist
keine Auskunft, sondern ein Würfelwurf - und ein zurückgehaltenes Drittel, das
nie etwas lernt, ist bei dieser Korpusgröße purer Verlust.

**Ein Lauf sind jetzt sieben Trainings.**

| | Lernt auf | Gemessen an |
|---|---|---|
| Faltung 1 … 6 | fünf Sechsteln | dem zurückgehaltenen Sechstel |
| Endmodell | allem | nichts |

Nach den sechs Faltungen liegt zu **jeder** Aufnahme eine Messung von einem
Modell vor, das sie nie gehört hat; diese Zeilen zusammen sind die Zahl des
Laufs. Danach wird ein siebtes Mal trainiert, auf allem, mit dem Median der
Durchgangszahl und dem Median des α aus den Faltungen - das ist der Stand, der
in „schreiben" diktiert.

**Vier Entscheidungen darin.**

* **Zwei Modelle, eine Zeile in der Tabelle.** Die Zahlen stammen aus den sechs
  Faltungsmodellen, ausgeliefert wird das siebte. Es hat mehr gesehen und ist
  sehr wahrscheinlich besser - und genau deshalb nicht mehr ehrlich messbar. Die
  Zahl daneben ist die vorsichtige. Das muss man wissen, und deshalb steht es
  in der Ansicht.
* **Die Faltung wird nicht gespeichert.** Die alte Zuteilung musste es, weil
  eine Aufnahme, die einmal geprüft hatte, nie wieder trainieren durfte. In
  fünf von sechs Faltungen trainiert jetzt jede Aufnahme ohnehin; die Faltung
  entscheidet nur, wo sie gemessen wird. Sie folgt deshalb dem Korpus und steht
  im Schnappschuss - eine Tabelle daneben wäre die erste Wahrheit, die nach der
  nächsten Löschung nicht mehr stimmt.
* **Gemessen wird immer auf allen Fassungen**, gelernt je nach `daten`. Damit
  ist das Manifest für beide Datensätze dasselbe und bleibt, was es sein soll:
  der Schnappschuss des Korpus, nicht die Anweisung an den Trainer.
* **Ein unabhängiger Test fehlt, und das steht so da.** Die Kreuzvalidierung
  sagt, wie gut das Verfahren auf **diesem** Korpus arbeitet, nicht, wie gut es
  auf der nächsten Aufnahme arbeitet. Wirklich unabhängige Testaufnahmen werden
  eigens aufgenommen werden.

**Kosten.** Siebenfache Rechenzeit je Lauf. Die Doku hat hier früher **G**
(Encoder kürzen) als Voraussetzung genannt; die gemessenen Laufzeiten auf
dieser Karte sagen etwas anderes - 0,6 bis 6,2 Minuten je Training, also unter
einer Stunde für einen ganzen Lauf. **G** bleibt nützlich, ist aber keine
Bedingung mehr.

**Eine Einschränkung, ehrlich benannt.** Mit `geduldig` steuert die
zurückgehaltene Faltung zugleich den Abbruch **und** liefert die Messung. Das
ist mild optimistisch - der Stopppunkt ist auf derselben Menge gewählt, an der
gemessen wird. Mit `fest` besteht das Problem nicht. Sauber wäre eine
geschachtelte Kreuzvalidierung; sie kostet das Quadrat und ist es bei dieser
Korpusgröße nicht wert.

### D - Zwei Handgriffe am Ende, die fast nichts kosten ✅ umgesetzt

**Was.** (i) *Gewichtsmittelung*: die besten drei bis fünf Zwischenstände
elementweise mitteln, statt einen zu nehmen. (ii) *Interpolation mit dem
Grundmodell*: θ_final = α·θ_grund + (1−α)·θ_feingetunt, α auf der Validierung
gewählt.

**Warum.** Beides sind Standardwerkzeuge geworden, weil sie keine zusätzliche
Trainingszeit kosten und keine Architekturänderung verlangen. Die Mittelung
über Stände in derselben Verlustmulde („Model Soup") verbessert Güte und
Robustheit ohne Kosten zur Laufzeit; die Interpolation zwischen Ausgangs- und
feingetuntem Stand (WiSE-FT) ist die direkteste bekannte Antwort auf
katastrophales Vergessen und in der Spracherkennung ausdrücklich erprobt.

**Warum es hier besonders passt.** Das volle Rezept fährt bewusst eine sehr
kleine Lernrate, *weil* Vergessen die Hauptgefahr ist. Eine Interpolation macht
diese Gefahr zu einem Regler, den man nach dem Training einstellt, statt zu
einer Wette, die man vor dem Training eingeht - und der Regler lässt sich
messen. Sehr wahrscheinlich erlaubt er zugleich eine **höhere** Lernrate im
Training, weil ihr Schaden nachträglich zurückgenommen werden kann.

**Was jetzt dasteht.** Gerechnet wird in `apps/lernen/training/abschluss.py`,
aufgerufen zwischen `trainer.train()` und `save_pretrained` - ohne einen
Eingriff in die Schleife. Der **Abschluss** ist eine dritte Achse des Auftrags
geworden, neben Methode und Datensatz (`wortlaut/laeufe.py`):

| Wahl | Was geschieht |
|---|---|
| `bester` | der beste Zwischenstand - die Vorgabe und das Verfahren von vorher |
| `mittel` | die besten Zwischenstände elementweise gemittelt |
| `interpoliert` | θ = α·θ_grund + (1−α)·θ_fein, α auf der Validierung gewählt |
| `beides` | erst mitteln, dann interpolieren |

**Fünf Entscheidungen darin.**

* **Eine Achse, keine Verbesserung.** Beides ist billig genug, um es einfach
  immer zu tun - und genau das wäre hier falsch gewesen: Jede Maßnahme kommt
  als weitere Achse in die Vergleichstafel, sonst ist hinterher nicht mehr zu
  sagen, was gewirkt hat. `bester` rechnet Gewicht für Gewicht das Verfahren
  von vorher, und ein Auftrag ohne dieses Feld ist derselbe Auftrag wie im
  August.
* **α wird an der zurückgehaltenen Faltung gewählt, nie an Gelerntem.** Sie
  wird nicht mitgelernt; ein α, das auf Trainingsmaterial gewählt wäre, machte
  aus der Messzahl eine Trainingszahl. Das Endmodell wählt gar nicht - es
  übernimmt den Median aus den sechs Faltungen (**C**). Gemessen wird der Validierungsverlust - dieselbe Größe, an der
  schon `load_best_model_at_end` den besten Durchgang erkennt. Der WER wäre das
  bessere Maß, verlangte aber je α einen Dekodierdurchgang; das gehört zu **B**.
* **α = 0 steht im Raster.** α = 0 ist der feingetunte Stand selbst. Steht es
  zur Wahl, kann die Interpolation auf der Validierung nicht verlieren - im
  schlechtesten Fall wählt sie den Stand, der ohne sie herausgekommen wäre. Ein
  gewähltes α = 0 ist deshalb keine Null, sondern ein Ergebnis, und es steht
  auch so in der Modelltabelle.
* **Für LoRA ist die Interpolation eine Multiplikation.** θ_fein = θ_grund + Δ,
  also ist α·θ_grund + (1−α)·θ_fein genau θ_grund + (1−α)·Δ - und Δ mit (1−α)
  zu malnehmen heißt, die B-Matrizen des Zusatzes zu skalieren. Kein
  Näherungsverfahren, kein zweiter Satz voller Gewichte. Die **Mittelung** ist
  bei LoRA dagegen eine Näherung: Gemittelt wird der Zusatz, und B·A ist in B
  und A zusammen nicht linear. Das ist das übliche Vorgehen; ob es taugt, sagt
  die Vergleichstafel.
* **Wer mittelt, braucht mehr Platz.** `save_total_limit` steigt von 1 auf die
  Zahl der zu mittelnden Stände - ein Zwischenstand, den der Trainer schon
  weggeräumt hat, lässt sich nicht mehr wiegen. Dafür fällt bei diesen Läufen
  der Optimierer aus den Sicherungen (`save_only_model`): Er wiegt zwei Drittel
  eines Zwischenstandes, und dieses Projekt setzt einen Lauf nie fort. Ohne
  Mittelung bleibt beides, wie es war.

**Was ein Stand davon mitbringt.** Im Manifest des Modellstandes steht neben
`methode` und `daten` jetzt `abschluss`, und daneben, was dabei herauskam: die
gemittelten Zwischenstände, das gewählte α, der Validierungsverlust davor,
nach der Mittelung und danach. Ein Stand, dessen α niemand mehr nachsehen kann,
wäre mit keinem anderen zu vergleichen.

**Wo es nicht rechnet.** Ohne Validierungsproben - ein Korpus unter einem
Dutzend Aufnahmen - gibt es weder eine Rangfolge der Zwischenstände noch ein
Maß für α. Dann fällt der Lauf auf `bester` zurück und schreibt es ins
Protokoll. Das ist ehrlicher, als α zu würfeln.

### E - LoRA genauer einstellen

**Was.** Ziele von `{q_proj, v_proj}` auf `{q,k,v,o_proj, fc1, fc2}`
erweitern; Rang 8 gegen 32 gegen 64 stellen; Encoder- und Decoder-Anteil
getrennt betrachten.

**Warum, und warum nur begrenzt.** Die Ein-Sprecher-Vergleiche der letzten
Zeit sagen übereinstimmend zwei Dinge: Adapter an den
Aufmerksamkeitsprojektionen tragen den Gewinn, und die exotischeren Varianten
der Familie (DoRA, VeRA, LoHA) bringen keinen belastbaren Vorsprung gegenüber
schlichtem LoRA. Zugleich schneidet in der Fallstudie mit starker Dysarthrie
volles Feintuning besser ab als LoRA - der Abstand zwischen dysarthrischer und
Standardsprache ist offenbar groß genug, dass die volle Kapazität hilft. Der
Erwartungswert dieses Vorschlags ist deshalb klein; er steht hier, weil er
billig ist und weil die getrennte Betrachtung von Encoder und Decoder eine
inhaltliche Frage berührt: Eine abweichende **Aussprache** ist ein
Encoder-Problem, ein abweichender **Wortschatz** ein Decoder-Problem. Welches
von beiden hier überwiegt, weiß das Projekt nicht - und es ließe sich messen.

### F - Die Korrekturen ernst nehmen

**Was.** Drei Stufen, aufeinander aufbauend:

1. Das Gewicht 0,5 gegen 0,25 / 0,75 / 1,0 stellen - eine Frage für **C**.
2. Das Gewicht **je Probe** aus der Erkennungsgüte ableiten statt pauschal je
   Quelle: Eine Korrektur, die der Mensch unverändert bestätigt hat, ist
   etwas anderes als eine, die er in drei Anläufen umgeschrieben hat. Die
   Information liegt in `schreiben` bereits vor.
3. Selbsttraining: unbeschriftetes Audio des Sprechers mit dem aktuellen Modell
   beschriften, nach Konfidenz filtern, gewichtet zurückspeisen.

**Warum.** Die Korrekturschleife ist der architektonische Kern dieses Projekts
- der Korpus wächst im Gebrauch. Sie ist zugleich die Stelle, an der die
zitierte Fallstudie ihren größten zusätzlichen Gewinn holt: von 10,7 % auf
9,7 % durch Hinzunahme der Korrekturen, und auf den Korrekturen selbst von
16,1 % auf 7,8 %. Die Datenquelle, die hier heute mit 0,5 abgewertet wird, ist
diejenige, die im Betrieb nicht versiegt.

**Risiko.** Selbsttraining verstärkt eigene Fehler - Konfidenzfilterung ist
notwendig und allein nicht hinreichend; die aktuelle Arbeit zu
Pseudobeschriftung in der Altersstimmenerkennung arbeitet deshalb mit
sprecheradaptiver, schrittweiser Aufnahme statt einer festen Schwelle. Dieser
Vorschlag gehört ans Ende des Plans, nicht an den Anfang.

### G - Die 30 Sekunden loswerden

**Was.** Die Positionseinbettungen des Encoders auf die tatsächlich benötigte
Länge kürzen (etwa 10 s statt 30 s) und entsprechend weniger Rahmen füllen.

**Warum.** Bei Äußerungen von drei bis fünf Sekunden entfallen heute rund 80 %
der Encoder-Rechnung auf Stille. Ein Faktor zwei bis vier auf der Trainings-
**und** Bewertungszeit ist keine Güteverbesserung, aber er ist die Voraussetzung
dafür, dass **C** bezahlbar wird - fünf Faltungen mal vier Rezeptvarianten sind
sonst ein Wochenende je Frage.

**Risiko, ehrlich benannt.** Gekürzte Positionseinbettungen sind eine
Abweichung von der Vorgabe, unter der Whisper trainiert wurde. Die Umwandlung
nach CTranslate2 und faster-whisper erwarten die 30-Sekunden-Geometrie; ein
gekürztes Modell wäre mit der bestehenden Erkennungsstrecke nicht ohne
Weiteres verwendbar. Praktikabler Mittelweg: gekürzt trainieren und für die
Auslieferung wieder auf volle Länge bringen, oder die Kürzung nur für die
Kreuzvalidierungs-Vorläufe nutzen, deren Ergebnis eine Rangfolge ist und kein
Modell. Vor der Umsetzung gehört das geprüft.

### H - Die Dekodierseite, die nichts kostet

**Was.** Flache Fusion eines kleinen n-Gramm-Modells oder Trie-basierte
Kontextverstärkung beim Strahlsuchlauf; dazu ein Startprompt mit dem
einschlägigen Vokabular.

**Warum.** Es ist die einzige Maßnahme dieser Liste, die **kein** Training
verlangt und trotzdem auf demselben Material wirkt - und dieses Projekt hat
das Textmaterial dafür bereits: Die Vorlagen aus `hören` und die bestätigten
Diktate aus `schreiben` sind ein sprecherspezifisches Korpus im passenden
Register. Namen, Fachwörter und wiederkehrende Wendungen sind genau die Klasse
von Fehlern, die Kontextverstärkung angeht, und sie sind bei einem einzelnen
Nutzer besonders gut vorhersagbar.

**Haken.** faster-whisper bringt flache Fusion nicht mit; das ist offene
Funktionalität, kein Schalter. Der billigere Einstieg ist der Startprompt -
eine Zeile in `LokalerTranskriptor.transkribiere` und sofort messbar. Achtung:
Ein Startprompt kann Whisper auch zum Halluzinieren verleiten; er gehört
gemessen wie alles andere, und zwar auf allen vier Fassungen.

### I - Vertrauensbereiche, und zwar zuerst ✅ umgesetzt

**Warum zuerst.** 60 gemessene Aufnahmen ergeben ein 95-%-Intervall, das mehrere
Prozentpunkte breit ist. Ein Großteil der Unterschiede, um die es in dieser
Liste geht, liegt darunter. Ohne Intervall ist jeder Vergleich in der
Modelltabelle eine Rangfolge von Rauschen - und das Projekt hat sich in seinem
eigenen Text darauf festgelegt, nichts zu behaupten, was es nicht gemessen hat.

**Was jetzt dasteht.** Gerechnet wird in `packages/wortlaut/src/wortlaut/streuung.py`
- eine eigene Datei neben `metriken.py`, weil es eine andere Art von Rechnung
ist: `metriken.py` bewertet ein Paar aus Vorlage und erkanntem Text,
`streuung.py` sagt, wie weit ein Mittelwert über viele solcher Paare trägt. Sie
kommt mit der Standardbibliothek aus und rechnet nichts neu ein zweites Mal:
Die Einzelergebnisse liegen je Zeile längst vor.

| | |
|---|---|
| `intervall(bloecke)` | 95-%-Bereich eines Mittelwerts, 2000 Ziehungen |
| `unterschied(bloecke)` | zwei Reihen gepaart: Differenz, Bereich, p-Wert |
| `bilde` / `bilde_paare` | Messungen zu Blöcken bündeln |
| `Verfahren.marke` | `bootstrap/aufnahme/2000/0.95/20260913` - das Verfahren als Zeichenkette |

**Drei Entscheidungen darin.**

* **Blockweise je Aufnahme.** Der gewöhnliche äußerungsweise Bootstrap ist hier
  zu optimistisch, weil die Äußerungen nicht unabhängig sind: Vier Fassungen
  derselben Aufnahme sind vier Messungen an einem Gegenstand. Auf den Daten
  dieses Projekts ist der naive Bereich etwa **halb so breit** wie der richtige
  - ein Test hält das fest (`packages/wortlaut/tests/test_streuung.py`). Die
  naive Ziehung bleibt als `einheit` wählbar: Sie ist das, was die meiste
  Literatur rechnet, und ohne sie wären die Zahlen hier mit keiner
  Veröffentlichung vergleichbar.
* **Fester Keim.** Ein Bereich, der bei jedem Aufruf ein wenig anders ausfällt,
  ist eine schlechte Auskunft. Die Ziehungen hängen allein an der Anzahl der
  Blöcke; dieselbe Messreihe ergibt auf jeder Maschine denselben Bereich. Dass
  zwei Modelle mit gleich vielen Blöcken dieselben Ziehungen bekommen, ist
  dabei kein Mangel, sondern die Voraussetzung für den gepaarten Vergleich.
* **Jede Zahl trägt ihr Verfahren.** Die `marke` steht neben jedem gespeicherten
  Bereich. Ein Intervall ohne seine Parameter ist nicht nachvollziehbar: 2,5 bis
  97,5 % über zweitausend blockweise Ziehungen ist etwas anderes als 5 bis 95 %
  über zweihundert.

**Wo es sichtbar wird.**

| Ort | Wie |
|---|---|
| `bewertung.jsonl` → `metriken.streuung` | von jedem **neuen** Lauf mitgeschrieben, je Maß ein Bereich |
| `GET /lernen/api/modelle` | `?intervall=aus\|aufnahme\|einheit`, dazu `?vergleich_mit=<ref>` |
| `GET /lernen/api/laeufe/{id}` | `?intervall=…` legt den gepaarten Abstand neben jedes Gegenüber |
| Modelltabelle | Auswahl „Sicherheit" und „Gegen"; zweite Zeile unter jeder Zahl |
| Einzelner Lauf | Auswahl „Sicherheit"; Spalte „Belegt?" mit p-Wert |

**Und was sich dadurch an den alten Zahlen ändert: nichts.** Das ist hier keine
Bequemlichkeit, sondern Bedingung. Dieser Teil der App ist Forschung: Was die
Tabelle heute zeigt, wird mit dem verglichen, was sie vor Monaten zeigte. Die
Vorgabe ist deshalb überall `aus`, und dann kommt Byte für Byte die Antwort von
vorher; eingeschaltet tritt der Bereich **neben** die Zahl, nie an ihre Stelle.
Ein Test hält beides fest - dass die Werte gleich bleiben und dass der
Mittelwert im Bereich derselbe ist wie der in der Tabelle
(`apps/lernen/tests/test_vergleich.py::TestVertrauensbereiche`).

**Eine Stelle, an der die Ansicht jetzt vorsichtiger ist.** Der beste Wert
jeder Spalte war immer hervorgehoben. Sind Bereiche eingeschaltet und
überlappen sich der beste und der zweitbeste, trägt die Spalte jetzt ein `≈`
mit der Erklärung, dass der Vorsprung nicht belegt ist. Das ist der vorsichtige
Test - überlappende Bereiche schließen einen echten Unterschied nicht aus -,
und genau deshalb steht daneben der Hinweis auf den gepaarten Vergleich, der
schärfer ist.

**Was noch fehlt.** Die Baseline aus „hören" trägt ihre Bereiche nicht in der
Datenbank; sie werden beim Zusammenstellen der Tabelle aus den Einzelzeilen
gerechnet. Das ist richtig so, solange die Zeilen da sind - fehlen sie einmal,
steht ein Grundmodell ohne Bereich da, während ein trainierter Stand seinen im
Manifest mitbringt.

### J - Aufhören, wenn es aufhört besser zu werden ✅ umgesetzt

**Woher der Vorschlag kommt.** Nicht aus der Literatur, sondern aus einem Lauf.
Neun Aufnahmen, LoRA, alle Optionen an: Die Validierungskurve fiel von 10,84
auf 5,53 und war am zwölften und letzten Durchgang noch im Fallen. Der beste
Zwischenstand war der letzte. Nicht die Überanpassung hat den Lauf beendet,
sondern die Zahl im Rezept.

Das ist keine Kleinigkeit, weil es **unsichtbar** ist: Ein Lauf, dessen Kurve
am Ende noch fällt, sieht in der Ansicht aus wie einer, der fertig ist. Die
Obergrenze war ausdrücklich als Obergrenze gedacht („im Zweifel lieber zu
hoch"), und genau im Zweifelsfall stand sie zu niedrig.

**Was.** Eine fünfte Achse des Auftrags:

| Wahl | Was geschieht |
|---|---|
| `fest` | die Zahl aus dem Rezept - die Vorgabe und das Verfahren von vorher |
| `geduldig` | eine weit höhere Obergrenze (LoRA 60, voll 40), Schluss nach `geduld` Prüfungen ohne Gewinn von mehr als `mindestgewinn` |

**Warum das nichts kostet außer Zeit.** Ausgeliefert wird der beste Durchgang
(`load_best_model_at_end`). Ein Lauf, der zu lange läuft, liefert denselben
Stand wie einer, der rechtzeitig aufhört - nur später. Die Obergrenze darf
deshalb weit oben stehen; bei einem kleinen Korpus sind 60 Durchgänge Minuten.

**Drei Entscheidungen darin.**

* **Geduld statt Sofortabbruch.** Fünf Prüfungen bei LoRA, vier beim vollen
  Training. Bei einer Validierung über wenige Aufnahmen ist der Verlust selbst
  eine Zufallsgröße; zwei Ausreißer nach oben sind kein Ende der Fahnenstange.
  Dazu ein Mindestgewinn: Was darunter liegt, ist Rauschen und verlängert den
  Lauf nur.
* **Ohne Validierung kein `geduldig`.** Dann gibt es kein Kriterium, und der
  Lauf fällt auf `fest` zurück und sagt es. Bis irgendetwas passiert
  weiterzulaufen wäre kein Verfahren, sondern eine Hoffnung.
* **Auch die hohe Grenze meldet sich.** Wer sie erreicht, ohne die Geduld
  aufzubrauchen, liest es im Protokoll. Genau diese Auskunft hat gefehlt.

**Was nebenbei mit repariert wurde: der Warmlauf.** Er stand als feste
Schrittzahl im Rezept (50), und derselbe kleine Lauf hatte insgesamt 24
Schritte - die Lernrate erreichte nie mehr als die Hälfte ihres Wertes, der
ganze Lauf war Rampe (gemessen bei Schritt 20: 3,2e-4 statt 1e-3). Der Warmlauf
ist jetzt auf ein Fünftel der Schritte gedeckelt. Das greift nur dort: Ein Lauf
über 396 Schritte behält seine 50 und rechnet Gewicht für Gewicht wie vorher.

**Und eine Korrektur an D.** Derselbe Lauf hat gezeigt, dass der Abschluss das
Ergebnis verschlechtern konnte: bester Durchgang 5,5295, nach Mittelung 5,6504,
nach der besten Interpolation 5,6435. Der Grund ist, dass bei `beides` die
Interpolation nicht beim besten Zwischenstand anfängt, sondern beim
gemittelten - α = 0 holt den besten Einzelstand also nicht zurück. Seitdem
merkt sich der Abschluss den Stand, mit dem er anfängt, und stellt ihn wieder
her, wenn er am Ende schlechter dasteht. Der Fall steht als „zurückgenommen" am
Modellstand, damit ihn niemand für einen Gewinn hält.

---

## 8. Ein Plan in vier Stufen

**Stufe 0 - messen können. ✅ Erledigt, September 2026.** Vorschlag **I**.
Nichts darüber ist prüfbar, bevor das steht. Jede Zahl in der Modelltabelle
kann jetzt ihr Intervall tragen, und der Vergleich zweier Stände nennt einen
p-Wert statt einer Rangfolge. Was bleibt: die Gewohnheit, beides auch
anzusehen, bevor ein Rezept geändert wird.

**Stufe 1 - billige Gewinne am fertigen Modell. Zur Hälfte erledigt,
September 2026.** Vorschlag **D** ✅, danach **H** in seiner kleinen Form
(Startprompt). Beide fassen die Trainingsschleife nicht an, beide sind
nachgelagert, beide lassen sich an Stufe 0 messen. Wenn hier nichts
herauskommt, ist das eine wichtige Information, bevor Stufe 2 Rechenzeit
verbrennt.

Was **D** angeht, ist damit der Weg gebaut und nicht die Frage beantwortet: Ob
Mittelung und Interpolation auf diesen Aufnahmen etwas bringen, sagt erst ein
Lauf je Wahl - gemessen mit den Bereichen aus Stufe 0 und gepaart gegen den
Stand mit `bester` derselben Methode und desselben Datensatzes. Genau dafür ist
es eine Achse geworden.

**Stufe 2 - das Trainingsziel richtigstellen.** Vorschlag **B**, dann **G**,
damit **C** bezahlbar wird. Erst danach **C**, und mit **C** dann die offenen
Zahlenfragen: Tempoveränderung ja oder nein, Korrekturgewicht, LoRA-Rang.

**A** ist hier herausgefallen, weil es schon steht ✅ - und zwar vollständig,
samt Tempo. Was bleibt, ist nicht die Umsetzung, sondern die Messung: vier
Läufe je Methode (`keine`, `masken`, `umgebung`, `voll`), gepaart gegen `keine`
verglichen und mit den Bereichen aus Stufe 0 gelesen. Die Frage „Tempo ja oder
nein" beantwortet dabei schon `umgebung` gegen `voll`; **C** würde sie nur
schärfer stellen.

**Stufe 3 - mehr aus der laufenden Nutzung.** Vorschlag **F** in seinen drei
Stufen, gestützt auf die Ergebnisse von **C**. Das ist zugleich die Stufe, die
am ehesten den Entwurf berührt: Ein Gewicht je Probe aus der Korrekturhistorie
verlangt ein zusätzliches Feld im Manifest.

Zwei Grundsätze, die über allen Stufen stehen: **Kein Modell hört die
Aufnahmen, an denen es gemessen wird** - seit September 2026 sorgt dafür die
Kreuzvalidierung statt eines stillgelegten Testdrittels (**C**). Und jede
Maßnahme kommt als **weitere Achse** in die bestehende Vergleichstafel, nicht
als stille Änderung des Rezepts; sonst ist hinterher nicht mehr zu sagen, was
gewirkt hat.

---

## 9. Was hier bewusst nicht vorgeschlagen wird

* **Ein größeres Grundmodell.** ~~Beantwortet die Frage dieses Dokuments
  nicht.~~ **Seit September 2026 wählbar**, und zwar genau so, wie es hier
  vorgesehen war: `whisper-medium` als **LoRA-Variante**, als eigene Achse des
  Auftrags und als eigene Zeile in der Modelltabelle. Volles Feintuning von
  `medium` sprengt weiterhin den Speicher einer 11-GB-Karte und wird gar nicht
  erst angeboten.

  Die Frage dieses Dokuments bleibt davon unberührt - sie lautet: mehr aus
  demselben Material **bei demselben Grundmodell**. Ein größeres Grundmodell
  beantwortet sie nicht, es verschiebt sie. Beides nebeneinander in derselben
  Tabelle zu haben ist trotzdem richtig: Erst dann ist zu sehen, ob ein
  Vorschlag von hier noch etwas bringt, wenn der Ausgangspunkt schon besser
  ist.
* **Eine Lernratensuche.** Bereits in [lernen.md](lernen.md) verworfen, und das
  Argument steht: Bei einer Validierung über 30 Aufnahmen unterscheidet man
  zwei benachbarte Lernraten nicht verlässlich. Nach **C** und **I** ließe sich
  die Frage neu stellen - dann aber als Frage mit Streuung.
* **Synthetische Sprache.** Text-zu-dysarthrischer-Sprache und
  Stimmumwandlung sind ein aktives Feld mit ermutigenden Ergebnissen, und für
  einen wachsenden Korpus sind sie der nächste große Hebel. Sie brauchen aber
  ein zweites, ebenfalls trainiertes Modell samt eigener Bewertung - das ist
  ein eigenes Vorhaben, kein Vorschlag für das Trainingsrezept.
* **Mehr Aufnahmen.** Der stärkste Hebel überhaupt, aber kein
  Trainingsverfahren. Er steht bereits in `lernen.md` und bleibt dort richtig.

---

## 10. Literatur

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
  (Tempoveränderung 0,9/1,0/1,1)
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
