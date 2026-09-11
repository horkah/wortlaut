/**
 * Zwei Texte nebeneinandergelegt: was gleich blieb, was fehlt, was dazukam.
 *
 * Gebraucht für die Auswertung („hören"): Dort steht die Vorlage neben dem,
 * was ein Modell daraus gehört hat, und der Unterschied ist die eigentliche
 * Aussage. Ihn als zwei Absätze untereinander zu zeigen hieße, das Vergleichen
 * dem Auge zu überlassen - bei „Häuser" gegen „Heuser" verliert das Auge.
 *
 * Verglichen wird auf **Zeichen** und nicht auf Wörtern. Ein Wortvergleich
 * markierte „Heuser" als ganz falsch, obwohl ein Buchstabe danebenliegt; erst
 * die Zeichenebene zeigt, ob ein Modell den Sprecher missverstanden oder nur
 * die Endung verschluckt hat. Das ist auch die Form, in der Textverarbeitungen
 * Änderungen nachverfolgen.
 *
 * Das Verfahren ist die längste gemeinsame Teilfolge - dasselbe, auf dem `diff`
 * beruht. Sie kostet Platz im Quadrat der Länge; bei einer Sprecheinheit von
 * ein paar Sätzen ist das nichts. Für den Fall, dass doch einmal ein langer
 * Text hier landet (ein Modell, das ins Fabulieren gerät), gibt es die Grenze
 * unten: Darüber wird auf Wörter umgeschaltet, was gröber ist, aber nicht
 * minutenlang rechnet.
 */

export type Art =
  /** In beiden Texten, unverändert. */
  | 'gleich'
  /** Steht in der Vorlage, fehlt in der Erkennung. */
  | 'weg'
  /** Steht in der Erkennung, nicht in der Vorlage. */
  | 'neu';

export interface Stueck {
  art: Art;
  text: string;
}

/**
 * Ab wann auf Wörter umgeschaltet wird. Vier Millionen Zellen sind für einen
 * Browser noch eine Sache von Millisekunden; das Hundertfache wäre es nicht.
 */
const ZELLENGRENZE = 4_000_000;

/**
 * In Zeichen zerlegen, aber in echte: `Array.from` geht nach Codepunkten und
 * zerreißt damit weder Emoji noch zusammengesetzte Umlaute in zwei Hälften,
 * die einzeln nichts bedeuten.
 */
function zeichen(text: string): string[] {
  return Array.from(text);
}

/**
 * In Wörter zerlegen - jedes mit seinem folgenden Leerraum, damit sich der
 * Text aus den Teilen wieder lückenlos zusammensetzen lässt.
 */
function woerter(text: string): string[] {
  return text.match(/\S+\s*/g) ?? [];
}

/** Zusammenhängendes zusammenfassen: aus vielen Zeichen wird ein Stück. */
function fasse_zusammen(stuecke: Stueck[]): Stueck[] {
  const gefasst: Stueck[] = [];
  for (const stueck of stuecke) {
    const letztes = gefasst[gefasst.length - 1];
    if (letztes && letztes.art === stueck.art) letztes.text += stueck.text;
    else gefasst.push({ ...stueck });
  }
  return gefasst.filter((stueck) => stueck.text !== '');
}

function vergleiche_teile(vorher: string[], nachher: string[]): Stueck[] {
  const n = vorher.length;
  const m = nachher.length;
  if (n === 0) return nachher.length ? [{ art: 'neu', text: nachher.join('') }] : [];
  if (m === 0) return [{ art: 'weg', text: vorher.join('') }];

  // Länge der längsten gemeinsamen Teilfolge ab (i, j), von hinten aufgebaut.
  const breite = m + 1;
  const tafel = new Int32Array((n + 1) * breite);
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      tafel[i * breite + j] =
        vorher[i] === nachher[j]
          ? tafel[(i + 1) * breite + j + 1] + 1
          : Math.max(tafel[(i + 1) * breite + j], tafel[i * breite + j + 1]);
    }
  }

  // Vorwärts durchlaufen und dabei aufschreiben, was passiert ist.
  const stuecke: Stueck[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (vorher[i] === nachher[j]) {
      stuecke.push({ art: 'gleich', text: vorher[i] });
      i++;
      j++;
    } else if (tafel[(i + 1) * breite + j] >= tafel[i * breite + j + 1]) {
      // Bei Gleichstand zuerst das Gestrichene: Ein ersetztes Wort liest sich
      // als „alt durchgestrichen, neu dahinter" und nicht andersherum - so
      // zeigt es auch eine Textverarbeitung.
      stuecke.push({ art: 'weg', text: vorher[i] });
      i++;
    } else {
      stuecke.push({ art: 'neu', text: nachher[j] });
      j++;
    }
  }
  while (i < n) stuecke.push({ art: 'weg', text: vorher[i++] });
  while (j < m) stuecke.push({ art: 'neu', text: nachher[j++] });

  return fasse_zusammen(stuecke);
}

/**
 * Vorlage gegen Erkennung. `vorher` ist die Vorlage, `nachher` das, was ein
 * Modell daraus gemacht hat.
 */
export function vergleiche(vorher: string, nachher: string): Stueck[] {
  const alsZeichen = [zeichen(vorher), zeichen(nachher)] as const;
  if (alsZeichen[0].length * alsZeichen[1].length <= ZELLENGRENZE) {
    return vergleiche_teile(alsZeichen[0], alsZeichen[1]);
  }
  return vergleiche_teile(woerter(vorher), woerter(nachher));
}

/** Wie viele Zeichen unverändert blieben - für eine Zeile Zusammenfassung. */
export function gleichanteil(stuecke: Stueck[]): number {
  let gleich = 0;
  let gesamt = 0;
  for (const stueck of stuecke) {
    const laenge = Array.from(stueck.text).length;
    gesamt += laenge;
    if (stueck.art === 'gleich') gleich += laenge;
  }
  return gesamt ? gleich / gesamt : 1;
}
