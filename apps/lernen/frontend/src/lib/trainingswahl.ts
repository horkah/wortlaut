/**
 * Die Wahl beim Beauftragen - über einen Reiterwechsel hinweg.
 *
 * Wer Läufe zum Vergleich beauftragt, ändert zwischen zweien meist eine Achse
 * und sieht sich zwischendurch Kurven an. Die Wahl liegt deshalb im
 * `localStorage` - wie der Trainerschlüssel (`trainerschluessel.ts`); ohne
 * Speicher gilt die Vorgabe.
 *
 * Nur Bedienkomfort: Was bestellt wurde, steht im Auftrag des Laufs
 * (`wortlaut/laeufe.py`).
 */

const SCHLUESSEL = 'wortlaut.trainingswahl';

/** Die Achsen eines Auftrags, so wie die Seite sie hält. */
export type Trainingswahl = {
  grundmodell: string;
  methode: string;
  datensatz: string;
  auswahl: string;
  abschluss: string;
  augmentierung: string;
  dauer: string;
  tempowahl: string;
};

/** Die Vorgabe jeder Achse, wie in `wortlaut/laeufe.py`. */
export const VORGABE: Trainingswahl = {
  grundmodell: '',
  methode: 'lora',
  datensatz: 'original',
  auswahl: 'alle',
  abschluss: 'bester',
  augmentierung: 'keine',
  dauer: 'fest',
  tempowahl: 'aus',
};

export function trainingswahl(): Trainingswahl {
  try {
    const roh = localStorage.getItem(SCHLUESSEL);
    if (!roh) return { ...VORGABE };
    const gelesen = JSON.parse(roh) as Partial<Trainingswahl>;
    // Feld für Feld über die Vorgabe gelegt: Fehlende Achsen stehen auf ihrer
    // Vorgabe, unbekannte fallen weg.
    return {
      grundmodell: gelesen.grundmodell ?? VORGABE.grundmodell,
      methode: gelesen.methode ?? VORGABE.methode,
      datensatz: gelesen.datensatz ?? VORGABE.datensatz,
      auswahl: gelesen.auswahl ?? VORGABE.auswahl,
      abschluss: gelesen.abschluss ?? VORGABE.abschluss,
      augmentierung: gelesen.augmentierung ?? VORGABE.augmentierung,
      dauer: gelesen.dauer ?? VORGABE.dauer,
      tempowahl: gelesen.tempowahl ?? VORGABE.tempowahl,
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
