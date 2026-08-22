/**
 * Was alle Ansichten teilen: die Route und wer hier gerade eingestellt ist.
 *
 * Die Route steht im Hash (`#/aufnahme`). Das genügt für vier Ansichten und
 * spart ein Routing-Paket samt Server-Konfiguration.
 *
 * Der Sprecher steht bewusst **nicht** mehr im `localStorage`. Er kommt vom
 * Server, der ihn aus dem vorgelegten Zugang ableitet: Ein gemerkter Wert
 * konnte auf einen fremden Korpus zeigen — genau der Fehlgriff, den dieser
 * Umbau ausschließt. Was der Browser aufbewahrt, ist allein der Zugang.
 */

import { ApiFehler, setzeZugang, werRuft } from './api';

const ZUFALL_SCHLUESSEL = 'wortlaut.zufall';

/**
 * Der Weg, auf dem ein Zugang in diesen Browser kommt: ein Link, einmal
 * geöffnet. Er steht im Hash und nicht in der Abfrage — ein Fragment geht nie
 * an den Server und landet damit in keinem Zugriffsprotokoll.
 */
const ZUGANG_ROUTE = '/zugang/';

function routeAusHash(): string {
  return window.location.hash.replace(/^#/, '') || '/';
}

export const zustand = $state({
  route: routeAusHash(),
  // Gestreut statt der Reihe nach vorsprechen. Aus, solange nichts anderes
  // dasteht: Der Text der Reihe nach ist der erwartete Fall.
  zufall: localStorage.getItem(ZUFALL_SCHLUESSEL) === 'true',
  // `unbekannt`, bis der Server geantwortet hat; `keiner`, wenn er den Zugang
  // abweist. Beides ist kein Fehler, sondern ein Zustand der Oberfläche.
  art: 'unbekannt' as 'unbekannt' | 'sprecher' | 'verwaltung' | 'keiner',
  sprecher: null as string | null,
  name: null as string | null,
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

/**
 * Einen Zugang aus dem Link übernehmen, falls einer darin steht.
 *
 * Der Eintrag im Verlauf wird dabei ersetzt statt ergänzt: Sonst stünde das
 * Geheimnis in der Adresszeile und im Zurück-Knopf.
 */
function nimmZugangAusLink(): void {
  const route = routeAusHash();
  if (!route.startsWith(ZUGANG_ROUTE)) return;
  setzeZugang(decodeURIComponent(route.slice(ZUGANG_ROUTE.length)));
  const { pathname, search } = window.location;
  window.history.replaceState(null, '', `${pathname}${search}#/`);
  zustand.route = '/';
}

/** Beim Server nachfragen, für wen dieser Browser eingestellt ist. */
export async function ladeZugang(): Promise<void> {
  nimmZugangAusLink();
  try {
    const wer = await werRuft();
    zustand.art = wer.art;
    zustand.sprecher = wer.sprecher_id;
    zustand.name = wer.name;
  } catch (ursache) {
    // Ein abgewiesener Zugang ist kein Fehler, sondern ein fehlender Schritt;
    // alles andere (Server weg) sieht die Ansicht ohnehin an ihren Anfragen.
    zustand.art = ursache instanceof ApiFehler && ursache.status === 401 ? 'keiner' : 'unbekannt';
    zustand.sprecher = null;
    zustand.name = null;
  }
}
