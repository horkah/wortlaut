/**
 * Die drei Apps unter einer Domain, plus die Menüpunkte innerhalb einer App.
 *
 * Alle drei sind gebaut. `verfuegbar: false` bleibt als Möglichkeit stehen:
 * Ein Reiter, der sichtbar, aber nicht anklickbar ist, zeigt, dass wortlaut
 * aus drei Teilen besteht, auch wenn einer davon noch fehlt.
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
    verfuegbar: true,
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
 * Wo die Grundmodelle über den eigenen Korpus laufen - die Auswertung.
 *
 * Nur „hören" führt sie, und zwar als **Reiter**: Dort liegt der Korpus, dort
 * wird gemessen, und jede Aufnahme ist eine fertige Prüfaufgabe - die Vorlage
 * steht daneben, also lässt sich vergleichen, was ein Erkenner daraus macht.
 *
 * Sie stand lange im Menü, mit der Begründung, Auswerten sei ein Nachsehen und
 * keine Tätigkeit. Das stimmt nicht mehr: Die Auswertung ist der Schritt, der
 * aus einem Korpus Zahlen macht, und ohne sie bleibt die Modellübersicht in
 * „lernen" leer. Sie gehört damit in dieselbe Reihe wie Textquelle, Aufnehmen
 * und Fortschritt - ans Ende, weil sie der letzte Schritt darin ist.
 */
export const AUSWERTUNG_PFAD = '/auswertung';

/**
 * Wo alle Modelle eines Menschen zusammen stehen - die eine Übersicht.
 *
 * Sie liegt in „lernen" und ist dort ein Reiter. Die selbst trainierten Stände
 * und die unveränderten Grundmodelle stehen dort in einer Tabelle, an
 * denselben Testaufnahmen gemessen, und eines davon wird freigegeben - das,
 * mit dem „schreiben" danach diktiert.
 *
 * Es gab das einmal zweimal: eine Liste der eigenen Stände mit einem
 * Freigabeknopf in „lernen" und daneben in „schreiben" eine zweite Liste, in
 * der sich zusätzlich ein Grundmodell auswählen ließ. Zwei Ansichten, zwei
 * Begriffe, dieselbe Entscheidung - und in keiner von beiden stand, ob sich
 * das Training gelohnt hat. Wer das wissen will, braucht beide Sorten in einer
 * Tabelle, auf denselben Zahlen.
 *
 * Deshalb steht hier auch eine **Adresse**: Aus „schreiben" führt die
 * Modellzeile unter dem Aufnahmeknopf hinüber, und zwar als voller Weg und
 * nicht als Hash-Route dieser App.
 *
 * Im Menü steht der Punkt dagegen nirgends, obwohl das eine Zeitlang so war:
 * Was eine Reiterreihe trägt, steht dort und nicht noch einmal hinter dem
 * Menüknopf. Ein zweiter Weg zu derselben Seite ist keine Bequemlichkeit,
 * sondern eine Stelle, an der jemand zweimal suchen muss.
 */
export const MODELLE_PFAD = '/modelle';
export const MODELLE_URL = `/lernen/#${MODELLE_PFAD}`;

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
 * Der Schlüssel eines Reiters - der App-Name steckt mit drin.
 *
 * Anders als bei den Menüpunkten, denn die Reiterrouten gehören je einer App
 * und dürfen sich zwischen zweien wiederholen: `/aufnahme` gibt es in „hören",
 * und nichts hindert „schreiben" daran, es später ebenso zu nennen. Ohne den
 * App-Namen im Schlüssel schaltete ein Haken dann zwei Reiter in zwei Apps.
 */
export function reiterSchluessel(app: AppSchluessel, pfad: string): string {
  return `reiter.${app}.${pfad}`;
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

/**
 * Die Ansichten innerhalb der Apps - die zweite Reihe der Kopfleiste.
 *
 * Sie sind aus demselben Grund abschaltbar wie die Apps selbst: Wer nur
 * aufnimmt, braucht die Auswertung nicht in der Leiste; wer nur trainiert,
 * kommt ohne die Aufteilung aus. Und es sind genau diese Reiter, die eine
 * Ansicht tragen, die man selten braucht und die viel Platz einnimmt - die
 * Auswertung in „hören" und die Modellübersicht in „lernen".
 *
 * Auch hier gilt: Ausgeblendet heißt unsichtbar, nicht abgeschaltet. Die
 * Route bleibt, was sie war, und ein Lesezeichen darauf führt weiterhin hin -
 * die Kopfleiste stellt dann sogar den Rückweg ins Menü (`Kopfleiste.svelte`).
 *
 * Keiner davon ist fest: Selbst wenn jemand alle abschaltet, bleibt die erste
 * Ansicht der App stehen (jede App fällt auf ihren ersten Reiter zurück), und
 * „Darstellung" steht weiterhin im Menü.
 *
 * „schreiben" fehlt hier, und das ist kein Versehen: Die App hat keine
 * Reiterreihe. Ihr Weg ist eine Folge - sprechen, hören, bessern, bestätigen -
 * und keine Auswahl (Grundentscheidung 7).
 */
export const SCHALTBARE_REITER: { app: AppSchluessel; eintraege: Schaltbar[] }[] = [
  {
    app: 'hoeren',
    eintraege: [
      { schluessel: reiterSchluessel('hoeren', '/quelle'), text: 'Textquelle' },
      { schluessel: reiterSchluessel('hoeren', '/aufnahme'), text: 'Aufnehmen' },
      { schluessel: reiterSchluessel('hoeren', '/fortschritt'), text: 'Fortschritt' },
      { schluessel: reiterSchluessel('hoeren', AUSWERTUNG_PFAD), text: 'Auswertung' },
    ],
  },
  {
    app: 'lernen',
    eintraege: [
      { schluessel: reiterSchluessel('lernen', '/aufteilung'), text: 'Aufteilung' },
      { schluessel: reiterSchluessel('lernen', '/training'), text: 'Training' },
      { schluessel: reiterSchluessel('lernen', MODELLE_PFAD), text: 'Modelle' },
    ],
  },
];
