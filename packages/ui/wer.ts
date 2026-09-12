/**
 * Wer in diesem Browser ruft - dieselbe Frage, dieselbe Antwort, in jeder App.
 *
 * Gefragt wird der Server, und zwar bei jedem Start: Der Sprecher wird aus dem
 * vorgelegten Zugang **abgeleitet** und nirgends behauptet (siehe jeweils
 * `backend/deps.py`). Ein im Browser gemerkter Name könnte auf einen fremden
 * Korpus zeigen - genau der Fehlgriff, den das ausschließt. Aufbewahrt wird
 * allein der Zugang (`zugang.ts`).
 *
 * Die Auswertung der Antwort stand dreimal da und war dreimal dieselbe, bis
 * auf eine Stelle: „schreiben" setzte `sprecher` fest, statt zu übernehmen,
 * was der Server geantwortet hatte. Es kam dasselbe heraus - sein `/api/zugang`
 * kennt keine andere Art -, aber es war eine zweite Regel für dieselbe Frage.
 *
 * Welchen Weg die Frage nimmt, bleibt Sache der App: „hören" fragt seine
 * eigene API, „lernen" ausdrücklich die von „hören" (dort liegt der Korpus).
 * Deshalb kommt `werRuft` als Argument herein und nicht als Import.
 */

import { ApiFehler } from './api';

/** Die drei, die der Server durchlässt; alles andere wird ein 401. */
export type Rufer = 'sprecher' | 'verwaltung' | 'aufsicht';

/**
 * Dazu die beiden Zustände, die es nur in der Oberfläche gibt: `unbekannt`,
 * solange die Antwort aussteht, und `keiner`, wenn der Server den Zugang
 * abweist. Beides ist kein Fehler, sondern ein Schritt, der noch fehlt.
 */
export type Art = Rufer | 'unbekannt' | 'keiner';

/** Was der Server auf `GET /api/zugang` antwortet. */
export interface Wer {
  art: Rufer;
  sprecher_id: string | null;
  name: string | null;
}

/** Was davon im Zustand einer App steht. */
export interface Zugangsstand {
  art: Art;
  sprecher: string | null;
  name: string | null;
}

/**
 * Der Stand vor der ersten Antwort. Zum **Hineinstreuen** in den `$state` einer
 * App gedacht (`{ ...OFFEN }`) und nicht zum Verweisen darauf: Drei Apps, die
 * sich ein Objekt teilen, teilen sich auch dessen Änderungen.
 */
export const OFFEN: Zugangsstand = { art: 'unbekannt', sprecher: null, name: null };

/** Beim Server nachfragen, für wen dieser Browser eingestellt ist. */
export async function ermittleZugang(werRuft: () => Promise<Wer>): Promise<Zugangsstand> {
  try {
    const wer = await werRuft();
    return { art: wer.art, sprecher: wer.sprecher_id, name: wer.name };
  } catch (ursache) {
    // Ein abgewiesener Zugang ist kein Fehler, sondern ein fehlender Schritt;
    // alles andere (Server weg) sieht die Ansicht ohnehin an ihren Anfragen.
    return {
      ...OFFEN,
      art: ursache instanceof ApiFehler && ursache.status === 401 ? 'keiner' : 'unbekannt',
    };
  }
}
