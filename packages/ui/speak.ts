/**
 * Vorlesen über die Web Speech API.
 *
 * Es braucht keine Infrastruktur und es entsteht keine Latenz. Der Preis
 * steht im README: Nachsprechen verändert Sprechtempo und Satzmelodie,
 * deshalb wird eine so entstandene Aufnahme als `nachgesprochen` markiert.
 *
 * Welche Stimmen es gibt und wie gut sie klingen, entscheidet allein das
 * Betriebssystem — dieselbe Seite klingt auf macOS natürlich und unter
 * Linux mit espeak-ng blechern. Von hier aus lässt sich das nicht ändern,
 * nur zur Auswahl stellen; siehe `docs/betrieb.md`.
 */

/** Etwas langsamer als normal: die Vorgabe soll nachgesprochen werden. */
export const TEMPO_VORGABE = 0.9;

/** Wie gesprochen wird — alles optional, alles mit brauchbarer Vorgabe. */
export type Sprechweise = {
  stimme?: SpeechSynthesisVoice | null;
  /** Faktor auf die Normalgeschwindigkeit, 1 ist unverändert. */
  tempo?: number;
  sprache?: string;
};

/** Ist überhaupt eine Stimme für diese Sprache da? */
export function stimmeVerfuegbar(sprache = 'de'): boolean {
  if (!('speechSynthesis' in window)) return false;
  const stimmen = window.speechSynthesis.getVoices();
  // Direkt nach dem Laden ist die Liste oft noch leer; dann lieber optimistisch
  // sein, als den Knopf grundlos auszublenden.
  return stimmen.length === 0 || stimmen.some((s) => s.lang.startsWith(sprache));
}

/** Stimmen für diese Sprache, die der Browser gerade kennt. */
export function stimmen(sprache = 'de'): SpeechSynthesisVoice[] {
  if (!('speechSynthesis' in window)) return [];
  return window.speechSynthesis.getVoices().filter((s) => s.lang.startsWith(sprache));
}

/**
 * Die gemerkte Stimme zurückholen, sonst die vom Browser bevorzugte.
 *
 * Gemerkt wird nur die `voiceURI`, weil ein `SpeechSynthesisVoice` sich nicht
 * speichern lässt. Fehlt die Stimme auf diesem Gerät, entscheidet der Browser.
 *
 * `aus` nimmt eine bereits geholte Liste entgegen — nötig für Ansichten, die
 * die Liste im Zustand halten, weil `getVoices()` selbst nichts meldet, wenn
 * sich etwas ändert.
 */
export function stimmeNachUri(
  uri: string | null,
  aus: SpeechSynthesisVoice[] = stimmen(),
): SpeechSynthesisVoice | null {
  return aus.find((s) => s.voiceURI === uri) ?? aus.find((s) => s.default) ?? aus[0] ?? null;
}

/**
 * Meldet, wenn der Browser eine neue Stimmenliste hat. Gibt eine Funktion
 * zurück, die die Anmeldung wieder löst.
 *
 * Nötig, weil die Liste auf manchen Systemen erst asynchron nach dem Laden
 * der Seite eintrifft — vorher wäre eine Auswahl leer.
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
    aeusserung.lang = wie.stimme?.lang ?? wie.sprache ?? 'de-DE';
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
