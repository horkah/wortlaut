/**
 * Vorlesen - vom Server, sonst vom Browser.
 *
 * Nachsprechen verändert Sprechtempo und Satzmelodie; eine so entstandene
 * Aufnahme wird deshalb als `nachgesprochen` markiert (siehe README).
 *
 * **Zwei Wege, und der erste ist der bessere.** Liegt auf dem Server eine
 * Stimme, ist der Satz dort schon gesprochen worden und kommt als Datei: Er
 * klingt dann auf jedem Gerät gleich - unter Linux wie auf dem iPhone -, und
 * wie gut er klingt, hängt am Modell und nicht am Betriebssystem
 * (`wortlaut/vorlesen.py`).
 *
 * Der zweite Weg ist die Web Speech API. Sie braucht keine Infrastruktur, und
 * sie bleibt, weil sie immer da ist: Solange keine Servestimme abgelegt wurde
 * oder eine Datei einmal nicht kommt, liest der Browser vor wie bisher. Welche
 * Stimmen es dort gibt und wie gut sie klingen, entscheidet allein das
 * Betriebssystem - dieselbe Seite klingt auf macOS natürlich und unter Linux
 * mit espeak-ng blechern. Von hier aus lässt sich das nicht ändern, nur zur
 * Auswahl stellen.
 */

import { api } from './api';

/** Etwas langsamer als normal: die Vorgabe soll nachgesprochen werden. */
export const TEMPO_VORGABE = 0.9;

/** Wie gesprochen wird - alles optional, alles mit brauchbarer Vorgabe. */
export type Sprechweise = {
  stimme?: SpeechSynthesisVoice | null;
  /** Faktor auf die Normalgeschwindigkeit, 1 ist unverändert. */
  tempo?: number;
  sprache?: string;
};

/**
 * Ist überhaupt eine Stimme für diese Sprache da?
 *
 * **`sprache` ohne Vorgabe, und das mit Absicht.** Hier stand `= 'de'`, und
 * damit bekam jeder Aufrufer die deutsche Antwort - auch der, der die Sprache
 * seines Profils gar nicht erst geholt hatte. Wer fragt, sagt jetzt, für wen
 * (`wortlaut/sprachen.py`).
 *
 * **`null` heißt „weiß ich nicht" und nicht „Deutsch".** So lange steht die
 * Antwort des Servers noch aus (`wer.ts`), und ein Verwalter hat gar keine
 * Sprache. Dann wird nicht gefiltert, statt eine zu erfinden: Lieber alle
 * Stimmen zeigen als die falschen.
 */
export function stimmeVerfuegbar(sprache: string | null): boolean {
  if (!('speechSynthesis' in window)) return false;
  const stimmen = window.speechSynthesis.getVoices();
  // Direkt nach dem Laden ist die Liste oft noch leer; dann lieber optimistisch
  // sein, als den Knopf grundlos auszublenden.
  if (stimmen.length === 0) return true;
  return !sprache || stimmen.some((s) => s.lang.startsWith(sprache));
}

/** Stimmen für diese Sprache, die der Browser gerade kennt. */
export function stimmen(sprache: string | null): SpeechSynthesisVoice[] {
  if (!('speechSynthesis' in window)) return [];
  const alle = window.speechSynthesis.getVoices();
  return sprache ? alle.filter((s) => s.lang.startsWith(sprache)) : alle;
}

/**
 * Die gemerkte Stimme zurückholen, sonst die vom Browser bevorzugte.
 *
 * Gemerkt wird nur die `voiceURI`, weil ein `SpeechSynthesisVoice` sich nicht
 * speichern lässt. Fehlt die Stimme auf diesem Gerät, entscheidet der Browser.
 *
 * `aus` nimmt die Liste entgegen, aus der gewählt wird - nötig für Ansichten,
 * die sie im Zustand halten, weil `getVoices()` selbst nichts meldet, wenn
 * sich etwas ändert. Ohne Vorgabe, seit `stimmen()` die Sprache verlangt: Die
 * bequeme Vorgabe wäre wieder die deutsche Liste gewesen.
 */
export function stimmeNachUri(
  uri: string | null,
  aus: SpeechSynthesisVoice[],
): SpeechSynthesisVoice | null {
  return aus.find((s) => s.voiceURI === uri) ?? aus.find((s) => s.default) ?? aus[0] ?? null;
}

/**
 * Meldet, wenn der Browser eine neue Stimmenliste hat. Gibt eine Funktion
 * zurück, die die Anmeldung wieder löst.
 *
 * Nötig, weil die Liste auf manchen Systemen erst asynchron nach dem Laden
 * der Seite eintrifft - vorher wäre eine Auswahl leer.
 */
export function beiStimmenAenderung(anhoerer: () => void): () => void {
  if (!('speechSynthesis' in window)) return () => {};
  window.speechSynthesis.addEventListener('voiceschanged', anhoerer);
  return () => window.speechSynthesis.removeEventListener('voiceschanged', anhoerer);
}

/** Spricht den Text und löst auf, wenn er zu Ende ist. */
export function sprich(text: string, wie: Sprechweise = {}): Promise<void> {
  return new Promise((fertig, fehler) => {
    if (!('speechSynthesis' in window)) {
      fehler(new Error('Dieser Browser kann nicht vorlesen.'));
      return;
    }
    window.speechSynthesis.cancel(); // eine Äußerung nach der anderen

    const aeusserung = new SpeechSynthesisUtterance(text);
    // Die Sprache der gewählten Stimme schlägt die angefragte: Wer eine Stimme
    // nennt, hat sie ausgesucht. Ohne beides spricht der Browser in seiner
    // eigenen Vorgabe - eine Sprache zu erfinden wäre schlechter als keine.
    const lang = wie.stimme?.lang ?? wie.sprache;
    if (lang) aeusserung.lang = lang;
    if (wie.stimme) aeusserung.voice = wie.stimme;
    aeusserung.rate = wie.tempo ?? TEMPO_VORGABE;
    aeusserung.onend = () => fertig();
    aeusserung.onerror = () => fehler(new Error('Vorlesen ist fehlgeschlagen.'));
    window.speechSynthesis.speak(aeusserung);
  });
}

export function brichVorlesenAb(): void {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
}


// ── Der Weg über den Server ────────────────────────────────────────────────

/** Eine Stimme, die der Server sprechen kann. */
export type Servestimme = {
  schluessel: string;
  name: string;
  erklaerung: string;
  sprache: string;
};

/**
 * Ein Schlüssel, den `stimmeNachUri` nie vergibt - daran ist eine Servestimme
 * von einer Browserstimme zu unterscheiden. Browserstimmen tragen eine
 * `voiceURI`, Servestimmen `<motor>/<stimme>`; ein Schrägstrich kommt in einer
 * `voiceURI` praktisch vor, deshalb das Präfix statt einer Heuristik.
 */
export const SERVE_PRAEFIX = 'serve:';

export function istServestimme(uri: string | null): boolean {
  return !!uri && uri.startsWith(SERVE_PRAEFIX);
}

export function serveSchluessel(uri: string): string {
  return uri.slice(SERVE_PRAEFIX.length);
}

/**
 * Die Stimmen liegen bei „hören" - auf der Wurzel der gemeinsamen Domain, also
 * aus jeder App derselbe Weg (wie `wer.ts`). Sie standen einmal nur in der API
 * von „hören", und die Stimmwahl unter „Audio" bot sie darum nur dort an: Aus
 * „lernen" und „schreiben" geöffnet, fehlten sie in derselben Ansicht.
 */
const hoeren = api('/api');

/** Welche Stimmen der Server sprechen kann. Leere Liste ist der Normalfall. */
export const holeServestimmen = () => hoeren.anfrage<Servestimme[]>('/vorlesen/stimmen');

/**
 * Ein fester Satz in dieser Stimme - zum Vergleichen, bevor man wählt.
 *
 * `no-cache`, weil sich unter derselben Adresse der Inhalt ändern kann: Wird
 * eine Stimme neu gesprochen, bleibt ihr Name derselbe (siehe `FRISCH` in der
 * API von „hören").
 */
export async function stimmprobe(stimme: string): Promise<Blob> {
  const antwort = await hoeren.hole(`/vorlesen/probe?stimme=${encodeURIComponent(stimme)}`, {
    cache: 'no-cache',
  });
  return antwort.blob();
}

let laufend: HTMLAudioElement | null = null;

/**
 * Eine vorgelesene Datei abspielen und auflösen, wenn sie zu Ende ist.
 *
 * `playbackRate` statt eines zweiten Modells für langsames Sprechen - und
 * `preservesPitch`, damit die Stimme dabei nicht in den Keller rutscht. Genau
 * das ist der Gewinn gegenüber der Browserstimme: Ein neuronal gesprochener
 * Satz hält auch bei 0,7 noch zusammen.
 */
export function spieleVor(url: string, tempo = TEMPO_VORGABE): Promise<void> {
  return new Promise((fertig, fehler) => {
    haltAn();
    const klang = new Audio(url);
    klang.playbackRate = tempo;
    // `preservesPitch` heißt in älteren Browsern anders; beides zu setzen ist
    // billiger als eine Abfrage, welcher gerade liest.
    type MitTonhoehe = HTMLAudioElement & { mozPreservesPitch?: boolean };
    klang.preservesPitch = true;
    (klang as MitTonhoehe).mozPreservesPitch = true;
    laufend = klang;
    klang.onended = () => {
      if (laufend === klang) laufend = null;
      fertig();
    };
    klang.onerror = () => fehler(new Error('Die vorgelesene Fassung ließ sich nicht abspielen.'));
    klang.play().catch(fehler);
  });
}

function haltAn(): void {
  if (laufend) {
    laufend.pause();
    laufend = null;
  }
}

/** Beide Wege anhalten - der Aufrufer weiß nicht, welcher gerade läuft. */
export function brichAllesAb(): void {
  haltAn();
  brichVorlesenAb();
}
