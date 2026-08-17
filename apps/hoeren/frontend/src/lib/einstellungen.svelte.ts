/**
 * Was sich am Gerät einstellen lässt: Vorlesen und Schriftgröße.
 *
 * Bewusst im Browser gespeichert und nicht am Sprecherprofil: Welche Stimmen
 * es gibt, hängt am Betriebssystem, und wer die App auf zwei Geräten benutzt,
 * braucht dort verschiedene Werte. Ein Schlüssel je Wert, wie beim Sprecher
 * und beim Token auch.
 */
import { TEMPO_VORGABE } from '$ui/speak';

const STIMME_SCHLUESSEL = 'wortlaut.stimme';
const TEMPO_SCHLUESSEL = 'wortlaut.tempo';
const SCHRIFT_SCHLUESSEL = 'wortlaut.schrift';

/** Grenzen, damit ein verdorbener Eintrag die Ansicht nicht unbrauchbar macht. */
export const TEMPO_SPANNE = { min: 0.5, max: 1.5, schritt: 0.1 };
export const SCHRIFT_SPANNE = { min: 1.2, max: 4, schritt: 0.1 };
export const SCHRIFT_VORGABE = 2;

function zahl(schluessel: string, vorgabe: number, spanne: { min: number; max: number }): number {
  const gelesen = Number(localStorage.getItem(schluessel));
  if (!Number.isFinite(gelesen) || gelesen === 0) return vorgabe;
  return Math.min(spanne.max, Math.max(spanne.min, gelesen));
}

export const einstellungen = $state({
  stimmeUri: localStorage.getItem(STIMME_SCHLUESSEL),
  tempo: zahl(TEMPO_SCHLUESSEL, TEMPO_VORGABE, TEMPO_SPANNE),
  schriftRem: zahl(SCHRIFT_SCHLUESSEL, SCHRIFT_VORGABE, SCHRIFT_SPANNE),
});

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
  setzeStimme(null);
  setzeTempo(TEMPO_VORGABE);
  setzeSchrift(SCHRIFT_VORGABE);
}
