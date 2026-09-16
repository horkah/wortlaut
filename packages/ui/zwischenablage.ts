/**
 * Text in die Zwischenablage legen - und zwar so, dass es auch klappt.
 *
 * **Warum eine eigene Datei für einen Einzeiler.** Weil `navigator.clipboard`
 * genau der Einzeiler ist, der auf dem Gerät der Zielperson fehlschlägt. Er
 * setzt einen sicheren Kontext voraus (HTTPS oder localhost) und eine frische
 * Nutzerhandlung - unter `http://192.168.…:5173` beim Entwickeln gibt es ihn
 * gar nicht, und ein `await` darauf wirft dann einen Fehler, den niemand
 * sieht. Hier stand er zweimal ohne Absicherung.
 *
 * Der Rückfall ist der alte Weg: ein Textfeld anlegen, auswählen,
 * `execCommand('copy')`. Er ist abgekündigt und funktioniert überall, auch in
 * Safari - und für diese App ist „abgekündigt, tut es aber" allemal besser als
 * „sauber, tut nichts".
 *
 * **Warum das hier überhaupt zählt.** Wer diese App benutzt, kann oft schlecht
 * lesen und schlecht zielen (Grundentscheidung 7). Text mit dem Finger
 * auszuwählen - antippen, halten, die Griffe an den Rand ziehen - ist genau
 * die Bewegung, die dann nicht gelingt. Ein Knopf, der den ganzen Text nimmt,
 * ersetzt sie.
 */

/**
 * Legt `text` in die Zwischenablage. `false` heißt: hat nicht geklappt, sag es
 * dem Menschen - still zu scheitern ist hier das Schlimmste, denn er merkt es
 * erst beim Einfügen in eine fremde App.
 */
export async function inDieZwischenablage(text: string): Promise<boolean> {
  if (!text) return false;

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Kein sicherer Kontext, keine Erlaubnis, keine Nutzerhandlung mehr -
      // der Rückfall darunter kommt oft trotzdem durch.
    }
  }
  return ueberEinTextfeld(text);
}

function ueberEinTextfeld(text: string): boolean {
  const feld = document.createElement('textarea');
  feld.value = text;
  // Außer Sicht, aber nicht `display:none` - was nicht gerendert wird, lässt
  // sich auch nicht auswählen. `readOnly` hält auf dem iPhone die Tastatur
  // unten, die sonst kurz aufspringt.
  feld.setAttribute('readonly', '');
  feld.style.position = 'fixed';
  feld.style.top = '-1000px';
  feld.style.opacity = '0';
  document.body.appendChild(feld);
  try {
    feld.select();
    feld.setSelectionRange(0, text.length); // iOS beachtet `select()` allein nicht
    return document.execCommand('copy');
  } catch {
    return false;
  } finally {
    feld.remove();
  }
}
