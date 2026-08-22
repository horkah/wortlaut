# Datenschutz

Stimmaufnahmen einer Person mit Sprechstörung sind Gesundheitsdaten nach
Art. 9 DSGVO. Das hat Folgen für den Aufbau, nicht nur für einen Hinweistext.

## Wo Daten liegen

| Daten | Ort | Anmerkung |
|---|---|---|
| Aufnahmen (WAV) | `WORTLAUT_DATA_DIR/korpus/<sprecher_id>/audio/` | nie im Git, nie in Logs |
| Vorlagen, Sitzungen, Messwerte | `…/korpus/<sprecher_id>/hoeren.sqlite` | eine Datei je Sprecher |
| Modellstände | `WORTLAUT_DATA_DIR/modelle/<sprecher_id>/` | enthalten Stimmcharakteristik |
| Diktate von „schreiben" | `…/diktate/<sprecher_id>/` | Arbeitsstand: Abschnitte, die noch nicht übergeben sind |

Eine Sprecher-Identität ist damit vollständig unter drei Verzeichnissen
lokalisiert, alle nach derselben Sprecher-ID benannt. Das ist keine Ordnungsliebe, sondern die Voraussetzung für eine
Löschung, die man auch nachweisen kann.

## Was den Server verlässt

Voreingestellt: nichts. Zwei Schalter können das ändern, beide bewusst:

- `WORTLAUT_LLM_PROVIDER` — schickt **Thema und Altersspanne** an einen
  LLM-Anbieter, um Vorlesetexte zu erzeugen. Keine Stimm- und keine
  Personendaten. Ohne diesen Wert bleibt der Textupload als einzige Quelle.
- `WORTLAUT_ASR=remote` mit `WORTLAUT_ASR_ENDPOINT` (App „schreiben") —
  schickt **Stimmaufnahmen** an einen Dritten. Wer diesen Schalter umlegt,
  verarbeitet Gesundheitsdaten außer Haus und braucht dafür eine
  Rechtsgrundlage und einen Auftragsverarbeitungsvertrag. Voreingestellt ist
  `local`: faster-whisper rechnet im eigenen Prozess, es geht nichts hinaus.
- `WORTLAUT_INTAKE_URL` (App „schreiben") — der Weg zurück zu „hören". Zeigt er
  auf die eigene Instanz, verlässt nichts den Server; er kann aber auf einen
  fremden zeigen, und dann tut es das.

## Datensparsamkeit im Ablauf

- Eine **verworfene** Aufnahme wird sofort gelöscht, nicht nur markiert. In der
  Datenbank bleibt der Datensatz mit `status = 'verworfen'` als Spur, die
  Audiodatei ist weg.
- Es gibt keine Rohaufnahme neben dem WAV: das hochgeladene Opus-Fragment liegt
  nur im temporären Verzeichnis, bis ffmpeg fertig ist.
- „schreiben" behält die zusammenhängende Diktataufnahme nicht: Nach dem
  Schnitt an den Segmentgrenzen bleiben nur die Abschnitte übrig.
- Ist ein Abschnitt als Korrektur im Korpus angekommen, wird seine Audiodatei
  in `diktate/` gelöscht. Die Zeile bleibt als Spur, die Aufnahme liegt nur
  noch an einer Stelle.
- Fehlermeldungen enthalten Pfade, aber keine Transkripte oder Audioinhalte.

## Löschung

```bash
uv run python scripts/purge_speaker.py <sprecher_id>               # Probelauf
uv run python scripts/purge_speaker.py <sprecher_id> --ja-wirklich # löschen
```

Entfernt Profil, Aufnahmen, Schnappschüsse, Modellstände und die Diktate von
„schreiben". Dasselbe geht in der Oberfläche als Aufsicht (siehe unten), mit
demselben Umfang: Was zu einer Person gehört, steht an einer Stelle
(`apps/hoeren/backend/services/loeschung.py`), damit Oberfläche und
Kommandozeile nicht Verschiedenes löschen.

Feiner geht es auch — eine einzelne Aufnahme oder alle Aufnahmen einer Person,
ohne ihr Profil anzutasten. Einen Weg, der mehrere Personen auf einmal löscht,
gibt es bewusst nicht.

**Sicherungen sind Kopien und müssen mitgelöscht werden.** Die Aufsicht kann
Korpora als `.tgz` ausleiten; was einmal heruntergeladen ist, weiß dieses
Projekt nicht mehr. Solche Archive enthalten vollständige Stimmaufnahmen und
gehören damit in die Löschroutine des Betriebs — ebenso wie ausgeleitete
Datensätze (`.zip`) und jede Sicherung außerhalb von `WORTLAUT_DATA_DIR`.
Aufbewahrungsfrist und Ablageort dafür festzulegen ist eine organisatorische
Entscheidung, die kein Skript abnehmen kann.

## Zugang

In `hören` hat jeder Sprecher seinen eigenen Zugang, und dieser Zugang ist
zugleich seine Kennung: Der Server liest aus ihm ab, welches Korpusverzeichnis
er öffnet, statt sich die Kennung sagen zu lassen. Nutzen mehrere Personen
dieselbe Instanz, kommt damit keine an die Stimmaufnahmen einer anderen — auch
nicht aus Versehen, denn eine Anfrage, die eine fremde Kennung behauptet, wird
mit 403 abgewiesen statt still ausgeführt. Ein verlorener Zugang wird
zurückgezogen, indem ein neuer ausgegeben wird; Einzelheiten in
[`betrieb.md`](betrieb.md#authentifizierung).

`WORTLAUT_AUTH_TOKEN` schützt daneben nur noch die Verwaltung — Profile
anlegen, Zugänge ausgeben — und öffnet selbst kein Korpus.

`WORTLAUT_ADMIN_TOKEN` dagegen schon: Er ist der Zugang der **Aufsicht**, die
in jedes Korpus sieht, Aufnahmen abhört, sichert und löscht. Damit ist er der
einzige Schlüssel, der an die Stimmaufnahmen aller Personen kommt, und
entsprechend zu behandeln — lang und zufällig, nicht in einem geteilten
Dokument, und getrennt vom Verwaltertoken. Ist er nicht gesetzt, ist die
Aufsicht abgeschaltet; das ist die Voreinstellung. Wer eine Instanz für andere
betreibt, sollte ihnen sagen, dass es diese Rolle gibt und wer sie hat: Für die
betroffenen Personen ist das eine Auskunft nach Art. 13/14 DSGVO und keine
technische Fußnote.

`schreiben` hat bewusst kein Nutzerkonto, weil die Zielperson schlecht lesen
und schreiben kann. Eine `schreiben`-Instanz gehört deshalb ins private Netz
oder hinter einen Zugang, den jemand anderes einrichtet. Umgekehrt braucht sie
den Sprecherzugang von `hören`, um Korrekturen abliefern zu dürfen: Der Rückweg
steht offen, der Hinweg nicht — und er führt in genau den Korpus, zu dem dieser
Zugang gehört.
