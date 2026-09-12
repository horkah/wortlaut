/**
 * Die Route im Hash - derselbe Router in allen drei Apps.
 *
 * `#/aufnahme`, `#/training`, `#/ergebnis`: Das genügt für eine Handvoll
 * Ansichten je App und spart ein Routing-Paket samt Server-Konfiguration. Die
 * Entscheidung war in jeder App dieselbe, und die drei Zeilen dahinter waren
 * es ebenfalls - unterschieden hat sie nur, in welche Variable das Ergebnis
 * ging.
 *
 * Was hier **nicht** steht, ist die Route selbst: Sie gehört in den `$state`
 * der App, neben das, was diese App sonst noch teilt - die Diktiersitzung in
 * „schreiben", das Streuen in „hören". Ein zweiter Zustand daneben wäre eine
 * zweite Wahrheit darüber, welche Ansicht gerade dasteht. `folgeHash` reicht
 * stattdessen jede Änderung dorthin durch.
 */

/** Die Route, wie sie in der Adresse steht - ohne `#`, leer heißt `/`. */
export function routeAusHash(): string {
  return window.location.hash.replace(/^#/, '') || '/';
}

/** Zu einer Route gehen. Es ändert sich der Hash, die Seite lädt nicht neu. */
export function gehZu(route: string): void {
  window.location.hash = route;
}

/**
 * Jede Änderung der Adresse an den Zustand der App weiterreichen - auch die,
 * die vom Zurück-Knopf des Browsers kommt.
 */
export function folgeHash(uebernimm: (route: string) => void): void {
  window.addEventListener('hashchange', () => uebernimm(routeAusHash()));
}
