/**
 * Wann dieses Bündel gebaut wurde.
 *
 * Der Wert wird beim Bauen eingesetzt (`define` in der jeweiligen
 * `vite.config.ts`), steht also fest im ausgelieferten Bündel und kostet zur
 * Laufzeit nichts. In der Entwicklung ist es der Start des Vite-Servers.
 *
 * Wozu: Eine Single-Page-App sieht nach einem Ausrollen genauso aus wie
 * vorher. Ohne sichtbares Datum lässt sich „ist das schon die neue Fassung?"
 * nur am Netzwerk-Reiter des Browsers beantworten — mit Datum genügt ein Blick
 * an den Seitenfuß.
 */
declare const __BAUDATUM__: string;

/** Das Baudatum als ISO-Datum (`2026-08-22`). */
export const BAUDATUM: string = __BAUDATUM__;

/** Dasselbe Datum, wie man es hierzulande schreibt (`22.08.2026`). */
export function baudatumLesbar(): string {
  const teile = BAUDATUM.split('-');
  return teile.length === 3 ? `${teile[2]}.${teile[1]}.${teile[0]}` : BAUDATUM;
}
