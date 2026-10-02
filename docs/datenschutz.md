# Datenschutz

Stimmaufnahmen einer Person mit Sprechstörung sind Gesundheitsdaten nach
Art. 9 DSGVO. Das bestimmt den Aufbau, nicht nur einen Hinweistext.

## Wo Daten liegen

| Daten | Ort | Anmerkung |
|---|---|---|
| Aufnahmen | `WORTLAUT_DATA_DIR/korpus/<sprecher_id>/audio/` | nie im Git, nie in Logs |
| Vorlagen, Sitzungen, Messwerte | `…/korpus/<sprecher_id>/hoeren.sqlite` | eine Datei je Sprecher |
| Diktate von „schreiben" | `…/diktate/<sprecher_id>/` | Arbeitsstand bis zur Übergabe |
| Laufverzeichnisse | `…/snapshots/<job_id>/` | Manifest mit Texten, markiert mit `sprecher.txt` |
| Modellstände | `…/modelle/<sprecher_id>/` | tragen Stimmcharakteristik |
| Register der Läufe | `…/lernen/<sprecher_id>/register.sqlite` | Texte, erkannte Texte und Messwerte jedes Laufs, auch gelöschter; zur wissenschaftlichen Auswertung, pseudonym: Kennung statt Name, kein Audio |
| Fehlerprotokoll | `…/protokoll/fehler.jsonl` | Warnungen und Fehler, sieben Tage; Kennungen und Pfade, nur für Aufsicht, Verwaltung und Trainerschlüssel |

Alles zu einer Person liegt unter Verzeichnissen mit ihrer Kennung - die
Voraussetzung für eine Löschung, die sich nachweisen lässt.

## Was den Server verlässt

Voreingestellt: nichts. Drei Schalter können das ändern:

- `WORTLAUT_LLM_PROVIDER` schickt **Thema und Altersspanne** an einen
  LLM-Anbieter, um Vorlesetexte zu erzeugen - keine Stimm- und keine
  Personendaten. Voreingestellt ist ein lokales Ollama.
- `WORTLAUT_ASR=remote` (App „schreiben") schickt **Stimmaufnahmen** an einen
  Dritten. Wer das einschaltet, verarbeitet Gesundheitsdaten außer Haus und
  braucht Rechtsgrundlage und Auftragsverarbeitungsvertrag.
- `WORTLAUT_INTAKE_URL` (App „schreiben") ist der Weg zurück zu „hören". Zeigt
  er auf einen fremden Server, verlassen Korrekturen das Haus.

**Die Zeichenerkennung gehört nicht dazu.** Ein fotografierter Brief ist
womöglich das Persönlichste, was die App sieht. Gelesen wird mit Tesseract im
eigenen Prozess (`wortlaut/text/ocr.py`), ohne Schalter. Das Bild wird nirgends
abgelegt: Starlette und pytesseract schreiben es zwar kurz nach `/tmp`, nach
der Antwort ist davon nichts mehr da - geprüft unter- und oberhalb der
Auslagerungsgrenze. Im Erkennungsweg steht kein Netzaufruf. Dieselbe Zusage
steht in der Oberfläche über dem Auswahlfeld, wo jemand zögert.

## Datensparsamkeit im Ablauf

- Eine **verworfene** Aufnahme verliert sofort ihr Audio; die Zeile bleibt als
  Spur mit `status = 'verworfen'`.
- Das hochgeladene Opus liegt nur temporär, bis ffmpeg fertig ist.
- „schreiben" behält die zusammenhängende Diktataufnahme nicht, und ein
  Abschnitt verliert seine Datei, sobald er im Korpus angekommen ist.
- Ein Lauf mit **Selbsttraining** lernt auch aus nie bestätigten Diktaten.
  Ihr Audio bleibt, wo es liegt; der Lauf nennt es im Manifest und legt die
  Beschriftung des Modells in `selbstbeschriftung.json` - beides unter der
  Sprecher-Marke des Laufs und mit ihm gelöscht. Voreingestellt ist es aus.
- Abgewandelte Fassungen und vorgelesene Sätze gehen mit ihrer Aufnahme und
  ihrem Sprecher.
- Fehlermeldungen enthalten Pfade, keine Transkripte oder Audioinhalte.

## Was der Aufbau zusichert

- **`lernen` schreibt den Korpus nie** - es gibt keinen Weg dafür, und ein
  Test hält das fest (`apps/lernen/tests/test_trennung.py`).
- **Der Trainings-Container hängt an keinem Netz**; er spricht nur mit dem
  Datenverzeichnis.
- **Kein Korpus öffnet sich über eine behauptete Kennung** - sie wird aus dem
  Zugang abgeleitet (siehe unten).

Eine vierstellige **PIN** vor „Meine Daten", „Darstellung" und
„Zugangsdaten" schützt gegen den Klick aus Versehen, nicht gegen einen
Angreifer; die Kennung bleibt der Zugang.

## Löschung

```bash
uv run python scripts/purge_speaker.py <sprecher_id>               # Probelauf
uv run python scripts/purge_speaker.py <sprecher_id> --ja-wirklich # löschen
```

Entfernt Profil, Aufnahmen, Laufverzeichnisse, Modellstände, das Register
der Läufe und Diktate. Das Löschen eines Laufs in „lernen" lässt das Register
stehen - dafür ist es da.
Dasselbe geht in der Oberfläche als Aufsicht, mit demselben Umfang aus
derselben Quelle (`apps/hoeren/backend/services/loeschung.py`). Feiner geht
es auch: eine Aufnahme, alle Aufnahmen einer Person. Einen Weg, der mehrere
Personen löscht, gibt es nicht.

**Sicherungen sind Kopien.** Was als `.tgz` oder `.zip` heruntergeladen wurde,
kennt das Projekt nicht mehr; solche Archive enthalten vollständige
Stimmaufnahmen und gehören in die Löschroutine des Betriebs. Frist und Ablage
dafür sind eine organisatorische Entscheidung.

## Zugang

Jeder Sprecher hat einen eigenen Zugang, der zugleich seine Kennung ist: Der
Server liest daraus ab, welchen Korpus er öffnet. Eine Anfrage, die eine
fremde Kennung behauptet, endet mit 403. Ein verlorener Zugang wird ersetzt
und ist damit zurückgezogen ([hören](hoeren.md#der-zugang-ist-die-kennung)).
Ein Link ist ein Lesezeichen: Wer ein Gerät weitergibt, gibt den Zugang mit.

`schreiben` und `lernen` leiten den Sprecher aus demselben Zugang ab. Was in
`schreiben` bestätigt wird, geht mit diesem Zugang in genau seinen Korpus.

`WORTLAUT_AUTH_TOKEN` schützt nur die Verwaltung und öffnet keinen Korpus.
`WORTLAUT_ADMIN_TOKEN` ist der Zugang der **Aufsicht** und der einzige
Schlüssel zu den Aufnahmen aller Personen - lang, zufällig, getrennt vom
Verwaltertoken, nicht in geteilten Dokumenten. Leer ist die Aufsicht
abgeschaltet. Wer eine Instanz für andere betreibt, sagt ihnen, dass es diese
Rolle gibt und wer sie hat: eine Auskunft nach Art. 13/14 DSGVO.
