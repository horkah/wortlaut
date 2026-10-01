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
 * Die APIs von „lernen" und „schreiben" lassen nur Sprecherzugänge durch und
 * könnten Verwaltung und Aufsicht nicht erkennen.
 */

import { ApiFehler, api } from './api';
import { mitAllenSchluesseln, type Recht } from './schluessel.svelte';

/**
 * Die API von „hören" - sie liegt auf der Wurzel der gemeinsamen Domain
 * (`APPS` in `apps.ts`), also ist dieser Weg aus jeder App derselbe.
 */
const hoeren = api('/api');

/**
 * Beim Server nachfragen, wer dieser Browser ist - und was seine Schlüssel
 * öffnen. Die einzige Anfrage, an die beide Schlüssel gehen.
 */
export const werRuft = () =>
  hoeren.anfrage<Wer>('/zugang', { headers: mitAllenSchluesseln() });

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
  /** Training beauftragen, neu starten, Läufe samt Modell löschen, Fehlerprotokoll. */
  trainieren: Exclude<Recht, 'unbekannt'>;
  /** Zuschnitt und Editieren in „hören". */
  bearbeiten: Exclude<Recht, 'unbekannt'>;
}

/** Was davon im gemeinsamen Zustand steht (`lage.svelte.ts`). */
export interface Zugangsstand {
  art: Art;
  sprecher: string | null;
  name: string | null;
  sprache: string | null;
  trainieren: Recht;
  bearbeiten: Recht;
}

/**
 * Der Stand vor der ersten Antwort - und der nach einer Abweisung, bis auf
 * `art`. Hineingestreut in den gemeinsamen Zustand (`lage.svelte.ts`).
 */
export const OFFEN: Zugangsstand = {
  art: 'unbekannt',
  sprecher: null,
  name: null,
  sprache: null,
  trainieren: 'unbekannt',
  bearbeiten: 'unbekannt',
};

/** Beim Server nachfragen, für wen dieser Browser eingestellt ist. */
export async function ermittleZugang(): Promise<Zugangsstand> {
  try {
    const wer = await werRuft();
    return {
      art: wer.art,
      sprecher: wer.sprecher_id,
      name: wer.name,
      sprache: wer.sprache,
      trainieren: wer.trainieren,
      bearbeiten: wer.bearbeiten,
    };
  } catch (ursache) {
    // Ein abgewiesener Zugang ist kein Fehler, sondern ein fehlender Schritt;
    // alles andere (Server weg) sieht die Ansicht ohnehin an ihren Anfragen.
    return {
      ...OFFEN,
      art: ursache instanceof ApiFehler && ursache.status === 401 ? 'keiner' : 'unbekannt',
    };
  }
}
