/**
 * Was alle Ansichten teilen: die Route und die laufende Diktiersitzung.
 *
 * Die Route steht im Hash (`#/text`). Das genügt für zwei Ansichten und spart
 * ein Routing-Paket samt Server-Konfiguration.
 *
 * Die Sitzung liegt zusätzlich im `sessionStorage`: Ein versehentliches
 * Neuladen soll den gesprochenen Text nicht verlieren, ein neuer Tab dagegen
 * mit einem leeren Blatt anfangen.
 */
import { sitzungHolen, type Sitzung } from './api';

const SITZUNG_SCHLUESSEL = 'wortlaut.diktat';

function routeAusHash(): string {
  return window.location.hash.replace(/^#/, '') || '/';
}

export const zustand = $state({
  route: routeAusHash(),
  sitzung: null as Sitzung | null,
});

window.addEventListener('hashchange', () => {
  zustand.route = routeAusHash();
});

export function gehZu(route: string): void {
  window.location.hash = route;
}

/** Die Sitzung übernehmen, wie der Server sie zuletzt gesehen hat. */
export function setzeSitzung(sitzung: Sitzung | null): void {
  zustand.sitzung = sitzung;
  if (sitzung) sessionStorage.setItem(SITZUNG_SCHLUESSEL, sitzung.id);
  else sessionStorage.removeItem(SITZUNG_SCHLUESSEL);
}

/**
 * Nach einem Neuladen die begonnene Sitzung zurückholen.
 *
 * Ist sie fort oder schon bestätigt, wird nichts wiederhergestellt — dann
 * fängt die App mit einem leeren Blatt an, was hier das Richtige ist.
 */
export async function stelleSitzungWiederHer(): Promise<void> {
  const kennung = sessionStorage.getItem(SITZUNG_SCHLUESSEL);
  if (!kennung || zustand.sitzung) return;
  try {
    const sitzung = await sitzungHolen(kennung);
    if (sitzung.status === 'offen') zustand.sitzung = sitzung;
    else sessionStorage.removeItem(SITZUNG_SCHLUESSEL);
  } catch {
    sessionStorage.removeItem(SITZUNG_SCHLUESSEL);
  }
}
