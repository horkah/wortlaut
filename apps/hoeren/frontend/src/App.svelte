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
    SPRECHER_PFAD,
    ZUGANGSDATEN_PFAD,
    type Menuepunkt,
  } from '$ui/apps';
  import { EINSICHT_ROUTE, ladeZugang, zustand } from './lib/zustand.svelte';
  import Verwaltung from './routes/Verwaltung.svelte';
  import Einsicht from './routes/Einsicht.svelte';
  import MeineDaten from './routes/MeineDaten.svelte';
  import Auswertung from './routes/Auswertung.svelte';
  import Quelle from './routes/Quelle.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Fortschritt from './routes/Fortschritt.svelte';
  import Zugangsdaten from './routes/Zugangsdaten.svelte';

  // Die Reihenfolge ist der Weg durch die Arbeit an einem Sprecher: Text
  // holen, aufnehmen, nachsehen, was zusammengekommen ist. Die Einstellungen
  // stehen bewusst nicht darin, sondern im Menü der Kopfleiste (warum:
  // `apps.ts`).
  const MENUE: Menuepunkt[] = [
    { pfad: '/quelle', text: 'Textquelle' },
    { pfad: '/aufnahme', text: 'Aufnehmen' },
    { pfad: '/fortschritt', text: 'Fortschritt' },
  ];

  // Wer der Server in diesem Browser sieht, entscheidet, was es zu sehen gibt:
  // Ein Sprecher nimmt auf, die Verwaltung legt Profile an und gibt Zugänge
  // aus, die Aufsicht sieht über alle Korpora. Auswählen kann niemand mehr
  // etwas - die Kennung steckt im Zugang.
  const spricht = $derived(zustand.art === 'sprecher');
  const beaufsichtigt = $derived(zustand.art === 'aufsicht');

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
          : // Die Auswertung misst den eigenen Korpus und braucht darum
            // ebenfalls einen Sprecher - sie steht hier neben „Meine Daten",
            // aus demselben Grund und mit derselben Bedingung.
            zustand.route === AUSWERTUNG_PFAD && spricht
            ? Auswertung
            : !spricht
            ? Verwaltung
            : ({
                '/quelle': Quelle,
                '/aufnahme': Aufnahme,
                '/fortschritt': Fortschritt,
              }[zustand.route] ?? Quelle),
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
  // Die Auswertung steht direkt hinter „Meine Daten": Beide zeigen dieselben
  // Aufnahmen, die eine als Bestand, die andere als Messung. Sie erscheint nur
  // für einen Sprecher - gemessen wird ein Korpus, und den bringt der Zugang
  // mit; Verwaltung und Aufsicht haben keinen eigenen.
  const uebergreifend = $derived([
    ...(spricht
      ? [
          { pfad: MEINE_DATEN_PFAD, text: 'Meine Daten' },
          { pfad: AUSWERTUNG_PFAD, text: 'Auswertung' },
        ]
      : [{ pfad: SPRECHER_PFAD, text: 'Sprecher' }]),
    { pfad: ZUGANGSDATEN_PFAD, text: 'Zugangsdaten' },
  ]);

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
          : '/quelle',
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
</script>

<Rahmen app="hoeren" punkte={menue} {uebergreifend} sprecher={name} route={offen}>
  <Ansicht />
</Rahmen>
