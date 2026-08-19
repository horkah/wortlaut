/**
 * Die drei Apps unter einer Domain, plus die Menüpunkte innerhalb einer App.
 *
 * `lernen` steht hier schon, bevor es die App gibt: die Leiste soll von
 * Anfang an zeigen, dass wortlaut aus drei Teilen besteht und welcher davon
 * gerade offen ist. Solange `verfuegbar: false` ist, ist der Reiter sichtbar,
 * aber nicht anklickbar.
 *
 * `pfad` ist der Ort unter der gemeinsamen Domain. `hören` ist der Einstieg
 * und liegt auf der Wurzel, jede weitere App bekommt einen Pfad; Caddy
 * verteilt sie auf die Container (siehe `Caddyfile`). Der Pfad steht auch im
 * `base` der jeweiligen Vite-Konfiguration — beides muss zusammenpassen.
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
