/**
 * Die Diagrammbibliothek, einmal eingerichtet - und die einzige Stelle, die
 * sie kennt.
 *
 * **Warum ECharts.** Die Kurven wissen voneinander - derselbe Zoom, derselbe
 * Zeiger, ein Klick markiert überall dasselbe (`verbinde`). Dazu Zeigen,
 * Ziehen und Zwei-Finger-Zoom auf dem Telefon und gemischte Reihen in einem
 * Bild.
 *
 * **Warum diese Datei.** Die Bausteine werden hier **namentlich** eingeführt
 * und nicht als ganzes Bündel - 90 statt 370 Kilobyte. Wer eine neue Art
 * braucht, trägt sie hier ein.
 *
 * In der App und nicht in `packages/ui`, das kein eigenes `node_modules` hat;
 * „lernen" hat seine eigene Fassung mit anderen Bausteinen.
 *
 * Geladen wird das Ganze erst, wenn eine Ansicht es braucht
 * (`await import('./diagramm')`) - die Aufnahmeseite schleppt es nicht mit.
 */
import { connect, init, use } from 'echarts/core';
import { BarChart, ScatterChart } from 'echarts/charts';
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

use([
  // Kurvenarten: Balken für den Hauptwert, Punkte für die Vergleichsreihen.
  // Was hier nicht steht, zeichnet diese Oberfläche nicht - eine Linienkurve
  // „für später" wäre nichts als ein Anhängsel am Bündel.
  BarChart,
  ScatterChart,
  // Achsenraster, Zeiger, Legende, Zoom - und die Markierung, mit der eine
  // Auswahl im Bild steht statt daneben.
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkAreaComponent,
  // Leinwand statt SVG: Bei einigen hundert Balken samt Zoom ist sie
  // flüssiger, und Diagramme sollen hier nicht in den Text hineinwachsen.
  CanvasRenderer,
]);

/** Ein Diagramm in diesem Element aufbauen. */
export { init };

/**
 * Mehrere Diagramme aneinanderkoppeln: gemeinsamer Zoomausschnitt, gemeinsamer
 * Zeiger. Noch von niemandem benutzt und trotzdem hier - es ist der Grund für
 * die Wahl dieser Bibliothek, und wer die nächste Ansicht baut, soll ihn
 * finden, ohne die Dokumentation zu durchsuchen.
 */
export { connect as verbinde };

/** Der Handgriff auf ein aufgebautes Diagramm. */
export type Diagramm = ReturnType<typeof init>;
