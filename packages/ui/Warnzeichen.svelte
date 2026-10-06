<script lang="ts">
  /**
   * Ein kleines „i" im Warnkreis, der Wortlaut der Hinweise dahinter.
   *
   * Für Listen, in denen viele Einträge Hinweise tragen können - die Aufnahmen
   * in „Meine Daten" und in der Einsicht. Dort stand der Text als eigener
   * Block unter jeder Zeile, und eine Aufnahme mit Hinweis war doppelt so hoch
   * wie eine ohne. Das Zeichen sitzt in der Textzeile und ist nicht höher als
   * sie: Eine Liste mit Hinweisen ist so lang wie eine ohne.
   *
   * Aufzuklappen auf jedem üblichen Weg: Zeiger darüber, Tastatur (Tab hin,
   * Esc weg) und Tippen - ein Telefon kennt kein Darüberfahren. Vorlesestimmen
   * lesen den Wortlaut über `aria-describedby`, auch ohne dass er offen ist.
   */
  let { hinweise }: { hinweise: string[] } = $props();

  const kennung = `warnzeichen-${Math.random().toString(36).slice(2, 10)}`;

  // Getrennt gehalten, damit ein Tippen offen bleibt, wenn danach der Zeiger
  // weiterzieht, und ein Darüberfahren sich nicht mit einem Klick beißt.
  let zeiger = $state(false);
  let fokus = $state(false);
  let getippt = $state(false);
  const offen = $derived(zeiger || fokus || getippt);

  /**
   * Die Blase bleibt im Fenster: Steht das Zeichen weit rechts, rückt sie
   * nach links, statt die Seite seitlich rollen zu lassen.
   */
  function imFenster(blase: HTMLElement) {
    const rand = 8;
    const ueber = blase.getBoundingClientRect().right - (window.innerWidth - rand);
    if (ueber > 0) blase.style.translate = `${-ueber}px 0`;
  }

  let huelle: HTMLElement;

  function schliesse() {
    zeiger = false;
    fokus = false;
    getippt = false;
  }

  // Ein zweites Tippen schließt, was das erste geöffnet hat - gleich, ob der
  // Browser dem Knopf dabei auch den Fokus gab (Android) oder nicht (iOS).
  function tippe() {
    if (getippt) schliesse();
    else getippt = true;
  }

  function taste(ereignis: KeyboardEvent) {
    if (ereignis.key === 'Escape') schliesse();
  }

  // Safari auf dem iPhone gibt einem angetippten Knopf keinen Fokus, also
  // kommt auch kein `blur`, wenn man woanders hintippt. Darum hier selbst.
  function anderswo(ereignis: PointerEvent) {
    if (getippt && !huelle.contains(ereignis.target as Node)) schliesse();
  }
</script>

<svelte:window onpointerdown={anderswo} />

<span class="warnzeichen" bind:this={huelle}>
  <button
    type="button"
    aria-label="Hinweis"
    aria-describedby={kennung}
    onmouseenter={() => (zeiger = true)}
    onmouseleave={() => (zeiger = false)}
    onfocus={() => (fokus = true)}
    onblur={() => {
      fokus = false;
      getippt = false;
    }}
    onclick={tippe}
    onkeydown={taste}
  >
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <circle cx="8" cy="8" r="8" fill="var(--warnung)" />
      <circle cx="8" cy="4.6" r="1.15" fill="var(--hintergrund)" />
      <rect x="6.95" y="6.9" width="2.1" height="5.6" rx="1.05" fill="var(--hintergrund)" />
    </svg>
  </button>
  <!-- Immer im Dokument, nur verborgen: `aria-describedby` braucht ein Ziel,
       das es gibt. -->
  <span id={kennung} role="tooltip" class="blase" hidden={!offen}>
    {#if offen}
      <span use:imFenster>
        {#each hinweise as hinweis}<span class="zeile">{hinweis}</span>{/each}
      </span>
    {:else}
      {hinweise.join(' ')}
    {/if}
  </span>
</span>

<style>
  /* Kein eigener Platz in der Zeile außer der Breite des Zeichens: Grundlinie
     und Zeilenhöhe bleiben die des Textes daneben. */
  .warnzeichen {
    position: relative;
    display: inline-block;
    vertical-align: -0.12em;
    line-height: 0;
    margin: 0 0.15rem;
  }

  button {
    display: inline-block;
    padding: 0;
    border: 0;
    background: none;
    line-height: 0;
    cursor: help;
    border-radius: 50%;
  }

  button:focus-visible {
    outline: 2px solid var(--akzent);
    outline-offset: 2px;
  }

  .blase {
    position: absolute;
    top: calc(100% + 0.4rem);
    left: -0.5rem;
    z-index: 10;
    width: max-content;
    max-width: min(20rem, calc(100vw - 1rem));
    line-height: 1.4;
    font-size: 0.85rem;
    color: var(--text);
    text-align: left;
    white-space: normal;
  }

  .blase > span {
    display: block;
    padding: 0.5rem 0.7rem;
    border: 1px solid var(--rand);
    border-left: 3px solid var(--warnung);
    border-radius: 0.4rem;
    background: var(--hintergrund);
    box-shadow: 0 4px 14px rgb(0 0 0 / 0.12);
  }

  .zeile {
    display: block;
  }

  .zeile + .zeile {
    margin-top: 0.3rem;
  }
</style>
