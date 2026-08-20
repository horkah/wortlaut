# Manueller Test

Schritt-für-Schritt-Anleitung für einen Menschen im Browser. Abschnitte 1–6
prüfen die App „hören" vom leeren Sprecherprofil bis zur ersten Aufnahme,
Abschnitt 7 die App „schreiben" vom Diktat bis zur Korrektur im Korpus.
Ergänzt `make test` (automatisiert, ohne Browser, ohne Mikrofon) — ersetzt es
nicht.

Dauer: etwa 10 Minuten für „hören", 10 weitere für „schreiben", plus die Zeit
für ein paar echte Aufnahmen.

## Voraussetzungen

- Server läuft: `make dev APP=hoeren` (Backend `:8000`, Vite `:5173`) —
  siehe [`docs/betrieb.md`](betrieb.md#entwicklung)
- Browser mit Mikrofonzugriff, aufgerufen über **`http://localhost:5173`**
  (nicht `:8000` — das Backend liefert dort nur `/api/…` und `/gesundheit`,
  ein `404` auf `/` davor ist normal, kein Fehler)
- `WORTLAUT_AUTH_TOKEN` in `.env` leer lassen, dann entfällt Schritt 1c

## 1. Sprecherprofil

1. Seite öffnen. Erwartet: Kopfzeile mit einer Reihe — „wortlaut“, dahinter
   die drei Apps, „hören“ dunkelgrün hinterlegt, „schreiben“ anklickbar und
   „lernen“ blass und tot (die gibt es noch nicht). Die zweite Reihe mit
   den Ansichten fehlt noch. Darunter Überschrift „Sprecher“ und
   „Noch kein Sprecherprofil vorhanden.“ — das ist der Leerzustand, keine
   kaputte Seite.
2. Unter „Neues Profil“: Namen eintragen, Basismodell auf
   `whisper-small (Entwicklung ohne GPU)` oder, für noch weniger Rechenlast,
   `whisper-tiny (noch weniger Rechenlast)` stellen, **Anlegen**. Für den
   Testablauf hier ohne Belang: `hören` selbst ruft Whisper nirgends auf —
   das Feld ist reine Metadaten für das spätere Training in `lernen`.
3. Erwartet: Profil erscheint in der Liste, App springt automatisch zur
   Ansicht „Textquelle“; in der Kopfzeile steht jetzt eine zweite Reihe
   (Sprecher, Textquelle, Aufnehmen, Fortschritt, Einstellungen) mit
   „Textquelle“ hell hinterlegt. Beim Wechsel der Ansicht wandert die
   Hinterlegung mit.
4. Falls `WORTLAUT_AUTH_TOKEN` gesetzt ist: stattdessen erscheint unter der
   leeren Liste „Zugang nötig: bitte Token eintragen.“ Token unter „Zugang“
   eintragen, **Speichern**, dann Schritt 2 wiederholen.

## 2. Textquelle

Einen der beiden Wege testen (beide, falls `WORTLAUT_LLM_PROVIDER` gesetzt
und ein Schlüssel hinterlegt ist):

**a) Eigener Text (funktioniert immer, ohne API-Schlüssel)**
1. Unter „Eigener Text“ eine `.txt`- oder `.md`-Datei mit mindestens ein
   paar Sätzen wählen, **Hochladen**.
2. Erwartet: Quelle erscheint unter „Vorhandene Quellen“ mit Art, Anzahl
   Einheiten und Zeitstempel; Knopf „Zur Aufnahme“ erscheint.

**b) Thema per Sprachmodell (nur mit gesetztem `WORTLAUT_LLM_PROVIDER` /
`WORTLAUT_LLM_API_KEY`)**
1. Thema eintragen (z. B. „Einkaufen im Wochenmarkt“), Altersspanne und
   Umfang auf den Vorgaben belassen, **Text erzeugen**.
2. Erwartet: nach kurzer Wartezeit erscheint die Quelle wie bei (a). Ohne
   gesetzten Anbieter erscheint stattdessen eine Fehlermeldung — das ist
   der erwartete Zustand „Keine Textquelle konfiguriert“, kein Bug.

## 3. Aufnehmen

1. **Zur Aufnahme.** Erwartet: eine Sprecheinheit groß in der Mitte, Zeile
   „0 von N Einheiten“, Fortschrittsbalken bei 0 %.
2. Browser fragt beim ersten Mal nach Mikrofonzugriff — **erlauben**.
   (`MediaRecorder` verlangt `localhost` oder HTTPS; unter `:5173` ist das
   erfüllt.)
3. Aufnehmen, stoppen. Erwartet: Ansicht wechselt zu „Wird geprüft …“, dann
   zur Wiedergabe der eigenen Aufnahme mit Dauer und Pegel in dBFS.
4. Falls Auffälligkeiten (Stille, Clipping, Dauer weit ab der Schätzung):
   Hinweistext unter „Aufgefallen ist:“ prüfen — er darf erscheinen, ohne
   dass die Aufnahme verworfen wird.
5. **Verwerfen und noch einmal** testen: dieselbe Einheit muss danach wieder
   offen sein (Zähler „N von …“ bleibt gleich, nicht +1).
6. **Weiter** testen: nächste Einheit erscheint, Zähler steigt um eins.
7. Falls eine deutsche Stimme im Browser vorhanden ist: Knopf
   „▶ Vorsprechen lassen“ testen. Erwartet: Einheit wird vorgelesen, danach
   erscheint „wird als „nachgesprochen“ gespeichert“ und die nächste
   Aufnahme wird entsprechend markiert (in Schritt 4 unter „Modus
   `nachgesprochen`“ sichtbar).
8. Einheiten aufnehmen, bis „Alles aufgenommen“ erscheint. Erwartet: zwei
   Knöpfe, „Neue Textquelle“ und „Fortschritt ansehen“.
9. Seite neu laden (F5), während noch offene Einheiten vorhanden sind.
   Erwartet: Sitzung setzt an derselben Stelle fort, keine bereits geprüfte
   Einheit wird erneut angezeigt.

## 4. Fortschritt

1. **Fortschritt** in der Kopfzeile.
2. Erwartet: Stundenzahl, Anzahl Aufnahmen, offene Einheiten; zwei Balken
   gegen die Marken „Brauchbar“ und „Gut“; Tabelle „Zusammensetzung“ mit den
   gerade aufgenommenen Modi (`gelesen` und ggf. `nachgesprochen`) und der
   Quelle (`vorlage`).
3. **Abmelden.** Erwartet: zurück zur Sprecheransicht, die Ansichtenreihe
   verschwindet, die App-Reihe bleibt; das angelegte Profil steht weiter in
   der Sprecherliste und lässt sich erneut auswählen.

## 5. Mikrofon

Die Einstellungen öffnen den Abschnitt „Mikrofon“ ganz oben.

1. **▶ Mikrofon testen** drücken. Beim ersten Mal fragt der Browser nach
   Zugriff — **erlauben**. Erwartet: ein Pegelbalken erscheint und bewegt
   sich beim Sprechen; darunter steht der Wert in dBFS und eine Einordnung
   („guter Pegel“ / „zu leise“ / „zu laut“). Die Grenzen sind dieselben, die
   der Server nach dem Absenden prüft — was hier „gut“ ist, gibt später
   keinen Hinweis.
2. Nicht sprechen. Erwartet: die Anzeige fällt auf „still“ zurück.
3. **Verstärkung** verschieben, dabei weitersprechen. Erwartet: der Balken
   folgt sofort, ohne dass der Test neu startet.
4. **Automatisch einmessen** drücken und fünf Sekunden lang normal sprechen —
   im selben Abstand wie später bei der Aufnahme. Erwartet: der Zähler läuft
   von 5 herunter, danach steht „Verstärkung auf N,N× gesetzt“ und der Regler
   ist entsprechend gesprungen. Wer während der fünf Sekunden schweigt,
   bekommt „Nichts gehört“ und die Verstärkung bleibt, wie sie war.
5. **● Probe aufnehmen**, ein paar Sätze sprechen, **■ Aufnahme beenden**.
   Erwartet: unter dem Pegelbalken erscheint ein Abspieler „Probe“, und die
   Wiedergabe ist so laut wie eingestellt.
6. Sind mehrere Mikrofone da: bei laufendem Test ein anderes **Mikrofon**
   wählen. Erwartet: der Test startet von selbst neu und der Balken reagiert
   auf das andere Gerät. Vor dem ersten Test heißen die Geräte nur
   „Mikrofon 1“, „Mikrofon 2“ — die echten Namen gibt der Browser erst nach
   erteilter Erlaubnis heraus.
7. **Pegel automatisch nachregeln** aus- und wieder einschalten. Erwartet:
   der Test startet jedes Mal neu (die Regelung sitzt in der Aufnahme des
   Browsers und lässt sich nur beim Öffnen setzen).
8. **■ Test beenden**. Erwartet: die Aufnahmeanzeige des Browsers im Tab
   erlischt. Sie darf nicht stehen bleiben — sonst hört die App weiter mit.
9. Zur **Aufnahme** wechseln und eine Einheit aufnehmen. Erwartet: der Wert
   „… dBFS“ unter der Wiedergabe liegt in derselben Gegend wie im Test.
10. Ein gewähltes Mikrofon abziehen (USB-Headset) und aufnehmen. Erwartet:
    die Aufnahme läuft mit der Vorgabe des Browsers und darüber steht „Das
    gewählte Mikrofon ist nicht da“ — keine verweigerte Aufnahme.

## 6. Vorlesen und Anzeige

1. Weiter unten in denselben **Einstellungen**.
2. **Probe hören** drücken. Erwartet: der Probesatz wird vorgelesen. (Meldet
   der Browser keine deutsche Stimme, steht statt der Auswahl ein Hinweis und
   der Knopf ist ausgegraut — siehe `docs/betrieb.md`.)
3. **Sprechtempo** verschieben, erneut **Probe hören**. Erwartet: die Anzeige
   neben dem Regler ändert sich (z. B. „0,7×“) und die Probe wird hörbar
   langsamer beziehungsweise schneller.
4. Sind mehrere Stimmen installiert: andere **Stimme** wählen, erneut Probe
   hören. Erwartet: hörbar andere Stimme.
5. **Schriftgröße der Vorlage** verschieben. Erwartet: der Beispieltext
   darunter wächst beziehungsweise schrumpft sofort mit.
6. Zur **Aufnahme** wechseln. Erwartet: die Vorlage erscheint in der
   eingestellten Größe, „▶ Vorsprechen lassen“ nutzt Stimme und Tempo aus den
   Einstellungen.
7. Seite neu laden (F5). Erwartet: alle Werte sind erhalten, auch Mikrofon
   und Verstärkung (`localStorage`).
8. **Auf Vorgaben zurücksetzen** drücken. Erwartet: Tempo 0,9×, Schriftgröße
   2,0 rem, Stimme wieder die des Browsers, Verstärkung 1,0×, Mikrofon
   wieder die Vorgabe des Browsers, Pegelregelung an.

## 7. App „schreiben“

Eigener Server, eigene Ports: `make dev APP=schreiben` (Backend `:8001`, Vite
`:5174`). „hören“ darf daneben weiterlaufen — für Schritt 7.6 muss es das
sogar. Vorher in der `.env`:

```
WORTLAUT_SPRECHER_ID=<die ID aus Schritt 1>
WORTLAUT_INTAKE_URL=http://localhost:8000/api/korpus/intake
WORTLAUT_INTAKE_TOKEN=<derselbe Wert wie WORTLAUT_AUTH_TOKEN, falls gesetzt>
```

Aufgerufen wird **`http://localhost:5174/schreiben/`** — mit Pfad; ohne ihn
bleibt die Seite leer, das ist kein Fehler.

1. Seite öffnen. Erwartet: dieselbe Kopfzeile, jetzt mit „schreiben“
   hinterlegt, keine zweite Reihe, und rechts oben blass der Modellstand —
   ohne `WORTLAUT_MODELL_REF` steht dort „whisper-tiny · unverändert“.
   Darunter mittig „Sprechen Sie einfach los.“ und ein großer Knopf.
2. **● Aufnehmen**, zwei bis drei kurze Sätze sprechen, **■ Fertig**.
   Erwartet: „Wird verstanden …“. Beim allerersten Mal dauert das länger, weil
   faster-whisper sein Modell herunterlädt (Fortschritt in der
   Backend-Konsole). Danach wechselt die Ansicht zum Text.
3. Erwartet: die Sätze stehen als einzeln umrandete Abschnitte untereinander,
   und die App liest von selbst vor; der gerade gesprochene Abschnitt ist
   blass hinterlegt. **■ Anhalten** stoppt sofort, **▶ Vorlesen** beginnt von
   vorn. Dass `tiny` dabei Unsinn versteht, ist erwartet und der Grund für
   die App „lernen“.
4. Einen falschen Abschnitt **anklicken**. Erwartet: er bekommt einen
   kräftigen Rahmen, darunter erscheint eine Karte mit dem Text groß, einem
   Abspieler „So klang es“ und einem Aufnahmeknopf. Diesen Satz noch einmal
   sprechen. Erwartet: nur dieser Abschnitt ändert sich, alle anderen stehen
   unverändert; links am Abschnitt bleibt eine schmale Markierung („neu“).
   Ein zweiter Klick auf denselben Abschnitt schließt die Karte wieder.
5. **Weitersprechen** drücken, einen weiteren Satz diktieren. Erwartet: die
   neuen Abschnitte hängen hinten an, die alten bleiben stehen.
6. **Fertig** drücken. Erwartet: „Der Text ist abgeschickt.“ und „N von N
   Abschnitten sind bei „hören“ angekommen.“ Zur Probe in „hören“ unter
   **Fortschritt** nachsehen: in der Tabelle „Zusammensetzung“ steht jetzt
   Quelle `korrektur` und Modus `frei`, mit der Zahl der Abschnitte.
7. Den Postausgang prüfen: „hören“ anhalten (`Strg-C` im Terminal), in
   „schreiben“ **Neuer Text**, kurz diktieren, **Fertig**. Erwartet: „Noch
   nicht alles übergeben“ mit dem Grund und einem Knopf **Noch einmal
   senden**. „hören“ wieder starten, den Knopf drücken. Erwartet: alles
   angekommen, kein doppelter Eintrag im Fortschritt von „hören“ (die
   Abschnittskennung verhindert das).
8. Seite neu laden (F5), solange ein Text unbestätigt ist. Erwartet: der Text
   ist wieder da. Einen neuen Tab öffnen: dort ein leeres Blatt.

## Aufräumen

Testdaten liegen unter `data/korpus/<sprecher_id>/` und
`data/diktate/<sprecher_id>/` (Pfad aus `WORTLAUT_DATA_DIR`). Löschen genügt
ein Entfernen der Verzeichnisse, oder
`uv run python scripts/purge_speaker.py <sprecher_id>` für den vollständigen
Weg über das Löschskript — es räumt beide zugleich weg.

## Bekannte, keine Fehler

| Beobachtung | Ursache |
|---|---|
| `GET / → 404` und `GET /favicon.ico → 404` in der Backend-Konsole | normal in der Entwicklung — das Backend liefert `/` nur aus, wenn unter `frontend/dist` ein gebautes Frontend liegt; in der Entwicklung läuft die Oberfläche über Vite auf `:5173` |
| Startseite zeigt nur „Sprecher“ und ein leeres Formular | Leerzustand vor dem ersten Profil, keine kaputte Seite |
| „schreiben“ versteht mit `tiny` erkennbar Falsches | erwartet — genau dafür gibt es die App „lernen“ |
| `http://localhost:5174` ohne `/schreiben/` bleibt leer | die App liegt unter einem Pfad (`base` in ihrer `vite.config.ts`, `BASIS` in ihrer `main.py`) |
| Der Reiter „schreiben" bleibt in „hören" stehen | „schreiben" läuft nicht (`make dev APP=schreiben`); im Betrieb: der Proxy verteilt `/schreiben/` nicht |

Bekannte Fehlerbilder mit Ursache: [`docs/betrieb.md#wenn-etwas-klemmt`](betrieb.md#wenn-etwas-klemmt).
