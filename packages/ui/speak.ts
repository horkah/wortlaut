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
 * Der zweite Weg ist die Web Speech API, die immer da ist: ohne Servestimme
 * oder wenn eine Datei nicht kommt. Ihre Stimmen bestimmt das Betriebssystem -
 * auf macOS natürlich, unter Linux mit espeak-ng blechern.
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
 * Eine gewählte Stimme des Servers genügt (`stimmeUri`) - sie spricht auch in
 * einem Browser, der selbst keine hat.
 *
 * **`sprache` ohne Vorgabe:** Wer fragt, sagt, für wen (`wortlaut/sprachen.py`).
 *
 * **`null` heißt „weiß ich nicht" und nicht „Deutsch".** So lange steht die
 * Antwort des Servers noch aus (`wer.ts`), und ein Verwalter hat gar keine
 * Sprache. Dann wird nicht gefiltert, statt eine zu erfinden: Lieber alle
 * Stimmen zeigen als die falschen.
 */
export function stimmeVerfuegbar(sprache: string | null, stimmeUri: string | null): boolean {
  if (istServestimme(stimmeUri)) return true;
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
 * sich etwas ändert. Ohne Vorgabe - sie wäre stillschweigend eine Sprache.
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

/**
 * Die Äußerung, die gerade spricht - festgehalten, weil WebKit eine, an der
 * nur noch die Sprachausgabe hängt, mitten im Satz wegräumt: Dann kommt nie
 * ein `end`, und wer abschnittweise vorliest, wartet für immer.
 */
let aeussernd: SpeechSynthesisUtterance | null = null;

/**
 * Fehler, nach denen eine ausdrücklich gewählte Stimme schuld ist. iOS führt
 * Stimmen in `getVoices()`, die auf dem Gerät gar nicht geladen sind; gewählt,
 * scheitern sie mit `synthesis-failed`. Ohne `voice` nimmt das System die
 * Stimme dieser Sprache, die es hat.
 */
const STIMME_SCHULD = new Set(['synthesis-failed', 'synthesis-unavailable', 'voice-unavailable']);

/** Spricht den Text und löst auf, wenn er zu Ende ist. */
export function sprich(text: string, wie: Sprechweise = {}): Promise<void> {
  return new Promise((fertig, fehler) => {
    if (!('speechSynthesis' in window)) {
      fehler(new Error('Dieser Browser kann nicht vorlesen.'));
      return;
    }
    const synth = window.speechSynthesis;
    // Eine Äußerung nach der anderen - aber nur abbrechen, was läuft: Safari
    // auf dem iPhone verschluckt eine Äußerung, die direkt nach einem
    // `cancel()` ins Leere kommt.
    if (synth.speaking || synth.pending) synth.cancel();

    const versuche = (stimme: SpeechSynthesisVoice | null) => {
      const aeusserung = new SpeechSynthesisUtterance(text);
      // Die Sprache der gewählten Stimme schlägt die angefragte: Wer eine
      // Stimme nennt, hat sie ausgesucht. Ohne beides spricht der Browser in
      // seiner eigenen Vorgabe - eine Sprache zu erfinden wäre schlechter als
      // keine.
      const lang = wie.stimme?.lang ?? wie.sprache;
      if (lang) aeusserung.lang = lang;
      if (stimme) aeusserung.voice = stimme;
      aeusserung.rate = wie.tempo ?? TEMPO_VORGABE;
      aeusserung.onend = () => {
        if (aeussernd === aeusserung) aeussernd = null;
        fertig();
      };
      aeusserung.onerror = (ereignis) => {
        if (aeussernd === aeusserung) aeussernd = null;
        // Angehalten ist auch fertig, wie bei `spieleVor`.
        if (ereignis.error === 'interrupted' || ereignis.error === 'canceled') fertig();
        else if (stimme && STIMME_SCHULD.has(ereignis.error)) versuche(null);
        else if (ereignis.error === 'not-allowed')
          fehler(new Error('Der Browser liest erst nach einem Tippen vor - bitte „▶ Vorlesen".'));
        else fehler(new Error(`Vorlesen ist fehlgeschlagen (${ereignis.error}).`));
      };
      aeussernd = aeusserung;
      synth.speak(aeusserung);
    };
    versuche(wie.stimme ?? null);
  });
}

/**
 * Die Sprachausgabe freischalten, solange ein Tippen im Gang ist.
 *
 * Safari auf dem iPhone spricht erst, nachdem die Seite einmal aus einem
 * Tippen heraus `speak()` gerufen hat; ein `speak()` ohne Tippen davor
 * scheitert mit `not-allowed`. Das trifft das Vorlesen von selbst in
 * „schreiben": Es beginnt, wenn der Text vom Server kommt, Sekunden nach dem
 * letzten Tippen. Eine stumme, leere Äußerung beim Tippen auf „● Aufnehmen"
 * genügt, und danach darf die Seite sprechen, solange sie offen ist.
 *
 * Eine Datei vom Server braucht das nicht - sie spielt, weil die Seite eben
 * noch das Mikrofon offen hatte.
 */
export function entsperreVorlesen(): void {
  if (!('speechSynthesis' in window)) return;
  const synth = window.speechSynthesis;
  if (synth.speaking || synth.pending) return;
  const stumm = new SpeechSynthesisUtterance('');
  stumm.volume = 0;
  synth.speak(stumm);
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
 * aus jeder App derselbe Weg (wie `wer.ts`).
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

let laufend: { klang: HTMLAudioElement; fertig: () => void } | null = null;

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
    // Angehalten ist auch fertig - sonst wartete, wer abschnittweise vorliest,
    // nach einem Halt für immer.
    laufend = { klang, fertig };
    klang.playbackRate = tempo;
    // `preservesPitch` heißt in älteren Browsern anders; beides zu setzen ist
    // billiger als eine Abfrage, welcher gerade liest.
    type MitTonhoehe = HTMLAudioElement & { mozPreservesPitch?: boolean };
    klang.preservesPitch = true;
    (klang as MitTonhoehe).mozPreservesPitch = true;
    klang.onended = () => {
      if (laufend?.klang === klang) laufend = null;
      fertig();
    };
    klang.onerror = () => fehler(new Error('Die vorgelesene Fassung ließ sich nicht abspielen.'));
    klang.play().catch(fehler);
  });
}

function haltAn(): void {
  if (laufend) {
    const { klang, fertig } = laufend;
    laufend = null;
    klang.pause();
    fertig();
  }
}

/**
 * Einen Text vorlesen, wie es eingestellt ist: mit der Stimme des Servers, wenn
 * eine gewählt ist und ihre Datei kommt, sonst mit der des Browsers.
 *
 * Der Rückfall ist stumm und das mit Absicht: Wer zuhören will, soll hören
 * und keine Fehlermeldung lesen. `datei` holt die gesprochene Fassung - aus
 * „hören" die einer Vorlage, aus „schreiben" die eines Abschnitts; nie ein
 * frei mitgeschickter Text.
 */
export async function liesVor(
  text: string,
  wie: { stimmeUri: string | null; sprache: string | null; tempo: number },
  datei: (stimme: string) => Promise<Blob>,
): Promise<void> {
  if (istServestimme(wie.stimmeUri)) {
    let url: string | null = null;
    try {
      url = URL.createObjectURL(await datei(serveSchluessel(wie.stimmeUri!)));
      await spieleVor(url, wie.tempo);
      return;
    } catch {
      // Weiter unten mit der Browserstimme.
    } finally {
      if (url) URL.revokeObjectURL(url);
    }
  }
  await sprich(text, {
    stimme: stimmeNachUri(wie.stimmeUri, stimmen(wie.sprache)),
    tempo: wie.tempo,
  });
}

/** Beide Wege anhalten - der Aufrufer weiß nicht, welcher gerade läuft. */
export function brichAllesAb(): void {
  haltAn();
  brichVorlesenAb();
}
