/**
 * Das Schloss vor „Darstellung" und „Zugangsdaten" - dieselbe PIN wie vor
 * „Meine Daten".
 *
 * Warum dieselbe und keine zweite: Es ist derselbe Mensch, derselbe Browser
 * und dasselbe Bedrohungsmodell - der Klick aus Versehen, nicht der Angreifer
 * (siehe `apps/hoeren/backend/services/pin.py`). Wer sich hier eine eigene
 * PIN je Seite merken müsste, merkte sich am Ende keine.
 *
 * Die PIN liegt allein im Speicher dieser Seite und nie im `localStorage`:
 * Dort steht schon der Zugang, und ein zweites dauerhaft gemerktes Geheimnis
 * nähme der PIN genau den Sinn, den sie haben soll. Ein Neuladen sperrt
 * folglich wieder zu - so ist es auch bei „Meine Daten".
 *
 * Gefragt wird immer die Konto-API von „hören", auch aus „schreiben" heraus.
 * Die PIN gehört zum Sprecher und steht in seinem Korpus, und den schreibt
 * allein „hören" (Grundentscheidung 6). „hören" liegt auf der Wurzel der
 * gemeinsamen Domain (`APPS` in `apps.ts`), darum der absolute Pfad - dieselbe
 * Annahme, unter der „schreiben" schon heute auf „Meine Daten" verlinkt.
 *
 * Ein Zugang, den der Server nicht kennt, lässt das Schloss **offen** statt zu:
 * Ohne Sprecher gibt es keine PIN, nach der zu fragen wäre, und „Zugangsdaten"
 * ist dann der einzige Weg herein. Ein Schloss, dessen Schlüssel hinter ihm
 * selbst läge, wäre kein Schutz, sondern ein zugemauerter Eingang.
 */
import { mitZugang } from './zugang';

/** Wo die PIN verwaltet wird - dorthin verweist das Schloss zum Ändern. */
const KONTO_API = '/api/konto';

export type Schlossstand =
  /** Noch nicht nachgefragt. */
  | 'unbekannt'
  /** Keine PIN gesetzt (oder kein Sprecherzugang): nichts zu entsperren. */
  | 'frei'
  /** PIN gesetzt und noch nicht eingegeben. */
  | 'zu'
  /** In dieser Sitzung entsperrt. */
  | 'offen';

export const schloss = $state<{ stand: Schlossstand; pin: string | null }>({
  stand: 'unbekannt',
  pin: null,
});

/** Genau vier Ziffern - dieselbe Regel wie im Backend (`services/pin.py`). */
export function gueltigePin(wert: string): boolean {
  return /^[0-9]{4}$/.test(wert);
}

// Einmal fragen, nicht je Ansicht: Darstellung und Zugangsdaten teilen sich
// dieses Schloss, und zwei Ansichten nacheinander sind kein zweiter Grund.
let laufendeFrage: Promise<void> | null = null;

/** Ob überhaupt eine PIN gesetzt ist; ohne Antwort bleibt das Schloss offen. */
export function frageSchloss(): Promise<void> {
  if (schloss.stand !== 'unbekannt') return Promise.resolve();
  laufendeFrage ??= (async () => {
    try {
      const antwort = await fetch(`${KONTO_API}/pin`, { headers: mitZugang() });
      if (!antwort.ok) throw new Error(String(antwort.status));
      const { gesetzt } = (await antwort.json()) as { gesetzt: boolean };
      schloss.stand = !gesetzt ? 'frei' : schloss.pin ? 'offen' : 'zu';
    } catch {
      // Kein Sprecherzugang, Verwaltung, Aufsicht oder gar kein Server: Es
      // gibt keine PIN, die hier zu prüfen wäre (siehe Kopfkommentar).
      schloss.stand = 'frei';
    }
  })();
  return laufendeFrage;
}

/**
 * Eine eingegebene PIN prüfen und, wenn sie stimmt, das Schloss öffnen.
 * Sagt, ob sie stimmte - die Ansicht formuliert die Meldung selbst.
 */
export async function entsperre(eingabe: string): Promise<boolean> {
  if (!gueltigePin(eingabe)) return false;
  const antwort = await fetch(`${KONTO_API}/pin/pruefung`, {
    headers: mitZugang({ 'X-Pin': eingabe }),
  });
  if (!antwort.ok) return false;
  merkePin(eingabe);
  return true;
}

/**
 * Eine anderswo schon geprüfte PIN übernehmen - „Meine Daten" entsperrt mit
 * einem Testabruf und meldet das Ergebnis hierher. Wer dort eingegeben hat,
 * soll nicht auf der nächsten Seite noch einmal gefragt werden: eine PIN, eine
 * Sitzung.
 */
export function merkePin(pin: string): void {
  schloss.pin = pin;
  schloss.stand = 'offen';
}

/**
 * Die PIN vergessen und neu nachfragen - nach „PIN entfernt" oder „PIN
 * geändert" stimmt die gemerkte nicht mehr.
 */
export function vergissPin(): void {
  schloss.pin = null;
  schloss.stand = 'unbekannt';
  laufendeFrage = null;
}
