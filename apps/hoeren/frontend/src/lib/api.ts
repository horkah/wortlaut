/**
 * Der einzige Ort, an dem diese App mit dem Backend spricht.
 *
 * Den Sprecher nennt keine Anfrage mehr: Der Server leitet ihn aus dem
 * vorgelegten Zugang ab (siehe backend/deps.py). Der Zugang ist entweder der
 * eines Sprechers — `<sprecher_id>.<geheimnis>`, gekommen über einen Link —,
 * der Verwaltertoken oder der Aufsichtstoken.
 *
 * Genau eine Ausnahme gibt es: Die Wege unter `/api/admin/…` nennen ihren
 * Sprecher in der Adresse. Sie gehören der Aufsicht, und die hat keinen
 * eigenen — sie sieht über alle hinweg (siehe backend/api/admin.py).
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
  art: 'sprecher' | 'verwaltung' | 'aufsicht';
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

/**
 * Eine Anfrage mit Zugang — die einzige Stelle, die ihn anhängt und einen
 * Fehlschlag auswertet. Zurück kommt die rohe Antwort, denn nicht alles hier
 * ist JSON: Texte und Archive gehen denselben Weg.
 */
async function hole(pfad: string, optionen: RequestInit = {}): Promise<Response> {
  const kopf = new Headers(optionen.headers);
  const angemeldet = zugang();
  if (angemeldet) kopf.set('Authorization', `Bearer ${angemeldet}`);

  const antwort = await fetch(`/api${pfad}`, { ...optionen, headers: kopf });
  if (!antwort.ok) {
    // FastAPI antwortet mit {"detail": …}; bei Netzfehlern bleibt der Status.
    const rumpf = await antwort.json().catch(() => null);
    throw new ApiFehler(antwort.status, rumpf?.detail ?? `Fehler ${antwort.status}`);
  }
  return antwort;
}

async function anfrage<T>(pfad: string, optionen: RequestInit = {}): Promise<T> {
  const antwort = await hole(pfad, optionen);
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
 * Über `hole` statt `anfrage`, weil hier kein JSON zurückkommt. Ein
 * `window.open` auf die Adresse ginge nicht: Die API verlangt einen Zugang im
 * Kopf der Anfrage und liefe sonst in ein 401.
 */
export async function quelleText(quelle: string): Promise<string> {
  return (await hole(`/sources/${quelle}/text`)).text();
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

// ── Aufsicht ────────────────────────────────────────────────────────────────
//
// Alles hier hängt am `WORTLAUT_ADMIN_TOKEN` des Servers. Ohne ihn antwortet
// jeder dieser Wege mit 401 — auch in der Entwicklung.

export type Kennzahlen = {
  aufnahmen: number;
  verworfen: number;
  sekunden: number;
  quellen: number;
  einheiten: number;
  sitzungen: number;
  bytes_audio: number;
};

export type Uebersicht = Sprecher & { kennzahlen: Kennzahlen };

export type AufsichtQuelle = {
  id: string;
  art: string;
  titel: string;
  parameter: Record<string, unknown>;
  aktiv: boolean;
  einheiten: number;
  erstellt: string;
};

export type AufsichtSitzung = {
  id: string;
  begonnen: string;
  zuletzt_aktiv: string;
  aufnahmen: number;
};

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
};

export type Einsicht = {
  sprecher: Uebersicht;
  quellen: AufsichtQuelle[];
  sitzungen: AufsichtSitzung[];
};

export type Aufnahmenseite = { gesamt: number; ab: number; aufnahmen: AufsichtAufnahme[] };

export const alleSprecher = () => anfrage<Uebersicht[]>('/admin/speakers');

export const einsicht = (sprecher: string) => anfrage<Einsicht>(`/admin/speakers/${sprecher}`);

export const aufsichtAufnahmen = (sprecher: string, ab = 0) =>
  anfrage<Aufnahmenseite>(`/admin/speakers/${sprecher}/recordings?ab=${ab}`);

export const sprecherUmbenennen = (sprecher: string, name: string) =>
  anfrage<Uebersicht>(`/admin/speakers/${sprecher}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });

/**
 * Löschen verlangt die Kennung ein zweites Mal — einmal als Ziel, einmal als
 * Absicht. Der Server prüft das; hier steht es, damit kein Aufruf ohne
 * gebaut werden kann.
 */
export const aufnahmeLoeschen = (sprecher: string, aufnahme: string) =>
  anfrage<void>(`/admin/speakers/${sprecher}/recordings/${aufnahme}`, { method: 'DELETE' });

export const alleAufnahmenLoeschen = (sprecher: string) =>
  anfrage<{ geloescht: number }>(
    `/admin/speakers/${sprecher}/recordings?bestaetigung=${encodeURIComponent(sprecher)}`,
    { method: 'DELETE' },
  );

export const sprecherLoeschen = (sprecher: string) =>
  anfrage<{ geloescht: string[]; zu_pruefen: string[] }>(
    `/admin/speakers/${sprecher}?bestaetigung=${encodeURIComponent(sprecher)}`,
    { method: 'DELETE' },
  );

/** Die Adresse einer Aufnahme zum Abhören — mit Zugang, deshalb über `blob()`. */
export const aufnahmeAudio = (sprecher: string, aufnahme: string) =>
  blob(`/admin/speakers/${sprecher}/recordings/${aufnahme}/audio`);

// ── Ausleiten ───────────────────────────────────────────────────────────────

/**
 * Eine Datei vom Server holen und dem Browser zum Speichern geben.
 *
 * Warum nicht schlicht ein Link: Diese Wege verlangen einen Zugang im Kopf der
 * Anfrage, und ein `window.open` schickte keinen mit — es liefe in ein 401.
 * Also wird geholt, in einen Blob gelegt und ein unsichtbarer Verweis
 * angeklickt.
 *
 * Der Preis: Die Datei liegt kurz im Arbeitsspeicher des Browsers. Für einen
 * Korpus von einigen hundert Megabyte geht das; wer einen sehr großen Bestand
 * wegsichert, nimmt besser `curl` (siehe docs/betrieb.md).
 */
export async function lade(pfad: string): Promise<void> {
  const [inhalt, dateiname] = await blobMitNamen(pfad);
  const adresse = URL.createObjectURL(inhalt);
  const verweis = document.createElement('a');
  verweis.href = adresse;
  verweis.download = dateiname;
  verweis.click();
  // Erst freigeben, wenn der Browser den Download übernommen hat.
  setTimeout(() => URL.revokeObjectURL(adresse), 10_000);
}

export const sicherungSprecher = (sprecher: string) =>
  lade(`/admin/speakers/${sprecher}/sicherung`);

export const datensatzSprecher = (sprecher: string) =>
  lade(`/admin/speakers/${sprecher}/datensatz`);

export const sicherungGesamt = () => lade('/admin/sicherung');

/** Wie `anfrage`, aber für alles, was kein JSON ist. */
async function blob(pfad: string): Promise<Blob> {
  return (await blobMitNamen(pfad))[0];
}

async function blobMitNamen(pfad: string): Promise<[Blob, string]> {
  const antwort = await hole(pfad);
  // Den Namen bestimmt der Server (er kennt die Zeitmarke); ohne Angabe bleibt
  // der letzte Teil des Pfades.
  const angabe = antwort.headers.get('content-disposition') ?? '';
  const treffer = angabe.match(/filename="?([^";]+)"?/);
  return [await antwort.blob(), treffer?.[1] ?? (pfad.split('/').pop() || 'wortlaut')];
}
