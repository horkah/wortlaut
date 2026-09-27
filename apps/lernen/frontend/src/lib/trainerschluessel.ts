/**
 * Der Trainerschlüssel im Browser - das zweite Geheimnis, und das seltenere.
 *
 * Der Zugang eines Sprechers sagt, wessen Modell entsteht; er liegt in
 * `$ui/zugang` und geht an jede Anfrage. Dieser Schlüssel beantwortet eine
 * andere Frage - ob jemand die Karte für Stunden belegen darf - und geht
 * deshalb an genau eine: `POST /lernen/api/laeufe` (siehe
 * `backend/api/laeufe.py`).
 *
 * Im `localStorage`, weil in Sitzungen trainiert wird und ein jedes Mal
 * leeres Feld in einer Textdatei landet. Unter eigenem Namen, damit
 * „abmelden" den Zugang räumt, ohne den Schlüssel mitzunehmen.
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
