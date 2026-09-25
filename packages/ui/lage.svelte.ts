/**
 * Welche Route offen ist und wer hier ruft - ein Zustand für alle drei Apps.
 *
 * Beides stand bis September 2026 in jeder App einzeln: dieselben Felder, in
 * den `$state` der App gestreut, dieselben vier Zeilen `ladeZugang`. Und weil
 * es drei Zustände waren, musste jede App dem gemeinsamen Rahmen einzeln
 * erzählen, wer angemeldet ist, welche Sprache er spricht, was er im Menü
 * sieht - und erzählte es jede ein wenig anders: „lernen" nannte die Aufsicht
 * gar nicht, „schreiben" nannte die Verwaltung „kein Zugang", und die Stimmen
 * vom Server bekam nur der Rahmen von „hören" gereicht.
 *
 * Jetzt liest der Rahmen selbst, und alles, was im Menü steht, liest mit ihm
 * dasselbe. Was eine App darüber hinaus teilt - die Diktiersitzung in
 * „schreiben", das Streuen in „hören" -, bleibt in ihrem `lib/zustand`.
 */

import { folgeHash, routeAusHash } from './route';
import { OFFEN, ermittleZugang, type Zugangsstand } from './wer';
import { nimmZugangAusLink } from './zugang';

export const lage = $state<Zugangsstand & { route: string }>({
  route: routeAusHash(),
  ...OFFEN,
});

folgeHash((route) => (lage.route = route));

/** Beim Server nachfragen, für wen dieser Browser eingestellt ist. */
export async function ladeZugang(): Promise<void> {
  // Steckte einer im Link, liegt er jetzt im Browser und die Adresse ist
  // wieder sauber (siehe `zugang.ts`).
  if (nimmZugangAusLink(routeAusHash())) lage.route = '/';
  Object.assign(lage, await ermittleZugang());
}
