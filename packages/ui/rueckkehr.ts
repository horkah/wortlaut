/**
 * Was „Meine Daten", die Auswertung und „Editieren" über einen Ausflug in den
 * Editor teilen.
 *
 * **Die Stelle**: Seite der Liste und offene Karte - damit die Liste nach
 * der Rückkehr dasteht wie vorher; die Lage im Fenster merkt sich jede
 * Ansicht selbst (`fensterlage.ts`). Blättert der Editor zu einer anderen
 * Aufnahme, wird deren Karte die offene, und das Fenster sucht sie
 * (`suchen`) statt der alten Lage.
 *
 * **Der Rückweg**: wohin „Zurück" im Editor führt - nach „Meine Daten" oder
 * in die Auswertung von „lernen", je nachdem, woher der Stift kam.
 *
 * **Die Reihenfolge**: die Liste, wie sie beim Öffnen des Editors sortiert
 * war, eingefroren. Der Editor blättert darin; erst „Meine Daten" sortiert
 * neu - wichtig beim Sortieren nach der letzten Änderung, die jedes
 * Speichern verschiebt.
 *
 * Beides im Speicher dieses Reiters, nicht über das Schließen hinaus. Ohne
 * Speicher beginnt die Liste oben und der Editor blättert nicht - kein
 * Fehlerfall.
 */
import { AUSWERTUNG_URL, MEINE_DATEN_PFAD, MENUE_TEXT } from './apps';
import type { Listeneintrag } from './aufnahme';

export type Stelle = { seite: number; aufgeklappt: string | null; suchen: boolean };
export type Reihenfolge = { eintraege: Listeneintrag[]; proSeite: number };

const STELLE = 'wortlaut.meine-daten.stelle';
const REIHENFOLGE = 'wortlaut.editor.reihenfolge';
const RUECKWEG = 'wortlaut.editor.rueckweg';

/**
 * Wohin „Zurück" führt und wie der Knopf es nennt. `ziel` ist eine Route von
 * „hören" oder, in eine andere App, deren volle Adresse samt `#`.
 */
export type Rueckweg = { text: string; ziel: string };

export const NACH_MEINEN_DATEN: Rueckweg = {
  text: MENUE_TEXT[MEINE_DATEN_PFAD],
  ziel: MEINE_DATEN_PFAD,
};

export const IN_DIE_AUSWERTUNG: Rueckweg = { text: 'Auswertung', ziel: AUSWERTUNG_URL };

function lies<T>(schluessel: string): T | null {
  try {
    const roh = sessionStorage.getItem(schluessel);
    return roh ? (JSON.parse(roh) as T) : null;
  } catch {
    return null;
  }
}

function schreibe(schluessel: string, wert: unknown): void {
  try {
    sessionStorage.setItem(schluessel, JSON.stringify(wert));
  } catch {
    // Siehe oben.
  }
}

/**
 * Beim Sprung in den Editor: wo die Liste steht, in welcher Reihenfolge, und
 * wohin es zurückgeht. Ohne Liste (aus der Auswertung) blättert der Editor nicht.
 */
export function merke(
  stelle: Stelle | null,
  reihenfolge: Reihenfolge | null,
  rueckweg: Rueckweg,
): void {
  if (stelle) schreibe(STELLE, stelle);
  else vergiss(STELLE);
  if (reihenfolge) schreibe(REIHENFOLGE, reihenfolge);
  else vergiss(REIHENFOLGE);
  schreibe(RUECKWEG, rueckweg);
}

function vergiss(schluessel: string): void {
  try {
    sessionStorage.removeItem(schluessel);
  } catch {
    // Siehe oben.
  }
}

/** Wohin „Zurück" im Editor führt - ohne Angabe nach „Meine Daten". */
export function rueckweg(): Rueckweg {
  return lies<Rueckweg>(RUECKWEG) ?? NACH_MEINEN_DATEN;
}

/** Zurück in „Meine Daten": die Stelle, einmal - und die Reihenfolge gilt nicht mehr. */
export function nimmStelle(): Stelle | null {
  const stelle = lies<Stelle>(STELLE);
  vergiss(STELLE);
  vergiss(REIHENFOLGE);
  return stelle;
}

/** Die eingefrorene Reihenfolge, solange der Editor offen ist. */
export function reihenfolge(): Reihenfolge | null {
  return lies<Reihenfolge>(REIHENFOLGE);
}

/** Der Editor ist bei einer anderen Aufnahme: Deren Karte steht nach der Rückkehr offen. */
export function wechsleZu(kennung: string): void {
  const folge = reihenfolge();
  const stelle = lies<Stelle>(STELLE);
  if (!folge || !stelle) return;
  const nummer = folge.eintraege.findIndex((eintrag) => eintrag.id === kennung);
  if (nummer < 0) return;
  schreibe(STELLE, {
    seite: Math.floor(nummer / folge.proSeite) + 1,
    aufgeklappt: kennung,
    suchen: true,
  } satisfies Stelle);
}
