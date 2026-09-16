/**
 * Was alle Ansichten teilen: die Route, wer hier ruft - und das Streuen.
 *
 * Die beiden ersten sind in jeder App dieselbe Sache und stehen deshalb nicht
 * mehr hier: Der Hash-Router liegt in `$ui/route`, die Auskunft über den
 * Zugang in `$ui/wer`. Was bleibt, ist das, was nur „hören" hat.
 */

import { folgeHash, routeAusHash } from '$ui/route';
import { OFFEN, ermittleZugang } from '$ui/wer';
import { nimmZugangAusLink } from '$ui/zugang';

export { gehZu } from '$ui/route';

const ZUFALL_SCHLUESSEL = 'wortlaut.zufall';

export const zustand = $state({
  route: routeAusHash(),
  // Gestreut statt der Reihe nach vorsprechen. Aus, solange nichts anderes
  // dasteht: Der Text der Reihe nach ist der erwartete Fall.
  zufall: localStorage.getItem(ZUFALL_SCHLUESSEL) === 'true',
  ...OFFEN,
});

folgeHash((route) => (zustand.route = route));

/**
 * Die Einsicht der Aufsicht in **einen** Sprecher: `#/aufsicht/<sprecher_id>`.
 *
 * Der Sprecher steht hier ausnahmsweise in der Adresse. Das ist kein Rückfall
 * in die alte Behauptung: Die Aufsicht hat keinen eigenen Sprecher, und der
 * Server prüft ihren Token, nicht die Kennung in der Adresse.
 */
export const EINSICHT_ROUTE = '/aufsicht/';

export function sprecherAusRoute(route: string): string {
  return route.startsWith(EINSICHT_ROUTE) ? route.slice(EINSICHT_ROUTE.length) : '';
}

export function setzeZufall(an: boolean): void {
  zustand.zufall = an;
  localStorage.setItem(ZUFALL_SCHLUESSEL, String(an));
}

/** Beim Server nachfragen, für wen dieser Browser eingestellt ist. */
export async function ladeZugang(): Promise<void> {
  // Steckte einer im Link, liegt er jetzt im Browser und die Adresse ist
  // wieder sauber (siehe `$ui/zugang`).
  if (nimmZugangAusLink(routeAusHash())) zustand.route = '/';
  Object.assign(zustand, await ermittleZugang());
}
