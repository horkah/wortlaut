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
import { mitSchluessel } from '$ui/schluessel.svelte';
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
  /** Die LoRA-Zusätze, die auf die Karte passen, als `ziele/rang`. */
  lora: string[];
  /** Sein Anfang im Optionscode: `S`, `M`, `L3`. */
  code: string;
};

/** Eine Wahlmöglichkeit beim Beauftragen - eine der Achsen eines Laufs. */
export type Wahl = {
  schluessel: string;
  name: string;
  erklaerung: string;
  /** Ihr Glied im Optionscode; leer bei der Vorgabe einer Achse. */
  code: string;
};

/** Der Modellstand, der aus einem Lauf hervorging - er ginge beim Löschen mit. */
export type StandHinweis = {
  version: string;
  freigegeben: boolean;
};

export type Lauf = {
  job_id: string;
  sprecher_id: string;
  /** Alle Achsen als Optionscode, etwa `ML-A-C` (`wortlaut/laeufe.optionscode`). */
  code: string;
  methode: string;
  /** Ob der Lauf auch auf Kopien mit Rauschen lernte (Code `A`). */
  rauschkopie: boolean;
  /** Nur bei LoRA: wo der Zusatz sitzt (qv | alle | encoder | decoder) und sein Rang. */
  lora_ziele: string;
  lora_rang: string;
  /** Worauf gelernt wurde: alle | kern (`wortlaut/laeufe.py`, „Die Auswahl"). */
  auswahl: string;
  /** Womit Korrekturen zählen: 0.5 | 0.25 | 0.75 | 1.0 | verlauf. */
  korrekturgewicht: string;
  /** Ob unbestätigte Diktate selbst beschriftet mitlernen: aus | an. */
  selbsttraining: string;
  /** Was am Ende mit den Gewichten geschah: bester | mittel | interpoliert | beides. */
  abschluss: string;
  /** Womit die Trainingsproben abgewandelt wurden: keine | masken | umgebung | voll. */
  augmentierung: string;
  /** Wie lange trainiert wurde: fest | geduldig. */
  dauer: string;
  /** Woran Checkpoint, Abbruch und α gewählt wurden: verlust | wer. */
  steuerung: string;
  /** Das Encoder-Fenster im Training: voll | gekuerzt. */
  fenster: string;
  /** Ob die Geschwindigkeit gesucht wurde oder die des Profils galt. */
  tempowahl: string;
  /** Womit jede Erkennung beginnt: aus | vokabular. */
  kontext: string;
  /**
   * Die Geschwindigkeit, mit der dieser Lauf wirklich gerechnet hat.
   * `null` heißt bei `optimal`: wird noch gesucht.
   */
  tempo: number | null;
  /** Ob der Faktor endgültig ist - bei `optimal` erst nach der letzten Faltung. */
  tempo_endgueltig: boolean;
  /** Das Whisper-Modell darunter - gegen das misst die Baseline. */
  basismodell: string;
  /** Worauf aufgesetzt wurde, als Schlüssel der Wahl: Grundmodell oder trainierter Stand. */
  grundmodell: string;
  erstellt: string;
  /** wartet | laeuft | fertig | gescheitert | abgebrochen */
  status: string;
  stufe: string;
  /** Welche Faltung gerade rechnet (ab 0); null heißt: das Endmodell. */
  faltung: number | null;
  faltungen_gesamt: number;
  /** 0 bis 1; `null`, solange der Trainer die Schrittzahl nicht genannt hat. */
  anteil: number | null;
  aufnahmen: number;
  zeilen: Record<string, number>;
  /** Beim Kern: worauf gelernt wird - schon vor der Wahl. `null` heißt: auf allem. */
  /** Worauf gelernt wird; beim Kern vor der Wahl geschätzt. */
  trainingsproben: number;
  trainingsproben_geschaetzt: boolean;
  kern_aufnahmen: number | null;
  /** Wie viele Aufnahmen der Trainer vor der Wahl noch nachmisst. */
  kern_offen: number;
  version: string | null;
  /** Der kurze Code des Standes aus diesem Lauf (`K7M2Q`); null, solange keiner da ist. */
  kennung: string | null;
  fehler: string | null;
  /** `null`, solange kein Modell aus diesem Lauf entstanden ist. */
  stand: StandHinweis | null;
  /** Nicht, solange er rechnet; ein hängender schon. */
  loeschbar: boolean;
  /** Anhalten verlangt, der Trainer hat den Prozess aber noch nicht beendet. */
  wird_angehalten: boolean;
  /** Gescheitert oder angehalten - dann lässt er sich neu starten. */
  neu_startbar: boolean;
  /** Sagt `laeuft`, schreibt aber nichts mehr (`wortlaut/laeufe.py`). */
  haengt: boolean;
  /** Sekunden ohne Schreiben, nur bei `laeuft`. */
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
  /** Über wie viele Aufnahmen gezogen wurde. */
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
};

export type Laufliste = {
  laeufe: Lauf[];
  methoden: Wahl[];
  lora_ziele: Wahl[];
  lora_raenge: Wahl[];
  auswahlen: Wahl[];
  korrekturgewichte: Wahl[];
  selbsttraininge: Wahl[];
  abschluesse: Wahl[];
  augmentierungen: Wahl[];
  dauern: Wahl[];
  steuerungen: Wahl[];
  fenster: Wahl[];
  tempi: Wahl[];
  kontexte: Wahl[];
  grundmodelle: Grundmodell[];
  /** Die Vorgabe, worauf trainiert wird. */
  basismodell: string;
  /** Wie viele Faltungen ein Lauf rechnet. */
  faltungen: number;
  bereit: boolean;
  hinweis: string;
  /** Wie viele brauchbare Aufnahmen es gibt. */
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
  /** `zeit` heißt: `wert` ist ein ISO-Zeitstempel und wird hier formatiert. */
  art: string;
};

export type Laufeinzeln = {
  lauf: Lauf;
  /** Jede Achse benannt, auch die auf Vorgabe - vom Server beschriftet. */
  steckbrief: SteckbriefZeile[];
  methoden: Wahl[];
  lora_ziele: Wahl[];
  lora_raenge: Wahl[];
  auswahlen: Wahl[];
  korrekturgewichte: Wahl[];
  selbsttraininge: Wahl[];
  abschluesse: Wahl[];
  augmentierungen: Wahl[];
  dauern: Wahl[];
  steuerungen: Wahl[];
  fenster: Wahl[];
  tempi: Wahl[];
  kontexte: Wahl[];
  grundmodelle: Grundmodell[];
  kurve_training: Punkt[];
  kurve_validierung: Punkt[];
  /** Je Maß Baseline und trainiert. */
  vergleich: Gegenueber[];
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

/** Eine Zeile der Modelltabelle: ein Grundmodell oder ein trainierter Stand. */
export type Modell = {
  ref: string;
  /** grundmodell | trainiert */
  art: string;
  name: string;
  herkunft: string;
  basismodell: string;
  methode: string | null;
  erstellt: string | null;
  version: string | null;
  /** Der kurze Code dieses Standes (`K7M2Q`); null bei einem Grundmodell. */
  kennung: string | null;
  /** Ein Satz, wenn mit diesem Stand etwas nicht stimmt - sonst leer. */
  vorbehalt: string;
  /** „nur 5 von 6 Faltungen", wenn das Endmodell nicht alle mittelt - sonst leer. */
  faltungen_hinweis: string;
  job_id: string | null;
  freigegeben: boolean;
  /** Worauf gemessen wurde: `cuda/int8_float16`, `cpu/int8`, leer = unbekannt oder gemischt. */
  rechenwerk: string;
  /** Maß → Wert. Leer heißt: auf den gemeinsamen Testaufnahmen nichts. */
  werte: Record<string, number>;
  /** Wie viele Aufnahmen in diesen Mitteln stecken. */
  aufnahmen: number;
  /** Maß → Vertrauensbereich. Leer, solange keiner angefordert wurde. */
  intervalle: Record<string, Intervall>;
  /** Maß → der gepaarte Abstand zum gewählten Vergleichsmodell. */
  unterschied: Record<string, Unterschied>;
};

export type Modelluebersicht = {
  modelle: Modell[];
  masse: Mass[];
  freigegeben: string;
  messaufnahmen: number;
  gemeinsame_aufnahmen: number;
  /** `false` heißt: Die Zahlen stehen nicht auf demselben Boden. */
  vergleichbar: boolean;
  /** `false` heißt: Die Rechenzeiten stammen von verschiedenen Maschinen. */
  zeit_vergleichbar: boolean;
  hinweis: string;
  /** Ob Bereiche gerechnet wurden: `aus` oder `aufnahme`. */
  intervall: string;
  /** Gegen welches Modell gepaart verglichen wurde; leer heißt: gegen keines. */
  vergleich_mit: string;
  streuung_marke: string;
};

/**
 * Ein Grundmodell im Einzelnen (`api/modelle.grundmodell`).
 *
 * Zwei Steckbriefe: was das Modell ist (aus der Modellkarte von OpenAI) und
 * was davon hier liegt und läuft (aus dem Modellcache gelesen). Darunter die
 * Zeile aus der Modelltabelle - und die des freigegebenen Modells, wenn das
 * ein anderes ist.
 */
export type Grundmodelleinzeln = {
  name: string;
  titel: string;
  erklaerung: string;
  freigegeben: boolean;
  /** Leer bei einem Grundmodell ohne Modellkarte. */
  steckbrief: SteckbriefZeile[];
  vor_ort: SteckbriefZeile[];
  modell: Modell | null;
  freigabe: Modell | null;
  masse: Mass[];
  vergleichbar: boolean;
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

/** Ein Lauf im Einzelnen: Steckbrief, Kurven, Vergleich mit der Baseline. */
export const lauf = (jobId: string) => anfrage<Laufeinzeln>(`/laeufe/${jobId}`);

/**
 * Einen Lauf beauftragen - mit Trainerschlüssel im eigenen Kopf; in
 * `Authorization` liegt der Zugang, der sagt, wessen Modell entsteht.
 */
export type Bestellung = {
  methode: string;
  lora_ziele: string;
  lora_rang: string;
  auswahl: string;
  korrekturgewicht: string;
  selbsttraining: string;
  abschluss: string;
  augmentierung: string;
  dauer: string;
  steuerung: string;
  fenster: string;
  tempowahl: string;
  kontext: string;
  grundmodell: string;
};

/**
 * Die Achsen als Objekt: gleich typisierte Argumente ließen sich unbemerkt
 * vertauschen. Der Schlüssel ist Erlaubnis, nicht Bestellung - er kommt aus
 * den Zugangsdaten (`$ui/schluessel.svelte`).
 */
export const beauftrage = (bestellung: Bestellung) =>
  anfrage<Lauf>('/laeufe', {
    ...alsJson(bestellung),
    headers: mitSchluessel(['trainer'], { 'Content-Type': 'application/json' }),
  });

/** Anhalten: einen wartenden sofort, einen rechnenden über den Trainer. */
export const halteAn = (jobId: string) =>
  anfrage<Lauf>(`/laeufe/${jobId}/abbruch`, { method: 'POST' });

/**
 * Einen gescheiterten oder angehaltenen Lauf neu starten. Der neue ersetzt den
 * alten; verlangt wie das Beauftragen den Trainerschlüssel.
 */
export const starteNeu = (jobId: string) =>
  anfrage<Lauf>(`/laeufe/${jobId}/neustart`, {
    method: 'POST',
    headers: mitSchluessel(['trainer']),
  });

/** Einen Lauf ersatzlos entfernen - samt Modell, nur mit Trainerschlüssel. */
export const loescheLauf = (jobId: string) =>
  anfrage<{ job_id: string; version: string; war_freigegeben: boolean }>(
    `/laeufe/${jobId}`,
    { method: 'DELETE', headers: mitSchluessel(['trainer']) },
  );

/**
 * Die Modelltabelle; ein Bereich ändert die Zahlen nicht. `vergleichMit`
 * paart jede andere Zeile gegen ein Modell - schärfer als zwei Bereiche.
 */
const modellabfrage = (intervall: string, vergleichMit: string) =>
  `?intervall=${encodeURIComponent(intervall)}&vergleich_mit=${encodeURIComponent(vergleichMit)}`;

export const grundmodell = (name: string) =>
  anfrage<Grundmodelleinzeln>(`/modelle/grundmodell/${encodeURIComponent(name)}`);

export const modelle = (intervall = 'aus', vergleichMit = '') =>
  anfrage<Modelluebersicht>(`/modelle${modellabfrage(intervall, vergleichMit)}`);

/** Dieses Modell freigeben - leere Kennung nimmt die Freigabe zurück. */
export const gibFrei = (ref: string, intervall = 'aus', vergleichMit = '') =>
  anfrage<Modelluebersicht>(
    `/modelle/freigabe${modellabfrage(intervall, vergleichMit)}`,
    alsJson({ ref }),
  );

/**
 * Die API einer anderen App - hier die von „schreiben". Sie
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

