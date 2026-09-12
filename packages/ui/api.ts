/**
 * Wie eine App mit ihrem Backend spricht - dieselbe Handvoll Zeilen für alle
 * drei.
 *
 * Eigen ist jeder App, **welche** Wege sie kennt und welche Formen darüber
 * gehen; das steht weiterhin in ihrem `lib/api.ts`. Wie eine Anfrage
 * hinausgeht, ist dagegen überall dasselbe: Der Zugang hängt im Kopf (siehe
 * `zugang.ts`), ein Fehlschlag wird zu einem `ApiFehler` mit Status und dem
 * Satz, den der Server dazu geschrieben hat, und aus einer geglückten Antwort
 * kommt JSON heraus - außer bei 204, wo nichts darin steht.
 *
 * Es stand dreimal da, einmal je App, und war schon auseinandergelaufen: Die
 * Zugangsprüfung von „lernen" wertete den `detail` des Servers nicht aus und
 * meldete „Fehler 401", wo „hören" beim selben Fehlschlag den Satz des Servers
 * zeigte. Zwei Meldungen für dieselbe Lage, und der Unterschied fällt nur dem
 * auf, der beide nacheinander liest.
 *
 * Unterschieden bleibt allein der **Ort**: „hören" liegt auf der Wurzel,
 * „lernen" unter `/lernen/`, „schreiben" unter `/schreiben/`. Den nennt jede
 * App einmal beim Aufruf von `api()` und nirgends sonst. Dass hier eine App
 * die API einer anderen anspricht, ist damit eine zweite Zeile und kein
 * zweiter Anlauf - „lernen" tut genau das, für die Zugangsprüfung und für den
 * Modellstand von „schreiben".
 */

import { mitZugang } from './zugang';

export class ApiFehler extends Error {
  constructor(
    readonly status: number,
    nachricht: string,
  ) {
    super(nachricht);
  }
}

/**
 * Ein Rumpf als JSON. `POST` ist der Regelfall; `PATCH` und `PUT` ändern nur
 * das Verb, nicht die Form - deshalb steht es hier als Parameter und nicht in
 * jedem Aufruf als dreizeiliges Objekt.
 */
export function alsJson(inhalt: unknown, methode = 'POST'): RequestInit {
  return {
    method: methode,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(inhalt),
  };
}

export interface Api {
  /**
   * Eine Anfrage mit Zugang; zurück kommt die rohe Antwort. Nicht alles hier
   * ist JSON: Texte und Sicherungsarchive gehen denselben Weg.
   */
  hole(pfad: string, optionen?: RequestInit): Promise<Response>;
  /** Dasselbe mit ausgepacktem JSON; ein 204 kommt als `undefined` zurück. */
  anfrage<T>(pfad: string, optionen?: RequestInit): Promise<T>;
}

/** Die API an einem Ort - `basis` ist ihm vorangestellt, etwa `/lernen/api`. */
export function api(basis: string): Api {
  async function hole(pfad: string, optionen: RequestInit = {}): Promise<Response> {
    const antwort = await fetch(`${basis}${pfad}`, {
      ...optionen,
      headers: mitZugang(optionen.headers),
    });
    if (!antwort.ok) {
      // FastAPI antwortet mit {"detail": …}; bei Netzfehlern bleibt der Status.
      const rumpf = await antwort.json().catch(() => null);
      throw new ApiFehler(antwort.status, rumpf?.detail ?? `Fehler ${antwort.status}`);
    }
    return antwort;
  }

  async function anfrage<T>(pfad: string, optionen: RequestInit = {}): Promise<T> {
    const antwort = await hole(pfad, optionen);
    return antwort.status === 204 ? (undefined as T) : ((await antwort.json()) as T);
  }

  return { hole, anfrage };
}
