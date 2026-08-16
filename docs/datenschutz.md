# Datenschutz

Stimmaufnahmen einer Person mit Sprechstörung sind Gesundheitsdaten nach
Art. 9 DSGVO. Das hat Folgen für den Aufbau, nicht nur für einen Hinweistext.

## Wo Daten liegen

| Daten | Ort | Anmerkung |
|---|---|---|
| Aufnahmen (WAV) | `WORTLAUT_DATA_DIR/korpus/<sprecher_id>/audio/` | nie im Git, nie in Logs |
| Vorlagen, Sitzungen, Messwerte | `…/korpus/<sprecher_id>/hoeren.sqlite` | eine Datei je Sprecher |
| Modellstände | `WORTLAUT_DATA_DIR/modelle/<sprecher_id>/` | enthalten Stimmcharakteristik |

Eine Sprecher-Identität ist damit vollständig unter zwei Verzeichnissen
lokalisiert. Das ist keine Ordnungsliebe, sondern die Voraussetzung für eine
Löschung, die man auch nachweisen kann.

## Was den Server verlässt

Voreingestellt: nichts. Zwei Schalter können das ändern, beide bewusst:

- `WORTLAUT_LLM_PROVIDER` — schickt **Thema und Altersspanne** an einen
  LLM-Anbieter, um Vorlesetexte zu erzeugen. Keine Stimm- und keine
  Personendaten. Ohne diesen Wert bleibt der Textupload als einzige Quelle.
- `WORTLAUT_ASR` / `WORTLAUT_ASR_ENDPOINT` (App „schreiben") — schickt
  **Stimmaufnahmen** an einen Dritten. Wer diesen Schalter umlegt, verarbeitet
  Gesundheitsdaten außer Haus und braucht dafür eine Rechtsgrundlage und einen
  Auftragsverarbeitungsvertrag.

## Datensparsamkeit im Ablauf

- Eine **verworfene** Aufnahme wird sofort gelöscht, nicht nur markiert. In der
  Datenbank bleibt der Datensatz mit `status = 'verworfen'` als Spur, die
  Audiodatei ist weg.
- Es gibt keine Rohaufnahme neben dem WAV: das hochgeladene Opus-Fragment liegt
  nur im temporären Verzeichnis, bis ffmpeg fertig ist.
- Fehlermeldungen enthalten Pfade, aber keine Transkripte oder Audioinhalte.

## Löschung

```bash
uv run python scripts/purge_speaker.py <sprecher_id>               # Probelauf
uv run python scripts/purge_speaker.py <sprecher_id> --ja-wirklich # löschen
```

Entfernt Profil, Aufnahmen, Schnappschüsse und Modellstände. Sicherungskopien
außerhalb von `WORTLAUT_DATA_DIR` liegen außerhalb dessen, was ein Skript
wissen kann — sie gehören in die Löschroutine des Betriebs.

## Zugang

`hören` und `lernen` stehen hinter einem Token (`WORTLAUT_AUTH_TOKEN`);
`schreiben` hat bewusst kein Nutzerkonto, weil die Zielperson schlecht lesen
und schreiben kann. Eine `schreiben`-Instanz gehört deshalb ins private Netz
oder hinter einen Zugang, den jemand anderes einrichtet.
