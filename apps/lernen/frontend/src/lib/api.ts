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
// Wer der Server in diesem Browser sieht - die Form steht in `$ui/wer`, weil
// alle drei Apps dieselbe Antwort lesen. Diese hier bekommt sie von „hören".
import type { Wer } from '$ui/wer';
export { setzeZugang, zugang } from '$ui/zugang';

/**
 * Wie der Korpus auf die Faltungen der Kreuzvalidierung fällt.
 *
 * Ohne Liste der Aufnahmen: Die steht unter „Meine Daten", einmal und
 * vollständig (siehe `routes/Aufteilung.svelte`).
 */
export type Aufteilung = {
  /** Wie viele Faltungen gerechnet werden - die Zahl kommt vom Server. */
  faltungen: number;
  aufnahmen: number;
  sekunden: number;
  /** Faltung (als Zeichenkette) → wie viele Aufnahmen darin liegen. */
  je_faltung: Record<string, number>;
  /** Ob jede Faltung wenigstens eine Aufnahme hat. */
  genug: boolean;
};

/**
 * Ein Grundmodell zur Wahl - und was es verträgt.
 *
 * `methoden` steht dabei, damit die Oberfläche die unmögliche Kombination gar
 * nicht erst anbietet: Volles Feintuning von `medium` sprengt den Speicher der
 * Karte (siehe `wortlaut/laeufe.py`).
 */
export type Grundmodell = {
  schluessel: string;
  name: string;
  erklaerung: string;
  methoden: string[];
};

/** Eine Wahlmöglichkeit beim Beauftragen - eine der Achsen eines Laufs. */
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
  /** Was am Ende mit den Gewichten geschah: bester | mittel | interpoliert | beides. */
  abschluss: string;
  /** Womit die Trainingsproben abgewandelt wurden: keine | masken | umgebung | voll. */
  augmentierung: string;
  /** Wie lange trainiert wurde: fest | geduldig. */
  dauer: string;
  /** Ob die Geschwindigkeit gesucht wurde oder die des Profils galt. */
  tempowahl: string;
  /**
   * Die Geschwindigkeit, mit der dieser Lauf wirklich gerechnet hat.
   * `null` heißt bei `optimal`: wird noch gesucht.
   */
  tempo: number | null;
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
  /** Der kurze Code des Standes aus diesem Lauf (`K7M2Q`); null, solange keiner da ist. */
  kennung: string | null;
  fehler: string | null;
  /** `null`, solange kein Modell aus diesem Lauf entstanden ist. */
  stand: StandHinweis | null;
  /** Ein rechnender Lauf lässt sich nicht löschen - ein anderer Container schreibt dort.
   *  Ein hängender schon: Dort schreibt seit einer Viertelstunde niemand mehr. */
  loeschbar: boolean;
  /** Sagt `laeuft`, hat aber seit einer Viertelstunde nichts geschrieben. */
  haengt: boolean;
  /** Seit wann nichts mehr geschrieben wurde, in Sekunden - nur bei `laeuft`. */
  stillstand_s: number | null;
};

export type Punkt = {
  schritt: number;
  epoche: number;
  verlust: number | null;
  lernrate: number | null;
  wer: number | null;
};

/**
 * Ein Vertrauensbereich um einen Mittelwert - gerechnet in
 * `wortlaut/streuung.py`, blockweise über die Aufnahmen.
 *
 * `mittel` ist **derselbe** Wert, der auch ohne Bereich in der Tabelle steht.
 * Der Bereich tritt daneben, nicht an seine Stelle.
 */
export type Intervall = {
  mittel: number;
  unten: number;
  oben: number;
  /** Der Standardfehler des Mittelwerts - die Streuung der Ziehungen. */
  streuung: number;
  /** Über wie viele Aufnahmen gezogen wurde und wie viele Messungen darin lagen. */
  bloecke: number;
  einheiten: number;
  /** Womit gerechnet wurde, z. B. `bootstrap/aufnahme/2000/0.95/20260913`. */
  marke: string;
};

/** Zwei Modelle auf denselben Aufnahmen, gepaart verglichen. */
export type Unterschied = {
  /** Dieses Modell minus das Vergleichsmodell. */
  differenz: number;
  unten: number;
  oben: number;
  /** Zweiseitiger Bootstrap-p-Wert zur Nullhypothese „kein Unterschied". */
  p: number;
  /** Ob der Bereich die Null ausschließt - nur dann ist etwas gezeigt. */
  belegt: boolean;
  bloecke: number;
  einheiten: number;
  marke: string;
};

export type Gegenueber = {
  mass: string;
  baseline: number | null;
  trainiert: number | null;
  besser: boolean | null;
  anzahl: number;
  /** Nur bei angefordertem Bereich; sonst `null`. */
  unterschied: Unterschied | null;
  bereich_baseline: Intervall | null;
  bereich_trainiert: Intervall | null;
};

export type Laufliste = {
  laeufe: Lauf[];
  methoden: Wahl[];
  datensaetze: Wahl[];
  abschluesse: Wahl[];
  augmentierungen: Wahl[];
  dauern: Wahl[];
  tempi: Wahl[];
  grundmodelle: Grundmodell[];
  /** Die Vorgabe, worauf trainiert wird. */
  basismodell: string;
  /** Wie viele Faltungen ein Lauf rechnet. */
  faltungen: number;
  bereit: boolean;
  hinweis: string;
  /** Ob der Server vor einem Auftrag den Trainerschlüssel sehen will. */
  schluessel_noetig: boolean;
  /** Wie viele brauchbare Aufnahmen es inzwischen gibt. */
  aufnahmen_jetzt: number;
  /** Wie viele davon der jüngste fertige Lauf noch nicht kannte. */
  aufnahmen_neu: number;
};

/** Ein Feld des Steckbriefs - Begriff, Wert und, wo nötig, die Einordnung. */
export type SteckbriefZeile = {
  begriff: string;
  wert: string;
  /** Was den Wert einordnet: Einheit, Herkunft, Vorbehalt. Leer, wo er für sich steht. */
  hinweis: string;
};

export type Laufeinzeln = {
  lauf: Lauf;
  /** Jede Achse benannt, auch die auf Vorgabe - vom Server beschriftet. */
  steckbrief: SteckbriefZeile[];
  methoden: Wahl[];
  datensaetze: Wahl[];
  abschluesse: Wahl[];
  augmentierungen: Wahl[];
  dauern: Wahl[];
  tempi: Wahl[];
  grundmodelle: Grundmodell[];
  kurve_training: Punkt[];
  kurve_validierung: Punkt[];
  /** Fassung → die Maße, jeweils vorher und nachher. */
  vergleich: Record<string, Gegenueber[]>;
  protokoll: string;
  /** Welche Blockart gerechnet wurde: `aus`, `aufnahme` oder `einheit`. */
  intervall: string;
  streuung_marke: string;
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

/** Eine Fassung der Aufnahme: das Original oder eine seiner Abwandlungen. */
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
  /** Der kurze Code dieses Standes (`K7M2Q`); null bei einem Grundmodell. */
  kennung: string | null;
  job_id: string | null;
  freigegeben: boolean;
  /** Worauf gemessen wurde: `cuda/int8_float16`, `cpu/int8`, leer = unbekannt oder gemischt. */
  rechenwerk: string;
  /** Fassung → Maß → Wert. Leer heißt: auf den gemeinsamen Testaufnahmen nichts. */
  werte: Record<string, Record<string, number>>;
  /** Fassung → wie viele Messeinheiten in diesem Mittel stecken. */
  einheiten: Record<string, number>;
  /** Fassung → Maß → Vertrauensbereich. Leer, solange keiner angefordert wurde. */
  intervalle: Record<string, Record<string, Intervall>>;
  /** Fassung → Maß → der gepaarte Abstand zum gewählten Vergleichsmodell. */
  unterschied: Record<string, Record<string, Unterschied>>;
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
  /** Welche Blockart gerechnet wurde: `aus`, `aufnahme` oder `einheit`. */
  intervall: string;
  /** Gegen welches Modell gepaart verglichen wurde; leer heißt: gegen keines. */
  vergleich_mit: string;
  streuung_marke: string;
};

/**
 * Was „schreiben" gerade lädt.
 *
 * Die Auskunft kommt aus der API von „schreiben" und nicht aus dieser App: Dort
 * wird diktiert, und eine zweite Wahrheit darüber wäre eine zu viel. Dass die
 * Modellübersicht sie trotzdem zeigt, hat denselben Grund wie alles andere auf
 * dieser Seite - hier steht die eine Antwort auf „womit spreche ich?".
 */
export type Diktatmodell = {
  sprecher_id: string;
  ref: string;
  basismodell: string;
  trainiert: boolean;
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

/**
 * Ein Lauf im Einzelnen. `intervall` schaltet die Vertrauensbereiche dazu:
 * `aus` (Vorgabe, die Antwort von vorher), `aufnahme` (blockweise gezogen -
 * die richtige Wahl) oder `einheit` (naiv je Messung, zum Vergleich mit der
 * Literatur).
 */
export const lauf = (jobId: string, intervall = 'aus') =>
  anfrage<Laufeinzeln>(`/laeufe/${jobId}?intervall=${encodeURIComponent(intervall)}`);

/**
 * Einen Lauf beauftragen - die einzige Anfrage dieser App, die ein zweites
 * Geheimnis trägt.
 *
 * Der Schlüssel steht in einem eigenen Kopf und nicht in `Authorization`:
 * Dort liegt der Zugang des Sprechers, aus dem der Server ableitet, wessen
 * Modell entsteht. Das eine gegen das andere zu tauschen hieße, entweder für
 * niemanden zu trainieren oder ohne Erlaubnis.
 */
export type Bestellung = {
  methode: string;
  daten: string;
  abschluss: string;
  augmentierung: string;
  dauer: string;
  tempowahl: string;
  grundmodell: string;
};

/**
 * Die Achsen als Objekt und nicht als Reihe von Argumenten: Es sind inzwischen
 * sieben, alle vom selben Typ, und zwei vertauschte fielen niemandem auf -
 * weder dem Übersetzer noch dem Leser. Der Schlüssel steht daneben, weil er
 * kein Teil der Bestellung ist, sondern die Erlaubnis dazu.
 */
export const beauftrage = (bestellung: Bestellung, schluessel: string) =>
  anfrage<Lauf>('/laeufe', {
    ...alsJson(bestellung),
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

/**
 * Die Modelltabelle. Ohne Parameter genau die Antwort von vorher - die Zahlen
 * hängen nicht davon ab, ob man einen Bereich dazubestellt.
 *
 * `vergleichMit` nennt ein Modell, gegen das jede andere Zeile gepaart
 * antritt. Das ist die schärfere Frage als zwei Bereiche nebeneinander: Beide
 * Modelle haben dieselben Aufnahmen gehört, und der gemeinsame Anteil fällt in
 * der Differenz heraus.
 */
const modellabfrage = (intervall: string, vergleichMit: string) =>
  `?intervall=${encodeURIComponent(intervall)}&vergleich_mit=${encodeURIComponent(vergleichMit)}`;

export const modelle = (intervall = 'aus', vergleichMit = '') =>
  anfrage<Modelluebersicht>(`/modelle${modellabfrage(intervall, vergleichMit)}`);

/** Dieses Modell freigeben - leere Kennung nimmt die Freigabe zurück. */
export const gibFrei = (ref: string, intervall = 'aus', vergleichMit = '') =>
  anfrage<Modelluebersicht>(
    `/modelle/freigabe${modellabfrage(intervall, vergleichMit)}`,
    alsJson({ ref }),
  );

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

