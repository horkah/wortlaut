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
  loraZiele: string;
  loraRang: string;
  datensatz: string;
  auswahl: string;
  korrekturgewicht: string;
  selbsttraining: string;
  abschluss: string;
  augmentierung: string;
  dauer: string;
  steuerung: string;
  tempowahl: string;
};

/** Die Vorgabe jeder Achse, wie in `wortlaut/laeufe.py`. */
export const VORGABE: Trainingswahl = {
  grundmodell: '',
  methode: 'lora',
  loraZiele: 'qv',
  loraRang: '32',
  datensatz: 'original',
  auswahl: 'alle',
  korrekturgewicht: '0.5',
  selbsttraining: 'aus',
  abschluss: 'bester',
  augmentierung: 'keine',
  dauer: 'fest',
  steuerung: 'verlust',
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
      loraZiele: gelesen.loraZiele ?? VORGABE.loraZiele,
      loraRang: gelesen.loraRang ?? VORGABE.loraRang,
      datensatz: gelesen.datensatz ?? VORGABE.datensatz,
      auswahl: gelesen.auswahl ?? VORGABE.auswahl,
      korrekturgewicht: gelesen.korrekturgewicht ?? VORGABE.korrekturgewicht,
      selbsttraining: gelesen.selbsttraining ?? VORGABE.selbsttraining,
      abschluss: gelesen.abschluss ?? VORGABE.abschluss,
      augmentierung: gelesen.augmentierung ?? VORGABE.augmentierung,
      dauer: gelesen.dauer ?? VORGABE.dauer,
      steuerung: gelesen.steuerung ?? VORGABE.steuerung,
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
