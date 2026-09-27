/**
 * Die Diagrammbibliothek für „lernen", einmal eingerichtet.
 *
 * Dieselbe Bibliothek und derselbe Aufbau wie in „hören"
 * (`apps/hoeren/frontend/src/lib/diagramm.ts`), aber mit anderen Bausteinen:
 * Dort werden Balken und Punkte über Aufnahmen gezeichnet, hier Linien über
 * Trainingsschritte. Die Bausteine namentlich - 90 statt 370 Kilobyte.
 *
 * Zweimal vorhanden, weil `packages/ui` kein eigenes `node_modules` hat und
 * ohne fremde Bibliothek auskommt; jede App trägt nur, was sie zeichnet.
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
