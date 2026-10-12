/**
 * Wohin „Hilfe" führt - je Ansicht eine Stelle im Handbuch auf GitHub.
 *
 * **Warum das Handbuch und keine Hilfeseite in der App.** Die Oberfläche
 * erklärt nicht von selbst (`docs/entwicklung.md`, Konventionen); wie etwas
 * gemeint ist und warum, steht unter `docs/`. Eine zweite Fassung davon in der
 * App ginge mit der ersten auseinander.
 *
 * **Warum eigene Anker.** Jede Stelle trägt im Markdown ein unsichtbares
 * `<a id="hilfe-…"></a>`; GitHub setzt `user-content-` davor und springt
 * trotzdem auf `#hilfe-…`. Der Anker, den GitHub aus einer Überschrift macht,
 * änderte sich mit jedem Wort darin - dieser bleibt, und
 * `tests/test_hilfe.py` prüft, dass es jeden hier genannten gibt.
 *
 * Gelesen wird die Fassung des Hauptzweigs (`blob/main`): Für eine einzelne
 * Datei gibt es keinen Weg, der nicht am Zweig hängt (anders als
 * `PROJEKT_URL`).
 */
import {
  AUDIO_PFAD,
  AUSWERTUNG_PFAD,
  DARSTELLUNG_PFAD,
  EDITIEREN_ROUTE,
  FEHLERLOG_PFAD,
  GRUNDMODELL_ROUTE,
  LAUF_ROUTE,
  MEINE_DATEN_PFAD,
  MODELLE_PFAD,
  SPRECHER_PFAD,
  SYSTEM_PFAD,
  ZUGANGSDATEN_PFAD,
  type AppSchluessel,
} from './apps';

const HANDBUCH = 'https://github.com/horkah/wortlaut/blob/main/docs/';

/** Die Route, für die die Hilfe ohne gültigen Zugang gilt. */
export const OHNE_ZUGANG = 'ohne-zugang';

type Stelle = [datei: string, anker: string];

/** In jeder App dieselben: das Menü und was ohne Zugang dasteht. */
const UEBERALL: Record<string, Stelle> = {
  [OHNE_ZUGANG]: ['hoeren.md', 'hilfe-zugang'],
  [ZUGANGSDATEN_PFAD]: ['hoeren.md', 'hilfe-zugangsdaten'],
  [AUDIO_PFAD]: ['hoeren.md', 'hilfe-audio'],
  [DARSTELLUNG_PFAD]: ['hoeren.md', 'hilfe-darstellung'],
  [SYSTEM_PFAD]: ['hoeren.md', 'hilfe-system'],
  [FEHLERLOG_PFAD]: ['betrieb.md', 'hilfe-fehlerprotokoll'],
  [MEINE_DATEN_PFAD]: ['hoeren.md', 'hilfe-meine-daten'],
  [SPRECHER_PFAD]: ['hoeren.md', 'hilfe-zugang'],
};

/**
 * Je App ihre Ansichten. Eine Route mit `/` am Ende gilt für alles, was so
 * beginnt (`/editieren/<id>`); `''` ist die App als Ganzes.
 */
const JE_APP: Record<AppSchluessel, Record<string, Stelle>> = {
  hoeren: {
    '/quelle': ['hoeren.md', 'hilfe-textquelle'],
    '/aufnahme': ['hoeren.md', 'hilfe-aufnehmen'],
    '/fortschritt': ['hoeren.md', 'hilfe-fortschritt'],
    [EDITIEREN_ROUTE]: ['hoeren.md', 'hilfe-editieren'],
    '/aufsicht/': ['hoeren.md', 'hilfe-aufsicht'],
    '': ['hoeren.md', 'hilfe-ablauf'],
  },
  lernen: {
    '/training': ['lernen.md', 'hilfe-training'],
    [LAUF_ROUTE]: ['lernen.md', 'hilfe-lauf'],
    [AUSWERTUNG_PFAD]: ['lernen.md', 'hilfe-auswertung'],
    [MODELLE_PFAD]: ['lernen.md', 'hilfe-modelle'],
    [GRUNDMODELL_ROUTE]: ['lernen.md', 'hilfe-grundmodell'],
    '': ['lernen.md', 'hilfe-training'],
  },
  schreiben: {
    '': ['schreiben.md', 'hilfe-schreiben'],
  },
};

function finde(tafel: Record<string, Stelle>, route: string): Stelle | undefined {
  if (tafel[route]) return tafel[route];
  const praefix = Object.keys(tafel).find((r) => r.endsWith('/') && route.startsWith(r));
  return praefix ? tafel[praefix] : undefined;
}

/**
 * Die Adresse der Hilfe zu dieser Ansicht.
 *
 * Zuerst die Route in der Adresse, dann die Ansicht, die die Kopfleiste als
 * offen markiert (bei leerer Adresse der gemerkte Reiter), zuletzt die App.
 */
export function hilfeAdresse(app: AppSchluessel, route: string, offen: string): string {
  const [datei, anker] =
    finde(UEBERALL, route) ??
    finde(JE_APP[app], route) ??
    finde(UEBERALL, offen) ??
    finde(JE_APP[app], offen) ??
    JE_APP[app][''];
  return `${HANDBUCH}${datei}#${anker}`;
}
