/**
 * Einen Lauf löschen - ersatzlos, und das steht vorher in der Abfrage.
 *
 * Zwei Stellen bieten es an: die Karte eines offenen Laufs unter „Training"
 * und die Einzelansicht, der einzige Ort, an dem ein fertiger Lauf noch als
 * Lauf steht. Die Rückfrage steht deshalb hier und nicht zweimal.
 *
 * Die Abfrage nennt, was verschwindet, und nicht nur „wirklich?". Ein
 * fertiger Lauf hat ein Modell hervorgebracht, und das geht mit: Bliebe es
 * stehen, zeigte es auf ein Verzeichnis, das es nicht mehr gibt, und die
 * Frage, worauf es trainiert wurde, wäre nicht mehr zu beantworten. Wer das
 * nicht weiß, bevor er bestätigt, erfährt es hinterher.
 *
 * Ein freigegebener Stand bekommt einen eigenen Satz dazu: Mit ihm ändert
 * sich, womit in „schreiben" diktiert wird.
 */

import { zeitpunkt } from '$ui/zeit';
import { loescheLauf, type Lauf } from './api';

/**
 * Fragt nach und löscht. `false` heißt: Die Rückfrage wurde verneint. Ein
 * Fehler des Servers kommt als Ausnahme heraus - die Ansicht zeigt ihn.
 */
export async function loescheNachRueckfrage(lauf: Lauf): Promise<boolean> {
  const zeilen = [`${lauf.code} vom ${zeitpunkt(lauf.erstellt)} löschen?`, ''];
  if (lauf.stand) {
    zeilen.push(`Das Modell „${lauf.stand.version}" wird mitgelöscht.`);
    if (lauf.stand.freigegeben) {
      zeilen.push(
        'Es ist gerade freigegeben - „schreiben" fällt danach auf das Grundmodell zurück, ' +
          'bis ein anderer Stand freigegeben wird.',
      );
    }
    // Die Folge, die niemand erwartet: Die Modelltafel rechnet jede Zahl
    // über die Messungen, die **alle** Modelle haben. Fällt eine Zeile weg,
    // wächst diese Schnittmenge - und jede übrige Zahl ändert sich.
    // Gemessen waren das 0,15 WER, als ein alter Stand verschwand.
    zeilen.push(
      'In der Modelltafel können sich dadurch die Zahlen der übrigen Modelle ändern: ' +
        'Sie stehen auf den Messungen, die alle Modelle gemeinsam haben.',
    );
    zeilen.push('');
  }
  zeilen.push('Auftrag, Schnappschuss, Kurven und Protokoll verschwinden mit.');
  zeilen.push('Das lässt sich nicht rückgängig machen.');

  if (!confirm(zeilen.join('\n'))) return false;
  await loescheLauf(lauf.job_id);
  return true;
}
