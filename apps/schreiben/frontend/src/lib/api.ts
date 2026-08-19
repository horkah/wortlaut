/**
 * Der einzige Ort, an dem diese App mit ihrem Backend spricht.
 *
 * Kein Token, kein Sprecherparameter: Eine Instanz gehört zu genau einer
 * Person und einem Modellstand (Grundentscheidung 7). Beides steht in der
 * Konfiguration des Servers, nicht in der Adresszeile.
 */

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

export class ApiFehler extends Error {
  constructor(
    readonly status: number,
    nachricht: string,
  ) {
    super(nachricht);
  }
}

async function anfrage<T>(pfad: string, optionen: RequestInit = {}): Promise<T> {
  const antwort = await fetch(`/api${pfad}`, optionen);
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

export const abschnittAudioUrl = (abschnitt: string) => `/api/segments/${abschnitt}/audio`;

// ── Abschließen ─────────────────────────────────────────────────────────────

export const bestaetigen = (sitzung: string) =>
  anfrage<Versand>(`/sessions/${sitzung}/bestaetigen`, { method: 'POST' });

export const postausgang = () => anfrage<PostausgangStand>('/outbox');

export const postausgangSenden = () =>
  anfrage<Omit<Versand, 'eingestellt'>>('/outbox/senden', { method: 'POST' });

// ── Kopfzeile ───────────────────────────────────────────────────────────────

export const modell = () => anfrage<Modell>('/model');
