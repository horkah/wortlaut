/**
 * Die Diagrammbibliothek, einmal eingerichtet - und die einzige Stelle, die
 * sie kennt.
 *
 * **Warum ECharts.** Die erste Kurve (Auswertung in „hören") käme mit weniger
 * aus. Kommen sollen aber mehrere, die voneinander wissen: derselbe
 * Zoomausschnitt, derselbe Zeiger, ein Klick, der in allen dasselbe markiert.
 * Das ist der Punkt, an dem die meisten schlanken Bibliotheken aufhören und an
 * dem man sie ersetzen müsste - also lieber gleich die, die es kann. ECharts
 * bringt mit, was gebraucht wird: Zeigen, Ziehen und Zwei-Finger-Zoom auf dem
 * Telefon genauso wie mit der Maus, gemischte Reihen in einem Bild (Balken und
 * Punkte), und `verbinde` unten koppelt mehrere Diagramme aneinander.
 *
 * **Warum diese Datei.** Die Bausteine werden hier **namentlich** eingeführt
 * und nicht als ganzes Bündel. Das ist kein Stil, sondern der Unterschied
 * zwischen 90 und 370 Kilobyte im Browser: Ein `import * as charts` und ein
 * Zugriff darauf zur Laufzeit lässt dem Bündler keine Wahl, als jede Kurvenart
 * mitzunehmen, die ECharts kennt - Landkarten, Baumdiagramme, Kerzencharts.
 * Wer eine neue Art braucht, trägt sie hier ein; das ist zugleich die Liste
 * dessen, was diese Oberfläche überhaupt zeichnet.
 *
 * **Warum in dieser App und nicht in `packages/ui`.** Die geteilten
 * Komponenten kommen bisher ohne eine einzige fremde Bibliothek aus - sie
 * haben kein eigenes `node_modules` und werden aus dem der jeweiligen App
 * gebaut. Ein `import 'echarts'` dort fände nichts. Solange nur „hören"
 * zeichnet, ist das der ehrlichere Ort; braucht eine zweite App Diagramme,
 * ist der Umzug nach `packages/ui` ein npm-Arbeitsbereich und diese Datei
 * unverändert.
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
