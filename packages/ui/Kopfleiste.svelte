<script lang="ts">
  /**
   * Die Kopfzeile aller drei Apps: oben die App, darunter die Ansicht.
   *
   * Zwei Reihen, weil es zwei Ebenen sind. Wer hier steht, soll ohne Nachdenken
   * beides sehen: in welcher der drei Apps er ist und welche Ansicht davon
   * gerade offen ist. Beides ist farbig hinterlegt, die App kräftig, die
   * Ansicht darunter blasser — sonst streiten die beiden Reihen um die
   * Aufmerksamkeit.
   */
  import { APPS, EINSTELLUNGEN_PFAD, type AppSchluessel, type Menuepunkt } from './apps';
  // Als Quelltext eingebunden und nicht als <img>, damit das Zeichen die
  // Schriftfarbe des Schriftzugs annimmt (die Datei zeichnet currentColor).
  import zeichen from '../../assets/wortlaut-logo.svg?raw';

  let {
    app,
    punkte = [],
    route = '/',
    hinweis = '',
  }: {
    /** Welche der drei Apps diese Seite ist. */
    app: AppSchluessel;
    /** Die Ansichten dieser App; leer lassen heißt: zweite Reihe ausblenden. */
    punkte?: Menuepunkt[];
    /** Die offene Hash-Route, ohne `#`. */
    route?: string;
    /**
     * Eine Zeile am rechten Rand der App-Reihe. „schreiben" zeigt darin
     * dauerhaft Basismodell und Datum seines Modellstands: Ein Modellwechsel
     * ist dort eine Konfigurationsänderung, und wer eine Ausgabe beurteilt,
     * muss sehen, welcher Stand sie erzeugt hat.
     */
    hinweis?: string;
  } = $props();

  // Die Einstellungen gehören zum Gerät, nicht zur App, und stehen deshalb
  // nicht in der Reiterreihe einer einzelnen App, sondern hier hinter dem
  // Menüknopf — in jeder App an derselben Stelle. Eingeklappt, weil sie selten
  // gebraucht werden: „schreiben" soll ein großer Knopf bleiben
  // (Grundentscheidung 7).
  let offen = $state(false);
  let huelle = $state<HTMLElement | null>(null);
  let knopf = $state<HTMLButtonElement | null>(null);

  // In den Einstellungen braucht es einen Weg zurück, und zwar hier: „schreiben"
  // hat gar keine Reiterreihe, und „hören" blendet sie ohne gewählten Sprecher
  // aus. Ohne diesen Eintrag käme man nur über den Zurück-Knopf des Browsers
  // wieder heraus.
  const inEinstellungen = $derived(route === EINSTELLUNGEN_PFAD);
  const appName = $derived(APPS.find((eintrag) => eintrag.schluessel === app)?.name ?? '');

  function schliesseWennDraussen(ereignis: MouseEvent) {
    if (offen && huelle && !huelle.contains(ereignis.target as Node)) offen = false;
  }

  // Nach Escape gehört die Marke dorthin zurück, wo sie herkam — sonst steht
  // sie im Nichts und die nächste Tabulatortaste fängt von vorn an.
  function schliesseMitTaste(ereignis: KeyboardEvent) {
    if (ereignis.key !== 'Escape' || !offen) return;
    offen = false;
    knopf?.focus();
  }
</script>

<svelte:window onclick={schliesseWennDraussen} onkeydown={schliesseMitTaste} />

<header class="kopf">
  <div class="ebene apps">
    <h1 class="marke">
      <span class="zeichen">{@html zeichen}</span>wortlaut
    </h1>
    <nav aria-label="Apps">
      {#each APPS as eintrag (eintrag.schluessel)}
        {#if eintrag.schluessel === app}
          <span class="reiter aktiv" aria-current="page">{eintrag.name}</span>
        {:else if eintrag.verfuegbar}
          <a class="reiter" href={eintrag.pfad} title={eintrag.aufgabe}>{eintrag.name}</a>
        {:else}
          <span class="reiter spaeter" title="{eintrag.aufgabe} — kommt später"
            >{eintrag.name}</span
          >
        {/if}
      {/each}
    </nav>
    {#if hinweis}
      <span class="hinweis">{hinweis}</span>
    {/if}

    <div class="menue" class:ohne-hinweis={!hinweis} bind:this={huelle}>
      <button
        bind:this={knopf}
        class="knopf-menue"
        aria-label="Menü"
        aria-expanded={offen}
        aria-haspopup="true"
        onclick={() => (offen = !offen)}
      >
        <!-- Strich und Maß stehen als Attribute, nicht nur im Stylesheet: Die
             drei Linien haben keine Fläche, ein reiner `fill` zeichnet also
             nichts. Bliebe das CSS einmal aus, wäre der Knopf unsichtbar
             statt unschön. -->
        <svg
          viewBox="0 0 24 24"
          width="24"
          height="24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <path d="M3 6h18M3 12h18M3 18h18" />
        </svg>
      </button>
      {#if offen}
        <nav class="klappe" aria-label="Menü">
          <a
            class="eintrag"
            class:aktiv={inEinstellungen}
            href="#{EINSTELLUNGEN_PFAD}"
            onclick={() => (offen = false)}>Einstellungen</a
          >
          {#if inEinstellungen}
            <a class="eintrag" href="#/" onclick={() => (offen = false)}>
              Zurück zu „{appName}“
            </a>
          {/if}
        </nav>
      {/if}
    </div>
  </div>

  {#if punkte.length}
    <nav class="ebene ansichten" aria-label="Ansichten">
      {#each punkte as punkt (punkt.pfad)}
        <a
          class="reiter"
          class:aktiv={punkt.pfad === route}
          aria-current={punkt.pfad === route ? 'page' : undefined}
          href="#{punkt.pfad}">{punkt.text}</a
        >
      {/each}
    </nav>
  {/if}
</header>

<style>
  .kopf {
    border-bottom: 1px solid var(--rand);
    background: #fff;
  }

  .ebene {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-wrap: wrap;
    max-width: 44rem;
    margin: 0 auto;
    padding: 0 1.25rem;
  }

  .apps {
    padding-top: 0.6rem;
  }

  .marke {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 1.1rem;
    margin: 0;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--gedaempft);
    margin-right: 0.6rem;
  }

  /* Das Zeichen trägt die Marke, darum kräftig; der Schriftzug bleibt leise.
     Etwas größer als die Versalhöhe, sonst wirkt es angeklebt. */
  .zeichen {
    color: var(--akzent);
  }

  .zeichen :global(svg) {
    display: block;
    width: 1.5em;
    height: 1.5em;
  }

  /* Randnotiz, kein Bedienelement: schiebt sich nach rechts und bleibt leise. */
  .hinweis {
    margin-left: auto;
    font-size: 0.8rem;
    color: var(--gedaempft);
    text-align: right;
  }

  /* Ganz rechts, in jeder App an derselben Stelle. Ohne Hinweis daneben muss
     der Knopf sich den Platz selbst nehmen. */
  .menue {
    position: relative;
    margin-left: 0.5rem;
  }

  .menue.ohne-hinweis {
    margin-left: auto;
  }

  .knopf-menue {
    display: block;
    padding: 0.35rem;
    border: 0;
    border-radius: 0.4rem;
    background: none;
    color: var(--akzent);
    cursor: pointer;
    line-height: 0;
  }

  .knopf-menue:hover,
  .knopf-menue[aria-expanded='true'] {
    background: var(--akzent-hell);
  }

  .knopf-menue svg {
    width: 1.4rem;
    height: 1.4rem;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    fill: none;
  }

  .klappe {
    position: absolute;
    top: calc(100% + 0.3rem);
    right: 0;
    z-index: 10;
    min-width: 11rem;
    padding: 0.25rem;
    border: 1px solid var(--rand);
    border-radius: 0.5rem;
    background: #fff;
    box-shadow: 0 4px 14px rgb(0 0 0 / 12%);
  }

  .eintrag {
    display: block;
    padding: 0.5rem 0.7rem;
    border-radius: 0.35rem;
    text-decoration: none;
    color: var(--akzent);
    white-space: nowrap;
  }

  .eintrag:hover {
    background: var(--akzent-hell);
  }

  .eintrag.aktiv {
    background: var(--akzent-hell);
    font-weight: 600;
  }

  .ansichten {
    padding-bottom: 0.4rem;
    gap: 0.25rem;
  }

  .reiter {
    display: inline-block;
    padding: 0.35rem 0.8rem;
    border-radius: 0.4rem 0.4rem 0 0;
    text-decoration: none;
    color: var(--akzent);
    white-space: nowrap;
  }

  .apps .reiter {
    font-size: 1.05rem;
  }

  .apps .reiter.aktiv {
    background: var(--akzent);
    color: #fff;
    font-weight: 600;
  }

  /* Noch nicht gebaut: sichtbar, damit der Aufbau erkennbar ist, aber tot. */
  .reiter.spaeter {
    color: var(--gedaempft);
    opacity: 0.6;
    cursor: default;
  }

  .ansichten .reiter {
    font-size: 0.95rem;
    border-radius: 0.4rem;
  }

  .ansichten .reiter.aktiv {
    background: var(--akzent-hell);
    color: var(--akzent);
    font-weight: 600;
  }

  a.reiter:hover {
    background: var(--akzent-hell);
  }
</style>
