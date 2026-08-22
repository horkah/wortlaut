/**
 * Was alle Ansichten teilen: die Route, die laufende Diktiersitzung und der
 * Modellstand.
 *
 * Die Route steht im Hash (`#/text`). Das genügt für zwei Ansichten und spart
 * ein Routing-Paket samt Server-Konfiguration.
 *
 * Die Sitzung liegt zusätzlich im `sessionStorage`: Ein versehentliches
 * Neuladen soll den gesprochenen Text nicht verlieren, ein neuer Tab dagegen
 * mit einem leeren Blatt anfangen.
 *
 * Der Modellstand steht hier und nicht nur lokal in `App.svelte`, weil ihn
 * zwei Stellen brauchen: die Kopfzeile den Sprecher (den diese Instanz fest
 * führt, siehe `Modell.sprecher_id`), die Aufnahmeansicht die Beschriftung
 * daneben dem Aufnahmeknopf.
 */
import { modell, sitzungHolen, type Modell, type Sitzung } from './api';

const SITZUNG_SCHLUESSEL = 'wortlaut.diktat';

function routeAusHash(): string {
  return window.location.hash.replace(/^#/, '') || '/';
}

export const zustand = $state({
  route: routeAusHash(),
  sitzung: null as Sitzung | null,
  modellstand: null as Modell | null,
});

window.addEventListener('hashchange', () => {
  zustand.route = routeAusHash();
});

export function gehZu(route: string): void {
  window.location.hash = route;
}

/** Ohne Auskunft bleibt der Modellstand leer — dann zeigen Kopfzeile und
 *  Aufnahmeansicht schlicht nichts an, statt einen Fehler vorzutäuschen. */
export async function ladeModellstand(): Promise<void> {
  try {
    zustand.modellstand = await modell();
  } catch {
    zustand.modellstand = null;
  }
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
