/**
 * Welche Route offen ist und wer hier ruft - ein Zustand für alle drei Apps.
 *
 * Der Rahmen und alles im Menü lesen von hier. Was eine App darüber hinaus
 * teilt - die Diktiersitzung in „schreiben", das Streuen in „hören" -, steht
 * in ihrem `lib/zustand`.
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
