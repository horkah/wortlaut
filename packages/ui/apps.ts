/**
 * Die drei Apps unter einer Domain, plus die Menüpunkte innerhalb einer App.
 *
 * `lernen` und `schreiben` stehen hier schon, bevor es sie gibt: die Leiste
 * soll von Anfang an zeigen, dass wortlaut aus drei Teilen besteht und welcher
 * davon gerade offen ist. Solange `verfuegbar: false` ist, sind sie sichtbar,
 * aber nicht anklickbar.
 *
 * `pfad` ist der Ort unter der gemeinsamen Domain. `hören` liegt derzeit
 * allein auf der Wurzel; sobald eine zweite App dazukommt, wird daraus
 * `/hoeren/` und Caddy verteilt die drei Pfade auf die drei Container.
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
    verfuegbar: false,
  },
];

/** Ein Menüpunkt innerhalb einer App; `pfad` ist die Hash-Route ohne `#`. */
export interface Menuepunkt {
  pfad: string;
  text: string;
}
