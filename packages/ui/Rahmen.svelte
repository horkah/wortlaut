<script lang="ts">
  /**
   * Der Rahmen jeder App: Kopfzeile, Inhalt, Fußzeile - einmal gebaut.
   *
   * Marke, App-Reiter, Sprecherzeile und Menüknopf stehen in
   * `Kopfleiste.svelte` und damit ohnehin nur an einer Stelle. Was bisher
   * fehlte, war der Rahmen darum: Jede App hängte Kopf- und Fußzeile selbst
   * auf und beantwortete die gerätebezogenen Menüpunkte selbst - dieselbe
   * Kette aus `route === EINSTELLUNGEN_PFAD ? … : route === DARSTELLUNG_PFAD`
   * in jeder `App.svelte`. Ein vierter solcher Punkt hätte jede App angefasst,
   * und wer einen vergisst, hat einen Menüeintrag, der ins Leere führt.
   *
   * Darum hier: Der Rahmen kennt die gerätebezogenen Ansichten
   * (`GERAETE_PUNKTE` in `apps.ts`) und zeigt sie selbst. Die App liefert nur
   * noch ihre eigenen Ansichten - als Inhalt zwischen den Klammern.
   *
   * Was die App darüber hinaus ins Menü stellt (Sprecher, Zugangsdaten),
   * reicht sie als `uebergreifend` durch: Punkte, die diese App auflöst, aber
   * nicht in ihre Reiterreihe gehören. So bleibt das Menü an einer Stelle
   * gebaut, ohne dass die Kopfleiste die Sonderfälle einzelner Apps kennt.
   */
  import type { Snippet } from 'svelte';
  import Kopfleiste from './Kopfleiste.svelte';
  import Fusszeile from './Fusszeile.svelte';
  import Einstellungen from './Einstellungen.svelte';
  import Darstellung from './Darstellung.svelte';
  import {
    DARSTELLUNG_PFAD,
    EINSTELLUNGEN_PFAD,
    type AppSchluessel,
    type Menuepunkt,
  } from './apps';

  let {
    app,
    punkte = [],
    uebergreifend = [],
    sprecher,
    route = '/',
    children,
  }: {
    /** Welche der drei Apps diese Seite ist. */
    app: AppSchluessel;
    /** Die Ansichten dieser App für die zweite Reihe; leer heißt: keine Reihe. */
    punkte?: Menuepunkt[];
    /** Menüpunkte dieser App, über den gerätebezogenen (siehe `Kopfleiste`). */
    uebergreifend?: Menuepunkt[];
    /**
     * Wer hier angemeldet ist - ein Sprechername oder, für „hören", auch
     * „Verwaltung"/„Aufsicht". `undefined` heißt „führt keinen Sprecher".
     */
    sprecher?: string | null;
    /** Die offene Hash-Route, ohne `#`. */
    route?: string;
    /** Die Ansicht, die diese App zur Route zeigt. */
    children: Snippet;
  } = $props();

  // Großgeschrieben, damit Svelte 5 den Wert als Komponente nimmt. `null`
  // heißt: keine gerätebezogene Ansicht offen, die App ist an der Reihe.
  const Geraet = $derived(
    route === EINSTELLUNGEN_PFAD ? Einstellungen : route === DARSTELLUNG_PFAD ? Darstellung : null,
  );
</script>

<Kopfleiste {app} {punkte} {uebergreifend} {sprecher} {route} />

<main>
  {#if Geraet}
    <Geraet />
  {:else}
    {@render children()}
  {/if}
</main>

<Fusszeile />
