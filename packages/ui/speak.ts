/**
 * Vorlesen über die Web Speech API.
 *
 * Deutsche Stimmen sind auf allen gängigen Systemen vorhanden, es braucht
 * keine Infrastruktur und es entsteht keine Latenz. Der Preis steht im
 * README: Nachsprechen verändert Sprechtempo und Satzmelodie, deshalb wird
 * eine so entstandene Aufnahme als `nachgesprochen` markiert.
 */

/** Ist überhaupt eine Stimme für diese Sprache da? */
export function stimmeVerfuegbar(sprache = 'de'): boolean {
  if (!('speechSynthesis' in window)) return false;
  const stimmen = window.speechSynthesis.getVoices();
  // Direkt nach dem Laden ist die Liste oft noch leer; dann lieber optimistisch
  // sein, als den Knopf grundlos auszublenden.
  return stimmen.length === 0 || stimmen.some((s) => s.lang.startsWith(sprache));
}

/** Spricht den Text und löst auf, wenn er zu Ende ist. */
export function sprich(text: string, sprache = 'de-DE'): Promise<void> {
  return new Promise((fertig, fehler) => {
    if (!('speechSynthesis' in window)) {
      fehler(new Error('Dieser Browser kann nicht vorlesen.'));
      return;
    }
    window.speechSynthesis.cancel(); // eine Äußerung nach der anderen

    const aeusserung = new SpeechSynthesisUtterance(text);
    aeusserung.lang = sprache;
    aeusserung.rate = 0.9; // etwas langsamer: es soll nachgesprochen werden
    aeusserung.onend = () => fertig();
    aeusserung.onerror = () => fehler(new Error('Vorlesen ist fehlgeschlagen.'));
    window.speechSynthesis.speak(aeusserung);
  });
}

export function brichVorlesenAb(): void {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
}
