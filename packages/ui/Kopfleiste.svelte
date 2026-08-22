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
  import {
    APPS,
    DARSTELLUNG_PFAD,
    EINSTELLUNGEN_PFAD,
    PROJEKT_URL,
    type AppSchluessel,
    type Menuepunkt,
  } from './apps';
  // Als Quelltext eingebunden und nicht als <img>, damit das Zeichen die
  // Schriftfarbe des Schriftzugs annimmt (die Datei zeichnet currentColor).
  import zeichen from '../../assets/wortlaut-logo.svg?raw';

  let {
    app,
    punkte = [],
    uebergreifend = [],
    sprecher,
    route = '/',
    hinweis = '',
  }: {
    /** Welche der drei Apps diese Seite ist. */
    app: AppSchluessel;
    /** Die Ansichten dieser App; leer lassen heißt: zweite Reihe ausblenden. */
    punkte?: Menuepunkt[];
    /**
     * Ansichten, die nicht zu dieser App gehören, sondern zur ganzen
     * Anwendung — sie stehen im Menü über den Einstellungen. „hören" reicht
     * hier den Sprecher herein; „schreiben" hat noch keine solche Ansicht.
     */
    uebergreifend?: Menuepunkt[];
    /**
     * Der Sprecher, für den diese Sitzung gilt — als Statuszeile hinter den
     * App-Reitern. `null` heißt „kein gültiger Zugang" und zeigt einen
     * Platzhalter; ausgelassen heißt „diese App führt keinen Sprecher" und
     * zeigt nichts.
     */
    sprecher?: string | null;
    /** Die offene Hash-Route, ohne `#`. */
    route?: string;
    /**
     * Eine Randnotiz im linken Block. „schreiben" zeigt darin
     * dauerhaft Basismodell und Datum seines Modellstands: Ein Modellwechsel
     * ist dort eine Konfigurationsänderung, und wer eine Ausgabe beurteilt,
     * muss sehen, welcher Stand sie erzeugt hat.
     */
    hinweis?: string;
  } = $props();

  // Warum Sprecher und Einstellungen hier hängen und nicht in der Reiterreihe:
  // siehe die Konstanten in `apps.ts`. Eingeklappt, weil sie selten gebraucht
  // werden — „schreiben" soll ein großer Knopf bleiben (Grundentscheidung 7).
  let offen = $state(false);
  let huelle = $state<HTMLElement | null>(null);
  let knopf = $state<HTMLButtonElement | null>(null);

  const inEinstellungen = $derived(route === EINSTELLUNGEN_PFAD);
  const inDarstellung = $derived(route === DARSTELLUNG_PFAD);
  // Auf einer übergreifenden Ansicht führt die Reiterreihe nicht zurück:
  // „schreiben" hat keine, „hören" blendet sie ohne gewählten Sprecher aus.
  // Ohne diesen Eintrag käme man nur über den Zurück-Knopf des Browsers heraus.
  const aussenstehend = $derived(
    inEinstellungen || inDarstellung || uebergreifend.some((punkt) => punkt.pfad === route),
  );
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
    <!-- Zwei Blöcke: links Marke und App-Reiter, rechts Sprecher und
         Menüknopf, dazwischen eine flexible Lücke. Jeder Block darf für sich
         umbrechen — nur so bleiben Sprecher und Menüknopf beieinander, dicht
         am rechten Rand, statt dass der Sprecher irgendwo in der Mitte
         hängen bleibt. Reicht die Breite nicht für eine Zeile, weicht der
         rechte Block als Ganzes in eine zweite aus. -->
    <div class="links">
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

    <div class="rechts">
      {#if sprecher !== undefined}
        <!-- Wer gerade spricht, steht immer da: Alles, was die App tut, hängt
             am Sprecher, und ein Griff in den falschen Korpus wäre teuer.
             Der Name kommt vom Server, der ihn aus dem vorgelegten Zugang
             ableitet — hier steht also, für wen dieser Browser eingestellt
             ist, und nicht, was er sich gemerkt hat. Er steht direkt neben
             dem Menüknopf: beides betrifft, wer hier gerade unterwegs ist. -->
        <span class="sprecher" class:leer={!sprecher} title="Eingestellter Sprecher">
          {sprecher ?? 'kein Zugang'}
        </span>
      {/if}

      <div class="menue" bind:this={huelle}>
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
            <!-- Erst wer, dann womit: Der Sprecher steht über den Einstellungen. -->
            {#each uebergreifend as punkt (punkt.pfad)}
              <a
                class="eintrag"
                class:aktiv={punkt.pfad === route}
                href="#{punkt.pfad}"
                onclick={() => (offen = false)}>{punkt.text}</a
              >
            {/each}
            <a
              class="eintrag"
              class:aktiv={inEinstellungen}
              href="#{EINSTELLUNGEN_PFAD}"
              onclick={() => (offen = false)}>Einstellungen</a
            >
            <!-- Unter den Einstellungen: wer nach Mikrofon und Stimme sucht,
                 hat die zuerst gesehen; wer nach Farbe und Schrift sucht,
                 findet sie hier gleich darunter. -->
            <a
              class="eintrag"
              class:aktiv={inDarstellung}
              href="#{DARSTELLUNG_PFAD}"
              onclick={() => (offen = false)}>Darstellung</a
            >
            <!-- Führt aus der App heraus: eigener Reiter, und das Pfeilzeichen
                 sagt es vorher. `noopener` verwehrt der geöffneten Seite den
                 Zugriff auf dieses Fenster. -->
            <a
              class="eintrag auswaerts"
              href={PROJEKT_URL}
              target="_blank"
              rel="noopener noreferrer"
              title="Quelltext und Beschreibung auf GitHub — öffnet einen neuen Reiter"
              onclick={() => (offen = false)}
            >
              Über wortlaut<span class="pfeil" aria-hidden="true">↗</span>
            </a>
            {#if aussenstehend}
              <a class="eintrag zurueck" href="#/" onclick={() => (offen = false)}>
                Zurück zu „{appName}“
              </a>
            {/if}
          </nav>
        {/if}
      </div>
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

  /* Zwei Blöcke, dazwischen eine flexible Lücke (siehe `.rechts`). Reicht die
     Breite nicht, weicht der rechte Block als Ganzes in eine zweite Zeile
     aus — beide Blöcke bleiben dabei in sich zusammenhängend. */
  .apps {
    padding-top: 0.6rem;
    flex-wrap: wrap;
    align-items: flex-start;
  }

  /* Marke, App-Reiter und Statuszeile in einem Block. Wird es eng, bricht er
     um, statt seine Teile gegeneinander zu drücken. */
  .links {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.4rem 0.5rem;
    /* Ohne `min-width: 0` weigert sich ein Flex-Element zu schrumpfen und
       drückt den Nachbarn hinaus. */
    min-width: 0;
    flex: 1 1 auto;
  }

  /* Sprecher und Menüknopf: Beide betreffen, wer hier unterwegs ist, darum
     stehen sie beieinander, dicht am rechten Rand. `margin-left: auto`
     erzeugt die flexible Lücke zum linken Block — bleibt Platz, wandert
     dieser Block ganz nach rechts, statt in der Mitte zu verharren. Kein
     eigenes Umbrechen: Rutscht der Knopf weg, ist die Klappe nicht mehr zu
     treffen. */
  .rechts {
    display: flex;
    align-items: center;
    flex-wrap: nowrap;
    gap: 0.5rem;
    flex: none;
    margin-left: auto;
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

  /* Randnotiz, kein Bedienelement: bleibt leise und darf schrumpfen. */
  .hinweis {
    min-width: 0;
    max-width: 100%;
    flex: 0 1 auto;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.8rem;
    color: var(--gedaempft);
  }

  /* Steht im rechten Block, neben dem Menüknopf. Kräftiger als der Hinweis:
     Das ist kein Fußnotentext, sondern die Antwort auf „für wen nehme ich
     hier eigentlich auf". */
  .sprecher {
    max-width: 12rem;
    min-width: 0;
    /* Gibt als Erstes nach, wenn es eng wird: Der Menüknopf ist ein Ziel,
       dieser Text nur eine Auskunft. */
    flex: 0 1 auto;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--akzent);
  }

  /* Kein gültiger Zugang: sichtbar, aber ohne Gewicht. */
  .sprecher.leer {
    font-weight: 400;
    font-style: italic;
    color: var(--gedaempft);
  }

  /* In jeder App an derselben Stelle, nie schrumpfend — ein Ziel für den
     Finger gibt keinen Platz her. */
  .menue {
    position: relative;
    flex: none;
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
    /* Auf einem schmalen Gerät darf sie nicht über den Rand hinauswachsen. */
    max-width: calc(100vw - 2rem);
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

  /* Verlässt die App — der Pfeil steht rechts und hält Abstand. */
  .eintrag.auswaerts {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .pfeil {
    font-size: 0.85em;
    color: var(--gedaempft);
  }

  /* Der Rückweg ist kein Ziel wie die anderen, sondern der Ausgang. */
  .eintrag.zurueck {
    margin-top: 0.25rem;
    border-top: 1px solid var(--rand);
    padding-top: 0.55rem;
    color: var(--gedaempft);
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
