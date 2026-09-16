/**
 * Wann dieses Bündel gebaut wurde.
 *
 * Der Wert wird beim Bauen eingesetzt (`define` in der jeweiligen
 * `vite.config.ts`), steht also fest im ausgelieferten Bündel und kostet zur
 * Laufzeit nichts. In der Entwicklung ist es der Start des Vite-Servers.
 *
 * Wozu: Eine Single-Page-App sieht nach einem Ausrollen genauso aus wie
 * vorher. Ohne sichtbares Datum lässt sich „ist das schon die neue Fassung?"
 * nur am Netzwerk-Reiter des Browsers beantworten - mit Datum genügt ein Blick
 * an den Seitenfuß.
 */
declare const __BAUDATUM__: string;

/** Das Baudatum als ISO-Zeitstempel (`2026-08-22T14:03:00.000Z`). */
export const BAUDATUM: string = __BAUDATUM__;

/**
 * Ein ISO-Zeitstempel, wie man ihn hierzulande schreibt (`22.08.2026, 14:03`).
 *
 * Nimmt den Wert entgegen, statt ihn sich zu holen: Der Seitenfuß zeigt in
 * erster Linie den Stand, den der **Server** meldet (`Fusszeile.svelte`), und
 * nur ersatzweise den aus diesem Bündel.
 */
export function lesbar(roh: string): string {
  const datum = new Date(roh);
  if (Number.isNaN(datum.getTime())) return roh;
  const tag = String(datum.getDate()).padStart(2, '0');
  const monat = String(datum.getMonth() + 1).padStart(2, '0');
  const stunde = String(datum.getHours()).padStart(2, '0');
  const minute = String(datum.getMinutes()).padStart(2, '0');
  return `${tag}.${monat}.${datum.getFullYear()}, ${stunde}:${minute}`;
}

/** Das Baudatum dieses Bündels, lesbar geschrieben. */
export function baudatumLesbar(): string {
  return lesbar(BAUDATUM);
}
