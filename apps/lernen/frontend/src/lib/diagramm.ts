/**
 * Die Diagrammbibliothek für „lernen", einmal eingerichtet - und die einzige
 * Stelle, die sie kennt.
 *
 * **Warum ECharts.** Die Kurven wissen voneinander - derselbe Zoom, derselbe
 * Zeiger, ein Klick markiert überall dasselbe (`verbinde`). Dazu Zeigen,
 * Ziehen und Zwei-Finger-Zoom auf dem Telefon und gemischte Reihen in einem
 * Bild.
 *
 * **Warum diese Datei.** Die Bausteine werden hier **namentlich** eingeführt
 * und nicht als ganzes Bündel. Wer eine neue Art braucht, trägt sie hier ein.
 *
 * In der App und nicht in `packages/ui`, das kein eigenes `node_modules` hat
 * und ohne fremde Bibliothek auskommt.
 *
 * Geladen wird das Ganze erst, wenn eine Ansicht es braucht
 * (`await import('./diagramm')`) - Training und Modelle schleppen es nicht mit.
 */
import { connect, init, use } from 'echarts/core';
import { BarChart, LineChart, ScatterChart } from 'echarts/charts';
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

use([
  // Kurvenarten: Linien für die Lernkurven über Schritte (`Lauf`), Balken für
  // den Hauptwert und Punkte für die Vergleichsreihen über Aufnahmen
  // (`Auswertung`). Was hier nicht steht, zeichnet diese Oberfläche nicht.
  LineChart,
  BarChart,
  ScatterChart,
  // Achsenraster, Zeiger, Legende, Zoom - die senkrechte Marke, mit der ein
  // Durchgang im Bild steht, und die Fläche, mit der eine gewählte Aufnahme
  // im Bild steht statt daneben.
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkAreaComponent,
  // Leinwand statt SVG: Bei einigen hundert Balken samt Zoom ist sie
  // flüssiger.
  CanvasRenderer,
]);

/** Ein Diagramm in diesem Element aufbauen. */
export { init };

/** Mehrere Diagramme aneinanderkoppeln: gemeinsamer Zoom, gemeinsamer Zeiger. */
export { connect as verbinde };

/** Der Handgriff auf ein aufgebautes Diagramm. */
export type Diagramm = ReturnType<typeof init>;
