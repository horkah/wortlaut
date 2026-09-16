/**
 * Wer in diesem Browser ruft - dieselbe Frage, dieselbe Antwort, in jeder App.
 *
 * Gefragt wird der Server, und zwar bei jedem Start: Der Sprecher wird aus dem
 * vorgelegten Zugang **abgeleitet** und nirgends behauptet (siehe jeweils
 * `backend/deps.py`). Ein im Browser gemerkter Name könnte auf einen fremden
 * Korpus zeigen - genau der Fehlgriff, den das ausschließt. Aufbewahrt wird
 * allein der Zugang (`zugang.ts`).
 *
 * **Gefragt wird immer „hören", aus jeder App.** Der Zugang liegt einmal im
 * Browser (`zugang.ts`), also hat die Frage „wer ist das?" auch nur eine
 * Antwort - und geben kann sie nur „hören": Dort liegt der Korpus, dort steht
 * der Name, und dort werden alle drei Arten von Zugang erkannt.
 *
 * Das war einmal Sache jeder App, und genau daran ist es zerbrochen.
 * „schreiben" fragte seine eigene API, und die lässt mit gutem Grund nur einen
 * **Sprecherzugang** durch - sie spricht für einen Menschen und hat nichts zu
 * verwalten. Wer dort seinen Aufsichtstoken eintrug, bekam ihn abgewiesen,
 * obwohl er stimmte; in „hören" nahm ihn dasselbe Feld an. Zwei Wahrheiten
 * über denselben Token, je nachdem, welche Seite gerade offen war.
 *
 * „lernen" hatte das längst richtig und schrieb den Grund sogar dazu: „Eine
 * eigene Auskunft hätte eine zweite Wahrheit über denselben Menschen
 * ergeben." Jetzt steht der Weg einmal hier, und keine App wählt ihn mehr
 * selbst.
 */

import { ApiFehler, api } from './api';

/**
 * Die API von „hören" - sie liegt auf der Wurzel der gemeinsamen Domain
 * (`APPS` in `apps.ts`), also ist dieser Weg aus jeder App derselbe.
 */
const hoeren = api('/api');

/** Beim Server nachfragen, wer dieser Browser ist. */
export const werRuft = () => hoeren.anfrage<Wer>('/zugang');

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
  /**
   * Die Sprache des Profils - `null` für Verwaltung und Aufsicht, die für
   * niemanden sprechen. Sie kommt von hier und nicht aus einer Konstanten in
   * der Oberfläche: Am Profil steht sie, und am Profil hängt sie
   * (`wortlaut/sprachen.py`).
   */
  sprache: string | null;
}

/** Was davon im Zustand einer App steht. */
export interface Zugangsstand {
  art: Art;
  sprecher: string | null;
  name: string | null;
  sprache: string | null;
}

/**
 * Der Stand vor der ersten Antwort. Zum **Hineinstreuen** in den `$state` einer
 * App gedacht (`{ ...OFFEN }`) und nicht zum Verweisen darauf: Drei Apps, die
 * sich ein Objekt teilen, teilen sich auch dessen Änderungen.
 */
export const OFFEN: Zugangsstand = {
  art: 'unbekannt',
  sprecher: null,
  name: null,
  sprache: null,
};

/** Beim Server nachfragen, für wen dieser Browser eingestellt ist. */
export async function ermittleZugang(): Promise<Zugangsstand> {
  try {
    const wer = await werRuft();
    return { art: wer.art, sprecher: wer.sprecher_id, name: wer.name, sprache: wer.sprache };
  } catch (ursache) {
    // Ein abgewiesener Zugang ist kein Fehler, sondern ein fehlender Schritt;
    // alles andere (Server weg) sieht die Ansicht ohnehin an ihren Anfragen.
    return {
      ...OFFEN,
      art: ursache instanceof ApiFehler && ursache.status === 401 ? 'keiner' : 'unbekannt',
    };
  }
}
