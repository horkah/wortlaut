/**
 * Was nur „hören" teilt: das Streuen - und die Einsicht der Aufsicht.
 *
 * Route und Zugang sind in jeder App dieselbe Sache und stehen deshalb in
 * `$ui/lage.svelte` (von hier aus weitergereicht, damit jede Ansicht ihren
 * Zustand an einer Stelle findet).
 */

export { gehZu } from '$ui/route';
export { ladeZugang, lage } from '$ui/lage.svelte';

const ZUFALL_SCHLUESSEL = 'wortlaut.zufall';

export const zustand = $state({
  // Gestreut statt der Reihe nach vorsprechen. Aus, solange nichts anderes
  // dasteht: Der Text der Reihe nach ist der erwartete Fall.
  zufall: localStorage.getItem(ZUFALL_SCHLUESSEL) === 'true',
});

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
