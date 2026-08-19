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
  import { APPS, type AppSchluessel, type Menuepunkt } from './apps';
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
</script>

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
