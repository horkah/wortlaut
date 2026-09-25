/**
 * Was nur „schreiben" teilt: die laufende Diktiersitzung und den Modellstand.
 *
 * Route und Zugang sind in jeder App dieselbe Sache und stehen deshalb in
 * `$ui/lage.svelte`. Gefragt wird mit demselben Zugang wie in „hören": ein
 * persönlicher Link, einmal geöffnet - gleich in welcher der Apps -, meldet in
 * allen an (siehe `$ui/zugang`). Ohne gültigen Zugang gibt es nichts zu
 * diktieren, und die Oberfläche sagt das, statt an einer Wand aus 401ern zu
 * scheitern.
 *
 * Die Sitzung liegt zusätzlich im `sessionStorage`: Ein versehentliches
 * Neuladen soll den gesprochenen Text nicht verlieren, ein neuer Tab dagegen
 * mit einem leeren Blatt anfangen.
 *
 * Der Modellstand steht hier und nicht nur lokal in `App.svelte`, weil ihn
 * zwei Stellen brauchen: die Kopfzeile die Beschriftung, die Aufnahmeansicht
 * dieselbe neben dem Aufnahmeknopf. Wessen Stand es ist, entscheidet der
 * Zugang: Jeder Sprecher läuft auf seinem eigenen Modell.
 */
import { modell, sitzungHolen, type Modell, type Sitzung } from './api';

export { gehZu } from '$ui/route';
export { lage } from '$ui/lage.svelte';

const SITZUNG_SCHLUESSEL = 'wortlaut.diktat';

export const zustand = $state({
  sitzung: null as Sitzung | null,
  modellstand: null as Modell | null,
});

/** Ohne Auskunft bleibt der Modellstand leer - dann zeigen Kopfzeile und
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
 * Ist sie fort oder schon bestätigt, wird nichts wiederhergestellt - dann
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
