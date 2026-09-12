/**
 * Was alle Ansichten teilen: die Route und wer hier gerade angemeldet ist.
 *
 * Die Route steht im Hash (`#/training`). Das genügt für drei Ansichten und
 * spart ein Routing-Paket samt Server-Konfiguration - dieselbe Wahl wie in den
 * beiden anderen Apps.
 *
 * Der Sprecher kommt vom Server, der ihn aus dem vorgelegten Zugang ableitet.
 * Was der Browser aufbewahrt, ist allein der Zugang - und zwar derselbe
 * Eintrag wie für „hören" und „schreiben" (`$ui/zugang`): Ein Mensch, ein
 * Link, drei Apps.
 */

import { nimmZugangAusLink } from '$ui/zugang';
import { ApiFehler, werRuft } from './api';

function routeAusHash(): string {
  return window.location.hash.replace(/^#/, '') || '/';
}

export const zustand = $state({
  route: routeAusHash(),
  // `unbekannt`, bis der Server geantwortet hat; `keiner`, wenn er den Zugang
  // abweist. Beides ist kein Fehler, sondern ein Zustand der Oberfläche.
  art: 'unbekannt' as 'unbekannt' | 'sprecher' | 'verwaltung' | 'aufsicht' | 'keiner',
  sprecher: null as string | null,
  name: null as string | null,
});

window.addEventListener('hashchange', () => {
  zustand.route = routeAusHash();
});

export function gehZu(route: string): void {
  window.location.hash = route;
}

/**
 * Ein einzelner Lauf: `#/lauf/<job_id>`.
 *
 * Die Kennung steht in der Adresse, damit ein Lauf verlinkbar bleibt - ein
 * Training dauert Stunden, und wer nach dem Mittagessen wieder hinsehen will,
 * soll den Reiter wiederfinden statt ihn zu suchen.
 */
export const LAUF_ROUTE = '/lauf/';

export function laufAusRoute(route: string): string {
  return route.startsWith(LAUF_ROUTE) ? route.slice(LAUF_ROUTE.length) : '';
}

/** Beim Server nachfragen, für wen dieser Browser eingestellt ist. */
export async function ladeZugang(): Promise<void> {
  if (nimmZugangAusLink(routeAusHash())) zustand.route = '/';
  try {
    const wer = await werRuft();
    zustand.art = wer.art;
    zustand.sprecher = wer.sprecher_id;
    zustand.name = wer.name;
  } catch (ursache) {
    zustand.art = ursache instanceof ApiFehler && ursache.status === 401 ? 'keiner' : 'unbekannt';
    zustand.sprecher = null;
    zustand.name = null;
  }
}
