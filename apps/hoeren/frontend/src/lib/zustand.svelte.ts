/**
 * Zwei Dinge, die alle Ansichten teilen: die Route und der gewählte Sprecher.
 *
 * Die Route steht im Hash (`#/aufnahme`). Das genügt für vier Ansichten und
 * spart ein Routing-Paket samt Server-Konfiguration.
 */

const SPRECHER_SCHLUESSEL = 'wortlaut.sprecher';
const ZUFALL_SCHLUESSEL = 'wortlaut.zufall';

function routeAusHash(): string {
  return window.location.hash.replace(/^#/, '') || '/';
}

export const zustand = $state({
  route: routeAusHash(),
  sprecher: localStorage.getItem(SPRECHER_SCHLUESSEL),
  // Gestreut statt der Reihe nach vorsprechen. Aus, solange nichts anderes
  // dasteht: Der Text der Reihe nach ist der erwartete Fall.
  zufall: localStorage.getItem(ZUFALL_SCHLUESSEL) === 'true',
});

window.addEventListener('hashchange', () => {
  zustand.route = routeAusHash();
});

export function gehZu(route: string): void {
  window.location.hash = route;
}

export function setzeZufall(an: boolean): void {
  zustand.zufall = an;
  localStorage.setItem(ZUFALL_SCHLUESSEL, String(an));
}

export function waehleSprecher(id: string | null): void {
  zustand.sprecher = id;
  if (id) localStorage.setItem(SPRECHER_SCHLUESSEL, id);
  else localStorage.removeItem(SPRECHER_SCHLUESSEL);
}
