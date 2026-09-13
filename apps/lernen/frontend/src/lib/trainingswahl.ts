/**
 * Die Wahl beim Beauftragen - über einen Reiterwechsel hinweg.
 *
 * Sechs Achsen hat ein Auftrag inzwischen: Grundmodell, Methode, Datensatz,
 * Abschluss, Augmentierung, Dauer. Wer vier Läufe hintereinander beauftragt,
 * um sie zu vergleichen, ändert zwischen zweien davon genau eine - und
 * zwischendurch sieht er sich die Kurven des vorigen an. Bis September 2026
 * stand nach der Rückkehr alles wieder auf der Vorgabe, und man fing von vorn
 * an zu klicken.
 *
 * Deshalb liegt die Wahl im `localStorage`, unter demselben Vorbehalt wie der
 * Trainerschlüssel nebenan (`trainerschluessel.ts`): Ein Browser mit
 * gesperrtem Speicher ist kein Fehlerfall, dann gilt eben die Vorgabe.
 *
 * **Was hier nicht liegt: das Ergebnis.** Dies ist ein Bedienkomfort und keine
 * zweite Wahrheit über einen Lauf. Was wirklich bestellt wurde, steht im
 * Auftrag des Laufs und nirgends sonst (`wortlaut/laeufe.py`) - diese Datei
 * merkt sich nur, wie die Knöpfe zuletzt standen.
 */

const SCHLUESSEL = 'wortlaut.trainingswahl';

/** Die Achsen eines Auftrags, so wie die Seite sie hält. */
export type Trainingswahl = {
  grundmodell: string;
  methode: string;
  datensatz: string;
  abschluss: string;
  augmentierung: string;
  dauer: string;
};

/**
 * Die Vorgabe - und zwar genau das, was dieses Projekt vor jeder dieser Achsen
 * gerechnet hat. Wer nichts wählt, bekommt das Verfahren von damals.
 */
export const VORGABE: Trainingswahl = {
  grundmodell: '',
  methode: 'lora',
  datensatz: 'original',
  abschluss: 'bester',
  augmentierung: 'keine',
  dauer: 'fest',
};

export function trainingswahl(): Trainingswahl {
  try {
    const roh = localStorage.getItem(SCHLUESSEL);
    if (!roh) return { ...VORGABE };
    const gelesen = JSON.parse(roh) as Partial<Trainingswahl>;
    // Feld für Feld über die Vorgabe gelegt: Eine Achse, die es beim letzten
    // Besuch noch nicht gab, steht damit auf ihrer Vorgabe statt auf
    // `undefined` - und eine, die es nicht mehr gibt, fällt weg.
    return {
      grundmodell: gelesen.grundmodell ?? VORGABE.grundmodell,
      methode: gelesen.methode ?? VORGABE.methode,
      datensatz: gelesen.datensatz ?? VORGABE.datensatz,
      abschluss: gelesen.abschluss ?? VORGABE.abschluss,
      augmentierung: gelesen.augmentierung ?? VORGABE.augmentierung,
      dauer: gelesen.dauer ?? VORGABE.dauer,
    };
  } catch {
    // Gesperrter Speicher oder kaputtes JSON - beides kein Fehlerfall.
    return { ...VORGABE };
  }
}

export function setzeTrainingswahl(wahl: Trainingswahl): void {
  try {
    localStorage.setItem(SCHLUESSEL, JSON.stringify(wahl));
  } catch {
    /* siehe oben */
  }
}
