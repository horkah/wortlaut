/**
 * Einen Ausschnitt einer Audiodatei abspielen, ohne ihn zu schneiden.
 *
 * Gebraucht vom Zuschnitt in „hören": Neben dem Knopf für die ganze Aufnahme
 * steht einer für das, was nach dem Schnitt übrig bliebe - und der muss
 * antworten, **bevor** irgendetwas geschrieben ist. Sonst wäre die Reihenfolge
 * umgekehrt: erst schreiben, dann hören, ob es richtig war.
 *
 * **Warum das keine vorläufige Datei auf dem Server braucht.** Der Browser hat
 * die Aufnahme ohnehin geladen, sobald jemand sie einmal anhört; ein Ausschnitt
 * daraus sind zwei Zahlen an `start()`. Vorläufige Dateien auf dem Server
 * wären dagegen Stimmaufnahmen mit ungeklärter Lebensdauer - jemand schiebt
 * eine Linie, bricht ab, schließt den Reiter, und die Datei liegt da. Für ein
 * Ergebnis, das ohne sie schneller da ist (siehe `docs/datenschutz.md`).
 *
 * **Warum Web Audio und nicht ein `<audio>`-Element.** Ein Element spielt von
 * einer Zeitmarke, aber es hört nicht an einer auf; dafür müsste ein Zeitgeber
 * mitlaufen und es anhalten, und der trifft auf einige Zehntel genau. Hier ist
 * das Ende ein Argument des Aufrufs und sitzt auf dem Abtastwert.
 *
 * Es spielt immer nur **eines**: Zwei Aufnahmen gleichzeitig sind kein Vergleich,
 * sondern Lärm. Ein neuer Aufruf beendet den vorigen.
 */

let werk: AudioContext | null = null;
let laeuft: AudioBufferSourceNode | null = null;

// Dekodiert wird je Aufnahme einmal. Das Ergebnis ist ein Vielfaches der
// Datei groß (float statt 16 bit), deshalb behält dieser Speicher nur, was
// auf einer Seite steht - wer weiterblättert, gibt ihn frei (`vergiss`).
const puffer = new Map<string, AudioBuffer>();

function kontext(): AudioContext {
  // Erst beim ersten Druck: Ein AudioContext, der vor einer Nutzereingabe
  // entsteht, startet in manchen Browsern gesperrt und bleibt es.
  werk ??= new AudioContext();
  return werk;
}

/** Was gerade läuft, anhalten. Läuft nichts, passiert nichts. */
export function stoppe(): void {
  if (!laeuft) return;
  // `onended` abhängen, bevor gestoppt wird: Sonst meldete der alte Knoten das
  // Ende, nachdem der neue schon spielt, und die Anzeige stünde auf „still".
  laeuft.onended = null;
  laeuft.stop();
  laeuft = null;
}

/**
 * Den Bereich [von, bis) einer Audiodatei abspielen.
 *
 * `schluessel` ist die Kennung, unter der die dekodierte Fassung liegen
 * bleibt - dieselbe Aufnahme wird nicht zweimal dekodiert, auch nicht, wenn
 * jemand den Ausschnitt fünfmal nacheinander hört.
 *
 * `fertig` meldet das Ende, damit die Ansicht ihren Knopf zurückstellen kann.
 * Es kommt nicht, wenn ein neuer Aufruf diesen hier beendet hat - dann ist
 * schon der nächste dran, und zwei Meldungen über einen Wechsel wären eine zu
 * viel.
 */
export async function spiele(
  schluessel: string,
  datei: Blob,
  von: number,
  bis: number,
  fertig?: () => void,
): Promise<void> {
  stoppe();
  const werkzeug = kontext();
  // Auf manchen Systemen steht der Kontext nach längerem Nichtstun still.
  if (werkzeug.state === 'suspended') await werkzeug.resume();

  let inhalt = puffer.get(schluessel);
  if (!inhalt) {
    inhalt = await werkzeug.decodeAudioData(await datei.arrayBuffer());
    puffer.set(schluessel, inhalt);
  }

  const anfang = Math.min(Math.max(von, 0), inhalt.duration);
  const laenge = Math.min(Math.max(bis, anfang), inhalt.duration) - anfang;
  if (laenge <= 0) return;

  const quelle = werkzeug.createBufferSource();
  quelle.buffer = inhalt;
  quelle.connect(werkzeug.destination);
  quelle.onended = () => {
    if (laeuft === quelle) laeuft = null;
    fertig?.();
  };
  laeuft = quelle;
  quelle.start(0, anfang, laenge);
}

/**
 * Dekodierte Aufnahmen freigeben - beim Blättern und beim Verlassen.
 *
 * Ohne Namen alles. Eine Seite von zehn Aufnahmen zu je acht Sekunden sind
 * gut fünf Megabyte im Speicher; über hundert Seiten wäre das der Grund,
 * warum der Reiter irgendwann hakt.
 */
export function vergiss(schluessel?: string): void {
  if (schluessel) puffer.delete(schluessel);
  else puffer.clear();
}
