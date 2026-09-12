/**
 * Der einzige Ort, an dem diese App mit ihrem Backend spricht.
 *
 * Jede Anfrage trägt den Zugang des Sprechers - denselben, den „hören" für ihn
 * ausgegeben hat und der in demselben Browser liegt (siehe `$ui/zugang`). Den
 * Sprecher nennt trotzdem keine Anfrage: Der Server leitet ihn aus dem Zugang
 * ab (`backend/deps.py`). Ein Modell gehört zu genau einem Menschen, und wer
 * hier eines trainiert, trainiert sein eigenes.
 */

import { alsJson, api } from '$ui/api';
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
  /** Ob der Server vor einem Auftrag den Trainerschlüssel sehen will. */
  schluessel_noetig: boolean;
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

/** Ein Maß in der Modelltabelle, beschriftet vom Server. */
export type Mass = {
  schluessel: string;
  name: string;
  kurz: string;
  erklaerung: string;
  /** Ob ein hoher Wert der bessere ist - die Fehlerraten sind andersherum. */
  hoch_ist_gut: boolean;
  einheit: string;
  stellen: number;
};

/** Eine Fassung der Aufnahme: Original oder eine der drei Abwandlungen. */
export type Fassung = {
  schluessel: string;
  name: string;
  erklaerung: string;
};

/** Eine Zeile der Modelltabelle: ein Grundmodell oder ein trainierter Stand. */
export type Modell = {
  ref: string;
  /** grundmodell | trainiert */
  art: string;
  name: string;
  herkunft: string;
  basismodell: string;
  methode: string | null;
  daten: string | null;
  erstellt: string | null;
  version: string | null;
  job_id: string | null;
  freigegeben: boolean;
  /** Worauf gemessen wurde: `cuda/int8_float16`, `cpu/int8`, leer = unbekannt oder gemischt. */
  rechenwerk: string;
  /** Fassung → Maß → Wert. Leer heißt: auf den gemeinsamen Testaufnahmen nichts. */
  werte: Record<string, Record<string, number>>;
  /** Fassung → wie viele Messeinheiten in diesem Mittel stecken. */
  einheiten: Record<string, number>;
};

export type Modelluebersicht = {
  modelle: Modell[];
  masse: Mass[];
  fassungen: Fassung[];
  freigegeben: string;
  testaufnahmen: number;
  gemeinsame_einheiten: number;
  /** `false` heißt: Die Zahlen stehen nicht auf demselben Boden. */
  vergleichbar: boolean;
  /** `false` heißt: Die Rechenzeiten stammen von verschiedenen Maschinen. */
  zeit_vergleichbar: boolean;
  hinweis: string;
};

/**
 * Was „schreiben" gerade lädt - und ob es vorher aussteuert.
 *
 * Die Auskunft kommt aus der API von „schreiben" und nicht aus dieser App: Dort
 * wird diktiert, dort liegt der Schalter, und eine zweite Wahrheit darüber wäre
 * eine zu viel. Dass die Modellübersicht sie trotzdem zeigt, hat denselben
 * Grund wie alles andere auf dieser Seite - hier steht die eine Antwort auf
 * „womit spreche ich?".
 */
export type Diktatmodell = {
  sprecher_id: string;
  ref: string;
  basismodell: string;
  trainiert: boolean;
  aussteuern: boolean;
  beschriftung: string;
};

/**
 * Alle Wege dieser App liegen unter ihrem Pfad, die API eingeschlossen.
 * `BASE_URL` ist das `base` aus der Vite-Konfiguration (`/lernen/`) - so steht
 * der Ort an einer Stelle und nicht zweimal. Wie eine Anfrage hinausgeht und
 * wie ein Fehlschlag aussieht, steht in `$ui/api` - einmal für alle drei Apps.
 */
const { anfrage } = api(`${import.meta.env.BASE_URL}api`);

export const aufteilung = () => anfrage<Aufteilung>('/aufteilung');

export const laeufe = () => anfrage<Laufliste>('/laeufe');

export const lauf = (jobId: string) => anfrage<Laufeinzeln>(`/laeufe/${jobId}`);

/**
 * Einen Lauf beauftragen - die einzige Anfrage dieser App, die ein zweites
 * Geheimnis trägt.
 *
 * Der Schlüssel steht in einem eigenen Kopf und nicht in `Authorization`:
 * Dort liegt der Zugang des Sprechers, aus dem der Server ableitet, wessen
 * Modell entsteht. Das eine gegen das andere zu tauschen hieße, entweder für
 * niemanden zu trainieren oder ohne Erlaubnis.
 */
export const beauftrage = (methode: string, daten: string, schluessel: string) =>
  anfrage<Lauf>('/laeufe', {
    ...alsJson({ methode, daten }),
    headers: { 'Content-Type': 'application/json', 'X-Trainer-Key': schluessel },
  });

export const brichAb = (jobId: string) =>
  anfrage<Lauf>(`/laeufe/${jobId}/abbruch`, { method: 'POST' });

/** Einen Lauf ersatzlos entfernen - samt dem Modell, das aus ihm entstand. */
export const loescheLauf = (jobId: string) =>
  anfrage<{ job_id: string; version: string; war_freigegeben: boolean }>(
    `/laeufe/${jobId}`,
    { method: 'DELETE' },
  );

export const modelle = () => anfrage<Modelluebersicht>('/modelle');

/** Dieses Modell freigeben - leere Kennung nimmt die Freigabe zurück. */
export const gibFrei = (ref: string) =>
  anfrage<Modelluebersicht>('/modelle/freigabe', alsJson({ ref }));

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

// Ausdrücklich die API von „hören": Dort liegt der Korpus, dort wird der
// Zugang geprüft, und dort steht der Name. Eine eigene Auskunft hätte eine
// zweite Wahrheit über denselben Menschen ergeben. Ein zweiter Ort ist seit
// `$ui/api` eine zweite Zeile und kein zweiter Anlauf - und nebenbei kommt der
// Satz, mit dem der Server einen Zugang abweist, jetzt auch hier an statt
// eines bloßen „Fehler 401".
const hoeren = api('/api');

export const werRuft = () => hoeren.anfrage<Wer>('/zugang');

/**
 * Wie bei `werRuft` die API einer anderen App - hier die von „schreiben". Sie
 * liegt unter derselben Domain, und der Zugang ist derselbe.
 */
const schreiben = api('/schreiben/api');

/**
 * Scheitert der Aufruf, gibt es `null` statt eines Fehlers: Diese App steht
 * auch ohne „schreiben" (wer nur trainiert und misst, braucht es nicht), und
 * eine Fehlermeldung für eine Karte, die dann schlicht entfällt, wäre eine
 * Warnung vor nichts.
 */
async function beiSchreiben<T>(optionen: RequestInit = {}): Promise<T | null> {
  try {
    return await schreiben.anfrage<T>('/model', optionen);
  } catch {
    return null;
  }
}

export const diktatmodell = () => beiSchreiben<Diktatmodell>();

export const aussteuernSetzen = (aussteuern: boolean) =>
  beiSchreiben<Diktatmodell>(alsJson({ aussteuern }, 'PUT'));
