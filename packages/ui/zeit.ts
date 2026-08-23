/**
 * Zeitpunkte, wie sie der Server schreibt, für Menschen lesbar machen.
 *
 * Der Server legt jeden Zeitstempel als ISO-8601 in UTC ab
 * (`db/models.py: jetzt()`, etwa `2026-08-23T02:57:00+00:00`). Wer nur die
 * ersten zehn Zeichen abschneidet, bekommt das Datum richtig und die Zeitzone
 * geschenkt - solange nur der Tag zählt, geht das gut.
 *
 * Sobald die Uhrzeit dazukommt, geht es nicht mehr gut: Eine Aufnahme um
 * 23:30 Uhr in Berlin steht in der Datenbank als 21:30 Uhr des Vortages, und
 * abgeschnitten liest sich das wie ein anderer Tag. Darum wird hier gerechnet
 * statt geschnitten - `Date` kennt den Versatz des Betrachters.
 */

const zwei = (zahl: number) => String(zahl).padStart(2, '0');

/** Nur der Tag, in der Zeitzone des Betrachters (`2026-08-23`). */
export function tag(zeitpunkt: string): string {
  const wann = new Date(zeitpunkt);
  if (Number.isNaN(wann.getTime())) return zeitpunkt;
  return `${wann.getFullYear()}-${zwei(wann.getMonth() + 1)}-${zwei(wann.getDate())}`;
}

/**
 * Tag und Uhrzeit, in der Zeitzone des Betrachters (`2026-08-23 04:57`).
 *
 * Für Sitzungen: Wer an einem Tag dreimal übt, sähe sonst dreimal dieselbe
 * Zeile und könnte sie nicht auseinanderhalten.
 */
export function tagUndZeit(zeitpunkt: string): string {
  const wann = new Date(zeitpunkt);
  if (Number.isNaN(wann.getTime())) return zeitpunkt;
  return `${tag(zeitpunkt)} ${zwei(wann.getHours())}:${zwei(wann.getMinutes())}`;
}
