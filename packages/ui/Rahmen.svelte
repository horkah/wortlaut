<script lang="ts">
  /**
   * Der Rahmen jeder App: Kopfzeile, Inhalt, Fußzeile - und alles hinter dem
   * Menüknopf, einmal gebaut.
   *
   * Marke, App-Reiter, Sprecherzeile und Menüknopf stehen in
   * `Kopfleiste.svelte`. Was dort hineingeht, rechnet dieser Rahmen selbst
   * aus dem gemeinsamen Zustand (`lage.svelte.ts`): wer angemeldet ist, was
   * im Menü steht, welcher Reiter offen ist. Und er zeigt jede Ansicht, die
   * im Menü steht und keiner einzelnen App gehört - Audio, Darstellung,
   * System, Zugangsdaten -, dazu den Hinweis, wenn kein Zugang da ist.
   *
   * **Warum so viel hier.** Bis September 2026 reichte jede App das dem Rahmen
   * einzeln herein, und jede ein wenig anders: Die Stimmen vom Server bekam
   * nur der Rahmen von „hören" - aus „lernen" und „schreiben" standen sie
   * unter „Audio" gar nicht zur Wahl -, „lernen" nannte die Aufsicht in der
   * Kopfzeile nicht, „schreiben" nannte die Verwaltung „kein Zugang", und die
   * Zugangsdaten hatten in jeder App einen eigenen Umschlag. Keine dieser
   * Abweichungen war entschieden worden. Was eine App nicht hereinreicht, kann
   * sie nicht anders hereinreichen.
   *
   * Die App liefert nur, was ihr gehört: die Ansicht zu jedem ihrer Reiter
   * (`ansichten`, die Reiter selbst stehen in `REITER`) und ihre Ansicht für
   * alles, was kein Reiter ist (`ansicht`).
   */
  import type { Component } from 'svelte';
  import Kopfleiste from './Kopfleiste.svelte';
  import Fusszeile from './Fusszeile.svelte';
  import Audio from './Audio.svelte';
  import Darstellung from './Darstellung.svelte';
  import System from './System.svelte';
  import Zugangsdaten from './Zugangsdaten.svelte';
  import KeinZugang from './KeinZugang.svelte';
  import {
    AUDIO_PFAD,
    DARSTELLUNG_PFAD,
    REITER,
    SYSTEM_PFAD,
    ZUGANGSDATEN_PFAD,
    menuePunkte,
    type AppSchluessel,
  } from './apps';
  import { merkeReiter, vorgabeReiter } from './reiter';
  import { ladeZugang, lage } from './lage.svelte';

  let {
    app,
    ansichten = {},
    ansicht = null,
    markiert,
  }: {
    /** Welche der drei Apps diese Seite ist. */
    app: AppSchluessel;
    /**
     * Die Ansicht zu jedem Reiter dieser App, nach Pfad. Ein Reiter ohne
     * Ansicht steht nicht in der Leiste; keiner heißt: keine zweite Reihe.
     */
    ansichten?: Record<string, Component>;
    /** Was die App zu einer Route zeigt, die kein Reiter ist; `null`: der Reiter. */
    ansicht?: Component | null;
    /**
     * Was die Kopfleiste auf einer solchen Route als offen markiert - etwa
     * „Training" für einen einzelnen Lauf. Ohne Angabe der Reiter, der als
     * Vorgabe gilt.
     */
    markiert?: string;
  } = $props();

  // Die Ansichten hinter dem Menüknopf, die keiner App gehören. Sie stehen
  // vor der Zugangsprüfung: Mikrofon und Schrift gehören zum Gerät, und die
  // Zugangsdaten sind genau der Ort, an dem ein fehlender Zugang eingetragen
  // wird - läge die Ansicht hinter der Prüfung, käme niemand je an sie heran.
  const MENUEANSICHTEN: Record<string, Component> = {
    [AUDIO_PFAD]: Audio,
    [DARSTELLUNG_PFAD]: Darstellung,
    [SYSTEM_PFAD]: System,
    [ZUGANGSDATEN_PFAD]: Zugangsdaten,
  };

  const menue = $derived(menuePunkte(lage.art, app));
  const reiter = $derived(REITER[app].filter((punkt) => punkt.pfad in ansichten));

  // Welcher Reiter gilt, solange in der Adresse nichts steht: der, auf dem
  // zuletzt gearbeitet wurde (siehe `reiter.ts`). Nicht angesprungen, sondern
  // als Vorgabe eingesetzt - die Adresse bleibt leer, und der Zurück-Knopf
  // führt nicht auf eine Seite, die niemand angesteuert hat.
  const vorgabe = $derived(vorgabeReiter(app, reiter));
  const aufReiter = $derived(reiter.some((punkt) => punkt.pfad === lage.route));

  // Gemerkt wird jede Route, die ein Reiter ist. Menüansichten nicht -
  // „Darstellung" ist kein Ort, an dem jemand weiterarbeiten will.
  $effect(() => {
    if (aufReiter) merkeReiter(app, lage.route);
  });

  // Was die Kopfleiste als offen markiert. Reiter und Menüansichten markieren
  // sich selbst; alles andere fällt auf das zurück, was die App dafür nennt,
  // sonst auf den Reiter, der wirklich dasteht - ohne das markierte eine
  // unbekannte Route (altes Lesezeichen) nichts.
  const offen = $derived(
    aufReiter || menue.some((punkt) => punkt.pfad === lage.route)
      ? lage.route
      : (markiert ?? (reiter.length ? vorgabe : lage.route)),
  );

  // Wer der Server in diesem Browser sieht, steht rechts oben - in jeder App
  // gleich. Verwaltung und Aufsicht stehen dort wie ein Sprechername: Sie
  // sagen, wer hier unterwegs ist. `undefined`, solange die Antwort aussteht,
  // zeigt nichts, statt kurz „kein Zugang" vorzutäuschen; `null` heißt „kein
  // gültiger Zugang".
  const angemeldet = $derived(
    lage.art === 'unbekannt'
      ? undefined
      : lage.art === 'aufsicht'
        ? 'Aufsicht'
        : lage.art === 'verwaltung'
          ? 'Verwaltung'
          : lage.name,
  );

  // Großgeschrieben, damit Svelte 5 den Wert als Komponente nimmt.
  const Inhalt = $derived(
    MENUEANSICHTEN[lage.route] ??
      (lage.art === 'keiner'
        ? KeinZugang
        : (ansicht ?? ansichten[lage.route] ?? ansichten[vorgabe] ?? null)),
  );

  ladeZugang();
</script>

<Kopfleiste {app} punkte={reiter} {menue} sprecher={angemeldet} route={offen} />

<main>
  {#if Inhalt}
    <Inhalt />
  {/if}
</main>

<Fusszeile />
