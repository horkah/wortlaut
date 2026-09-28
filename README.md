<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/wortlaut-logo-invers.svg" />
  <img src="assets/wortlaut-logo.svg" alt="" width="88" height="88" />
</picture>

# wortlaut

**Spracherkennung, die *diesen einen Menschen* versteht.**

Aus dem Laut wird das Wort, und zwar der Wortlaut: was die Person gesagt hat,
nicht das, was ein Sprachmodell für plausibel hält.

> **Dieses Repository beschreibt nur den aktuellen Stand.** Code, Kommentare,
> Doku und Oberfläche sagen, was gilt und warum - nie, wie es vorher war. Die
> Geschichte steht allein in der Commit-History. Ausgenommen sind datierte
> Berichte wie der [Modellbericht](docs/modellbericht.md), der
> [Kernbericht](docs/kernbericht.md) und der [Optionenbericht](docs/optionenbericht.md).

---

## Das Problem

Diktieren funktioniert, für die meisten. Wer mit Dysarthrie spricht, nach einem
Schlaganfall, mit Zerebralparese, Parkinson, Multipler Sklerose oder breitem
Dialekt, erlebt anderes: Das Diktierfeld schreibt Unsinn, die
Sprachassistentin schweigt. Die Modelle sind auf Millionen Stunden
durchschnittlicher Sprache trainiert, und diese Stimme kommt darin nicht vor.

Oft können die Betroffenen auch schlecht schreiben. Ihnen fehlt damit
ausgerechnet der Ausweg „Dann tippen Sie es halt".

Größere Allgemeinmodelle verschieben die Grenze nur. Was fehlt, ist ein
Modell, das **diese Person** kennt.

---

## Was wortlaut tut

wortlaut baut dieses Modell - aus etwa anderthalb Stunden Aufnahmen, auf einer
einzelnen Grafikkarte. Drei Apps greifen ineinander:

| | | |
|---|---|---|
| **hören** | Sprachproben sammeln | Ein kurzer Satz, eine Aufnahme, ein fertiges Paar aus Text und Ton. Wer nicht flüssig liest, lässt sich den Satz vorlesen und spricht ihn nach. |
| **lernen** | ein eigenes Modell trainieren | Feintuning von Whisper für genau diese Stimme, gemessen per sechsfacher Kreuzvalidierung und neben den unveränderten Grundmodellen in einer Tafel. |
| **schreiben** | diktieren | Ein großer Knopf: sprechen, zuhören, einen Abschnitt neu einsprechen, fertig. Kein Anmeldefeld. |

Jeder in **schreiben** bestätigte Text geht mit seinem Audio als Korrektur in
den Korpus von **hören** zurück. Der Korpus wächst im Gebrauch, und das nächste
Training nimmt ihn mit.

---

## Warum es funktioniert

**Jede Aufnahme ist von Haus aus ausgerichtet.** Aufgenommen wird
äußerungsweise. Forced Alignment, Segmentierung und Zeitmarken-Drift entfallen
- die Stellen, an denen Sprachdatensätze sonst unsauber werden.

**Gemessen statt behauptet.** Zu jeder Aufnahme steht die Vorlage daneben,
jede Aufnahme ist also eine Prüfaufgabe. Die Kreuzvalidierung misst jede
Aufnahme mit einem Modell, das sie nie gesehen hat; die eigenen Stände stehen
in derselben Tafel wie `whisper-small`, `medium` und `large-v3`, mit
Vertrauensbereichen. Ist das eigene Modell noch nicht besser als `medium`,
wird `medium` freigegeben.

**Die Stimme bleibt im Haus.** Aufnahmen einer Person mit Sprechstörung sind
Gesundheitsdaten nach Art. 9 DSGVO. Erkennung, Training, Zeichenerkennung und
Textquelle laufen auf der eigenen Maschine; Adapter für fremde Dienste sind
Schalter mit lokaler Voreinstellung, und der Trainings-Container holt aus dem
Netz nur die Grundmodelle - Aufnahmen verlassen die Maschine nicht.

**Die Oberfläche ist für den gebaut, der sie braucht.** Ein persönlicher Link
statt einer Anmeldung, höchstens eine vierstellige PIN. Schrift, Kontrast und
sogar die sichtbaren Reiter sind einstellbar - wer nur diktiert, sieht nur den
Knopf.

---

## Ausprobieren

Python 3.12 mit [uv](https://docs.astral.sh/uv/), Node 20 und **ffmpeg im
Pfad**. Ohne Grafikkarte läuft alles, nur langsamer.

```bash
cp .env.example .env
uv sync
make test                    # ohne GPU, ohne Netz, ohne Mikrofon
make dev APP=hoeren          # Backend :8000, Oberfläche :5173
```

Im Betrieb ein Container für alle drei Apps und, mit Karte, einer für das
Training:

```bash
docker compose up -d
docker compose --profile training up -d training
```

Ein eigenes Modell von der Kommandozeile - LoRA auf `whisper-large-v3`,
zugeschnitten auf die Karte, die da ist (Genauigkeit, Stapel,
Gradientensparen; siehe [Betrieb](docs/betrieb.md#der-trainer)):

```bash
make train SPEAKER=spr_7f2a RECIPE=whisper_lora   # beauftragen, zusehen, WER gegen das Grundmodell
make release JOB=job_01J8…                        # freigeben - „schreiben" diktiert damit
```

---

## Weiterlesen

| | |
|---|---|
| [Der Entwurf](docs/architektur.md) | Grundentscheidungen, Aufbau, Nahtstellen, Technik |
| [App „hören"](docs/hoeren.md) | Sammeln, Zugänge, Aufsicht, Zuschnitt, Auswertung |
| [App „lernen"](docs/lernen.md) | Kreuzvalidierung, Aufträge, Modelltafel, Freigabe |
| [Das Trainingsverfahren](docs/trainingsverfahren.md) | die Rechnung in Pseudocode und ihre Bausteine |
| [App „schreiben"](docs/schreiben.md) | Diktieren, Abschnitte, Postausgang |
| [Konfiguration](docs/konfiguration.md) | jede Umgebungsvariable |
| [Entwicklung](docs/entwicklung.md) | lokal starten, Trainer, Tests, Konventionen |
| [Betrieb](docs/betrieb.md) | Compose, Reverse Proxy, Sichern, Fehlersuche |
| [Datenschutz](docs/datenschutz.md) | was gespeichert wird und wie es verschwindet |
| [Manueller Test](docs/manueller-test.md) | der ganze Weg zum Durchklicken |
| [Andere Sprachen](docs/sprachen.md) | wortlaut in einer anderen Sprache (englisch) |
| [Modellbericht](docs/modellbericht.md) | Vergleich aller Stände, Stand 26.09.2026 |
| [Kernbericht](docs/kernbericht.md) | Kernauswahl gegen alle Aufnahmen, Stand 27.09.2026 |
| [Optionenbericht](docs/optionenbericht.md) | was die neuen Trainingsoptionen bringen, laufend ergänzt, Stand 28.09.2026 |

---

## Lizenz

[MIT](LICENSE). Whisper steht ebenfalls unter MIT.
