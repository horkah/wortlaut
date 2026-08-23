<script lang="ts">
  /**
   * Eine Seite aus vielen: „‹ 1 … 4 5 6 … 12 ›" - für lange Listen, die eine
   * Aufnahme oder Sitzung je Zeile zeigen und bei Hunderten Einträgen sonst
   * eine einzige, unlesbare Seite wären.
   *
   * Bewusst zustandslos: Diese Komponente zählt nur mit, sie lädt nichts
   * selbst nach. Wer sie einsetzt, hält `seite` selbst (meist als
   * `$state`), reicht die Gesamtzahl der Seiten herein und lädt in `aendere`
   * neu - genau wie bei jeder anderen Liste in dieser App auch.
   */
  let {
    seite,
    gesamtSeiten,
    aendere,
  }: {
    /** Die aktuell offene Seite, 1-gezählt. */
    seite: number;
    gesamtSeiten: number;
    aendere: (seite: number) => void;
  } = $props();

  const ELLIPSE = '…';

  /**
   * Welche Seitenzahlen stehen: immer die erste und letzte, dazu die
   * aktuelle mit einer Nachbarin auf jeder Seite; die Lücken dazwischen
   * werden zu einer Ellipse statt jede Zahl aufzuzählen.
   */
  const eintraege = $derived.by((): (number | typeof ELLIPSE)[] => {
    const angezeigt = new Set(
      [1, gesamtSeiten, seite - 1, seite, seite + 1].filter((n) => n >= 1 && n <= gesamtSeiten),
    );
    const zahlen = [...angezeigt].sort((a, b) => a - b);
    const ergebnis: (number | typeof ELLIPSE)[] = [];
    let vorige = 0;
    for (const zahl of zahlen) {
      if (vorige && zahl - vorige > 1) ergebnis.push(ELLIPSE);
      ergebnis.push(zahl);
      vorige = zahl;
    }
    return ergebnis;
  });
</script>

{#if gesamtSeiten > 1}
  <nav class="pager" aria-label="Seiten">
    <button class="knopf" disabled={seite <= 1} onclick={() => aendere(seite - 1)}>‹</button>
    {#each eintraege as eintrag, i (i)}
      {#if eintrag === ELLIPSE}
        <span class="ellipse">{ELLIPSE}</span>
      {:else}
        <button
          class="knopf"
          class:aktiv={eintrag === seite}
          aria-current={eintrag === seite ? 'page' : undefined}
          onclick={() => aendere(eintrag)}
        >
          {eintrag}
        </button>
      {/if}
    {/each}
    <button class="knopf" disabled={seite >= gesamtSeiten} onclick={() => aendere(seite + 1)}>
      ›
    </button>
  </nav>
{/if}

<style>
  .pager {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.3rem;
    margin: 0.75rem 0;
  }

  .pager .knopf {
    padding: 0.3rem 0.65rem;
    min-width: 2.2rem;
    text-align: center;
  }

  .pager .knopf.aktiv {
    background: var(--akzent);
    color: #fff;
  }

  .ellipse {
    padding: 0 0.2rem;
    color: var(--gedaempft);
  }
</style>
