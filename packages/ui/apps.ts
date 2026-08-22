/**
 * Die drei Apps unter einer Domain, plus die Menüpunkte innerhalb einer App.
 *
 * `lernen` steht hier schon, bevor es die App gibt: die Leiste soll von
 * Anfang an zeigen, dass wortlaut aus drei Teilen besteht und welcher davon
 * gerade offen ist. Solange `verfuegbar: false` ist, ist der Reiter sichtbar,
 * aber nicht anklickbar.
 *
 * `pfad` ist der Ort unter der gemeinsamen Domain. `hören` ist der Einstieg
 * und liegt auf der Wurzel, jede weitere App bekommt einen Pfad; der Reverse
 * Proxy des Wirts verteilt sie unverändert auf die Container (siehe
 * `docs/betrieb.md`). Derselbe Pfad steht im `base` der jeweiligen
 * Vite-Konfiguration und im `BASIS` ihres Backends — alle drei müssen
 * zusammenpassen, sonst führt der Reiter ins Leere oder auf die falsche App.
 */
export type AppSchluessel = 'hoeren' | 'lernen' | 'schreiben';

export interface AppEintrag {
  schluessel: AppSchluessel;
  name: string;
  aufgabe: string;
  pfad: string;
  verfuegbar: boolean;
}

export const APPS: AppEintrag[] = [
  {
    schluessel: 'hoeren',
    name: 'hören',
    aufgabe: 'Sprachproben sammeln',
    pfad: '/',
    verfuegbar: true,
  },
  {
    schluessel: 'lernen',
    name: 'lernen',
    aufgabe: 'ein eigenes Modell feintunen',
    pfad: '/lernen/',
    verfuegbar: false,
  },
  {
    schluessel: 'schreiben',
    name: 'schreiben',
    aufgabe: 'diktieren und vorlesen lassen',
    pfad: '/schreiben/',
    verfuegbar: true,
  },
];

/** Ein Menüpunkt innerhalb einer App; `pfad` ist die Hash-Route ohne `#`. */
export interface Menuepunkt {
  pfad: string;
  text: string;
}

/**
 * Wo die Einstellungen liegen — in jeder App dieselbe Hash-Route.
 *
 * Sie gehören zum Gerät und nicht zu einer App (Mikrofon, Stimme, Schrift
 * teilen sich alle drei über den `localStorage`), stehen deshalb in keiner
 * Reiterreihe, sondern hinter dem Menüknopf der Kopfleiste. Eine Konstante,
 * damit Kopfleiste und Apps nicht getrennt voneinander raten.
 */
export const EINSTELLUNGEN_PFAD = '/einstellungen';
