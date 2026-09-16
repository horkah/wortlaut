/**
 * Den Text an eine andere App weitergeben - über das Teilen-Blatt des Geräts.
 *
 * **Warum das mehr ist als Kopieren.** Kopieren ist der halbe Weg: Der Text
 * liegt danach in der Zwischenablage, und der Mensch muss die Ziel-App selbst
 * öffnen, das richtige Feld finden, hineintippen, halten, „Einfügen" treffen.
 * Das Teilen-Blatt macht daraus einen Schritt - antippen, WhatsApp wählen,
 * fertig; der Text ist dann schon im Nachrichtenfeld.
 *
 * Für jemanden, der schlecht liest und schlecht zielt (Grundentscheidung 7),
 * ist das der Unterschied zwischen „geht" und „geht allein". Deshalb steht das
 * Teilen vor dem Kopieren, wo es beides gibt.
 *
 * **Warum trotzdem beides.** `navigator.share` gibt es nur auf Telefonen und
 * in Safari - auf einem Linux-Rechner mit Firefox gibt es ihn nicht, und dort
 * ist Kopieren der richtige Weg. Der Knopf erscheint deshalb nur, wo er etwas
 * tut, statt eine Enttäuschung zu versprechen (`kannTeilen`).
 */

/** Ob dieses Gerät ein Teilen-Blatt hat. Sonst gibt es keinen Knopf. */
export function kannTeilen(): boolean {
  return typeof navigator !== 'undefined' && typeof navigator.share === 'function';
}

/** Was beim Teilen herauskam - für die Meldung daneben. */
export type Teilergebnis = 'geteilt' | 'abgebrochen' | 'ging-nicht';

/**
 * Öffnet das Teilen-Blatt mit diesem Text.
 *
 * **Abbrechen ist kein Fehler.** Wer das Blatt wieder zuzieht, hat sich
 * umentschieden; der Browser wirft dafür einen `AbortError`, und den als
 * rote Meldung anzuzeigen wäre eine Rüge für eine richtige Handlung.
 */
export async function teile(text: string): Promise<Teilergebnis> {
  if (!text || !kannTeilen()) return 'ging-nicht';
  try {
    await navigator.share({ text });
    return 'geteilt';
  } catch (ursache) {
    const abgebrochen = ursache instanceof DOMException && ursache.name === 'AbortError';
    return abgebrochen ? 'abgebrochen' : 'ging-nicht';
  }
}
