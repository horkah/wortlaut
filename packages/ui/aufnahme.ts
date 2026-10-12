/**
 * Eine eigene Aufnahme als Karte - anhören, löschen, ihre Genauigkeit.
 *
 * Die Wege gehören „hören", das den Korpus schreibt (Grundentscheidung 6);
 * die Karte steht in „Meine Daten" (hören) und in der Auswertung (lernen).
 * Deshalb hier, einmal für beide, und nicht im `lib/api.ts` einer App.
 */

import { api } from './api';

// Die Wege von „hören" liegen auf der Wurzel - aus jeder App derselbe Ort.
const { hole, anfrage } = api('/api');

/** Eine Aufnahme mit dem Text, zu dem sie gehört (`services/uebersicht.py`). */
export type AufsichtAufnahme = {
  id: string;
  prompt_id: string;
  text: string;
  quelle_art: string;
  dauer_s: number;
  pegel_dbfs: number;
  modus: string;
  status: string;
  hinweise: string[];
  externe_id: string | null;
  audio_vorhanden: boolean;
  erstellt: string;
  /** Wann zuletzt in „Editieren" gespeichert; null heißt nie. */
  geaendert: string | null;
  quelle_id: string;
  quelle_titel: string;
  validiert: boolean;
  /** Die Genauigkeit des Modells von „schreiben" auf dieser Aufnahme, 0 bis 100; null ungemessen. */
  qualitaet: number | null;
  /** Editiert und seitdem nicht gelernt - dann steht die Marke statt der Zahl. */
  editiert: boolean;
};

/** Eine Aufnahme in der Reihenfolge der Liste - zum Blättern im Editor. */
export type Listeneintrag = { id: string; status: string };

/** Wo die Farbskala der Genauigkeit rot und wo sie dunkelgrün ist, in Prozent. */
export type Guteskala = { rot: number; gruen: number };

/** Der Lautstärkeverlauf einer eigenen Aufnahme - die Wellenform zum Anhören. */
export type Wellenform = { dauer_s: number; fenster_s: number; verlauf: number[] };

export const aufnahmeVerwerfen = (aufnahme: string) =>
  anfrage<void>(`/recordings/${aufnahme}`, { method: 'DELETE' });

/**
 * Eine eigene Aufnahme anhören.
 *
 * Als Blob und nicht als Adresse im `src`: Die Datei hängt am Zugang, und ein
 * `<audio src>` schickt keine Kopfzeilen mit.
 */
export const meineAufnahmeAudio = async (aufnahme: string): Promise<Blob> =>
  (await hole(`/recordings/${aufnahme}/audio`)).blob();

export const meineWellenform = (aufnahme: string) =>
  anfrage<Wellenform>(`/recordings/${aufnahme}/verlauf`);
