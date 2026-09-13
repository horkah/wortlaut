<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/wortlaut-logo-invers.svg" />
  <img src="assets/wortlaut-logo.svg" alt="" width="88" height="88" />
</picture>

# wortlaut

**Spracherkennung, die *diesen einen Menschen* versteht.**

Aus dem Laut wird das Wort, und zwar der Wortlaut: was die Person gesagt hat -
nicht das, was ein Sprachmodell für plausibel hält.

---

## Das Problem

Diktieren funktioniert. Für die meisten.

Wer mit Dysarthrie spricht, nach einem Schlaganfall, mit Zerebralparese, mit
starkem Akzent oder breitem Dialekt, erlebt etwas anderes: Das Telefon
antwortet nicht, das Diktierfeld schreibt Unsinn, die Sprachassistentin
schweigt. Nicht weil die Technik schlecht wäre - sondern weil sie auf
Millionen Stunden durchschnittlicher Sprache trainiert wurde und diese Stimme
darin nicht vorkommt.

Die Betroffenen können oft auch schlecht schreiben. Ihnen fehlt damit
ausgerechnet der Ausweg, auf den alle anderen verwiesen werden: „Dann tippen
Sie es halt."

Ein Nischenproblem ist das nicht: Dysarthrie ist eine der häufigsten Folgen
von Schlaganfall, Parkinson, Multipler Sklerose und Zerebralparese, und dazu
kommt jeder, dessen Dialekt oder Akzent weit genug von der Norm abweicht, um an
einem Standardmodell zu scheitern.

Was diesen Menschen fehlt, ist kein besseres Allgemeinmodell. Größer trainierte
Modelle verschieben die Grenze nur nach hinten, sie heben sie nicht auf. Was
fehlt, ist ein Modell, das **sie** kennt.

---

## Was wortlaut tut

wortlaut baut dieses Modell. Gebraucht werden dafür etwa anderthalb Stunden
Sprachaufnahmen, eine einzelne Grafikkarte und ein Nachmittag Rechenzeit. Drei
Apps, die ineinandergreifen:

| | | |
|---|---|---|
| **hören** | Sprachproben sammeln | Die App zeigt einen kurzen Satz, die Person spricht ihn. Ein Satz, eine Aufnahme, ein fertiges Paar aus Text und Ton. Wer nicht flüssig liest, lässt sich den Satz vorher vorlesen und spricht ihn nach. |
| **lernen** | ein eigenes Modell trainieren | Aus den Proben entsteht ein feingetuntes Whisper für genau diese Stimme. Vier Varianten laufen gegeneinander, gemessen an Aufnahmen, die keines davon je gesehen hat. |
| **schreiben** | diktieren | Ein großer Knopf. Sprechen, zuhören, einen misslungenen Abschnitt neu einsprechen, fertig. Kein Anmeldefeld, nichts zu tippen. |

Und dann schließt sich der Kreis: Jeder Text, den jemand in **schreiben**
bestätigt, geht als Korrektur zurück in den Korpus von **hören** - mit dem
Audio, das dazugehört. Der Korpus wächst also im Gebrauch weiter, ohne dass
jemand dafür eine Übung machen müsste, und das nächste Training nimmt ihn mit.

---

## Warum es funktioniert

**Jede Aufnahme ist von Haus aus ausgerichtet.** Aufgenommen wird
äußerungsweise, nie am Stück. Damit entfallen Forced Alignment,
Segmentierungsheuristiken und Zeitmarken-Drift - die drei Stellen, an denen
Sprachdatensätze üblicherweise unsauber werden. Das ist der größte
Vereinfachungsgewinn im ganzen Entwurf und der Grund, warum zwei Stunden
Material hier weiter tragen als anderswo.

**Nichts wird behauptet, alles wird gemessen.** Der Korpus weiß, was gesprochen
werden *sollte* - die Vorlage steht daneben. Jede Aufnahme ist damit eine
fertige Prüfaufgabe. Ein Drittel davon wird von der ersten Aufnahme an zum
Prüfen zurückgelegt und nie wieder umsortiert; kein trainiertes Modell sieht es
je. Auf genau diesen Aufnahmen treten die eigenen Stände gegen `whisper-small`,
`medium` und `large-v3` an - in einer Tabelle, auf denselben Zahlen, mit
derselben Rechnung.

Die Antwort darf dabei auch lauten: *Mein eigenes Modell ist noch nicht besser
als `medium`.* Dann wird `medium` freigegeben. Ein Projekt, das diese Antwort
nicht geben kann, misst nicht - es wirbt.

**Die Stimme bleibt, wo sie ist.** Aufnahmen einer Person mit Sprechstörung
sind Gesundheitsdaten nach Art. 9 DSGVO. Deshalb läuft alles auf der eigenen
Maschine - Erkennung, Training und Textquelle, alle drei auf derselben Karte,
wenn eine da ist. Die Adapter für fremde Dienste sind
bewusste Schalter mit lokaler Voreinstellung, und der Trainings-Container hängt
an keinem Netzweg - Stimmdaten können ihn auf keinem Weg verlassen, den jemand
aus Versehen öffnet.

**Die Oberfläche ist für den gebaut, der sie braucht.** Kein Anmeldefeld,
sondern ein persönlicher Link, einmal geöffnet. Kein Passwort, sondern
höchstens eine vierstellige PIN. Schriftgröße, Kontrast, Schriftart und sogar
die Frage, welche Reiter überhaupt dastehen, sind einstellbar - wer nur
diktiert, sieht nur den Knopf.

---

## Wo es steht

Alle drei Apps laufen, mit Tests, unter einer Adresse, in einem Container.

| | |
|---|---|
| **hören** | Textquelle per LLM oder Upload, äußerungsweise aufnehmen, Qualitätsprüfung, Fortschritt, Auswertung gegen drei Grundmodelle, Sicherung, vollständige Löschung |
| **lernen** | 2:1-Aufteilung mit Bestandsgarantie, vier Trainingsläufe (voll/LoRA × mit/ohne Abwandlungen), Lernkurven, Vergleich gegen die Baseline, eine Modelltabelle mit Freigabe |
| **schreiben** | diktieren, vorlesen lassen, abschnittsweise neu einsprechen, Korrekturen zurück in den Korpus - gepuffert, wiederholbar, nichts geht verloren |

Was fehlt: eine phonetisch ausgewogene Vorlagenliste, Tests für das Frontend,
und die Zahlen aus einem echten Einsatz über mehrere Monate. Was bewusst fehlt,
steht in [Der Entwurf](docs/architektur.md#bewusst-nicht-enthalten).

---

## Ausprobieren

Gebraucht werden Python 3.12 mit [uv](https://docs.astral.sh/uv/), Node 20 und
**ffmpeg im Pfad**. Ohne Grafikkarte läuft alles, nur langsamer: Erkennen
dauert dann Sekunden statt Sekundenbruchteile, Trainieren Tage statt Stunden.

```bash
cp .env.example .env
uv sync
make test                    # läuft ohne GPU, ohne Netz, ohne Mikrofon
make dev APP=hoeren          # Backend :8000, Oberfläche :5173
```

Im Betrieb ist es ein Container für alles drei plus, wer eine Karte hat, ein
zweiter für das Training:

```bash
docker compose up -d
docker compose --profile training up -d training
```

Einzelheiten: [Entwicklung](docs/entwicklung.md) ·
[Betrieb](docs/betrieb.md) · [Konfiguration](docs/konfiguration.md)

---

## Weiterlesen

| | |
|---|---|
| [Der Entwurf](docs/architektur.md) | die Grundentscheidungen, der Aufbau, die Nahtstellen, die Technikwahl |
| [App „hören"](docs/hoeren.md) | Sammeln, Zugänge, Aufsicht, Auswertung |
| [App „lernen"](docs/lernen.md) | Aufteilung, Training, Modelltabelle, Freigabe |
| [Das Trainingsverfahren](docs/trainingsverfahren.md) | was gerechnet wird, in Pseudocode - und was sich daran verbessern lässt |
| [App „schreiben"](docs/schreiben.md) | Diktieren, Abschnitte, Postausgang |
| [Konfiguration](docs/konfiguration.md) | jede Umgebungsvariable, mit Begründung |
| [Entwicklung](docs/entwicklung.md) | lokal starten, Trainer, Tests |
| [Betrieb](docs/betrieb.md) | Reverse Proxy, Sicherungen, Fehlersuche |
| [Datenschutz](docs/datenschutz.md) | was gespeichert wird, wie lange, und wie es verschwindet |
| [Manueller Test](docs/manueller-test.md) | der ganze Weg zum Selbst-Durchklicken |

---

## Lizenz

[MIT](LICENSE). Whisper steht ebenfalls unter MIT - keine
Attributionspflicht, keine Nutzungsbeschränkung.
