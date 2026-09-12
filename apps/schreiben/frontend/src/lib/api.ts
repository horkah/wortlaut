/**
 * Der einzige Ort, an dem diese App mit ihrem Backend spricht.
 *
 * Jede Anfrage trägt den Zugang des Sprechers - denselben, den „hören" für ihn
 * ausgegeben hat und der in demselben Browser liegt (siehe `$ui/zugang`). Den
 * Sprecher nennt trotzdem keine Anfrage: Der Server leitet ihn aus dem Zugang
 * ab (`backend/deps.py`). So kann diese App gar nicht erst in ein fremdes
 * Verzeichnis schreiben, und der Mensch muss dafür nichts tun - sein Link war
 * einmal zu öffnen, hier oder drüben.
 */

import { alsJson, api } from '$ui/api';
// Wer der Server in diesem Browser sieht - die Form steht in `$ui/wer`, weil
// alle drei Apps dieselbe Antwort lesen. Hier ist es immer ein Sprecher:
// Verwalter- und Aufsichtstoken weist dieser Server ab (`backend/deps.py`).
import type { Wer } from '$ui/wer';
export { setzeZugang, zugang } from '$ui/zugang';

export type Abschnitt = {
  id: string;
  position: number;
  text: string;
  /** `initial` aus dem ersten Diktat, `neu` = einzeln nachgesprochen. */
  herkunft: string;
  dauer_s: number;
  hat_audio: boolean;
};

export type Sitzung = {
  id: string;
  status: 'offen' | 'bestaetigt';
  erstellt: string;
  bestaetigt: string | null;
  abschnitte: Abschnitt[];
};

export type Modell = {
  sprecher_id: string;
  /** Was gerade geladen ist: eine Standkennung oder ein Grundmodellname. */
  ref: string;
  basismodell: string;
  methode: string | null;
  daten: string | null;
  erstellt: string | null;
  wer: number | null;
  laufzeit: string;
  /** Ob ein trainierter Stand läuft oder ein unverändertes Grundmodell. */
  trainiert: boolean;
  /** Ob das Diktat vor dem Erkennen ausgesteuert wird. */
  aussteuern: boolean;
  beschriftung: string;
};

export type Versand = { eingestellt: number; gesendet: number; offen: number; fehler: string | null };

export type PostausgangStand = { offen: number; gesendet: number; letzter_fehler: string | null };

/**
 * Alle Wege dieser App liegen unter ihrem Pfad, die API eingeschlossen.
 * `BASE_URL` ist das `base` aus der Vite-Konfiguration (`/schreiben/`) - so
 * steht der Ort an einer Stelle und nicht zweimal. Wie eine Anfrage hinausgeht
 * und wie ein Fehlschlag aussieht, steht in `$ui/api` - einmal für alle drei
 * Apps. Der Ort bleibt trotzdem als Wert stehen: `abschnittAudioUrl` gibt eine
 * Adresse heraus und stellt keine Anfrage.
 */
const API = `${import.meta.env.BASE_URL}api`;

const { anfrage } = api(API);

/** Aufnahmen gehen immer als Formulardatei; die Umwandlung macht der Server. */
function alsFormular(aufnahme: Blob): RequestInit {
  const formular = new FormData();
  formular.append('audio', aufnahme, 'aufnahme.webm');
  return { method: 'POST', body: formular };
}

// ── Diktieren ───────────────────────────────────────────────────────────────

export const sitzungBeginnen = () => anfrage<Sitzung>('/sessions', { method: 'POST' });

export const sitzungHolen = (sitzung: string) => anfrage<Sitzung>(`/sessions/${sitzung}`);

export const diktieren = (sitzung: string, aufnahme: Blob) =>
  anfrage<Sitzung>(`/sessions/${sitzung}/segments`, alsFormular(aufnahme));

export const abschnittNeuSprechen = (abschnitt: string, aufnahme: Blob) =>
  anfrage<Sitzung>(`/segments/${abschnitt}/neu`, alsFormular(aufnahme));

export const abschnittAudioUrl = (abschnitt: string) => `${API}/segments/${abschnitt}/audio`;

// ── Abschließen ─────────────────────────────────────────────────────────────

export const bestaetigen = (sitzung: string) =>
  anfrage<Versand>(`/sessions/${sitzung}/bestaetigen`, { method: 'POST' });

export const postausgang = () => anfrage<PostausgangStand>('/outbox');

export const postausgangSenden = () =>
  anfrage<Omit<Versand, 'eingestellt'>>('/outbox/senden', { method: 'POST' });

// ── Kopfzeile ───────────────────────────────────────────────────────────────

/** Für wen dieser Browser eingestellt ist - die Antwort kommt vom Server. */
export const werRuft = () => anfrage<Wer>('/zugang');

/**
 * Welches Modell hier arbeitet - freigegeben wird es in der Modellübersicht
 * von „lernen" (siehe `MODELLE_URL` in `$ui/apps`). Diese App liest nur.
 */
export const modell = () => anfrage<Modell>('/model');

/** Die Aufbereitung ändern - bisher genau eine: das Aussteuern. */
export const erkennungSetzen = (aenderung: { aussteuern?: boolean }) =>
  anfrage<Modell>('/model', alsJson(aenderung, 'PUT'));
