/**
 * Was „Meine Daten", die Auswertung und „Editieren" über einen Ausflug in den
 * Editor teilen.
 *
 * **Die Stelle**: Seite der Liste, offene Karte, Lage im Fenster - damit die
 * Liste nach der Rückkehr dasteht wie vorher. Blättert der Editor zu einer
 * anderen Aufnahme, wird deren Karte die offene, und das Fenster sucht sie
 * statt der alten Lage.
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
import type { Listeneintrag } from './aufnahme';

export type Stelle = { seite: number; aufgeklappt: string | null; y: number | null };
export type Reihenfolge = { eintraege: Listeneintrag[]; proSeite: number };

const STELLE = 'wortlaut.meine-daten.stelle';
const REIHENFOLGE = 'wortlaut.editor.reihenfolge';

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

/** Beim Sprung in den Editor: wo die Liste steht und in welcher Reihenfolge. */
export function merke(stelle: Stelle, reihenfolge: Reihenfolge | null): void {
  schreibe(STELLE, stelle);
  if (reihenfolge) schreibe(REIHENFOLGE, reihenfolge);
  else {
    try {
      sessionStorage.removeItem(REIHENFOLGE);
    } catch {
      // Siehe oben.
    }
  }
}

/** Zurück in „Meine Daten": die Stelle, einmal - und die Reihenfolge gilt nicht mehr. */
export function nimmStelle(): Stelle | null {
  const stelle = lies<Stelle>(STELLE);
  try {
    sessionStorage.removeItem(STELLE);
    sessionStorage.removeItem(REIHENFOLGE);
  } catch {
    // Siehe oben.
  }
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
    y: null,
  } satisfies Stelle);
}
