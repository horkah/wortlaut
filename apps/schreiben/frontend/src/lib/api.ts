/**
 * Der einzige Ort, an dem diese App mit ihrem Backend spricht.
 *
 * Jede Anfrage trägt den Zugang des Sprechers — denselben, den „hören" für ihn
 * ausgegeben hat und der in demselben Browser liegt (siehe `$ui/zugang`). Den
 * Sprecher nennt trotzdem keine Anfrage: Der Server leitet ihn aus dem Zugang
 * ab (`backend/deps.py`). So kann diese App gar nicht erst in ein fremdes
 * Verzeichnis schreiben, und der Mensch muss dafür nichts tun — sein Link war
 * einmal zu öffnen, hier oder drüben.
 */

import { mitZugang } from '$ui/zugang';
export { setzeZugang, zugang } from '$ui/zugang';

/** Wer der Server in diesem Browser sieht. */
export type Wer = { art: string; sprecher_id: string; name: string };

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
  ref: string;
  basismodell: string;
  methode: string | null;
  erstellt: string | null;
  wer: number | null;
  laufzeit: string;
  beschriftung: string;
};

export type Versand = { eingestellt: number; gesendet: number; offen: number; fehler: string | null };

export type PostausgangStand = { offen: number; gesendet: number; letzter_fehler: string | null };

/**
 * Alle Wege dieser App liegen unter ihrem Pfad, die API eingeschlossen.
 * `BASE_URL` ist das `base` aus der Vite-Konfiguration (`/schreiben/`) — so
 * steht der Ort an einer Stelle und nicht zweimal.
 */
const API = `${import.meta.env.BASE_URL}api`;

export class ApiFehler extends Error {
  constructor(
    readonly status: number,
    nachricht: string,
  ) {
    super(nachricht);
  }
}

async function anfrage<T>(pfad: string, optionen: RequestInit = {}): Promise<T> {
  const antwort = await fetch(`${API}${pfad}`, {
    ...optionen,
    headers: mitZugang(optionen.headers),
  });
  if (!antwort.ok) {
    // FastAPI antwortet mit {"detail": …}; bei Netzfehlern bleibt der Status.
    const rumpf = await antwort.json().catch(() => null);
    throw new ApiFehler(antwort.status, rumpf?.detail ?? `Fehler ${antwort.status}`);
  }
  return antwort.status === 204 ? (undefined as T) : ((await antwort.json()) as T);
}

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

/** Für wen dieser Browser eingestellt ist — die Antwort kommt vom Server. */
export const werRuft = () => anfrage<Wer>('/zugang');

/** Der Modellstand **dieses** Sprechers; „lernen" gibt ihn je Person frei. */
export const modell = () => anfrage<Modell>('/model');
