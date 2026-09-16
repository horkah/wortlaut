<script lang="ts">
  /**
   * Was „lernen" an eigenen Ansichten hat - der Rahmen darum steht in
   * `$ui/Rahmen.svelte` und ist in jeder App derselbe.
   *
   * Drei Ansichten, und ihre Reihenfolge ist der Weg durch die Arbeit:
   * nachsehen, wie die Aufnahmen aufgeteilt sind, ein Training beauftragen und
   * ihm zusehen, und am Ende entscheiden, welches Modell gelten soll.
   *
   * Die letzte davon - „Modelle" - ist zugleich die Ansicht, auf der auch
   * „schreiben" und „hören" landen, wenn dort jemand auf das Modell klickt.
   * Sie liegt hier, weil hier die Stände entstehen; sie zeigt aber alles, was
   * dieser Mensch laden kann, die unveränderten Grundmodelle eingeschlossen.
   */
  import Rahmen from '$ui/Rahmen.svelte';
  import KeinZugang from '$ui/KeinZugang.svelte';
  import {
    GERAETE_PUNKTE,
    MEINE_DATEN_PFAD,
    MODELLE_PFAD,
    ohneZugang,
    uebergreifendePunkte,
    ZUGANGSDATEN_PFAD,
    type Menuepunkt,
  } from '$ui/apps';
  import { merkeReiter, vorgabeReiter } from '$ui/reiter';
  import { LAUF_ROUTE, gehZu, laufAusRoute, ladeZugang, zustand } from './lib/zustand.svelte';
  import Aufteilung from './routes/Aufteilung.svelte';
  import Training from './routes/Training.svelte';
  import Lauf from './routes/Lauf.svelte';
  import Modelle from './routes/Modelle.svelte';
  import Zugangsdaten from './routes/Zugangsdaten.svelte';

  const MENUE: Menuepunkt[] = [
    { pfad: '/aufteilung', text: 'Aufteilung' },
    { pfad: '/training', text: 'Training' },
    { pfad: MODELLE_PFAD, text: 'Modelle' },
  ];

  // Nur ein Sprecher hat hier etwas zu sehen: Ein Modell gehört zu genau einem
  // Menschen, und der Korpus, auf dem es lernt, hängt am Zugang.
  const spricht = $derived(zustand.art === 'sprecher');

  // Wer gar keinen Zugang vorweist, sieht nicht das Formular, sondern denselben
  // einen Schritt wie in „hören" und „schreiben" (`$ui/KeinZugang.svelte`).
  // Ausgenommen bleibt die Ansicht der Zugangsdaten selbst: Dorthin führt der
  // Schritt, sie darf nicht hinter ihm liegen.
  const keinZugang = $derived(ohneZugang(zustand.art, zustand.route));
  const jobId = $derived(laufAusRoute(zustand.route));

  // Welcher Reiter gilt, solange in der Adresse nichts steht: der, auf dem
  // zuletzt gearbeitet wurde (siehe `$ui/reiter`). Gerade hier zählt das - ein
  // Training dauert Stunden, und wer zwischendurch nachsieht, will „Training"
  // sehen und nicht die Aufteilung.
  const vorgabe = $derived(vorgabeReiter('lernen', MENUE));

  $effect(() => {
    if (spricht && MENUE.some((punkt) => punkt.pfad === zustand.route)) {
      merkeReiter('lernen', zustand.route);
    }
  });

  // Was diese App über die gerätebezogenen Punkte hinaus ins Menü stellt.
  // „Meine Daten" liegt in „hören" - dort ist der Korpus -, steht aber hier:
  // Wer beim Trainieren wissen will, worauf trainiert wird, soll nicht erst
  // die App wechseln müssen, um den Weg dorthin zu finden.
  //
  // Die Adresse führt aus dieser App heraus und muss deshalb vollständig sein -
  // Wurzel **und** Hash, genau wie in „schreiben". Ohne das `/#` bliebe
  // `/meine-daten` ein Pfad, den niemand ausliefert: Das Frontend kennt nur
  // Hash-Routen, und das Backend antwortet auf unbekannte Pfade mit 404
  // (`StaticFiles` liefert dafür keine `index.html`). Es stand hier eine Weile
  // ohne, und der Menüpunkt führte auf eine leere Seite mit „Not Found".
  //
  // „Auswertung" steht hier ausdrücklich **nicht** mehr: Sie ist ein Reiter in
  // „hören", und ein Menüpunkt daneben wäre ein zweiter Weg zu derselben
  // Seite. Das Menü führt, was keine Reiterreihe trägt; alles, was eine hat,
  // steht dort und nirgends sonst.
  const uebergreifend = $derived(uebergreifendePunkte(zustand.art, 'lernen'));

  // Die Reiter dieser App und ihre Ansichten. Eine Abbildung und keine Kette
  // von Vergleichen: Dieselbe Zuordnung beantwortet, was `zustand.route` zeigt
  // und was die Vorgabe zeigt.
  const ANSICHTEN: Record<string, typeof Aufteilung> = {
    '/aufteilung': Aufteilung,
    '/training': Training,
    [MODELLE_PFAD]: Modelle,
  };

  // Großgeschriebene Variablen sind in Svelte 5 als Komponente verwendbar.
  //
  // Die Zugangsdaten stehen vor der Zugangsprüfung: Ohne Zugang liefert die
  // API nichts, und genau dort wird er eingetragen. Läge die Ansicht dahinter,
  // käme niemand je an sie heran.
  // Ein einzelner Lauf steht nicht in dieser Kette: Er braucht eine Kennung
  // als Eigenschaft, und die Markierung unten reicht sie ihm durch.
  const Ansicht = $derived(
    zustand.route === ZUGANGSDATEN_PFAD || !spricht
      ? Zugangsdaten
      : (ANSICHTEN[zustand.route] ?? ANSICHTEN[vorgabe] ?? Aufteilung),
  );

  // Was die Kopfleiste als offen markiert. Menüansichten markieren sich
  // selbst; alles andere fällt auf den Reiter zurück, der wirklich dasteht -
  // ohne das markierte eine unbekannte Route (altes Lesezeichen) nichts. Ein
  // einzelner Lauf gehört zu „Training": Er ist keine eigene Ansicht in der
  // Reihe, sondern das, was hinter einem Klick darin liegt.
  const offen = $derived(
    [...uebergreifend, ...GERAETE_PUNKTE].some((punkt) => punkt.pfad === zustand.route)
      ? zustand.route
      : jobId
        ? '/training'
        : MENUE.some((punkt) => punkt.pfad === zustand.route)
          ? zustand.route
          : vorgabe,
  );

  const name = $derived(spricht || zustand.art === 'keiner' ? zustand.name : undefined);

  ladeZugang();
</script>

<Rahmen
  app="lernen"
  punkte={spricht ? MENUE : []}
  {uebergreifend}
  sprecher={name}
  sprache={zustand.sprache}
  route={offen}
>
  {#if keinZugang}
    <KeinZugang {gehZu} />
  {:else if jobId && spricht && zustand.route !== ZUGANGSDATEN_PFAD}
    <Lauf {jobId} />
  {:else}
    <Ansicht />
  {/if}
</Rahmen>
