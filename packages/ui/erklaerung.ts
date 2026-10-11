/**
 * Die Erklärung zu einer Überschrift, als Blase darunter.
 *
 * Wer eine Ansicht kennt, soll von ihr nichts sehen: kein Zeichen, kein
 * anderer Mauszeiger, keine Hervorhebung beim Antippen. Mit der Maus
 * erscheint sie, wenn der Zeiger kurz auf der Überschrift verweilt, und geht,
 * wenn er sie verlässt. Auf dem Telefon öffnet ein Tippen auf die Überschrift
 * sie, ein zweites Tippen oder eines anderswo schließt sie, ebenso Esc.
 * Vorlesestimmen lesen den Text über `aria-description` mit.
 *
 *     <h2 use:erklaert={'Was hier geschieht und warum.'}>Auswertung</h2>
 *
 * Es gibt nur eine Blase im Dokument; eine neue verdrängt die alte. Sie hängt
 * im Dokument und nicht im Fenster, rollt also mit der Seite.
 */
import type { Action } from 'svelte/action';

const VERWEILEN_MS = 400;
const RAND_PX = 8;
const ABSTAND_PX = 6;
/** Länger gedrückt oder dabei gewischt ist kein Tippen, sondern Markieren oder Rollen. */
const TIPPEN_MS = 600;
const TIPPEN_PX = 10;

let blase: HTMLElement | null = null;
let traeger: HTMLElement | null = null;
let horcht = false;

function zeige(element: HTMLElement, text: string) {
  if (!blase) {
    blase = document.createElement('div');
    blase.className = 'erklaerung';
    blase.setAttribute('aria-hidden', 'true');
  }
  blase.textContent = text;
  blase.style.left = '0';
  blase.style.top = '0';
  document.body.append(blase);
  traeger = element;

  const ort = element.getBoundingClientRect();
  const breite = blase.offsetWidth;
  const hoehe = blase.offsetHeight;
  const links = Math.max(RAND_PX, Math.min(ort.left, window.innerWidth - breite - RAND_PX));
  // Darunter, wenn es passt; sonst darüber.
  const oben =
    ort.bottom + ABSTAND_PX + hoehe <= window.innerHeight || ort.top < hoehe + ABSTAND_PX
      ? ort.bottom + ABSTAND_PX
      : ort.top - ABSTAND_PX - hoehe;
  blase.style.left = `${links + window.scrollX}px`;
  blase.style.top = `${oben + window.scrollY}px`;
}

function verberge() {
  blase?.remove();
  traeger = null;
}

function horche() {
  if (horcht) return;
  horcht = true;
  document.addEventListener('pointerdown', (ereignis) => {
    if (traeger && !traeger.contains(ereignis.target as Node)) verberge();
  });
  document.addEventListener('keydown', (ereignis) => {
    if (ereignis.key === 'Escape') verberge();
  });
  window.addEventListener('resize', verberge);
}

/** Ein Tippen auf einen Link oder Knopf in der Überschrift gilt diesem. */
function aufBedienelement(element: HTMLElement, ziel: EventTarget | null): boolean {
  const treffer = (ziel as Element | null)?.closest?.('a, button, input, select, textarea, label');
  return !!treffer && element.contains(treffer);
}

export const erklaert: Action<HTMLElement, string> = (element, anfang) => {
  let text = anfang;
  let verweilen: ReturnType<typeof setTimeout> | undefined;
  let druck: { x: number; y: number; zeit: number } | null = null;

  horche();
  element.style.setProperty('-webkit-tap-highlight-color', 'transparent');

  function beschrifte() {
    if (text) element.setAttribute('aria-description', text);
    else element.removeAttribute('aria-description');
  }
  beschrifte();

  function hinein(ereignis: PointerEvent) {
    if (ereignis.pointerType !== 'mouse' || !text) return;
    clearTimeout(verweilen);
    verweilen = setTimeout(() => zeige(element, text), VERWEILEN_MS);
  }

  function hinaus(ereignis: PointerEvent) {
    if (ereignis.pointerType !== 'mouse') return;
    clearTimeout(verweilen);
    if (traeger === element) verberge();
  }

  function runter(ereignis: PointerEvent) {
    druck =
      ereignis.pointerType === 'mouse'
        ? null
        : { x: ereignis.clientX, y: ereignis.clientY, zeit: ereignis.timeStamp };
  }

  function hoch(ereignis: PointerEvent) {
    const war = druck;
    druck = null;
    if (!war || !text || aufBedienelement(element, ereignis.target)) return;
    const gewischt = Math.hypot(ereignis.clientX - war.x, ereignis.clientY - war.y) > TIPPEN_PX;
    if (gewischt || ereignis.timeStamp - war.zeit > TIPPEN_MS) return;
    if (traeger === element) verberge();
    else zeige(element, text);
  }

  element.addEventListener('pointerenter', hinein);
  element.addEventListener('pointerleave', hinaus);
  element.addEventListener('pointerdown', runter);
  element.addEventListener('pointerup', hoch);

  return {
    update(neu: string) {
      text = neu;
      beschrifte();
      if (traeger === element) {
        if (text) zeige(element, text);
        else verberge();
      }
    },
    destroy() {
      clearTimeout(verweilen);
      if (traeger === element) verberge();
      element.removeEventListener('pointerenter', hinein);
      element.removeEventListener('pointerleave', hinaus);
      element.removeEventListener('pointerdown', runter);
      element.removeEventListener('pointerup', hoch);
    },
  };
};
