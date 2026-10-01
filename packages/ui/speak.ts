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

/**
 * So lange darf es dauern, bis eine Äußerung oder Datei hörbar anfängt.
 *
 * Safari auf dem iPhone verwirft ein `speak()` oder `play()`, das es nicht
 * zulässt, manchmal ohne jedes Ereignis - ohne diese Frist wartete, wer
 * abschnittweise vorliest, für immer, und der Knopf bliebe auf „■ Anhalten".
 */
const ANLAUF_MS = 4000;

/** Spricht den Text und löst auf, wenn er zu Ende ist. */
export function sprich(text: string, wie: Sprechweise = {}): Promise<void> {
  return new Promise((fertig, fehler) => {
    if (!('speechSynthesis' in window)) {
      fehler(new Error('Dieser Browser kann nicht vorlesen.'));
      return;
    }
    const synth = window.speechSynthesis;
    // Eine Äußerung nach der anderen - abgebrochen wird aber nur eine eigene,
    // die noch spricht: Safari auf dem iPhone verschluckt eine Äußerung, die
    // direkt nach einem `cancel()` kommt. Die stumme aus `entsperreVorlesen`
    // ist dann gleich durch und darf vorausgehen.
    if (aeussernd) synth.cancel();

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
      const vorbei = () => {
        clearTimeout(wache);
        if (aeussernd === aeusserung) aeussernd = null;
      };
      // Solange das Gerät spricht, ist es angelaufen, auch wenn `start` fehlt.
      const wache = setTimeout(() => {
        if (aeussernd !== aeusserung || synth.speaking) return;
        vorbei();
        synth.cancel();
        fehler(new Error('Das Gerät hat nicht angefangen vorzulesen - bitte „▶ Vorlesen" tippen.'));
      }, ANLAUF_MS);
      aeusserung.onstart = () => clearTimeout(wache);
      aeusserung.onend = () => {
        vorbei();
        fertig();
      };
      aeusserung.onerror = (ereignis) => {
        const meine = aeussernd === aeusserung;
        vorbei();
        // Angehalten ist auch fertig, wie bei `spieleVor` - auch, wenn schon
        // die nächste Äußerung dran ist.
        if (ereignis.error === 'interrupted' || ereignis.error === 'canceled') fertig();
        else if (!meine) return; // schon vom Wachhund erledigt
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
 * Vorlesen freischalten, solange ein Tippen im Gang ist - beide Wege.
 *
 * Safari auf dem iPhone lässt eine Seite erst sprechen, nachdem sie einmal aus
 * einem Tippen heraus `speak()` gerufen hat, und ein Audio-Element erst
 * spielen, nachdem es einmal aus einem Tippen heraus `play()` bekam. Das
 * Vorlesen von selbst in „schreiben" beginnt aber, wenn der Text vom Server
 * kommt, Sekunden nach dem letzten Tippen, und jeder weitere Abschnitt noch
 * später. Deshalb hier beim Tippen: eine Äußerung aus einem Leerzeichen, stumm,
 * und eine Zehntelsekunde Stille im einen Abspieler, den `spieleVor` danach
 * für jede Datei wiederverwendet.
 *
 * Gerufen aus jedem Knopf, nach dem vorgelesen wird - einmal genügt je Seite,
 * mehrmals schadet nicht.
 */
export function entsperreVorlesen(): void {
  if (!laufend) {
    const klang = abspieler();
    klang.src = stille();
    klang.play().catch(() => {}); // abgebrochen, sobald die erste Datei kommt
  }
  if (!('speechSynthesis' in window) || sprachausgabeFrei) return;
  sprachausgabeFrei = true;
  const stumm = new SpeechSynthesisUtterance(' ');
  stumm.volume = 0;
  window.speechSynthesis.speak(stumm);
}

let sprachausgabeFrei = false;

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

/**
 * Der eine Abspieler für alles Vorgelesene.
 *
 * Einer und nicht einer je Datei: Safari auf dem iPhone lässt ein
 * Audio-Element ohne Tippen nur spielen, wenn es schon einmal aus einem Tippen
 * heraus gespielt hat (`entsperreVorlesen`). Ein neues Element je Abschnitt
 * wäre jedes Mal gesperrt.
 */
let spieler: HTMLAudioElement | null = null;

function abspieler(): HTMLAudioElement {
  return (spieler ??= new Audio());
}

let stilleUrl: string | null = null;

/** Eine Zehntelsekunde Stille als WAV - genug, damit `play()` etwas hat. */
function stille(): string {
  if (stilleUrl) return stilleUrl;
  const proben = 800; // 0,1 s bei 8 kHz, 16 Bit, mono
  const daten = new DataView(new ArrayBuffer(44 + 2 * proben));
  const schreibe = (stelle: number, text: string) =>
    [...text].forEach((zeichen, i) => daten.setUint8(stelle + i, zeichen.charCodeAt(0)));
  schreibe(0, 'RIFF');
  daten.setUint32(4, 36 + 2 * proben, true);
  schreibe(8, 'WAVEfmt ');
  daten.setUint32(16, 16, true);
  daten.setUint16(20, 1, true); // PCM
  daten.setUint16(22, 1, true); // mono
  daten.setUint32(24, 8000, true);
  daten.setUint32(28, 16000, true);
  daten.setUint16(32, 2, true);
  daten.setUint16(34, 16, true);
  schreibe(36, 'data');
  daten.setUint32(40, 2 * proben, true);
  stilleUrl = URL.createObjectURL(new Blob([daten.buffer], { type: 'audio/wav' }));
  return stilleUrl;
}

let laufend: { fertig: () => void } | null = null;

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
    const klang = abspieler();
    // Angehalten ist auch fertig - sonst wartete, wer abschnittweise vorliest,
    // nach einem Halt für immer.
    const dieser = { fertig };
    laufend = dieser;
    const vorbei = () => {
      clearTimeout(wache);
      if (laufend === dieser) laufend = null;
    };
    const scheitere = (ursache: unknown) => {
      if (laufend !== dieser) return; // angehalten oder abgelöst
      vorbei();
      fehler(ursache instanceof Error ? ursache : new Error(String(ursache)));
    };
    const wache = setTimeout(
      () => scheitere(new Error('Die vorgelesene Fassung fing nicht an zu spielen.')),
      ANLAUF_MS,
    );
    klang.onplaying = () => clearTimeout(wache);
    klang.onended = () => {
      if (laufend !== dieser) return;
      vorbei();
      fertig();
    };
    klang.onerror = () => scheitere(new Error('Die vorgelesene Fassung ließ sich nicht abspielen.'));
    klang.src = url;
    // Nach `src` gesetzt: Eine neue Quelle stellt das Tempo zurück.
    klang.defaultPlaybackRate = tempo;
    klang.playbackRate = tempo;
    // `preservesPitch` heißt in älteren Browsern anders; beides zu setzen ist
    // billiger als eine Abfrage, welcher gerade liest.
    type MitTonhoehe = HTMLAudioElement & { mozPreservesPitch?: boolean };
    klang.preservesPitch = true;
    (klang as MitTonhoehe).mozPreservesPitch = true;
    klang.play().catch(scheitere);
  });
}

function haltAn(): void {
  if (laufend) {
    const { fertig } = laufend;
    laufend = null;
    spieler?.pause();
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
