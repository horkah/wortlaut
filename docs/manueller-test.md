# Manueller Test — App „hören“

Schritt-für-Schritt-Anleitung für einen Menschen im Browser. Prüft den
kompletten Weg vom leeren Sprecherprofil bis zur ersten Aufnahme, einmal quer
durch alle Ansichten. Ergänzt `make test` (automatisiert, ohne Browser, ohne
Mikrofon) — ersetzt es nicht.

Dauer: etwa 10 Minuten, plus die Zeit für ein paar echte Aufnahmen.

## Voraussetzungen

- Server läuft: `make dev APP=hoeren` (Backend `:8000`, Vite `:5173`) —
  siehe [`docs/betrieb.md`](betrieb.md#entwicklung)
- Browser mit Mikrofonzugriff, aufgerufen über **`http://localhost:5173`**
  (nicht `:8000` — das Backend liefert dort nur `/api/…` und `/gesundheit`,
  ein `404` auf `/` davor ist normal, kein Fehler)
- `WORTLAUT_AUTH_TOKEN` in `.env` leer lassen, dann entfällt Schritt 1c

## 1. Sprecherprofil

1. Seite öffnen. Erwartet: Kopfzeile „wortlaut · hören“ **ohne** Navigation,
   Überschrift „Sprecher“, darunter „Noch kein Sprecherprofil vorhanden.“ —
   das ist der Leerzustand, keine kaputte Seite.
2. Unter „Neues Profil“: Namen eintragen, Basismodell auf
   `whisper-small (Entwicklung ohne GPU)` oder, für noch weniger Rechenlast,
   `whisper-tiny (noch weniger Rechenlast)` stellen, **Anlegen**. Für den
   Testablauf hier ohne Belang: `hören` selbst ruft Whisper nirgends auf —
   das Feld ist reine Metadaten für das spätere Training in `lernen`.
3. Erwartet: Profil erscheint in der Liste, App springt automatisch zur
   Ansicht „Textquelle“, die Navigation oben ist jetzt sichtbar.
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

1. **Fortschritt** in der Navigation.
2. Erwartet: Stundenzahl, Anzahl Aufnahmen, offene Einheiten; zwei Balken
   gegen die Marken „Brauchbar“ und „Gut“; Tabelle „Zusammensetzung“ mit den
   gerade aufgenommenen Modi (`gelesen` und ggf. `nachgesprochen`) und der
   Quelle (`vorlage`).
3. **Abmelden.** Erwartet: zurück zur Startansicht, Navigation verschwindet,
   das angelegte Profil steht weiter in der Sprecherliste und lässt sich
   erneut auswählen.

## 5. Einstellungen

1. **Einstellungen** in der Navigation.
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
7. Seite neu laden (F5). Erwartet: alle drei Werte sind erhalten
   (`localStorage`).
8. **Auf Vorgaben zurücksetzen** drücken. Erwartet: Tempo 0,9×, Schriftgröße
   2,0 rem, Stimme wieder die des Browsers.

## Aufräumen

Testdaten liegen unter `data/korpus/<sprecher_id>/` (Pfad aus
`WORTLAUT_DATA_DIR`). Löschen genügt ein Entfernen des Verzeichnisses, oder
`uv run python scripts/purge_speaker.py <sprecher_id>` für den vollständigen
Weg über das Löschskript.

## Bekannte, keine Fehler

| Beobachtung | Ursache |
|---|---|
| `GET / → 404` und `GET /favicon.ico → 404` in der Backend-Konsole | normal in der Entwicklung — das Backend liefert `/` nur aus, wenn unter `frontend/dist` ein gebautes Frontend liegt; in der Entwicklung läuft die Oberfläche über Vite auf `:5173` |
| Startseite zeigt nur „Sprecher“ und ein leeres Formular | Leerzustand vor dem ersten Profil, keine kaputte Seite |

Bekannte Fehlerbilder mit Ursache: [`docs/betrieb.md#wenn-etwas-klemmt`](betrieb.md#wenn-etwas-klemmt).
