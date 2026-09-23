<script lang="ts">
  /**
   * Was „hören" an eigenen Ansichten hat - der Rahmen darum steht in
   * `$ui/Rahmen.svelte` und ist in jeder App derselbe.
   */
  import Rahmen from '$ui/Rahmen.svelte';
  import {
    AUSWERTUNG_PFAD,
    GERAETE_PUNKTE,
    MEINE_DATEN_PFAD,
    ohneZugang,
    SPRECHER_PFAD,
    uebergreifendePunkte,
    ZUGANGSDATEN_PFAD,
    EDITIEREN_ROUTE,
    ZUSCHNITT_PFAD,
    type Menuepunkt,
  } from '$ui/apps';
  import KeinZugang from '$ui/KeinZugang.svelte';
  import { merkeReiter, vorgabeReiter } from '$ui/reiter';
  import { zugang } from '$ui/zugang';
  import type { Servestimme } from '$ui/speak';
  import { servestimmen, stimmprobe } from './lib/api';
  import { EINSICHT_ROUTE, gehZu, ladeZugang, zustand } from './lib/zustand.svelte';
  import Verwaltung from './routes/Verwaltung.svelte';
  import Einsicht from './routes/Einsicht.svelte';
  import MeineDaten from './routes/MeineDaten.svelte';
  import Auswertung from './routes/Auswertung.svelte';
  import Quelle from './routes/Quelle.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Fortschritt from './routes/Fortschritt.svelte';
  import Zugangsdaten from './routes/Zugangsdaten.svelte';
  import Zuschnitt from './routes/Zuschnitt.svelte';
  import Editieren from './routes/Editieren.svelte';

  // Die Reihenfolge ist der Weg durch die Arbeit an einem Sprecher: Text
  // holen, aufnehmen, nachsehen, was zusammengekommen ist - und am Ende
  // messen, was die Modelle daraus machen. Die Einstellungen stehen bewusst
  // nicht darin, sondern im Menü der Kopfleiste (warum: `apps.ts`).
  //
  // Die Auswertung stand lange im Menü, als „Nachsehen" und nicht als
  // Tätigkeit. Sie ist beides nicht: Sie ist der Schritt, der aus dem Korpus
  // Zahlen macht, und ohne sie bleibt die Modellübersicht in „lernen" leer.
  // Hierher gehört sie, ans Ende der Reihe.
  const MENUE: Menuepunkt[] = [
    { pfad: '/quelle', text: 'Textquelle' },
    { pfad: '/aufnahme', text: 'Aufnehmen' },
    { pfad: '/fortschritt', text: 'Fortschritt' },
    { pfad: AUSWERTUNG_PFAD, text: 'Auswertung' },
  ];

  // Wer der Server in diesem Browser sieht, entscheidet, was es zu sehen gibt:
  // Ein Sprecher nimmt auf, die Verwaltung legt Profile an und gibt Zugänge
  // aus, die Aufsicht sieht über alle Korpora. Auswählen kann niemand mehr
  // etwas - die Kennung steckt im Zugang.
  const spricht = $derived(zustand.art === 'sprecher');
  const beaufsichtigt = $derived(zustand.art === 'aufsicht');

  // Welcher Reiter gilt, solange in der Adresse nichts steht: der, auf dem
  // zuletzt gearbeitet wurde (siehe `$ui/reiter`). Nicht angesprungen, sondern
  // als Vorgabe eingesetzt - die Adresse bleibt leer, und der Zurück-Knopf
  // führt nicht auf eine Seite, die niemand angesteuert hat.
  const vorgabe = $derived(vorgabeReiter('hoeren', MENUE));

  // Gemerkt wird beim Verlassen wie beim Ankommen: Jede Route, die ein Reiter
  // dieser App ist, wird festgehalten. Menüansichten nicht - „Darstellung" ist
  // kein Ort, an dem jemand weiterarbeiten will.
  $effect(() => {
    if (spricht && MENUE.some((punkt) => punkt.pfad === zustand.route)) {
      merkeReiter('hoeren', zustand.route);
    }
  });

  // Die Reiter dieser App und ihre Ansichten. Eine Abbildung und keine
  // Kette von Vergleichen: Dieselbe Zuordnung beantwortet, was `zustand.route`
  // zeigt und was die Vorgabe zeigt.
  const ANSICHTEN: Record<string, typeof Quelle> = {
    '/quelle': Quelle,
    '/aufnahme': Aufnahme,
    '/fortschritt': Fortschritt,
    [AUSWERTUNG_PFAD]: Auswertung,
  };

  // Großgeschriebene Variablen sind in Svelte 5 als Komponente verwendbar.
  //
  // Die Zugangsdaten stehen vor der Zugangsprüfung: Ohne Zugang liefert die
  // API nichts, und der Verwaltertoken wird genau dort eingetragen. Läge die
  // Ansicht dahinter, käme niemand je an sie heran.
  const Ansicht = $derived(
    zustand.route === ZUGANGSDATEN_PFAD
      ? Zugangsdaten
      : // Die Einsicht der Aufsicht in einen einzelnen Korpus. Sie steht in
        // keiner Reiterreihe: Hierher führt ein Klick aus der Sprecherliste,
        // zurück derselbe Weg.
        beaufsichtigt && zustand.route.startsWith(EINSICHT_ROUTE)
        ? Einsicht
        : // Dasselbe für den Sprecher selbst - dieselbe Ansicht wie die
          // Einsicht der Aufsicht, nur auf die eigenen Daten (siehe
          // `MeineDaten.svelte`).
          zustand.route === MEINE_DATEN_PFAD
          ? MeineDaten
          : // Der Zuschnitt, erreichbar aus „Meine Daten" und nur von dort.
            // Er steht in keiner Reiterreihe und in keinem Menü (siehe
            // `ZUSCHNITT_PFAD` in `$ui/apps`), braucht aber denselben
            // Sprecher wie sie - es sind dessen eigene Aufnahmen.
            spricht && zustand.route === ZUSCHNITT_PFAD
            ? Zuschnitt
            : // „Editieren" - eine Aufnahme aus dem Zuschnitt: teilen oder mit
              // berichtigtem Text kopieren.
              spricht && zustand.route.startsWith(EDITIEREN_ROUTE)
              ? Editieren
            : !spricht
            ? Verwaltung
            : // Die Reiter dieser App. Die Auswertung steht mit darin: Sie
              // misst den eigenen Korpus und braucht darum einen Sprecher,
              // genau wie das Aufnehmen selbst.
              (ANSICHTEN[zustand.route] ?? ANSICHTEN[vorgabe] ?? Quelle),
  );

  // Nur wer aufnimmt, hat Ansichten zu wechseln; die Verwaltung hat eine
  // einzige Seite, und eine Reiterreihe wäre dort eine Zeile voller
  // Sackgassen.
  const menue = $derived(spricht ? MENUE : []);
  // Was diese App über die gerätebezogenen Punkte hinaus ins Menü stellt.
  //
  // Der Sprecher steht nicht mehr im Menü, wenn einer spricht: Er wird nicht
  // gewählt, sondern abgeleitet. Für Verwaltung und Aufsicht ist er der
  // Rückweg aus der Einsicht in einen einzelnen Korpus.
  //
  // Die Zugangsdaten stehen immer da - auch und gerade, wenn dieser Browser
  // keinen gültigen Zugang hat: Genau dann ist der Punkt der einzige Weg
  // hinein, und ein Menü, das ihn erst nach erfolgreicher Anmeldung zeigt,
  // hätte die Tür hinter dem Schloss.
  //
  // „Modelle" steht hier ausdrücklich **nicht**: Die Ansicht ist ein Reiter in
  // „lernen", und ein Menüpunkt daneben wäre ein zweiter Weg zu derselben
  // Seite. Das Menü führt, was keine Reiterreihe trägt; alles, was eine hat,
  // steht dort und nirgends sonst. Wer von hier aus hinüber will, klickt den
  // App-Reiter „lernen" in der oberen Reihe.
  const uebergreifend = $derived(uebergreifendePunkte(zustand.art, 'hoeren'));

  // Wer gar nichts vorweist, sieht denselben einen Schritt wie in „lernen" und
  // „schreiben" (`$ui/KeinZugang.svelte`).
  //
  // Das fehlte hier bis September 2026, und der Grund war ein alter: „hören"
  // zeigt jedem, der kein Sprecher ist, die Verwaltung - und das stimmte,
  // solange „kein Sprecher" nur Verwaltung oder Aufsicht heißen konnte. Wer
  // ohne jeden Zugang ankam, landete damit auf einer Seite, deren Anfragen
  // sämtlich abgewiesen wurden, und las statt eines Satzes eine Reihe Fehler.
  const keinZugang = $derived(ohneZugang(zustand.art, zustand.route));

  // Was die Kopfleiste als offen markiert. Menüansichten markieren sich
  // selbst; alles andere fällt auf den Reiter zurück, der wirklich dasteht -
  // ohne das markierte eine unbekannte Route (altes Lesezeichen) nichts.
  const offen = $derived(
    [...uebergreifend, ...GERAETE_PUNKTE].some((punkt) => punkt.pfad === zustand.route)
      ? zustand.route
      : !spricht
        ? SPRECHER_PFAD
        : MENUE.some((punkt) => punkt.pfad === zustand.route)
          ? zustand.route
          : vorgabe,
  );

  // Für die Kopfzeile: der Name, den der Server zum vorgelegten Zugang nennt -
  // nicht der, den sich der Browser gemerkt hat. `undefined` heißt „führt
  // keinen Sprecher, und ist auch nicht Verwaltung oder Aufsicht" - der Fall
  // tritt praktisch nicht ein, da `art` dann eines von beiden ist.
  //
  // Verwaltung und Aufsicht stehen genau hier und nicht mehr als eigener
  // Hinweis links: Sie sagen, wer hier unterwegs ist, genau wie ein
  // Sprechername das tut, und sollen deshalb genauso aussehen und genauso
  // rechtsbündig stehen - nicht in der Reiterreihe verschwinden.
  const name = $derived(
    spricht || zustand.art === 'keiner'
      ? zustand.name
      : beaufsichtigt
        ? 'Aufsicht'
        : zustand.art === 'verwaltung'
          ? 'Verwaltung'
          : undefined,
  );

  ladeZugang();

  /**
   * Welche Stimmen der Server sprechen kann.
   *
   * Einmal geholt und an den Rahmen weitergereicht, damit die Stimmwahl unter
   * „Einstellungen" sie anbietet. Eine leere Liste ist der Normalfall: Dann
   * liest der Browser vor wie bisher (`packages/ui/speak.ts`).
   *
   * Scheitert die Abfrage - kein Zugang, Server alt -, bleibt die Liste leer.
   * Vorlesen ist eine Hilfe und keine Bedingung; ein Fehler darüber gehört
   * nicht auf die Seite.
   */
  let stimmenVomServer = $state<Servestimme[]>([]);

  $effect(() => {
    if (!zugang()) return;
    servestimmen()
      .then((gefunden) => (stimmenVomServer = gefunden))
      .catch(() => (stimmenVomServer = []));
  });
</script>

<Rahmen
  app="hoeren"
  punkte={menue}
  {uebergreifend}
  sprecher={name}
  sprache={zustand.sprache}
  route={offen}
  servestimmen={stimmenVomServer}
  probeHolen={stimmprobe}
>
  {#if keinZugang}
    <KeinZugang {gehZu} />
  {:else}
    <Ansicht />
  {/if}
</Rahmen>
