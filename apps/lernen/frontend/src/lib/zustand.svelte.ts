/**
 * Was nur „lernen" teilt: der Weg zu einem einzelnen Lauf.
 *
 * Route und Zugang sind in jeder App dieselbe Sache und stehen deshalb in
 * `$ui/lage.svelte` - der Zugang selbst ist derselbe Eintrag desselben
 * Browsers wie für „hören" und „schreiben" (`$ui/zugang`): Ein Mensch, ein
 * Link, drei Apps.
 */

export { gehZu } from '$ui/route';
export { lage } from '$ui/lage.svelte';

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
