/**
 * Die Schlüssel neben dem Zugang - einmal im Browser, für alle Apps.
 *
 * Der Zugang (`zugang.ts`) sagt, wer ruft, und geht an jede Anfrage. Zwei Wege
 * kosten mehr und stehen hinter je einem eigenen Geheimnis
 * (`wortlaut/schluessel.py` im Backend):
 *
 * - der **Trainerschlüssel**: ein Training beauftragen oder neu starten, einen
 *   Lauf samt Modell löschen, das Fehlerprotokoll lesen;
 * - der **Bearbeitungsschlüssel**: Zuschnitt und Editieren in „hören".
 *
 * Eingetragen werden beide an genau einer Stelle, unter „Zugangsdaten"
 * (`Zugangsdaten.svelte`). Ob ein Schlüssel gilt, sagt nicht der Browser,
 * sondern der Server - als `trainieren` und `bearbeiten` in der Auskunft über
 * den Zugang (`wer.ts`, `lage.svelte.ts`). Eine Ansicht zeigt einen Knopf
 * danach, nie danach, ob irgendetwas eingetragen ist.
 *
 * Im `localStorage`, weil in Sitzungen gearbeitet wird; unter eigenem Namen
 * je Schlüssel, damit ein Zugangswechsel sie nicht mitnimmt. Ein Schlüssel
 * geht nur an die Wege, die er öffnet (`mitSchluessel`) - und an die Auskunft.
 */

export type Schluesselart = 'trainer' | 'bearbeitung';

/** Was der Server zu einem Schlüssel sagt; `unbekannt`, solange er nicht gefragt ist. */
export type Recht = 'aus' | 'fehlt' | 'falsch' | 'gilt' | 'unbekannt';

export const SCHLUESSEL: Record<
  Schluesselart,
  { speicher: string; kopf: string; name: string; umgebung: string }
> = {
  trainer: {
    speicher: 'wortlaut.trainerschluessel',
    kopf: 'X-Trainer-Key',
    name: 'Trainerschlüssel',
    umgebung: 'WORTLAUT_TRAINER_KEY',
  },
  bearbeitung: {
    speicher: 'wortlaut.bearbeitungsschluessel',
    kopf: 'X-Editor-Key',
    name: 'Bearbeitungsschlüssel',
    umgebung: 'WORTLAUT_EDITOR_KEY',
  },
};

const ARTEN = Object.keys(SCHLUESSEL) as Schluesselart[];

function gespeichert(art: Schluesselart): string {
  try {
    return localStorage.getItem(SCHLUESSEL[art].speicher) ?? '';
  } catch {
    // Ein Browser mit gesperrtem Speicher ist kein Fehlerfall: Dann steht das
    // Feld eben bei jedem Besuch wieder leer da.
    return '';
  }
}

const stand = $state(
  Object.fromEntries(ARTEN.map((art) => [art, gespeichert(art)])) as Record<Schluesselart, string>,
);

export function schluessel(art: Schluesselart): string {
  return stand[art];
}

export function setzeSchluessel(art: Schluesselart, wert: string): void {
  const getrimmt = wert.trim();
  stand[art] = getrimmt;
  try {
    if (getrimmt) localStorage.setItem(SCHLUESSEL[art].speicher, getrimmt);
    else localStorage.removeItem(SCHLUESSEL[art].speicher);
  } catch {
    /* siehe oben */
  }
}

/** Die Köpfe einer Anfrage, ergänzt um diese Schlüssel - sofern eingetragen. */
export function mitSchluessel(arten: Schluesselart[], headers?: HeadersInit): Headers {
  const kopf = new Headers(headers);
  for (const art of arten) {
    if (stand[art]) kopf.set(SCHLUESSEL[art].kopf, stand[art]);
  }
  return kopf;
}

/** Alle Schlüssel - nur für die Auskunft, was dieser Browser darf. */
export const mitAllenSchluesseln = (headers?: HeadersInit) => mitSchluessel(ARTEN, headers);
