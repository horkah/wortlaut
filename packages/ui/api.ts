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
 * Einmal für alle Apps; unterschieden ist nur der Ort („hören" auf der
 * Wurzel, `/lernen/`, `/schreiben/`), den jede App beim Aufruf von `api()`
 * nennt. Die API einer anderen App anzusprechen ist so eine zweite Zeile -
 * „lernen" fragt „hören" und „schreiben".
 */

import { mitZugang } from './zugang';

/** Was ein Fehlschlag zu sagen hat - der Satz des Servers, sonst der Fehler selbst. */
export function fehlertext(ursache: unknown): string {
  return ursache instanceof Error ? ursache.message : String(ursache);
}

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
