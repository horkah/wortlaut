/**
 * Einen Lauf löschen - ersatzlos, und das steht vorher in der Abfrage.
 *
 * Zwei Stellen bieten es an: die Karte eines offenen Laufs unter „Training"
 * und die Einzelansicht, der einzige Ort, an dem ein fertiger Lauf noch als
 * Lauf steht. Die Rückfrage steht deshalb hier und nicht zweimal.
 *
 * Nur mit Trainerschlüssel - wer trainieren darf, darf auch löschen. Ob er
 * gilt, sagt der Server (`lage.trainieren`); solange nicht, zeigen beide
 * Stellen keinen Papierkorb (`darfLoeschen`).
 *
 * Die Abfrage nennt, was verschwindet: Das Modell eines fertigen Laufs geht
 * mit (`services/auftraege.loesche`).
 *
 * Ein freigegebener Stand bekommt einen eigenen Satz dazu: Mit ihm ändert
 * sich, womit in „schreiben" diktiert wird.
 */

import { lage } from '$ui/lage.svelte';
import { zeitpunkt } from '$ui/zeit';
import { loescheLauf, type Lauf } from './api';

/** Ob der Papierkorb erscheint: nur, wenn der Server den Trainerschlüssel annimmt. */
export function darfLoeschen(): boolean {
  return lage.trainieren === 'gilt';
}

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
    // Die Modelltafel rechnet über die gemeinsamen Messungen; fällt eine
    // Zeile weg, ändert sich jede übrige Zahl.
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
