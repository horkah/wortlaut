/**
 * Was sich am Gerät einstellen lässt: Mikrofon, Vorlesen und Darstellung.
 *
 * Bewusst im Browser gespeichert und nicht am Sprecherprofil: Welche Stimmen
 * und welche Mikrofone es gibt, hängt am Gerät, und wer die App auf zwei
 * Geräten benutzt, braucht dort verschiedene Werte. Ein Schlüssel je Wert,
 * wie beim Sprecher und beim Token auch.
 *
 * Geteilt zwischen den Apps, nicht kopiert: `localStorage` gehört dem
 * Ursprung, und alle drei Apps liegen unter derselben Adresse. Wer das
 * Mikrofon in „hören" einmisst, hat es damit auch in „schreiben" eingemessen.
 *
 * Weil die Werte geteilt sind, ist es auch die Ansicht dazu — sie steht einmal
 * in `Einstellungen.svelte` (Mikrofon, Vorlesen) und einmal in
 * `Darstellung.svelte` (Farben, Schrift).
 */
import { VERSTAERKUNG_SPANNE, VERSTAERKUNG_VORGABE } from './mikrofon';
import { TEMPO_VORGABE } from './speak';

const MIKROFON_SCHLUESSEL = 'wortlaut.mikrofon';
const VERSTAERKUNG_SCHLUESSEL = 'wortlaut.verstaerkung';
const AUTOPEGEL_SCHLUESSEL = 'wortlaut.autopegel';
const STIMME_SCHLUESSEL = 'wortlaut.stimme';
const TEMPO_SCHLUESSEL = 'wortlaut.tempo';
const SCHRIFT_SCHLUESSEL = 'wortlaut.schrift';
const SCHRIFTART_SCHLUESSEL = 'wortlaut.schriftart';
const GRUNDSCHRIFT_SCHLUESSEL = 'wortlaut.grundschrift';
const FARBE_SCHLUESSEL_VORSILBE = 'wortlaut.farbe.';

/** Grenzen, damit ein verdorbener Eintrag die Ansicht nicht unbrauchbar macht. */
export const TEMPO_SPANNE = { min: 0.5, max: 1.5, schritt: 0.1 };
export const SCHRIFT_SPANNE = { min: 1.2, max: 4, schritt: 0.1 };
export const SCHRIFT_VORGABE = 2;
export const GRUNDSCHRIFT_SPANNE = { min: 14, max: 28, schritt: 1 };
export const GRUNDSCHRIFT_VORGABE = 18;

/** Die Pegelregelung des Browsers ist an, solange nichts anderes dasteht. */
export const AUTOPEGEL_VORGABE = true;

/**
 * Die Farbtöne, die die App tatsächlich benutzt (siehe `app.css`), mit dem
 * Namen für die Ansicht und der Vorgabe, auf die „Auf Vorgaben zurücksetzen"
 * zurückfällt. `schluessel` ist zugleich der Name der CSS-Variable — ohne die
 * beiden führenden Bindestriche — und der Teil hinter `FARBE_SCHLUESSEL_VORSILBE`.
 */
export const FARBEN: { schluessel: string; name: string; vorgabe: string }[] = [
  { schluessel: 'akzent', name: 'Akzentfarbe', vorgabe: '#1b4d3e' },
  { schluessel: 'akzent-hell', name: 'Akzentfarbe, hell', vorgabe: '#e4ece9' },
  { schluessel: 'text', name: 'Schriftfarbe', vorgabe: '#1c1b19' },
  { schluessel: 'hintergrund', name: 'Hintergrund', vorgabe: '#faf9f7' },
  { schluessel: 'rand', name: 'Rahmen', vorgabe: '#d8d4cd' },
  { schluessel: 'gedaempft', name: 'Gedämpfter Text', vorgabe: '#6b6b6b' },
  { schluessel: 'warnung', name: 'Warnung', vorgabe: '#8a5300' },
  { schluessel: 'fehler', name: 'Fehler / läuft', vorgabe: '#b3261e' },
];

/** Zur Wahl stehende Schriftarten; die erste ist die Vorgabe aus `app.css`. */
export const SCHRIFTARTEN: { wert: string; name: string }[] = [
  { wert: "system-ui, -apple-system, 'Segoe UI', sans-serif", name: 'Systemschrift' },
  { wert: "Georgia, 'Times New Roman', serif", name: 'Serifenschrift' },
  { wert: "'Comic Sans MS', 'Comic Neue', sans-serif", name: 'Rundschrift' },
  { wert: "'Courier New', monospace", name: 'Feste Breite' },
];
export const SCHRIFTART_VORGABE = SCHRIFTARTEN[0].wert;

function zahl(schluessel: string, vorgabe: number, spanne: { min: number; max: number }): number {
  const gelesen = Number(localStorage.getItem(schluessel));
  if (!Number.isFinite(gelesen) || gelesen === 0) return vorgabe;
  return Math.min(spanne.max, Math.max(spanne.min, gelesen));
}

function farbwerte(): Record<string, string> {
  const werte: Record<string, string> = {};
  for (const farbe of FARBEN) {
    werte[farbe.schluessel] =
      localStorage.getItem(FARBE_SCHLUESSEL_VORSILBE + farbe.schluessel) ?? farbe.vorgabe;
  }
  return werte;
}

export const einstellungen = $state({
  mikrofonId: localStorage.getItem(MIKROFON_SCHLUESSEL),
  verstaerkung: zahl(VERSTAERKUNG_SCHLUESSEL, VERSTAERKUNG_VORGABE, VERSTAERKUNG_SPANNE),
  autoPegel: (localStorage.getItem(AUTOPEGEL_SCHLUESSEL) ?? String(AUTOPEGEL_VORGABE)) === 'true',
  stimmeUri: localStorage.getItem(STIMME_SCHLUESSEL),
  tempo: zahl(TEMPO_SCHLUESSEL, TEMPO_VORGABE, TEMPO_SPANNE),
  schriftRem: zahl(SCHRIFT_SCHLUESSEL, SCHRIFT_VORGABE, SCHRIFT_SPANNE),
  schriftart: localStorage.getItem(SCHRIFTART_SCHLUESSEL) ?? SCHRIFTART_VORGABE,
  grundschriftPx: zahl(GRUNDSCHRIFT_SCHLUESSEL, GRUNDSCHRIFT_VORGABE, GRUNDSCHRIFT_SPANNE),
  farben: farbwerte(),
});

/**
 * Farben, Schriftart und Grundschriftgröße als Stil auf das Wurzelelement
 * schreiben — der einzige Weg, wie diese drei über `app.css` hinaus wirken,
 * ohne dass jede Komponente ihren eigenen Stil mitbrächte. Ein Inline-Stil
 * auf `:root` sticht die Variable aus dem Stylesheet, ein entfernter Stil
 * lässt die Vorgabe aus `app.css` wieder durch.
 */
function wendeDarstellungAn(): void {
  const wurzel = document.documentElement.style;
  for (const farbe of FARBEN) wurzel.setProperty(`--${farbe.schluessel}`, einstellungen.farben[farbe.schluessel]);
  wurzel.setProperty('--schrift-familie', einstellungen.schriftart);
  wurzel.fontSize = `${einstellungen.grundschriftPx}px`;
}
wendeDarstellungAn();

export function setzeMikrofon(id: string | null): void {
  einstellungen.mikrofonId = id;
  if (id) localStorage.setItem(MIKROFON_SCHLUESSEL, id);
  else localStorage.removeItem(MIKROFON_SCHLUESSEL);
}

export function setzeVerstaerkung(wert: number): void {
  einstellungen.verstaerkung = wert;
  localStorage.setItem(VERSTAERKUNG_SCHLUESSEL, String(wert));
}

export function setzeAutoPegel(an: boolean): void {
  einstellungen.autoPegel = an;
  localStorage.setItem(AUTOPEGEL_SCHLUESSEL, String(an));
}

export function setzeStimme(uri: string | null): void {
  einstellungen.stimmeUri = uri;
  if (uri) localStorage.setItem(STIMME_SCHLUESSEL, uri);
  else localStorage.removeItem(STIMME_SCHLUESSEL);
}

export function setzeTempo(wert: number): void {
  einstellungen.tempo = wert;
  localStorage.setItem(TEMPO_SCHLUESSEL, String(wert));
}

export function setzeSchrift(wert: number): void {
  einstellungen.schriftRem = wert;
  localStorage.setItem(SCHRIFT_SCHLUESSEL, String(wert));
}

export function setzeFarbe(schluessel: string, wert: string): void {
  einstellungen.farben[schluessel] = wert;
  localStorage.setItem(FARBE_SCHLUESSEL_VORSILBE + schluessel, wert);
  wendeDarstellungAn();
}

export function setzeSchriftart(wert: string): void {
  einstellungen.schriftart = wert;
  localStorage.setItem(SCHRIFTART_SCHLUESSEL, wert);
  wendeDarstellungAn();
}

export function setzeGrundschrift(px: number): void {
  einstellungen.grundschriftPx = px;
  localStorage.setItem(GRUNDSCHRIFT_SCHLUESSEL, String(px));
  wendeDarstellungAn();
}

export function setzeZurueck(): void {
  setzeMikrofon(null);
  setzeVerstaerkung(VERSTAERKUNG_VORGABE);
  setzeAutoPegel(AUTOPEGEL_VORGABE);
  setzeStimme(null);
  setzeTempo(TEMPO_VORGABE);
}

/** Nur die Darstellung zurücksetzen — eigener Knopf in `Darstellung.svelte`. */
export function setzeDarstellungZurueck(): void {
  for (const farbe of FARBEN) setzeFarbe(farbe.schluessel, farbe.vorgabe);
  setzeSchriftart(SCHRIFTART_VORGABE);
  setzeGrundschrift(GRUNDSCHRIFT_VORGABE);
  setzeSchrift(SCHRIFT_VORGABE);
}
