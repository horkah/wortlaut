/**
 * Was nur „lernen" teilt: der Weg zu einem einzelnen Lauf.
 *
 * Route und Zugang sind in jeder App dieselbe Sache und stehen deshalb in
 * `$ui/lage.svelte` - der Zugang selbst ist derselbe Eintrag desselben
 * Browsers wie für „hören" und „schreiben" (`$ui/zugang`): Ein Mensch, ein
 * Link, drei Apps.
 */

import { GRUNDMODELL_ROUTE, LAUF_ROUTE } from '$ui/apps';

export { gehZu } from '$ui/route';
export { lage } from '$ui/lage.svelte';
// Ein einzelner Lauf (`#/lauf/<job_id>`) und ein Grundmodell
// (`#/grundmodell/<name>`) - in `$ui/apps`, weil „hören" dorthin verlinkt.
export { GRUNDMODELL_ROUTE, LAUF_ROUTE };

export function laufAusRoute(route: string): string {
  return route.startsWith(LAUF_ROUTE) ? route.slice(LAUF_ROUTE.length) : '';
}

export function grundmodellAusRoute(route: string): string {
  return route.startsWith(GRUNDMODELL_ROUTE)
    ? decodeURIComponent(route.slice(GRUNDMODELL_ROUTE.length))
    : '';
}
