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
„schreiben". Sicherungskopien
außerhalb von `WORTLAUT_DATA_DIR` liegen außerhalb dessen, was ein Skript
wissen kann — sie gehören in die Löschroutine des Betriebs.

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

`schreiben` hat bewusst kein Nutzerkonto, weil die Zielperson schlecht lesen
und schreiben kann. Eine `schreiben`-Instanz gehört deshalb ins private Netz
oder hinter einen Zugang, den jemand anderes einrichtet. Umgekehrt braucht sie
den Sprecherzugang von `hören`, um Korrekturen abliefern zu dürfen: Der Rückweg
steht offen, der Hinweg nicht — und er führt in genau den Korpus, zu dem dieser
Zugang gehört.
