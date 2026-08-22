/**
 * Der einzige Ort, an dem diese App mit dem Backend spricht.
 *
 * Den Sprecher nennt keine Anfrage mehr: Der Server leitet ihn aus dem
 * vorgelegten Zugang ab (siehe backend/deps.py). Der Zugang ist entweder der
 * eines Sprechers — `<sprecher_id>.<geheimnis>`, gekommen über einen Link —
 * oder der Verwaltertoken.
 */

export type Sprecher = {
  id: string;
  name: string;
  sprache: string;
  basismodell: string;
  erstellt: string;
  /** Wann der geltende Zugang ausgegeben wurde; null heißt: noch keiner da. */
  zugang_erneuert: string | null;
};

/** Wer der Server in diesem Browser sieht. */
export type Wer = {
  art: 'sprecher' | 'verwaltung';
  sprecher_id: string | null;
  name: string | null;
};

/** Ein frisch ausgegebener Zugang — im Klartext nur genau hier. */
export type NeuerZugang = { sprecher_id: string; zugang: string; erneuert: string };

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

// Was hier liegt, ist entweder ein Sprecherzugang oder der Verwaltertoken —
// der Server sieht am Aufbau, welches von beidem (backend/services/zugang.py).
const ZUGANG_SCHLUESSEL = 'wortlaut.zugang';

export function zugang(): string {
  return localStorage.getItem(ZUGANG_SCHLUESSEL) ?? '';
}

export function setzeZugang(wert: string): void {
  localStorage.setItem(ZUGANG_SCHLUESSEL, wert.trim());
}

async function anfrage<T>(pfad: string, optionen: RequestInit = {}): Promise<T> {
  const kopf = new Headers(optionen.headers);
  const angemeldet = zugang();
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

// ── Wer ruft ────────────────────────────────────────────────────────────────

/** Für wen dieser Browser eingestellt ist — die Antwort kommt vom Server. */
export const werRuft = () => anfrage<Wer>('/zugang');

// ── Verwaltung ──────────────────────────────────────────────────────────────

export const sprecherListe = () => anfrage<Sprecher[]>('/speakers');

export const sprecherAnlegen = (eingabe: { name: string; basismodell: string }) =>
  anfrage<Sprecher>('/speakers', alsJson(eingabe));

/** Neuen Zugang ausgeben. Ein vorhandener gilt danach nicht mehr. */
export const zugangAusgeben = (sprecher: string) =>
  anfrage<NeuerZugang>(`/speakers/${sprecher}/zugang`, { method: 'POST' });

export const zugangZurueckziehen = (sprecher: string) =>
  anfrage<void>(`/speakers/${sprecher}/zugang`, { method: 'DELETE' });

// ── Textquellen ─────────────────────────────────────────────────────────────

export const quellen = () => anfrage<Quelle[]>('/sources');

export const quelleAusLLM = (auftrag: { thema: string; altersspanne: string; umfang: number }) =>
  anfrage<Quelle>('/sources/llm', alsJson(auftrag));

export function quelleAusDatei(datei: File) {
  const formular = new FormData();
  formular.append('datei', datei);
  return anfrage<Quelle>('/sources/upload', { method: 'POST', body: formular });
}

export const quelleLoeschen = (quelle: string) =>
  anfrage<void>(`/sources/${quelle}`, { method: 'DELETE' });

/** Stilllegen oder wieder aufnehmen; gibt die Quelle im neuen Zustand zurück. */
export const quelleUmstellen = (quelle: string, aktiv: boolean) =>
  anfrage<Quelle>(`/sources/${quelle}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ aktiv }),
  });

/**
 * Der geschnittene Text einer Quelle als Klartext.
 *
 * Eigene Anfrage statt `anfrage`: Hier kommt kein JSON zurück. Nötig ist das,
 * weil die API einen Zugang verlangt — ein `window.open` auf die Adresse
 * schickte keinen mit und liefe in ein 401.
 */
export async function quelleText(quelle: string): Promise<string> {
  const kopf = new Headers();
  const angemeldet = zugang();
  if (angemeldet) kopf.set('Authorization', `Bearer ${angemeldet}`);

  const antwort = await fetch(`/api/sources/${quelle}/text`, { headers: kopf });
  if (!antwort.ok) {
    const rumpf = await antwort.json().catch(() => null);
    throw new ApiFehler(antwort.status, rumpf?.detail ?? `Fehler ${antwort.status}`);
  }
  return antwort.text();
}

// ── Aufnehmen ───────────────────────────────────────────────────────────────

export const sitzungBeginnen = () =>
  anfrage<{ id: string; begonnen: string }>('/sessions', { method: 'POST' });

export const naechsteEinheit = (sitzung: string | null, zufall = false) => {
  const suche = new URLSearchParams();
  if (sitzung) suche.set('session', sitzung);
  if (zufall) suche.set('zufall', 'true');
  const anhang = suche.toString();
  return anfrage<Naechste>(`/prompts/next${anhang ? `?${anhang}` : ''}`);
};

export function aufnahmeSenden(eingabe: {
  audio: Blob;
  prompt_id: string;
  modus: string;
  session: string | null;
}) {
  const formular = new FormData();
  formular.append('audio', eingabe.audio, 'aufnahme.webm');
  formular.append('prompt_id', eingabe.prompt_id);
  formular.append('modus', eingabe.modus);
  if (eingabe.session) formular.append('session', eingabe.session);
  return anfrage<Aufnahme>('/recordings', { method: 'POST', body: formular });
}

export const aufnahmeVerwerfen = (aufnahme: string) =>
  anfrage<void>(`/recordings/${aufnahme}`, { method: 'DELETE' });

// ── Fortschritt ─────────────────────────────────────────────────────────────

export const fortschritt = () => anfrage<Fortschritt>('/progress');
