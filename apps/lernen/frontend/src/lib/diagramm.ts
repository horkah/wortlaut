/**
 * Die Diagrammbibliothek für „lernen", einmal eingerichtet.
 *
 * Dieselbe Bibliothek und derselbe Aufbau wie in „hören"
 * (`apps/hoeren/frontend/src/lib/diagramm.ts`), aber mit anderen Bausteinen:
 * Dort werden Balken und Punkte über Aufnahmen gezeichnet, hier Linien über
 * Trainingsschritte. Die Bausteine werden **namentlich** eingeführt und nicht
 * als ganzes Bündel - das ist kein Stil, sondern der Unterschied zwischen 90
 * und 370 Kilobyte im Browser.
 *
 * **Warum die Datei zweimal existiert.** Die geteilten Komponenten unter
 * `packages/ui` kommen ohne eine einzige fremde Bibliothek aus; sie haben kein
 * eigenes `node_modules` und werden aus dem der jeweiligen App gebaut. Ein
 * `import 'echarts'` dort fände nichts. Der Umzug dorthin ist ein
 * npm-Arbeitsbereich - und dann steht diese Liste einmal statt zweimal. Bis
 * dahin ist die Doppelung die ehrlichere Lösung: Zwei Apps zeichnen
 * Verschiedenes, und jede trägt nur, was sie zeichnet.
 *
 * Geladen wird das Ganze erst, wenn eine Ansicht es braucht
 * (`await import('./diagramm')`) - die Aufteilung schleppt es nicht mit.
 */
import { connect, init, use } from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

use([
  // Eine einzige Kurvenart: Die Lernkurven sind Linien über Schritte. Balken
  // und Punkte braucht diese App nicht, also trägt ihr Bündel sie nicht.
  LineChart,
  // Achsenraster, Zeiger, Legende, Zoom - und die senkrechte Marke, mit der
  // ein Durchgang im Bild steht statt daneben.
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

/** Ein Diagramm in diesem Element aufbauen. */
export { init };

/** Mehrere Diagramme aneinanderkoppeln: gemeinsamer Zoom, gemeinsamer Zeiger. */
export { connect as verbinde };

/** Der Handgriff auf ein aufgebautes Diagramm. */
export type Diagramm = ReturnType<typeof init>;
