/**
 * Der einzige Ort, an dem diese App mit ihrem Backend spricht.
 *
 * Jede Anfrage trägt den Zugang des Sprechers - denselben, den „hören" für ihn
 * ausgegeben hat und der in demselben Browser liegt (siehe `$ui/zugang`). Den
 * Sprecher nennt trotzdem keine Anfrage: Der Server leitet ihn aus dem Zugang
 * ab (`backend/deps.py`). Ein Modell gehört zu genau einem Menschen, und wer
 * hier eines trainiert, trainiert sein eigenes.
 */

import { mitZugang } from '$ui/zugang';
export { setzeZugang, zugang } from '$ui/zugang';

/** Ein Teil der Aufteilung, beschriftet vom Server. */
export type Teil = {
  schluessel: string;
  name: string;
  erklaerung: string;
};

export type Probe = {
  /** Der Platz im Muster - daran hängt, welcher Teil zugeteilt wurde. */
  nummer: number;
  aufnahme_id: string;
  teil: string;
  dauer_s: number;
  erstellt: string;
  text: string;
};

export type Aufteilung = {
  teile: Teil[];
  muster: string[];
  anzahl: Record<string, number>;
  sekunden: Record<string, number>;
  proben: Probe[];
  /** Zuteilungen zu gelöschten Aufnahmen - der Platz bleibt vergeben. */
  verwaist: number;
};

/** Eine Wahlmöglichkeit beim Beauftragen: Methode oder Datensatz. */
export type Wahl = {
  schluessel: string;
  name: string;
  erklaerung: string;
};

/** Der Modellstand, der aus einem Lauf hervorging - er ginge beim Löschen mit. */
export type StandHinweis = {
  version: string;
  freigegeben: boolean;
};

export type Lauf = {
  job_id: string;
  sprecher_id: string;
  methode: string;
  daten: string;
  basismodell: string;
  erstellt: string;
  /** wartet | laeuft | fertig | gescheitert | abgebrochen */
  status: string;
  stufe: string;
  /** 0 bis 1; `null`, solange der Trainer die Schrittzahl nicht genannt hat. */
  anteil: number | null;
  aufnahmen: number;
  zeilen: Record<string, number>;
  version: string | null;
  fehler: string | null;
  /** `null`, solange kein Modell aus diesem Lauf entstanden ist. */
  stand: StandHinweis | null;
  /** Ein rechnender Lauf lässt sich nicht löschen - ein anderer Container schreibt dort. */
  loeschbar: boolean;
};

export type Punkt = {
  schritt: number;
  epoche: number;
  verlust: number | null;
  lernrate: number | null;
  wer: number | null;
};

export type Gegenueber = {
  mass: string;
  grundlinie: number | null;
  trainiert: number | null;
  besser: boolean | null;
  anzahl: number;
};

export type Laufliste = {
  laeufe: Lauf[];
  methoden: Wahl[];
  datensaetze: Wahl[];
  basismodell: string;
  bereit: boolean;
  hinweis: string;
  /** Wie viele brauchbare Aufnahmen es inzwischen gibt. */
  aufnahmen_jetzt: number;
  /** Wie viele davon der jüngste fertige Lauf noch nicht kannte. */
  aufnahmen_neu: number;
};

export type Laufeinzeln = {
  lauf: Lauf;
  methoden: Wahl[];
  datensaetze: Wahl[];
  kurve_training: Punkt[];
  kurve_validierung: Punkt[];
  /** Fassung → die Maße, jeweils vorher und nachher. */
  vergleich: Record<string, Gegenueber[]>;
  protokoll: string;
};

export type Modellstand = {
  id: string;
  version: string;
  basismodell: string;
  methode: string;
  daten: string;
  erstellt: string;
  status: string;
  wer: number | null;
  genauigkeit: number | null;
  test_einheiten: number | null;
  job_id: string | null;
  beschriftung: string;
};

/**
 * Alle Wege dieser App liegen unter ihrem Pfad, die API eingeschlossen.
 * `BASE_URL` ist das `base` aus der Vite-Konfiguration (`/lernen/`) - so steht
 * der Ort an einer Stelle und nicht zweimal.
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
    const rumpf = await antwort.json().catch(() => null);
    throw new ApiFehler(antwort.status, rumpf?.detail ?? `Fehler ${antwort.status}`);
  }
  return antwort.status === 204 ? (undefined as T) : ((await antwort.json()) as T);
}

function alsJson(inhalt: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(inhalt),
  };
}

export const aufteilung = () => anfrage<Aufteilung>('/aufteilung');

export const laeufe = () => anfrage<Laufliste>('/laeufe');

export const lauf = (jobId: string) => anfrage<Laufeinzeln>(`/laeufe/${jobId}`);

export const beauftrage = (methode: string, daten: string) =>
  anfrage<Lauf>('/laeufe', alsJson({ methode, daten }));

export const brichAb = (jobId: string) =>
  anfrage<Lauf>(`/laeufe/${jobId}/abbruch`, { method: 'POST' });

/** Einen Lauf ersatzlos entfernen - samt dem Modell, das aus ihm entstand. */
export const loescheLauf = (jobId: string) =>
  anfrage<{ job_id: string; version: string; war_freigegeben: boolean }>(
    `/laeufe/${jobId}`,
    { method: 'DELETE' },
  );

export const modelle = () => anfrage<{ staende: Modellstand[] }>('/modelle');

export const gibFrei = (version: string) =>
  anfrage<{ staende: Modellstand[] }>(`/modelle/${version}/freigabe`, { method: 'POST' });

/**
 * Wer der Server in diesem Browser sieht - die Auskunft von „hören".
 *
 * `art` ist eng getippt und nicht `string`: Der Zustand der Oberfläche hängt
 * daran (siehe `zustand.svelte.ts`), und ein Tippfehler in einem Vergleich
 * soll auffallen, bevor die Seite leer bleibt.
 */
export type Wer = {
  art: 'sprecher' | 'verwaltung' | 'aufsicht';
  sprecher_id: string;
  name: string;
};

export async function werRuft(): Promise<Wer> {
  // Ausdrücklich die API von „hören": Dort liegt der Korpus, dort wird der
  // Zugang geprüft, und dort steht der Name. Eine eigene Auskunft hier wäre
  // eine zweite Wahrheit über denselben Menschen.
  const antwort = await fetch('/api/zugang', { headers: mitZugang() });
  if (!antwort.ok) throw new ApiFehler(antwort.status, `Fehler ${antwort.status}`);
  return (await antwort.json()) as Wer;
}
