/**
 * Zeitpunkte und Zeitspannen, wie sie der Server schreibt, für Menschen
 * lesbar machen.
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

/**
 * Eine Zeitspanne in Sekunden, als Stunden, Minuten und Sekunden.
 *
 * **Warum keine Dezimalstunden.** Der Fortschritt stand hier lange als
 * „0,43 Stunden". Das ist richtig gerechnet und für die Zielperson (die
 * schlecht liest, Grundentscheidung 7) keine Auskunft: Niemand weiß aus dem
 * Stand, wie viele Minuten das sind, und niemand sollte es ausrechnen müssen,
 * um zu sehen, wie weit er heute gekommen ist. „25 min 48 s" beantwortet
 * dieselbe Frage ohne Umweg.
 *
 * **Warum höchstens zwei Einheiten.** Neben Stunden sind Sekunden Rauschen -
 * wer zwei Stunden Sprache gesammelt hat, interessiert sich nicht für die
 * achte davon. Die Regel ist deshalb: von der größten Einheit, die nicht null
 * ist, eine weitere hinunter, und eine glatte Null am Ende fällt weg
 * (`20 h`, nicht `20 h 0 min`).
 *
 * **Warum Abkürzungen und keine Wörter.** „2 Stunden 14 Minuten" liest sich
 * schöner, passt aber in keine Tabellenzelle - und dieselbe Angabe steht in
 * der Sprecherliste, in „Meine Daten" und im Fortschritt, wo sie überall
 * dieselbe sein soll. `h`, `min` und `s` versteht auch, wer den Rest nicht
 * liest.
 */
export function dauer(sekunden: number): string {
  // Gerundet, bevor gerechnet wird: Sonst zeigte eine Aufnahme von 59,6
  // Sekunden „59 s", die Summe zweier solcher aber „2 min" - und die beiden
  // Zahlen widersprächen einander um eine Sekunde, die es nie gab.
  const gesamt = Math.max(0, Math.round(sekunden));
  const stunden = Math.floor(gesamt / 3600);
  const minuten = Math.floor((gesamt % 3600) / 60);
  const rest = gesamt % 60;

  if (stunden) return minuten ? `${stunden} h ${minuten} min` : `${stunden} h`;
  if (minuten) return rest ? `${minuten} min ${rest} s` : `${minuten} min`;
  return `${rest} s`;
}
