/**
 * Der Zugang im Browser - einer für alle Apps.
 *
 * Ein Mensch hat genau einen Zugang (`<sprecher_id>.<geheimnis>`, ausgegeben
 * von „hören"), und beide Apps liegen unter derselben Domain. Der
 * `localStorage` gehört dem Ursprung und nicht dem Pfad, also ist es
 * buchstäblich derselbe Eintrag: Wer seinen persönlichen Link einmal geöffnet
 * hat - gleich in welcher App -, ist auch in der anderen angemeldet. Genau das
 * macht den zweiten Zugang für „schreiben" überflüssig, den es nie geben
 * sollte (die Zielperson kann schlecht lesen und schreiben).
 *
 * Deshalb steht der Schlüssel hier und nicht zweimal in zwei `api.ts`: Zwei
 * Namen für dasselbe Geheimnis wären zwei Anmeldungen für denselben Menschen.
 */

// Was hier liegt, ist ein Sprecherzugang, der Verwalter- oder der
// Aufsichtstoken - der Server sieht am Aufbau, welches von beidem
// (`wortlaut.zugang` im Backend).
const SCHLUESSEL = 'wortlaut.zugang';

/**
 * Der Weg, auf dem ein Zugang in diesen Browser kommt: ein Link, einmal
 * geöffnet. Er steht im Hash und nicht in der Abfrage - ein Fragment geht nie
 * an den Server und landet damit in keinem Zugriffsprotokoll.
 */
export const ZUGANG_ROUTE = '/zugang/';

export function zugang(): string {
  return localStorage.getItem(SCHLUESSEL) ?? '';
}

export function setzeZugang(wert: string): void {
  localStorage.setItem(SCHLUESSEL, wert.trim());
}

/** Den Zugang an eine Anfrage hängen - die einzige Stelle, die das tut. */
export function mitZugang(headers?: HeadersInit): Headers {
  const kopf = new Headers(headers);
  const angemeldet = zugang();
  if (angemeldet) kopf.set('Authorization', `Bearer ${angemeldet}`);
  return kopf;
}

/**
 * Einen Zugang aus dem Link übernehmen, falls einer darin steht; sagt, ob es
 * einen gab.
 *
 * Der Eintrag im Verlauf wird dabei ersetzt statt ergänzt: Sonst stünde das
 * Geheimnis in der Adresszeile und im Zurück-Knopf.
 *
 * Beide Apps verstehen denselben Link. Er zeigt zwar auf „hören", aber ein
 * Lesezeichen wandert, und wer ihn in „schreiben" öffnet, soll nicht vor einer
 * Seite stehen, die ihn nicht kennt.
 */
export function nimmZugangAusLink(route: string): boolean {
  if (!route.startsWith(ZUGANG_ROUTE)) return false;
  setzeZugang(decodeURIComponent(route.slice(ZUGANG_ROUTE.length)));
  const { pathname, search } = window.location;
  window.history.replaceState(null, '', `${pathname}${search}#/`);
  return true;
}
