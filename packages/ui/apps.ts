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
 * Vite-Konfiguration und im `BASIS` ihres Backends - alle drei müssen
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
  /**
   * Nur setzen, wenn dieser Punkt aus dieser App heraus in eine andere führt:
   * eine volle Adresse statt der Hash-Route dieser App (siehe
   * `MEINE_DATEN_PFAD`). `Kopfleiste.svelte` verlinkt dann dorthin statt auf
   * `#${pfad}` - eine ganze Seite lädt neu, statt nur den Hash zu ändern.
   * `pfad` bleibt trotzdem gesetzt: Er ist der Schlüssel für `{#each}` und
   * markiert (zu Recht) nie den aktiven Reiter dieser App.
   */
  href?: string;
}

/**
 * Wo die Einstellungen liegen - in jeder App dieselbe Hash-Route.
 *
 * Sie gehören zum Gerät und nicht zu einer App (Mikrofon, Stimme, Schrift
 * teilen sich alle drei über den `localStorage`), stehen deshalb in keiner
 * Reiterreihe, sondern hinter dem Menüknopf der Kopfleiste. Eine Konstante,
 * damit Kopfleiste und Apps nicht getrennt voneinander raten.
 */
export const EINSTELLUNGEN_PFAD = '/einstellungen';

/**
 * Wo Farben, Schriftart und Schriftgrößen eingestellt werden.
 *
 * Eine eigene Ansicht und kein Abschnitt in `Einstellungen.svelte`: Dort
 * stehen Mikrofon und Stimme - etwas, das man einmal einmisst und dann in
 * Ruhe lässt. Die Darstellung dagegen darf jeder anfassen, der die Schrift zu
 * klein oder den Kontrast zu schwach findet, ohne durch Technisches zu
 * blättern. Aus demselben Grund wie `EINSTELLUNGEN_PFAD` gerätebezogen und
 * über den `localStorage` geteilt (siehe `einstellungen.svelte.ts`), deshalb
 * ebenfalls im Menü der Kopfleiste und nicht in einer Reiterreihe.
 */
export const DARSTELLUNG_PFAD = '/darstellung';

/**
 * Wo die Zugangsdaten dieser Instanz verwaltet werden - Verwalter- und
 * Aufsichtstoken.
 *
 * Eine eigene Ansicht aus demselben Grund wie `DARSTELLUNG_PFAD`: Wer ein
 * Mikrofon einmisst, will nicht an einem Formular für Serverzugänge
 * vorbeiblättern, und umgekehrt.
 *
 * Beide Apps kennen den Punkt, denn beide lesen denselben Zugang aus demselben
 * Browser (`zugang.ts`); die Ansicht dazu gibt es ebenfalls nur einmal
 * (`Zugangsdaten.svelte`). Trotzdem steht der Pfad hier und nicht in
 * `GERAETE_PUNKTE`: Ein Zugang gehört nicht zum Gerät, sondern zum Menschen,
 * und was er in der jeweiligen App bedeutet, weiß nur sie - „hören" nimmt in
 * dasselbe Feld auch Verwalter- und Aufsichtstoken. Jede App stellt ihn
 * deshalb selbst ins Menü, wie jeden anderen app-eigenen Punkt auch.
 */
export const ZUGANGSDATEN_PFAD = '/zugangsdaten';

/**
 * Wo ein Sprecher seine eigenen Daten ansieht - Profil, Sitzungen, Aufnahmen.
 *
 * Anders als `ZUGANGSDATEN_PFAD` gehört diese Ansicht nur „hören": Dort liegt
 * der Korpus, den sie zeigt. `schreiben` kennt den Pfad trotzdem - es stellt
 * den Menüpunkt mit einem `href` (siehe `Menuepunkt`), das auf die laufende
 * „hören"-Seite verweist, statt eine eigene, leere Ansicht dafür zu bauen.
 */
export const MEINE_DATEN_PFAD = '/meine-daten';

/**
 * Wo die Modelle gegeneinander antreten - Auswertung der eigenen Aufnahmen.
 *
 * Nur „hören" führt den Punkt: Dort liegt der Korpus, und gemessen wird an
 * ihm. Jede Aufnahme ist eine fertige Prüfaufgabe - die Vorlage steht daneben,
 * also lässt sich vergleichen, was ein Erkenner daraus macht. Der Punkt steht
 * im Menü und nicht in der Reiterreihe, weil er nicht zum Weg durch die Arbeit
 * gehört: Aufnehmen ist eine Tätigkeit, Auswerten ein Nachsehen.
 *
 * Im Menü steht er direkt hinter „Meine Daten": Beide zeigen dieselben
 * Aufnahmen, die eine als Bestand, die andere als Messung.
 */
export const AUSWERTUNG_PFAD = '/auswertung';

/**
 * Die Menüpunkte, die zum Gerät gehören - in jeder App dieselben.
 *
 * Sie stehen hier als Daten und nicht als feste Zeilen in der Kopfleiste,
 * weil zwei Stellen sie brauchen: die Kopfleiste, um sie ins Menü zu
 * schreiben, und der Rahmen, um ihre Ansichten zu zeigen (`Rahmen.svelte`).
 * Ein vierter gerätebezogener Punkt ist damit ein Eintrag in dieser Liste
 * und eine Zeile im Rahmen - und keine Änderung in jeder App.
 */
export const GERAETE_PUNKTE: Menuepunkt[] = [
  { pfad: EINSTELLUNGEN_PFAD, text: 'Einstellungen' },
  // Unter den Einstellungen: wer nach Mikrofon und Stimme sucht, hat die
  // zuerst gesehen; wer nach Farbe und Schrift sucht, findet sie gleich
  // darunter.
  { pfad: DARSTELLUNG_PFAD, text: 'Darstellung' },
];

/**
 * Wo der Sprecher gewählt und angelegt wird.
 *
 * Auch das gehört nicht in die Reiterreihe einer App: Der Sprecher ist die
 * Klammer um alles - der Korpus hat je Sprecher eine eigene Datenbank, und
 * „schreiben" wird später auf denselben Sprecher zurückgeführt. Er steht
 * deshalb im selben Menü wie die Einstellungen und über ihnen: erst wer,
 * dann womit.
 */
export const SPRECHER_PFAD = '/sprecher';

/**
 * Das Projekt selbst - Quelltext und Beschreibung.
 *
 * Ziel ist die Startseite des Bestands: GitHub zeigt die README dort unter der
 * Dateiliste ohnehin an, und zwar immer in der Fassung des Hauptzweigs. Der
 * Anker `#readme-ov-file` springt gleich dorthin - es ist derselbe, den GitHub
 * in seiner eigenen Seitenspalte unter „Readme" benutzt.
 *
 * Warum nicht `blob/main/README.md`: Das zeigte dieselbe Datei allein, hinge
 * aber am Namen des Hauptzweigs. Wird der einmal umbenannt, ist der Verweis
 * ein 404. Hier scheitert schlimmstenfalls der Sprung - die Seite steht
 * trotzdem, und die README steht darauf.
 */
export const PROJEKT_URL = 'https://github.com/horkah/wortlaut#readme-ov-file';

/**
 * Was sich unter „Darstellung" ein- und ausblenden lässt.
 *
 * Der Anlass ist derselbe wie bei Farbe und Schriftgröße: Diese Oberfläche
 * steht vor einem Menschen, der schlecht liest (Grundentscheidung 7), und
 * jeder Reiter, den er nie braucht, ist eine Gelegenheit, sich zu verlaufen.
 * Wer nur diktiert, soll die Verwaltung nicht sehen müssen; wer nur aufnimmt,
 * braucht „schreiben" nicht in der Leiste.
 *
 * Ausgeblendet heißt **unsichtbar, nicht abgeschaltet**: Die Route bleibt, was
 * sie war, und ein Lesezeichen führt weiterhin hin. Das ist Absicht - die
 * Schalter sind eine Aufräumhilfe für die Leiste, kein Rechtemodell. Wer
 * Rechte will, hat sie längst: den Zugang (`zugang.ts`) und die PIN
 * (`pin.svelte.ts`).
 *
 * Gespeichert wird im Browser wie Farbe und Schrift (`einstellungen.svelte.ts`),
 * und damit ebenfalls über alle drei Apps hinweg geteilt.
 */
export interface Schaltbar {
  /** Zugleich der Name hinter der Vorsilbe im `localStorage`. */
  schluessel: string;
  text: string;
  /**
   * Nicht abschaltbar. Zwei Punkte müssen stehen bleiben, sonst sperrt man
   * sich selbst aus: „Darstellung", weil dort diese Schalter liegen, und
   * „Meine Daten", weil dort die PIN vergeben wird, die inzwischen vor
   * „Darstellung" und „Zugangsdaten" steht.
   */
  fest?: boolean;
  /** Warum dieser Punkt fest ist - die Ansicht schreibt es dazu. */
  grund?: string;
}

export function appSchluessel(schluessel: AppSchluessel): string {
  return `app.${schluessel}`;
}

export function menueSchluessel(pfad: string): string {
  return `menue.${pfad}`;
}

/**
 * „Über wortlaut" hat keine Route, sondern führt aus der App heraus
 * (`PROJEKT_URL`) - einen Pfad als Schlüssel gibt es dafür nicht.
 */
export const PROJEKT_SCHLUESSEL = 'menue.projekt';

/** Die drei Apps in der Kopfleiste, in ihrer Reihenfolge dort. */
export const SCHALTBARE_APPS: Schaltbar[] = APPS.map((eintrag) => ({
  schluessel: appSchluessel(eintrag.schluessel),
  text: eintrag.name,
}));

/**
 * Die Punkte im Menüknopf, in ihrer Reihenfolge dort: erst die der App
 * (`uebergreifend`), dann die gerätebezogenen, zuletzt der Weg nach draußen.
 *
 * Die Liste steht vollständig hier und nicht je App: „Darstellung" ist in
 * jeder App dieselbe Ansicht und soll überall dieselben Schalter zeigen -
 * sonst hinge es davon ab, wo man sie gerade geöffnet hat, ob ein Punkt
 * wiederzufinden ist. Was eine App gar nicht führt (`SPRECHER_PFAD` in
 * „schreiben"), steht dort ohnehin nicht im Menü; der Schalter dazu ist dann
 * eine Einstellung ohne Wirkung, aber keine falsche.
 */
export const SCHALTBARE_MENUEPUNKTE: Schaltbar[] = [
  { schluessel: menueSchluessel(SPRECHER_PFAD), text: 'Sprecher' },
  {
    schluessel: menueSchluessel(MEINE_DATEN_PFAD),
    text: 'Meine Daten',
    fest: true,
    grund: 'Hier wird die PIN vergeben, die vor dieser Seite steht.',
  },
  { schluessel: menueSchluessel(AUSWERTUNG_PFAD), text: 'Auswertung' },
  { schluessel: menueSchluessel(ZUGANGSDATEN_PFAD), text: 'Zugangsdaten' },
  { schluessel: menueSchluessel(EINSTELLUNGEN_PFAD), text: 'Einstellungen' },
  {
    schluessel: menueSchluessel(DARSTELLUNG_PFAD),
    text: 'Darstellung',
    fest: true,
    grund: 'Diese Seite selbst - ohne sie käme kein Schalter zurück.',
  },
  { schluessel: PROJEKT_SCHLUESSEL, text: 'Über wortlaut' },
];
