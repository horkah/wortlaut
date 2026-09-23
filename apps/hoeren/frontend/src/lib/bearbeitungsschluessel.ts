/**
 * Der Bearbeitungsschlüssel im Browser - das zweite Geheimnis dieser App.
 *
 * Wortgleich zum Trainerschlüssel in „lernen"
 * (`apps/lernen/frontend/src/lib/trainerschluessel.ts`), und das ist Absicht:
 * Es ist dieselbe Bauart für dieselbe Art von Frage. Der Zugang eines
 * Sprechers sagt, wessen Aufnahmen das sind; er liegt in `$ui/zugang` und geht
 * an jede Anfrage. Dieser Schlüssel beantwortet, ob jemand in den Bestand
 * greifen darf, und geht deshalb nur an die Wege unter `/api/zuschnitt/…`
 * (siehe `backend/api/zuschnitt.py`).
 *
 * Warum er im `localStorage` liegt und nicht jedes Mal neu getippt wird: Wer
 * zuschneidet, tut das in Sitzungen - eine Seite nach der anderen, über
 * Hunderte Aufnahmen -, und ein Feld, das nach jedem Blättern leer ist, wird
 * abgeschrieben und landet auf einem Zettel neben dem Rechner. Er steht unter
 * einem eigenen Namen und nicht beim Zugang, damit „abmelden" das eine räumen
 * kann, ohne das andere mitzunehmen.
 */

const SCHLUESSEL = 'wortlaut.bearbeitungsschluessel';

export function bearbeitungsschluessel(): string {
  try {
    return localStorage.getItem(SCHLUESSEL) ?? '';
  } catch {
    // Ein Browser mit gesperrtem Speicher ist kein Fehlerfall: Dann steht das
    // Feld eben bei jedem Besuch wieder leer da.
    return '';
  }
}

export function setzeBearbeitungsschluessel(wert: string): void {
  try {
    const getrimmt = wert.trim();
    if (getrimmt) localStorage.setItem(SCHLUESSEL, getrimmt);
    else localStorage.removeItem(SCHLUESSEL);
  } catch {
    /* siehe oben */
  }
}
