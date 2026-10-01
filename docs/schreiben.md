# App „schreiben" - diktieren und vorlesen lassen

Ein großer Knopf: sprechen, den Text hören, einzelne Abschnitte neu
einsprechen, bestätigen. Was bestätigt ist, geht als Korrektur in den Korpus
von [hören](hoeren.md) und trainiert das nächste Modell mit. Welches Modell
hier arbeitet, entscheidet [lernen](lernen.md).

---

## Ablauf

1. Die Person spricht; Whisper liefert Text mit Segmentgrenzen.
2. Die App liest die Abschnitte vor; jeder ist anklickbar.
3. Ein Klick → nur dieser Abschnitt wird neu eingesprochen und erkannt; der
   Rest bleibt. Der Abschnitt zählt seine Anläufe mit (`segments.anlaeufe`).
4. Bestätigt, geht jeder Abschnitt als Korrekturpaar samt Anläufen an
   `POST /api/korpus/intake` von `hören`. Der Postausgang puffert, wenn `hören`
   nicht erreichbar ist. Aus den Anläufen kann `lernen` das Gewicht der
   Korrektur ableiten ([Das Trainingsverfahren](trainingsverfahren.md#die-korrekturen)).

## Aufbau

```
backend/
├── main.py                 FastAPI unter /schreiben, Ausliefern des Frontends
├── config.py               Einstellungen und Ablage-Layout
├── deps.py                 Zugang, Datenbank, Ablage, Transkriptor, Sprache
├── api/
│   ├── sessions.py         Sitzung anlegen, ansehen, bestätigen
│   ├── segments.py         diktieren, Abschnitt neu einsprechen, anhören
│   ├── model.py            welches Modell geladen ist
│   └── outbox.py           Postausgang ansehen, noch einmal senden
├── services/
│   ├── segmenter.py        umwandeln, erkennen, an Zeitmarken schneiden
│   └── outbox.py           Korrekturen an „hören", mit Wiederholung
└── db/                     models.py, migrations/

frontend/src/routes/        Aufnahme, Ergebnis
```

Kopfzeile, Menü samt Audio, Darstellung, System und Zugangsdaten sowie der
Hinweis ohne Zugang kommen aus dem gemeinsamen `Rahmen` in `packages/ui/`.

---

## Der Abschnitt ist die Einheit

Whisper meldet zu jedem Segment Anfang und Ende, und dort wird die Aufnahme
zerschnitten (`wortlaut.audio.schneide_ausschnitt`). Jeder Abschnitt hat seine
eigene WAV-Datei - so lässt er sich einzeln ersetzen und einzeln
zurückgeben. Die zusammenhängende Aufnahme wird danach nicht behalten.

Ein Segment, das erst hinter dem letzten Abtastwert beginnt - meist der
Untertitelsatz, den Whisper aus der Stille erfindet -, hat kein Audio und wird
übergangen. Ein Ende hinter der Aufnahme wird auf sie gestutzt.

## Ein großer Knopf

Die Zielperson kann schlecht lesen und schreiben (Grundentscheidung 7):

- **Zwei Ansichten, keine Menüführung.** Sprechen und Ergebnis; die zweite
  Reiterreihe bleibt leer.
- **Vorgelesen wird von selbst**, mit mitlaufender Markierung - wer den Text
  nicht sicher liest, hört den Fehler. Ob von selbst vorgelesen wird, steht
  unter „Audio"; „▶ Vorlesen" steht über dem Text. Gelesen wird in der
  Stimme, die unter „Audio" gewählt ist - eine des Servers wie in `hören`
  (`GET …/segments/{id}/vorlesung`), sonst die des Geräts. Von selbst liest
  nur eine Stimme vom Server: Die des Geräts spricht auf dem iPhone nur aus
  einem Tippen heraus, mit ihr bleibt es bei „▶ Vorlesen".
- **Nichts zu tippen.** Der Zugang kommt über den persönlichen Link, derselbe
  Eintrag wie in `hören`.
- **Bearbeitet wird durch Sprechen.** „Text weitergeben" öffnet das
  Teilen-Blatt des Geräts, „Text kopieren" nimmt ihn ganz.
- **Einstellungen stehen im Menü**, gemeinsam für alle Apps, dazu **Meine
  Daten** in `hören`.

## Welches Modell erkennt

Solange in `lernen` nichts freigegeben ist, lädt faster-whisper das
unveränderte Grundmodell aus `WORTLAUT_ASR_MODELL`; sonst die Freigabe dieses
Sprechers, samt dem Tempo, auf dem der Stand gelernt hat (siehe
[Der Entwurf](architektur.md#welches-modell-schreiben-lädt)). Erkannt wird
auf der Karte, wenn eine da ist; ist sie voll, auf dem Prozessor.

Die Zeile unter dem Aufnahmeknopf nennt dauerhaft, welches Modell arbeitet
(`whisper-small · unverändert`, `K7M2Q · whisper-small · LoRA · …`) - aber
keine Kennzahl: Wie gut ein Modell ist, steht in der Modelltafel von `lernen`,
und ein Klick auf die Zeile führt dorthin.

## Der Postausgang

Zwischen `schreiben` und `hören` liegt eine Tabelle, kein direkter Aufruf.
Wiederholen ist gefahrlos - `hören` erkennt die Abschnittskennung als
`externe_id` wieder -, und nichts wird still verworfen: Ein Fehlschlag zählt
hoch, schreibt seinen Grund in die Zeile und bleibt offen. Gesendet wird mit
dem Zugang dessen, der bestätigt hat; die Korrektur landet damit zwingend in
seinem Korpus. Erst wenn ein Abschnitt dort angekommen ist, wird seine Datei
hier gelöscht.

## Endpunkte

```
POST   /schreiben/api/sessions                      neue Diktiersitzung
GET    /schreiben/api/sessions/{id}
POST   /schreiben/api/sessions/{id}/segments        multipart: audio → Abschnitte
POST   /schreiben/api/sessions/{id}/bestaetigen     → Postausgang, sofort senden
POST   /schreiben/api/segments/{id}/neu             multipart: audio, ersetzt einen
GET    /schreiben/api/segments/{id}/audio
GET    /schreiben/api/segments/{id}/vorlesung?stimme=   der Text in einer Serverstimme; 404: Browser
GET    /schreiben/api/model                         welches Modell geladen ist
GET    /schreiben/api/outbox
POST   /schreiben/api/outbox/senden                 noch einmal versuchen
GET    /gesundheit                                  ohne Zugang, auf der Wurzel
```

Jeder Weg außer `/gesundheit` verlangt den Sprecherzugang und leitet die
Kennung daraus ab; nur Sprecherzugänge kommen durch. Wer gerade ruft, fragt
jede App bei `hören` (`packages/ui/wer.ts`) - dort werden alle drei Arten von
Zugang erkannt.

## Ablage

```
data/diktate/<sprecher_id>/
├── audio/<abschnitt_id>.wav     16 kHz mono, je ein Abschnitt
└── schreiben.sqlite             Sitzungen, Abschnitte, Postausgang
```

Nach Sprecher gegliedert wie der Korpus, damit eine Löschung sie findet; neben
und nicht im Korpus, weil `hören` dessen einziger Schreiber ist. Was hier
liegt, ist Arbeitsstand.
