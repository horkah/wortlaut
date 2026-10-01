/**
 * Der Trainerschlüssel im Browser - das zweite Geheimnis, und das seltenere.
 *
 * Der Zugang eines Sprechers sagt, wessen Modell entsteht; er liegt in
 * `zugang.ts` und geht an jede Anfrage. Dieser Schlüssel beantwortet eine
 * andere Frage - ob jemand die Karte für Stunden belegen darf - und geht
 * deshalb nur an die Wege, die er öffnet: `POST /lernen/api/laeufe`, das
 * Löschen eines Laufs und das Fehlerprotokoll (`GET /api/fehlerlog`).
 *
 * Im `localStorage`, weil in Sitzungen trainiert wird und ein jedes Mal
 * leeres Feld in einer Textdatei landet. Unter eigenem Namen, damit
 * „abmelden" den Zugang räumt, ohne den Schlüssel mitzunehmen. Hier in
 * `packages/ui` und als Zustand, weil das Menü jeder App wissen will, ob er da
 * ist - und es sofort wissen soll, wenn er eingetragen wird.
 */

const SCHLUESSEL = 'wortlaut.trainerschluessel';

function gespeichert(): string {
  try {
    return localStorage.getItem(SCHLUESSEL) ?? '';
  } catch {
    // Ein Browser mit gesperrtem Speicher ist kein Fehlerfall: Dann steht das
    // Feld eben bei jedem Auftrag wieder leer da.
    return '';
  }
}

const stand = $state({ wert: gespeichert() });

export function trainerschluessel(): string {
  return stand.wert;
}

export function setzeTrainerschluessel(wert: string): void {
  const getrimmt = wert.trim();
  stand.wert = getrimmt;
  try {
    if (getrimmt) localStorage.setItem(SCHLUESSEL, getrimmt);
    else localStorage.removeItem(SCHLUESSEL);
  } catch {
    /* siehe oben */
  }
}
