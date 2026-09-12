/**
 * Wo man zuletzt war - je App ein Eintrag, über Sitzungen hinweg.
 *
 * **Warum überhaupt.** Der Weg durch eine App ist eine Reihe von Ansichten,
 * aber niemand geht sie jeden Tag von vorn. Wer eine Woche lang aufnimmt, will
 * „Aufnehmen" sehen, nicht „Textquelle"; wer gerade ein Training beaufsichtigt,
 * will „Training" sehen und nicht die Aufteilung. Die App jedes Mal auf ihren
 * ersten Reiter zu stellen heißt, diesem Menschen jeden Tag denselben Klick
 * abzuverlangen - und die Zielperson kann schlecht lesen
 * (Grundentscheidung 7): Ein Klick weniger ist hier mehr wert als anderswo.
 *
 * **Warum im `localStorage` und nicht in der Adresse.** Die Adresse merkt sich
 * das ohnehin - wer ein Lesezeichen auf `#/training` legt, landet dort. Gemeint
 * ist aber der andere Fall: die App ohne Hash öffnen, vom Startbildschirm des
 * Telefons, aus einem alten Lesezeichen, nach einem Neustart des Browsers.
 * Dann steht in der Adresse nichts, und genau dann soll hier etwas stehen.
 *
 * **Warum die Adresse trotzdem leer bleibt.** Gemerkt wird der Reiter, nicht
 * hingesprungen: Die App zeigt ihn als ihre Vorgabe für die leere Route. Ein
 * Sprung schriebe den Hash in den Verlauf, und der Zurück-Knopf führte dann auf
 * eine Seite, die man nie angesteuert hat.
 *
 * **Warum je App und nicht einer für alle.** Es sind verschiedene Reihen:
 * „Aufnehmen" gibt es in `hören`, „Training" in `lernen`. Ein gemeinsamer
 * Eintrag wäre in der jeweils anderen App ein unbekannter Pfad.
 *
 * Gespeichert wie Mikrofon, Stimme und Farben (`einstellungen.svelte.ts`) -
 * im Browser, weil es zum Gerät gehört und nicht zum Menschen: Wer am
 * Arbeitsplatz trainiert und auf dem Telefon aufnimmt, will auf beiden das
 * Seine wiederfinden.
 */
import { reiterSchluessel, type AppSchluessel, type Menuepunkt } from './apps';
import { istSichtbar } from './einstellungen.svelte';

const VORSILBE = 'wortlaut.reiter.';

/** Sich diesen Reiter für diese App merken. */
export function merkeReiter(app: AppSchluessel, pfad: string): void {
  localStorage.setItem(VORSILBE + app, pfad);
}

/**
 * Welcher Reiter gelten soll, wenn in der Adresse nichts steht.
 *
 * Der gemerkte, falls er noch zur App gehört **und** sichtbar ist. Sonst der
 * erste sichtbare, sonst der erste überhaupt. Die Sichtbarkeitsprüfung ist der
 * Grund für die zweite Stufe: Wer einen Reiter unter „Darstellung" ausgeblendet
 * hat, soll nicht beim nächsten Öffnen genau darauf landen - das sähe aus, als
 * hätte der Schalter nichts getan.
 */
export function vorgabeReiter(app: AppSchluessel, punkte: Menuepunkt[]): string {
  if (!punkte.length) return '/';
  const sichtbar = punkte.filter((punkt) => istSichtbar(reiterSchluessel(app, punkt.pfad)));
  const gemerkt = localStorage.getItem(VORSILBE + app);
  if (gemerkt && sichtbar.some((punkt) => punkt.pfad === gemerkt)) return gemerkt;
  return (sichtbar[0] ?? punkte[0]).pfad;
}
