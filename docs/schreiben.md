# App „schreiben" - diktieren und vorlesen lassen

Ein großer Knopf: sprechen, den Text hören, einzelne Abschnitte neu
einsprechen, bestätigen. Was bestätigt wurde, geht als Korrektur zurück in den
Korpus von [hören](hoeren.md) und trainiert dort das nächste Modell mit.

Der Entwurf dahinter steht in [Der Entwurf](architektur.md); welches Modell
hier arbeitet, entscheidet [lernen](lernen.md).

Die **Grundentscheidungen**, auf die hier verwiesen wird, stehen
[dort](architektur.md#grundentscheidungen).

---

## Ablauf

1. Nutzer spricht, Whisper liefert Text mit Segmentgrenzen.
2. Die App liest jeden Abschnitt vor. Jeder Abschnitt ist anklickbar.
3. Klick → nur dieser Abschnitt wird neu eingesprochen und neu transkribiert. Das
   neue Audio ersetzt den alten Ausschnitt, der Rest bleibt stehen.
4. Bestätigt der Nutzer den fertigen Text, geht jeder Abschnitt als Korrekturpaar an
   `POST /api/korpus/intake` von `hören`. Die Outbox puffert, wenn `hören` nicht
   erreichbar ist.

## Aufbau

```
backend/
├── main.py                 FastAPI, Router, Ausliefern des Frontends
├── config.py               Settings aus ENV; auch das Ablage-Layout
├── deps.py                 Zugang, Datenbank, Ablage, Transkriptor
├── api/
│   ├── sessions.py         Sitzung anlegen, ansehen, bestätigen
│   ├── segments.py         diktieren, Abschnitt neu einsprechen, anhören
│   ├── model.py            was geladen ist, und ob ausgesteuert wird
│   ├── outbox.py           Postausgang ansehen und noch einmal senden
│   └── zugang.py           wer ruft - für die Kopfzeile
├── services/
│   ├── segmenter.py        umwandeln, transkribieren, an Zeitmarken schneiden
│   └── outbox.py           Korrekturen zurück an „hören", mit Wiederholung
└── db/                     models.py und migrations/

frontend/src/
├── lib/                    api.ts, zustand.svelte.ts
└── routes/                 Aufnahme, Ergebnis, Zugangsdaten
```

Geteilt mit den anderen Apps und über `$ui` eingebunden: `Rahmen`,
`Kopfleiste`, `Recorder`, `AudioPlayer`, `SegmentList`, `KeinZugang`,
`mikrofon.ts`, `speak.ts`, `einstellungen.svelte.ts` und `app.css` - alles in
`packages/ui/`.

---

## Der Abschnitt ist die Einheit

Was `hören` die Vorlage ist, ist `schreiben` der Abschnitt: die Einheit, an der
alles hängt. Whisper meldet zu jedem Segment Anfang und Ende, und genau dort
wird die Aufnahme zerschnitten (`wortlaut.audio.schneide_ausschnitt`). Jeder
Abschnitt hat deshalb seine eigene WAV-Datei - anders ließe er sich weder
einzeln ersetzen noch einzeln als Audio-Text-Paar zurückgeben.

Die zusammenhängende Aufnahme wird nach dem Schnitt nicht behalten. Sie wäre
eine zweite Kopie derselben Stimmdaten und wird nicht mehr gebraucht.

## Ein großer Knopf

Die Zielperson kann schlecht lesen und schreiben (Grundentscheidung 7). Daraus
folgt mehr als der Verzicht auf ein Anmeldefeld - und der Verzicht bleibt, auch
seit die App einen Sprecher führt: Der Zugang kommt über den persönlichen Link
und liegt danach im Browser, hier wie in `hören`.

- **Zwei Ansichten, keine Menüführung.** Sprechen und Ergebnis; der Weg
  dazwischen ergibt sich, statt gewählt zu werden. Die zweite Reiterreihe der
  Kopfzeile bleibt leer.
- **Vorgelesen wird von selbst.** Wer den Text nicht sicher lesen kann, hört
  den Fehler - deshalb liest die Ergebnisansicht sofort los und markiert
  mitlaufend, wo sie gerade ist.
- **Nichts zu tippen, auch nicht zum Anmelden.** Der Zugang kommt über den
  persönlichen Link und liegt danach im Browser - derselbe Eintrag, den `hören`
  liest, denn beide Apps liegen unter derselben Adresse.
- **Einstellungen nur im Menü.** Mikrofon, Stimme, Tempo und Schriftgröße
  gelten für alle drei Apps und stehen eingeklappt hinter dem Menüknopf, damit
  die Oberfläche ein großer Knopf bleibt. Dort liegt auch der eine Verweis,
  der aus dieser App herausführt: **Meine Daten** nach `hören`. Zu den Modellen
  geht es nicht über das Menü, sondern über die Modellzeile unter dem
  Aufnahmeknopf - wer sie liest, denkt gerade darüber nach.
- **Bearbeitet wird durch Sprechen.** Der fertige Text ist zum Kopieren da,
  nicht zum Tippen.

## Ohne Freigabe fängt es mit `small` an

Erkannt wird auf der Karte, wenn eine da ist - dieselbe Einstellung wie in der
Auswertung von `hören` und beim Trainer (`WORTLAUT_GERAET`, siehe
[Konfiguration](konfiguration.md#rechenwerk---worauf-erkannt-wird)). Für ein
Diktat ist das der Unterschied zwischen einer Sekunde Warten und mehreren.
Ist die Karte voll, weil gerade trainiert wird, weicht die Erkennung auf den
Prozessor aus: lieber langsam verstanden als gar nicht.

Solange in `lernen` nichts freigegeben ist, lädt faster-whisper das
unveränderte `whisper-small` aus `WORTLAUT_ASR_MODELL`. Die Zeile unter dem
Aufnahmeknopf schreibt dauerhaft hin, was gerade arbeitet (`whisper-small ·
unverändert`, später `whisper-small · LoRA · mit Abwandlungen · Stand
2026-09-12`) - wer eine Ausgabe beurteilt, beurteilt immer ein bestimmtes
Modell.

**Eine Kennzahl steht dort bewusst nicht.** Sie stand einmal: die
Wortfehlerrate aus dem Manifest des Standes. Die ist das Mittel über die
Testeinheiten *seines* Laufs, während die Modellübersicht in `lernen` über die
Einheiten mittelt, die alle Modelle gemeinsam haben - zwei Zahlen zum selben
Modell, beide richtig, und nebeneinander ein Rätsel. Wie gut ein Modell ist,
steht an genau einer Stelle; diese Zeile sagt, **welches** es ist.

Dieselbe Zeile ist der Weg zur Entscheidung: Ein Klick darauf führt in die
**Modellübersicht** von [lernen](lernen.md), wo die eigenen Stände und die
Grundmodelle an denselben Testaufnahmen gemessen nebeneinanderstehen und eines
davon freigegeben wird. Gewählt wird hier nichts - diese App liest die Freigabe
und sagt, was daraus geladen wurde.

## Der Postausgang

Zwischen `schreiben` und `hören` liegt eine Tabelle und kein direkter Aufruf:
Dass beide gleichzeitig erreichbar sind, ist nicht zugesichert. Zwei Zusagen
halten das einfach - Wiederholen ist gefahrlos (`hören` erkennt die
Abschnittskennung als `externe_id` wieder), und nichts wird stillschweigend
verworfen: Ein Fehlschlag zählt hoch und schreibt seinen Grund in die Zeile,
der Eintrag bleibt offen.

Erst wenn ein Abschnitt im Korpus angekommen ist, wird seine Audiodatei hier
gelöscht.

## Endpunkte

```
POST   /schreiben/api/sessions              neue Diktiersitzung
GET    /schreiben/api/sessions/{id}
POST   /schreiben/api/sessions/{id}/segments        multipart: audio → Abschnitte
POST   /schreiben/api/sessions/{id}/bestaetigen     → Postausgang, sofort senden
POST   /schreiben/api/segments/{id}/neu     multipart: audio, ersetzt einen
GET    /schreiben/api/segments/{id}/audio
GET    /schreiben/api/model                 was geladen ist, und ob ausgesteuert wird
GET    /schreiben/api/outbox
POST   /schreiben/api/outbox/senden         noch einmal versuchen
GET    /schreiben/api/zugang                wer ruft - für die Kopfzeile
GET    /gesundheit                          ohne Zugang, auf der Wurzel
```

Alles unter `/schreiben` - dem Ort dieser App unter der gemeinsamen Domain.
Nur `/gesundheit` bleibt auf der Wurzel: Eine Überwachung spricht den Container
unmittelbar an.

Kein Sprecherparameter, aber ein Zugang: Jeder Weg außer `/gesundheit` verlangt
den Sprecherzugang aus `hören` und leitet die Kennung daraus ab - dieselbe
Regel wie drüben, aus demselben Grund (die Bindung zieht der Server, nicht der
Aufrufer).

## Ablage

```
data/diktate/<sprecher_id>/
├── audio/<abschnitt_id>.wav     16 kHz mono, je ein Abschnitt
└── schreiben.sqlite             Sitzungen, Abschnitte, Postausgang
```

Nach Sprecher gegliedert wie der Korpus: Sonst fände
`scripts/purge_speaker.py` diese Dateien nicht, und eine Löschung wäre
unvollständig.

Bewusst **neben** und nicht **im** Korpus: `hören` ist dessen einziger
Schreiber (Grundentscheidung 6). Was hier liegt, ist Arbeitsstand. Sobald ein
Abschnitt im Korpus angekommen ist, wird seine Audiodatei hier gelöscht -
zweimal braucht sie niemand, und es sind Gesundheitsdaten.
