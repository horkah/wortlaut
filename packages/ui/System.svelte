<script lang="ts">
  /**
   * Worauf wortlaut läuft und wie viel es gerade zu tun hat - der Menüpunkt
   * „System".
   *
   * Oben die Karte, weil sie die Frage ist, mit der man hierher kommt: Läuft
   * das Training noch, ist der Speicher voll, wird sie zu heiß? Darunter
   * Prozessor, Arbeitsspeicher und Platten. Die Werte kommen vom Server
   * (`GET /api/system`, siehe `wortlaut/systemlage.py`) und zeigen die
   * Maschine, nicht den Browser.
   *
   * **Einmal je Sekunde, aber nicht endlos.** Jede Abfrage ruft auf dem Server
   * `nvidia-smi` auf. Das kostet wenig, aber es kostet - und eine offen
   * vergessene Ansicht soll nicht die Nacht hindurch fragen. Nach fünf
   * Minuten hält die Aktualisierung an; wer die Ansicht verlässt und
   * wiederkommt, startet sie neu, und ein Knopf tut dasselbe. Solange der
   * Reiter im Hintergrund liegt, wird ebenfalls nicht gefragt.
   */
  import { onDestroy } from 'svelte';
  import { ApiFehler, api } from './api';

  interface Karte {
    index: number;
    name: string;
    treiber: string | null;
    compute_capability: string | null;
    speicher_mib: number | null;
    speicher_belegt_mib: number | null;
    auslastung: number | null;
    speicher_auslastung: number | null;
    temperatur: number | null;
    leistung_w: number | null;
    leistung_grenze_w: number | null;
    luefter: number | null;
    takt_mhz: number | null;
    takt_max_mhz: number | null;
    pcie: string | null;
  }

  interface Systemlage {
    kernel: string;
    betriebszeit_s: number | null;
    prozessor: {
      modell: string | null;
      kerne: number | null;
      kerne_verfuegbar: number | null;
      auslastung: number | null;
      je_kern: number[];
      lastmittel: number[];
    };
    speicher: {
      gesamt: number | null;
      belegt: number | null;
      swap_gesamt: number | null;
      swap_belegt: number | null;
      grenze: number | null;
    };
    karten: Karte[];
    ablagen: { name: string; pfad: string; gesamt: number; belegt: number }[];
  }

  const TAKT_MS = 1000;
  const DAUER_MS = 5 * 60 * 1000;
  // So viele Sekunden zeigt der Verlauf - eine Minute ist lang genug, um einen
  // Schritt des Trainings von einer Pause zu unterscheiden.
  const VERLAUF = 60;

  const hoeren = api('/api');

  let lage = $state<Systemlage | null>(null);
  let fehler = $state('');
  let beginn = $state(0);
  let jetzt = $state(Date.now());
  let angehalten = $state(false);
  // Verläufe je Größe: `gpu0`, `vram0`, …, `cpu`.
  let verlaeufe = $state<Record<string, number[]>>({});

  let wecker: ReturnType<typeof setTimeout> | undefined;
  let beendet = false;

  function merke(schluessel: string, wert: number | null) {
    if (wert === null) return;
    const bisher = verlaeufe[schluessel] ?? [];
    verlaeufe[schluessel] = [...bisher, wert].slice(-VERLAUF);
  }

  async function frage() {
    wecker = undefined;
    if (beendet) return;
    jetzt = Date.now();
    if (jetzt - beginn >= DAUER_MS) {
      angehalten = true;
      return;
    }
    // Im Hintergrund nicht fragen, aber weiter warten: Kommt der Reiter nach
    // vorn, geht es mit dem nächsten Takt weiter.
    if (!document.hidden) {
      try {
        const neu = await hoeren.anfrage<Systemlage>('/system');
        if (beendet) return;
        lage = neu;
        fehler = '';
        for (const karte of neu.karten) {
          merke(`gpu${karte.index}`, karte.auslastung);
          merke(`vram${karte.index}`, anteil(karte.speicher_belegt_mib, karte.speicher_mib));
        }
        merke('cpu', neu.prozessor.auslastung);
        merke('ram', anteil(neu.speicher.belegt, neu.speicher.gesamt));
      } catch (grund) {
        fehler =
          grund instanceof ApiFehler && grund.status === 401
            ? 'Diese Auskunft gibt es nur mit gültigem Zugang - siehe „Zugangsdaten“.'
            : grund instanceof Error
              ? grund.message
              : String(grund);
        // Ohne Zugang wird es in der nächsten Sekunde nicht besser.
        if (grund instanceof ApiFehler && grund.status === 401) return;
      }
    }
    if (!beendet) wecker = setTimeout(frage, TAKT_MS);
  }

  function starte() {
    clearTimeout(wecker);
    beginn = Date.now();
    angehalten = false;
    frage();
  }

  starte();

  onDestroy(() => {
    beendet = true;
    clearTimeout(wecker);
  });

  // ── Darstellung der Werte ────────────────────────────────────────────────

  const zahl = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 });
  const ganz = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 });

  function anteil(teil: number | null, ganzes: number | null): number | null {
    return teil === null || !ganzes ? null : (100 * teil) / ganzes;
  }

  function bytes(wert: number | null): string {
    if (wert === null) return '–';
    const gib = wert / 1024 ** 3;
    return gib >= 1000 ? `${zahl.format(gib / 1024)} TiB` : `${zahl.format(gib)} GiB`;
  }

  function mib(wert: number | null): string {
    return wert === null ? '–' : `${zahl.format(wert / 1024)} GiB`;
  }

  function prozent(wert: number | null): string {
    return wert === null ? '–' : `${ganz.format(wert)} %`;
  }

  function dauer(sekunden: number | null): string {
    if (sekunden === null) return '–';
    const tage = Math.floor(sekunden / 86400);
    const stunden = Math.floor((sekunden % 86400) / 3600);
    const minuten = Math.floor((sekunden % 3600) / 60);
    return tage > 0 ? `${tage} d ${stunden} h` : `${stunden} h ${minuten} min`;
  }

  // Ab hier wird es eng - der Balken sagt es in der Farbe der Warnung.
  function stufe(wert: number | null, grenze = 90): string {
    return wert !== null && wert >= grenze ? 'hoch' : '';
  }

  /** Der Verlauf als Linie in einem Feld von VERLAUF × 100. */
  function linie(werte: number[] | undefined): string {
    if (!werte?.length) return '';
    const versatz = VERLAUF - werte.length;
    return werte
      .map((wert, i) => `${versatz + i},${100 - Math.max(0, Math.min(100, wert))}`)
      .join(' ');
  }

  function flaeche(werte: number[] | undefined): string {
    if (!werte?.length) return '';
    const versatz = VERLAUF - werte.length;
    return `${versatz},100 ${linie(werte)} ${VERLAUF - 1},100`;
  }

  const restzeit = $derived(Math.max(0, DAUER_MS - (jetzt - beginn)));
  const restText = $derived(
    `${Math.floor(restzeit / 60000)}:${String(Math.floor((restzeit % 60000) / 1000)).padStart(2, '0')}`,
  );
</script>

{#snippet verlauf(schluessel: string, titel: string)}
  <svg
    class="verlauf"
    viewBox="0 0 {VERLAUF - 1} 100"
    preserveAspectRatio="none"
    role="img"
    aria-label="{titel}, letzte Minute"
  >
    <line x1="0" y1="50" x2={VERLAUF - 1} y2="50" class="mitte" />
    <polygon points={flaeche(verlaeufe[schluessel])} class="flaeche" />
    <polyline points={linie(verlaeufe[schluessel])} class="strich" />
  </svg>
{/snippet}

{#snippet balken(wert: number | null, grenze?: number)}
  <div class="balken" class:hoch={stufe(wert, grenze) === 'hoch'}>
    <div style:width="{Math.max(0, Math.min(100, wert ?? 0))}%"></div>
  </div>
{/snippet}

<div class="kopf">
  <h2>System</h2>
  <p class="status" aria-live="polite">
    {#if angehalten}
      <span class="punkt aus"></span>
      Angehalten nach fünf Minuten
      <button class="knopf klein" onclick={starte}>Weiter beobachten</button>
    {:else if lage}
      <span class="punkt an"></span>
      Live · hält in {restText} an
    {/if}
  </p>
</div>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{#if !lage && !fehler}
  <p class="gedaempft">Frage den Server …</p>
{:else if lage}
  {#each lage.karten as karte (karte.index)}
    <section class="karte">
      <header>
        <h3>{karte.name}</h3>
        <p class="gedaempft">
          GPU {karte.index}
          {#if karte.speicher_mib !== null}· {mib(karte.speicher_mib)} VRAM{/if}
          {#if karte.compute_capability}· Compute Capability {karte.compute_capability}{/if}
          {#if karte.pcie}· PCIe {karte.pcie}{/if}
          {#if karte.treiber}· Treiber {karte.treiber}{/if}
        </p>
      </header>

      <div class="messwerte">
        <div class="messwert">
          <span class="name">Auslastung</span>
          <span class="wert">{prozent(karte.auslastung)}</span>
          {@render verlauf(`gpu${karte.index}`, 'GPU-Auslastung')}
        </div>
        <div class="messwert">
          <span class="name">VRAM</span>
          <span class="wert">
            {mib(karte.speicher_belegt_mib)}
            <small>von {mib(karte.speicher_mib)}</small>
          </span>
          {@render verlauf(`vram${karte.index}`, 'Belegter VRAM')}
        </div>
      </div>

      <dl class="kacheln">
        <div>
          <dt>Temperatur</dt>
          <dd class:hoch={stufe(karte.temperatur, 83) === 'hoch'}>
            {karte.temperatur === null ? '–' : `${ganz.format(karte.temperatur)} °C`}
          </dd>
        </div>
        <div>
          <dt>Leistung</dt>
          <dd>
            {karte.leistung_w === null ? '–' : `${ganz.format(karte.leistung_w)} W`}
            {#if karte.leistung_grenze_w !== null}<small
                >/ {ganz.format(karte.leistung_grenze_w)} W</small
              >{/if}
          </dd>
        </div>
        <div>
          <dt>Takt</dt>
          <dd>
            {karte.takt_mhz === null ? '–' : `${ganz.format(karte.takt_mhz)} MHz`}
          </dd>
        </div>
        <div>
          <dt>Lüfter</dt>
          <dd>{prozent(karte.luefter)}</dd>
        </div>
      </dl>
    </section>
  {:else}
    <section class="karte">
      <h3>Keine Grafikkarte</h3>
      <p class="gedaempft">
        Dieser Server sieht keine nvidia-Karte - erkannt und diktiert wird auf dem Prozessor.
      </p>
    </section>
  {/each}

  <div class="zweispaltig">
    <section class="karte">
      <header>
        <h3>Prozessor</h3>
        <p class="gedaempft">
          {lage.prozessor.modell ?? 'unbekannt'}
          {#if lage.prozessor.kerne !== null}
            · {lage.prozessor.kerne} Kerne{#if lage.prozessor.kerne_verfuegbar !== null && lage.prozessor.kerne_verfuegbar !== lage.prozessor.kerne}, davon {lage
                .prozessor.kerne_verfuegbar} nutzbar{/if}
          {/if}
        </p>
      </header>
      <div class="messwert">
        <span class="name">Auslastung</span>
        <span class="wert">{prozent(lage.prozessor.auslastung)}</span>
        {@render verlauf('cpu', 'Prozessorauslastung')}
      </div>
      {#if lage.prozessor.je_kern.length}
        <div class="kerne" aria-label="Auslastung je Kern">
          {#each lage.prozessor.je_kern as last, i (i)}
            <div
              class="kern"
              class:hoch={stufe(last) === 'hoch'}
              title="Kern {i}: {prozent(last)}"
            >
              <div style:height="{Math.max(2, last)}%"></div>
            </div>
          {/each}
        </div>
      {/if}
      {#if lage.prozessor.lastmittel.length}
        <p class="gedaempft fuss">
          Load Average {lage.prozessor.lastmittel.map((wert) => zahl.format(wert)).join(' · ')}
        </p>
      {/if}
    </section>

    <section class="karte">
      <header>
        <h3>Arbeitsspeicher</h3>
        <p class="gedaempft">
          {bytes(lage.speicher.gesamt)} RAM
          {#if lage.speicher.grenze !== null}· Container-Grenze {bytes(lage.speicher.grenze)}{/if}
        </p>
      </header>
      <div class="messwert">
        <span class="name">Belegt</span>
        <span class="wert">
          {bytes(lage.speicher.belegt)}
          <small>von {bytes(lage.speicher.gesamt)}</small>
        </span>
        {@render verlauf('ram', 'Belegter Arbeitsspeicher')}
      </div>
      {#if lage.speicher.swap_gesamt}
        <div class="zeile">
          <span>Swap</span>
          <span>{bytes(lage.speicher.swap_belegt)} / {bytes(lage.speicher.swap_gesamt)}</span>
        </div>
        {@render balken(anteil(lage.speicher.swap_belegt, lage.speicher.swap_gesamt))}
      {/if}
    </section>
  </div>

  {#if lage.ablagen.length}
    <section class="karte">
      <h3>Speicherplatz</h3>
      {#each lage.ablagen as ablage (ablage.pfad)}
        {@const belegt = anteil(ablage.belegt, ablage.gesamt)}
        <div class="zeile" title={ablage.pfad}>
          <span>{ablage.name}</span>
          <span>{bytes(ablage.belegt)} / {bytes(ablage.gesamt)} · {prozent(belegt)}</span>
        </div>
        {@render balken(belegt)}
      {/each}
    </section>
  {/if}

  <p class="gedaempft fuss">
    {lage.kernel} · läuft seit {dauer(lage.betriebszeit_s)}
  </p>
{/if}

<style>
  .kopf {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.25rem 1rem;
    margin: 0 0 0.75rem;
  }

  .kopf h2 {
    margin: 0;
  }

  .status {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin: 0;
    font-size: 0.85rem;
    color: var(--gedaempft);
    font-variant-numeric: tabular-nums;
  }

  .punkt {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: var(--rand);
  }

  /* Ein ruhiges Pulsieren: Hier wird gerade gefragt. */
  .punkt.an {
    background: var(--akzent);
    animation: puls 2s ease-in-out infinite;
  }

  @keyframes puls {
    50% {
      opacity: 0.35;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .punkt.an {
      animation: none;
    }
  }

  .knopf.klein {
    padding: 0.2rem 0.6rem;
    font-size: 0.85rem;
    margin-left: 0.3rem;
  }

  .karte header {
    margin-bottom: 0.6rem;
  }

  h3 {
    font-size: 1rem;
    margin: 0 0 0.15rem;
  }

  header .gedaempft {
    margin: 0;
    font-size: 0.8rem;
  }

  .messwerte {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
    gap: 0.75rem;
  }

  /* Name und Zahl in einer Zeile, darunter der Verlauf der letzten Minute. */
  .messwert {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: baseline;
    gap: 0 0.5rem;
  }

  .messwert .name {
    font-size: 0.8rem;
    color: var(--gedaempft);
  }

  .messwert .wert {
    font-size: 1.35rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--akzent);
  }

  small {
    font-size: 0.75rem;
    font-weight: 400;
    color: var(--gedaempft);
  }

  .verlauf {
    grid-column: 1 / -1;
    width: 100%;
    height: 2.6rem;
    margin-top: 0.2rem;
    border-radius: 0.3rem;
    background: var(--hintergrund);
  }

  .verlauf .flaeche {
    fill: var(--akzent-hell);
  }

  .verlauf .strich {
    fill: none;
    stroke: var(--akzent);
    stroke-width: 1.5;
    stroke-linejoin: round;
    vector-effect: non-scaling-stroke;
  }

  .verlauf .mitte {
    stroke: var(--rand);
    stroke-width: 1;
    stroke-dasharray: 2 3;
    vector-effect: non-scaling-stroke;
  }

  .kacheln {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(6.5rem, 1fr));
    gap: 0.4rem;
    margin: 0.75rem 0;
  }

  .kacheln > div {
    padding: 0.4rem 0.6rem;
    border-radius: 0.4rem;
    background: var(--hintergrund);
  }

  dt {
    font-size: 0.75rem;
    color: var(--gedaempft);
  }

  dd {
    margin: 0;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  dd.hoch {
    color: var(--warnung);
  }

  .balken.hoch > div {
    background: var(--warnung);
  }

  /* Prozessor und Speicher nebeneinander, wenn Platz ist. */
  .zweispaltig {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr));
    gap: 0 0.75rem;
  }

  /* Ein Säulchen je Kern - wie viele es sind, sagt der Server. */
  .kerne {
    display: flex;
    align-items: flex-end;
    gap: 3px;
    height: 2rem;
    margin-top: 0.6rem;
  }

  .kern {
    flex: 1;
    height: 100%;
    display: flex;
    align-items: flex-end;
    border-radius: 0.2rem;
    background: var(--hintergrund);
    overflow: hidden;
  }

  .kern > div {
    width: 100%;
    background: var(--akzent);
    opacity: 0.8;
    transition: height 0.4s ease;
  }

  .kern.hoch > div {
    background: var(--warnung);
  }

  .zeile {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    margin: 0.6rem 0 0.25rem;
    font-size: 0.85rem;
    font-variant-numeric: tabular-nums;
  }

  .zeile span:last-child {
    color: var(--gedaempft);
  }

  .balken > div {
    transition: width 0.4s ease;
  }

  .fuss {
    margin: 0.6rem 0 0;
    font-size: 0.8rem;
  }
</style>
