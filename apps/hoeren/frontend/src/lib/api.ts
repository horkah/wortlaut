/**
 * Der einzige Ort, an dem diese App mit dem Backend spricht.
 *
 * Jede Anfrage nennt den Sprecher als Abfrageparameter — das Korpus hat je
 * Sprecher eine eigene Datenbank (siehe docs/betrieb.md).
 */

export type Sprecher = {
  id: string;
  name: string;
  sprache: string;
  basismodell: string;
  erstellt: string;
};

export type Einheit = { id: string; text: string; dauer_geschaetzt_s: number };

export type Naechste = {
  vorher: Einheit | null;
  aktuell: Einheit | null;
  nachher: Einheit | null;
  erledigt: number;
  gesamt: number;
};

export type Aufnahme = {
  id: string;
  prompt_id: string;
  dauer_s: number;
  pegel_dbfs: number;
  modus: string;
  status: string;
  hinweise: string[];
};

export type Quelle = {
  id: string;
  art: string;
  titel: string;
  einheiten: number;
  aktiv: boolean;
  erstellt: string;
};

export type Fortschritt = {
  sekunden: number;
  aufnahmen: number;
  offene_einheiten: number;
  nach_modus: Record<string, number>;
  nach_quelle: Record<string, number>;
  marke_brauchbar_s: number;
  marke_gut_s: number;
};

export class ApiFehler extends Error {
  constructor(
    readonly status: number,
    nachricht: string,
  ) {
    super(nachricht);
  }
}

const TOKEN_SCHLUESSEL = 'wortlaut.token';

export function token(): string {
  return localStorage.getItem(TOKEN_SCHLUESSEL) ?? '';
}

export function setzeToken(wert: string): void {
  localStorage.setItem(TOKEN_SCHLUESSEL, wert.trim());
}

async function anfrage<T>(pfad: string, optionen: RequestInit = {}): Promise<T> {
  const kopf = new Headers(optionen.headers);
  const angemeldet = token();
  if (angemeldet) kopf.set('Authorization', `Bearer ${angemeldet}`);

  const antwort = await fetch(`/api${pfad}`, { ...optionen, headers: kopf });
  if (!antwort.ok) {
    // FastAPI antwortet mit {"detail": …}; bei Netzfehlern bleibt der Status.
    const rumpf = await antwort.json().catch(() => null);
    throw new ApiFehler(antwort.status, rumpf?.detail ?? `Fehler ${antwort.status}`);
  }
  return antwort.status === 204 ? (undefined as T) : ((await antwort.json()) as T);
}

function alsJson(rumpf: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rumpf),
  };
}

// ── Sprecher ────────────────────────────────────────────────────────────────

export const sprecherListe = () => anfrage<Sprecher[]>('/speakers');

/** Ein einzelner Sprecher — für den Namen in der Kopfzeile. */
export const sprecherHolen = (id: string) => anfrage<Sprecher>(`/speakers/${id}`);

export const sprecherAnlegen = (eingabe: { name: string; basismodell: string }) =>
  anfrage<Sprecher>('/speakers', alsJson(eingabe));

// ── Textquellen ─────────────────────────────────────────────────────────────

export const quellen = (sprecher: string) =>
  anfrage<Quelle[]>(`/sources?sprecher=${sprecher}`);

export const quelleAusLLM = (
  sprecher: string,
  auftrag: { thema: string; altersspanne: string; umfang: number },
) => anfrage<Quelle>(`/sources/llm?sprecher=${sprecher}`, alsJson(auftrag));

export function quelleAusDatei(sprecher: string, datei: File) {
  const formular = new FormData();
  formular.append('datei', datei);
  return anfrage<Quelle>(`/sources/upload?sprecher=${sprecher}`, {
    method: 'POST',
    body: formular,
  });
}

export const quelleLoeschen = (sprecher: string, quelle: string) =>
  anfrage<void>(`/sources/${quelle}?sprecher=${sprecher}`, { method: 'DELETE' });

/** Stilllegen oder wieder aufnehmen; gibt die Quelle im neuen Zustand zurück. */
export const quelleUmstellen = (sprecher: string, quelle: string, aktiv: boolean) =>
  anfrage<Quelle>(`/sources/${quelle}?sprecher=${sprecher}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ aktiv }),
  });

/**
 * Der geschnittene Text einer Quelle als Klartext.
 *
 * Eigene Anfrage statt `anfrage`: Hier kommt kein JSON zurück. Nötig ist das,
 * weil die API einen Token verlangt — ein `window.open` auf die Adresse
 * schickte keinen mit und liefe in ein 401.
 */
export async function quelleText(sprecher: string, quelle: string): Promise<string> {
  const kopf = new Headers();
  const angemeldet = token();
  if (angemeldet) kopf.set('Authorization', `Bearer ${angemeldet}`);

  const antwort = await fetch(`/api/sources/${quelle}/text?sprecher=${sprecher}`, {
    headers: kopf,
  });
  if (!antwort.ok) {
    const rumpf = await antwort.json().catch(() => null);
    throw new ApiFehler(antwort.status, rumpf?.detail ?? `Fehler ${antwort.status}`);
  }
  return antwort.text();
}

// ── Aufnehmen ───────────────────────────────────────────────────────────────

export const sitzungBeginnen = (sprecher: string) =>
  anfrage<{ id: string; begonnen: string }>(`/sessions?sprecher=${sprecher}`, { method: 'POST' });

export const naechsteEinheit = (sprecher: string, sitzung: string | null) =>
  anfrage<Naechste>(
    `/prompts/next?sprecher=${sprecher}` + (sitzung ? `&session=${sitzung}` : ''),
  );

export function aufnahmeSenden(
  sprecher: string,
  eingabe: { audio: Blob; prompt_id: string; modus: string; session: string | null },
) {
  const formular = new FormData();
  formular.append('audio', eingabe.audio, 'aufnahme.webm');
  formular.append('prompt_id', eingabe.prompt_id);
  formular.append('modus', eingabe.modus);
  if (eingabe.session) formular.append('session', eingabe.session);
  return anfrage<Aufnahme>(`/recordings?sprecher=${sprecher}`, { method: 'POST', body: formular });
}

export const aufnahmeVerwerfen = (sprecher: string, aufnahme: string) =>
  anfrage<void>(`/recordings/${aufnahme}?sprecher=${sprecher}`, { method: 'DELETE' });

// ── Fortschritt ─────────────────────────────────────────────────────────────

export const fortschritt = (sprecher: string) =>
  anfrage<Fortschritt>(`/progress?sprecher=${sprecher}`);
