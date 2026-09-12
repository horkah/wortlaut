/**
 * Was alle Ansichten teilen: die Route und wer hier gerade angemeldet ist.
 *
 * Beides ist in jeder App dieselbe Sache und steht deshalb nicht mehr hier:
 * Der Hash-Router liegt in `$ui/route`, die Auskunft über den Zugang in
 * `$ui/wer` - und der Zugang selbst ist derselbe Eintrag desselben Browsers
 * wie für „hören" und „schreiben" (`$ui/zugang`): Ein Mensch, ein Link, drei
 * Apps. Was bleibt, ist der Weg zu einem einzelnen Lauf.
 */

import { folgeHash, routeAusHash } from '$ui/route';
import { OFFEN, ermittleZugang } from '$ui/wer';
import { nimmZugangAusLink } from '$ui/zugang';
import { werRuft } from './api';

export { gehZu } from '$ui/route';

export const zustand = $state({
  route: routeAusHash(),
  ...OFFEN,
});

folgeHash((route) => (zustand.route = route));

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
  Object.assign(zustand, await ermittleZugang(werRuft));
}
