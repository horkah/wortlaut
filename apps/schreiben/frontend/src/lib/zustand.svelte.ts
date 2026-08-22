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
 * zwei Stellen brauchen: die Kopfzeile die Beschriftung, die Aufnahmeansicht
 * dieselbe neben dem Aufnahmeknopf. Wessen Stand es ist, entscheidet der
 * Zugang: Jeder Sprecher läuft auf seinem eigenen Modell.
 *
 * Wer hier ruft, steht ebenfalls hier — abgeleitet vom Server aus dem
 * vorgelegten Zugang, nicht gemerkt. Ohne gültigen Zugang gibt es nichts zu
 * diktieren, und die Oberfläche sagt das, statt an einer Wand aus 401ern zu
 * scheitern.
 */
import { nimmZugangAusLink } from '$ui/zugang';
import { ApiFehler, modell, sitzungHolen, werRuft, type Modell, type Sitzung } from './api';

const SITZUNG_SCHLUESSEL = 'wortlaut.diktat';

function routeAusHash(): string {
  return window.location.hash.replace(/^#/, '') || '/';
}

export const zustand = $state({
  route: routeAusHash(),
  sitzung: null as Sitzung | null,
  modellstand: null as Modell | null,
  // `unbekannt`, bis der Server geantwortet hat; `keiner`, wenn er den Zugang
  // abweist. Beides ist kein Fehler, sondern ein Zustand der Oberfläche.
  art: 'unbekannt' as 'unbekannt' | 'sprecher' | 'keiner',
  sprecher: null as string | null,
  name: null as string | null,
});

window.addEventListener('hashchange', () => {
  zustand.route = routeAusHash();
});

export function gehZu(route: string): void {
  window.location.hash = route;
}

/**
 * Beim Server nachfragen, für wen dieser Browser eingestellt ist.
 *
 * Derselbe Weg wie in „hören", und mit demselben Zugang: Ein persönlicher
 * Link, einmal geöffnet — gleich in welcher der beiden Apps —, meldet in
 * beiden an (siehe `$ui/zugang`).
 */
export async function ladeZugang(): Promise<void> {
  if (nimmZugangAusLink(routeAusHash())) zustand.route = '/';
  try {
    const wer = await werRuft();
    zustand.art = 'sprecher';
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
