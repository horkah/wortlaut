/**
 * Der Trainerschlüssel im Browser - das zweite Geheimnis, und das seltenere.
 *
 * Der Zugang eines Sprechers sagt, wessen Modell entsteht; er liegt in
 * `$ui/zugang` und geht an jede Anfrage. Dieser Schlüssel beantwortet eine
 * andere Frage - ob jemand die Karte für Stunden belegen darf - und geht
 * deshalb an genau eine: `POST /lernen/api/laeufe` (siehe
 * `backend/api/laeufe.py`).
 *
 * Warum er überhaupt im `localStorage` liegt und nicht jedes Mal neu getippt
 * wird: Wer trainiert, tut das in Sitzungen - vier Läufe hintereinander, um
 * sie zu vergleichen -, und ein Feld, das bei jedem Auftrag leer ist, wird
 * abgeschrieben und landet in einer Textdatei neben dem Browser. Er steht
 * unter einem eigenen Namen und nicht beim Zugang, damit „abmelden" das eine
 * räumen kann, ohne das andere mitzunehmen.
 */

const SCHLUESSEL = 'wortlaut.trainerschluessel';

export function trainerschluessel(): string {
  try {
    return localStorage.getItem(SCHLUESSEL) ?? '';
  } catch {
    // Ein Browser mit gesperrtem Speicher ist kein Fehlerfall: Dann steht das
    // Feld eben bei jedem Auftrag wieder leer da.
    return '';
  }
}

export function setzeTrainerschluessel(wert: string): void {
  try {
    const getrimmt = wert.trim();
    if (getrimmt) localStorage.setItem(SCHLUESSEL, getrimmt);
    else localStorage.removeItem(SCHLUESSEL);
  } catch {
    /* siehe oben */
  }
}
