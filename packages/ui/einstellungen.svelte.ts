/**
 * Was sich am Gerät einstellen lässt: Mikrofon, Vorlesen und Schriftgröße.
 *
 * Bewusst im Browser gespeichert und nicht am Sprecherprofil: Welche Stimmen
 * und welche Mikrofone es gibt, hängt am Gerät, und wer die App auf zwei
 * Geräten benutzt, braucht dort verschiedene Werte. Ein Schlüssel je Wert,
 * wie beim Sprecher und beim Token auch.
 *
 * Geteilt zwischen den Apps, nicht kopiert: `localStorage` gehört dem
 * Ursprung, und alle drei Apps liegen unter derselben Adresse. Wer das
 * Mikrofon in „hören" einmisst, hat es damit auch in „schreiben" eingemessen
 * — dort gibt es bewusst keine Einstellungsansicht (Grundentscheidung 7).
 */
import { VERSTAERKUNG_SPANNE, VERSTAERKUNG_VORGABE } from './mikrofon';
import { TEMPO_VORGABE } from './speak';

const MIKROFON_SCHLUESSEL = 'wortlaut.mikrofon';
const VERSTAERKUNG_SCHLUESSEL = 'wortlaut.verstaerkung';
const AUTOPEGEL_SCHLUESSEL = 'wortlaut.autopegel';
const STIMME_SCHLUESSEL = 'wortlaut.stimme';
const TEMPO_SCHLUESSEL = 'wortlaut.tempo';
const SCHRIFT_SCHLUESSEL = 'wortlaut.schrift';

/** Grenzen, damit ein verdorbener Eintrag die Ansicht nicht unbrauchbar macht. */
export const TEMPO_SPANNE = { min: 0.5, max: 1.5, schritt: 0.1 };
export const SCHRIFT_SPANNE = { min: 1.2, max: 4, schritt: 0.1 };
export const SCHRIFT_VORGABE = 2;

/** Die Pegelregelung des Browsers ist an, solange nichts anderes dasteht. */
export const AUTOPEGEL_VORGABE = true;

function zahl(schluessel: string, vorgabe: number, spanne: { min: number; max: number }): number {
  const gelesen = Number(localStorage.getItem(schluessel));
  if (!Number.isFinite(gelesen) || gelesen === 0) return vorgabe;
  return Math.min(spanne.max, Math.max(spanne.min, gelesen));
}

export const einstellungen = $state({
  mikrofonId: localStorage.getItem(MIKROFON_SCHLUESSEL),
  verstaerkung: zahl(VERSTAERKUNG_SCHLUESSEL, VERSTAERKUNG_VORGABE, VERSTAERKUNG_SPANNE),
  autoPegel: (localStorage.getItem(AUTOPEGEL_SCHLUESSEL) ?? String(AUTOPEGEL_VORGABE)) === 'true',
  stimmeUri: localStorage.getItem(STIMME_SCHLUESSEL),
  tempo: zahl(TEMPO_SCHLUESSEL, TEMPO_VORGABE, TEMPO_SPANNE),
  schriftRem: zahl(SCHRIFT_SCHLUESSEL, SCHRIFT_VORGABE, SCHRIFT_SPANNE),
});

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

export function setzeZurueck(): void {
  setzeMikrofon(null);
  setzeVerstaerkung(VERSTAERKUNG_VORGABE);
  setzeAutoPegel(AUTOPEGEL_VORGABE);
  setzeStimme(null);
  setzeTempo(TEMPO_VORGABE);
  setzeSchrift(SCHRIFT_VORGABE);
}
