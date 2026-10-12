/**
 * Wo im Fenster jede Ansicht stand - zurück in einer Ansicht, steht sie wieder
 * dort.
 *
 * Gilt für jede Route jeder App, Reiter wie Menüansichten; der Rahmen meldet
 * die Ansicht, die dasteht (`zeigeAn` in `Rahmen.svelte`). Gemerkt wird je App
 * und Route, im Speicher dieses Reiters (`sessionStorage`) - über einen
 * Wechsel der App hinweg, der die Seite neu lädt, aber nicht über das
 * Schließen hinaus.
 *
 * **Warum ein Nachziehen und kein einzelnes `scrollTo`.** Eine Ansicht holt
 * ihren Inhalt erst nach dem Aufbau; solange er fehlt, ist die Seite zu kurz
 * für die alte Stelle. Gezogen wird deshalb Bild für Bild, bis die Stelle
 * erreicht ist - höchstens `NACHZIEHEN_MS` lang, und nur, bis jemand selbst
 * scrollt, tippt oder eine Taste drückt. Wer selbst an eine Stelle springt
 * (die Karte nach dem Editor in „Meine Daten"), ruft vorher `lasse`.
 */

const SPEICHER = 'wortlaut.fensterlage';
const NACHZIEHEN_MS = 5000;

let lagen: Record<string, number> = lies();
// Die Ansicht, die dasteht, und die Stelle, zu der gerade gezogen wird.
let aktuell = '';
let ziel: number | null = null;
let bis = 0;
let bild = 0;
let schreiber: ReturnType<typeof setTimeout> | undefined;

function lies(): Record<string, number> {
  try {
    const roh = sessionStorage.getItem(SPEICHER);
    return roh ? (JSON.parse(roh) as Record<string, number>) : {};
  } catch {
    return {};
  }
}

function sichere(): void {
  clearTimeout(schreiber);
  try {
    sessionStorage.setItem(SPEICHER, JSON.stringify(lagen));
  } catch {
    // Ohne Speicher gilt die Stelle bis zum Neuladen - kein Fehlerfall.
  }
}

function ziehe(): void {
  cancelAnimationFrame(bild);
  if (ziel === null) return;
  window.scrollTo(0, ziel);
  if (Math.abs(window.scrollY - ziel) < 2 || performance.now() > bis) {
    ziel = null;
    lagen[aktuell] = window.scrollY;
    return;
  }
  bild = requestAnimationFrame(ziehe);
}

/** Nicht weiter nachziehen - die Ansicht oder der Mensch bestimmt die Stelle. */
export function lasse(): void {
  ziel = null;
  cancelAnimationFrame(bild);
}

/** Diese Ansicht steht jetzt da: an ihre gemerkte Stelle, sonst nach oben. */
export function zeigeAn(schluessel: string): void {
  if (schluessel === aktuell) return;
  aktuell = schluessel;
  ziel = lagen[schluessel] ?? 0;
  bis = performance.now() + NACHZIEHEN_MS;
  ziehe();
}

// Der Browser stellt sonst beim Neuladen und beim Zurück-Knopf selbst eine
// Stelle her - und zöge gegen diese hier.
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

window.addEventListener(
  'scroll',
  () => {
    // Während des Nachziehens ist die Lage eine Zwischenstation.
    if (ziel !== null || !aktuell) return;
    lagen[aktuell] = window.scrollY;
    clearTimeout(schreiber);
    schreiber = setTimeout(sichere, 250);
  },
  { passive: true },
);

// Wer selbst scrollt oder tippt, hat Vorrang.
for (const art of ['wheel', 'touchstart', 'pointerdown', 'keydown']) {
  window.addEventListener(art, lasse, { passive: true, capture: true });
}

// Ein Wechsel der App lädt die Seite neu - vorher sichern, was noch aussteht.
window.addEventListener('pagehide', sichere);
