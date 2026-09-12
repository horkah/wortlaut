<script lang="ts">
  /**
   * Ein einzelner Lauf: die Kurven, und am Ende die Zahl, die zählt.
   *
   * **Warum zwei Kurven.** Der Trainingsverlust sagt, ob überhaupt etwas
   * passiert; er fällt auch dann weiter, wenn das Modell nur noch die
   * Trainingssätze auswendig lernt. Erst die Validierung daneben zeigt, wann
   * das anfängt - sie ist die Reihe, die wieder steigt, während die andere
   * sinkt. Eine Kurve allein beantwortete die falsche Frage.
   *
   * **Warum der Vergleich unten und nicht oben.** Weil er erst am Ende
   * entsteht: Die Testaufnahmen hört das fertige Modell, nicht das
   * halbfertige. Solange oben eine Kurve wächst, gibt es unten nichts zu
   * sehen - und das ist besser, als eine Zahl zu zeigen, die sich noch ändert.
   */
  import { onMount } from 'svelte';
  import { einstellungen } from '$ui/einstellungen.svelte';
  import type { Diagramm } from '../lib/diagramm';
  import { lauf as ladeLauf, type Laufeinzeln } from '../lib/api';
  import { gehZu } from '../lib/zustand.svelte';

  let { jobId }: { jobId: string } = $props();

  const TAKT_LAEUFT = 3000;
  const TAKT_RUHT = 30000;

  let daten = $state<Laufeinzeln | null>(null);
  let fehler = $state('');
  let protokollOffen = $state(false);

  let huelle = $state<HTMLDivElement | null>(null);
  // Ohne `$state`: ECharts führt seinen eigenen Zustand, und ein Proxy darum
  // herum brächte nur Ärger.
  let diagramm: Diagramm | null = null;
  // Ob der Aufbau schon läuft. Er ist asynchron (die Bibliothek wird erst
  // dann geladen), also genügt `diagramm === null` als Wächter nicht: Zwei
  // Durchläufe des Effekts kämen beide daran vorbei und bauten zwei Diagramme
  // in dasselbe Element.
  let baut = false;

  const lauf = $derived(daten?.lauf ?? null);
  const laeuft = $derived(lauf?.status === 'laeuft');
  const kurve = $derived(daten?.kurve_training ?? []);
  const pruefung = $derived(daten?.kurve_validierung ?? []);
  const hatKurve = $derived(kurve.length > 0);
  const vergleich = $derived(daten?.vergleich ?? {});
  const fassungen = $derived(Object.keys(vergleich));

  // Die gewählten Farben als **ein** Wert; `einstellungen.farben` selbst zu
  // lesen meldet nur an, dass es das Feld gibt, nicht seinen Inhalt - eine
  // geänderte Akzentfarbe käme im Diagramm sonst erst nach einem Seitenwechsel an.
  const farbstand = $derived(Object.values(einstellungen.farben).join('|'));

  const MASSNAMEN: Record<string, string> = {
    genauigkeit: 'Genauigkeit',
    wer: 'Wortfehlerrate',
    cer: 'Zeichenfehlerrate',
    mer: 'Trefferfehlerrate',
    wil: 'Wortinformationsverlust',
  };

  const FASSUNGSNAMEN: Record<string, string> = {
    original: 'Original',
    pegel: 'Ausgesteuert',
    lauter: '15 % lauter',
    rauschen: 'Mit Rauschen',
  };

  function farbe(name: string, ersatz: string): string {
    const wert = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return wert || ersatz;
  }

  function zeige(mass: string, wert: number | null): string {
    if (wert === null) return '–';
    return mass === 'genauigkeit' ? `${wert.toFixed(1)} %` : wert.toFixed(3);
  }

  /** Um wie viel besser - in Prozentpunkten bei der Genauigkeit, sonst relativ. */
  function unterschied(mass: string, vorher: number | null, nachher: number | null): string {
    if (vorher === null || nachher === null) return '';
    if (mass === 'genauigkeit') {
      const punkte = nachher - vorher;
      return `${punkte >= 0 ? '+' : ''}${punkte.toFixed(1)} Pp.`;
    }
    if (!vorher) return '';
    const anteil = ((nachher - vorher) / vorher) * 100;
    return `${anteil >= 0 ? '+' : ''}${anteil.toFixed(0)} %`;
  }

  function option() {
    const schrift = farbe('--text', '#1c1b19');
    const leise = farbe('--gedaempft', '#6b6b6b');
    const rand = farbe('--rand', '#d8d4cd');
    const akzent = farbe('--akzent', '#1b4d3e');

    return {
      // Die Schriftart der Oberfläche gilt auch hier: Wer sie unter
      // „Darstellung" umstellt, soll nicht ein Diagramm in einer anderen
      // Schrift bekommen.
      textStyle: { fontFamily: einstellungen.schriftart, color: schrift },
      animationDuration: 300,
      grid: { left: 8, right: 14, top: 16, bottom: 64, containLabel: true },
      tooltip: {
        trigger: 'axis',
        confine: true,
        valueFormatter: (wert: number | null) =>
          wert === null || wert === undefined ? '–' : wert.toFixed(4),
      },
      legend: { bottom: 28, itemGap: 18, textStyle: { color: leise } },
      dataZoom: [
        { type: 'inside', throttle: 60 },
        { type: 'slider', height: 14, bottom: 4, borderColor: rand, fillerColor: `${akzent}22` },
      ],
      xAxis: {
        type: 'value',
        name: 'Schritt',
        nameLocation: 'end' as const,
        nameGap: 6,
        nameTextStyle: { color: leise },
        axisLine: { lineStyle: { color: rand } },
        axisLabel: { color: leise },
      },
      yAxis: {
        type: 'value',
        name: 'Verlust',
        nameTextStyle: { color: leise, align: 'left' as const },
        axisLabel: { color: leise },
        splitLine: { lineStyle: { color: rand, opacity: 0.6 } },
      },
      series: [
        {
          id: 'training',
          name: 'Training',
          type: 'line' as const,
          // Ohne Punkte: Bei tausend Schritten wäre die Linie ein Band aus
          // Symbolen, und der Verlauf - das Einzige, was hier zählt - ginge
          // darin unter.
          showSymbol: false,
          smooth: true,
          data: kurve.map((punkt) => [punkt.schritt, punkt.verlust]),
          lineStyle: { color: akzent, width: 2 },
          itemStyle: { color: akzent },
        },
        {
          id: 'validierung',
          name: 'Validierung',
          type: 'line' as const,
          // Hier schon: Es ist ein Punkt je Durchgang, und genau die einzelnen
          // Punkte liest man ab.
          symbolSize: 7,
          smooth: false,
          data: pruefung.map((punkt) => [punkt.schritt, punkt.verlust]),
          lineStyle: { color: '#d55e00', width: 2, type: 'dashed' as const },
          itemStyle: { color: '#d55e00' },
        },
      ],
    };
  }

  function zeichne() {
    if (!diagramm) return;
    // `replaceMerge` statt `notMerge`: Es ersetzt die Reihen vollständig,
    // lässt aber den Zoomausschnitt, wo er ist. Ohne das spränge die Ansicht
    // bei jedem Takt zurück, während man gerade etwas anschaut.
    diagramm.setOption(option(), { replaceMerge: ['series'] });
  }

  async function baueDiagramm(ziel: HTMLDivElement) {
    baut = true;
    try {
      const { init } = await import('../lib/diagramm');
      diagramm = init(ziel, undefined, { renderer: 'canvas' });
      new ResizeObserver(() => diagramm?.resize()).observe(ziel);
      zeichne();
    } catch (ursache) {
      // Ein Nachladen, das scheitert, hinterließe sonst ein weißes Rechteck
      // ohne jede Auskunft - genau das Bild, das auch ein Fehler im Aufbau
      // erzeugt. Lieber sagen, was los ist.
      baut = false;
      fehler =
        'Das Diagramm konnte nicht geladen werden: ' +
        (ursache instanceof Error ? ursache.message : String(ursache));
    }
  }

  async function hole() {
    try {
      daten = await ladeLauf(jobId);
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  onMount(() => {
    let uhr: ReturnType<typeof setTimeout>;
    let beendet = false;

    async function takt() {
      await hole();
      if (beendet) return;
      uhr = setTimeout(takt, laeuft ? TAKT_LAEUFT : TAKT_RUHT);
    }

    takt();

    return () => {
      beendet = true;
      clearTimeout(uhr);
      diagramm?.dispose();
      diagramm = null;
      baut = false;
    };
  });

  /**
   * Das Diagramm aufbauen, sobald seine Leinwand im Baum steht.
   *
   * Und ausdrücklich nicht in `onMount`: Die Leinwand steht erst da, wenn der
   * Lauf geladen ist - vorher zeigt die Seite „Wird geladen …". `onMount`
   * läuft aber, bevor die erste Antwort da ist; `huelle` wäre dann `null`, der
   * Aufbau bräche ab, und niemand riefe ihn ein zweites Mal. Übrig bliebe das
   * leere weiße Feld, in dem das Diagramm stehen sollte.
   */
  $effect(() => {
    if (huelle && !diagramm && !baut) baueDiagramm(huelle);
  });

  $effect(() => {
    void daten;
    void farbstand;
    void einstellungen.schriftart;
    if (diagramm) zeichne();
  });
</script>

<p class="zurueck">
  <a href="#/training" onclick={() => gehZu('/training')}>← Alle Läufe</a>
</p>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{#if !lauf}
  <p class="gedaempft">Wird geladen …</p>
{:else}
  <h2>{lauf.methode === 'lora' ? 'Feintuning (LoRA)' : 'Volles Training'}</h2>
  <p class="gedaempft">
    {lauf.daten === 'original' ? 'Nur Originale' : 'Mit Abwandlungen'} ·
    {lauf.basismodell} · {lauf.aufnahmen} Aufnahmen
    {#if lauf.version}
      · Stand <strong>{lauf.version}</strong>
    {/if}
  </p>

  {#if lauf.status === 'gescheitert' && lauf.fehler}
    <p class="fehler">{lauf.fehler}</p>
  {/if}

  <!-- Das Diagramm bleibt im Baum, auch solange nichts darin steht: ECharts
       bindet sich beim Aufbau an dieses Element, und ein `{#if}` darum nähme
       es ihm unter den Füßen weg. -->
  <div class="bild" class:leer={!hatKurve}>
    <div class="leinwand" bind:this={huelle}></div>
    {#if !hatKurve}
      <p class="gedaempft ueberlagert">
        {lauf.status === 'wartet'
          ? 'Wartet auf den Trainer - sobald er anfängt, wächst hier eine Kurve.'
          : 'Noch keine Schritte gerechnet.'}
      </p>
    {/if}
  </div>

  {#if hatKurve}
    <p class="gedaempft">
      Die durchgezogene Linie ist der Trainingsverlust, die gestrichelte die Validierung. Fallen
      beide, lernt das Modell. Fällt die eine und steigt die andere, lernt es die Trainingssätze
      auswendig - dann waren es zu viele Durchgänge.
      {#if pruefung.length}
        Geprüft wird einmal je Durchgang; {pruefung.length}
        {pruefung.length === 1 ? 'Prüfung' : 'Prüfungen'} bisher.
      {/if}
    </p>
  {/if}

  {#if fassungen.length}
    <h3>Gegen die Grundlinie</h3>
    <p class="gedaempft">
      Dieselben Testaufnahmen, die das Modell nie gesehen hat - einmal durch das unveränderte
      {lauf.basismodell} (gemessen in der Auswertung von „hören") und einmal durch diesen Stand.
    </p>

    {#each fassungen as fassung (fassung)}
      <h4>{FASSUNGSNAMEN[fassung] ?? fassung}</h4>
      <table class="vergleich">
        <thead>
          <tr>
            <th scope="col">Maß</th>
            <th scope="col">Grundlinie</th>
            <th scope="col">Dieser Stand</th>
            <th scope="col">Unterschied</th>
          </tr>
        </thead>
        <tbody>
          {#each vergleich[fassung] as eintrag (eintrag.mass)}
            <tr>
              <th scope="row">{MASSNAMEN[eintrag.mass] ?? eintrag.mass}</th>
              <td>{zeige(eintrag.mass, eintrag.grundlinie)}</td>
              <td class="stark">{zeige(eintrag.mass, eintrag.trainiert)}</td>
              <td class:besser={eintrag.besser === true} class:schlechter={eintrag.besser === false}>
                {unterschied(eintrag.mass, eintrag.grundlinie, eintrag.trainiert)}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      <p class="gedaempft klein">
        Über {vergleich[fassung][0]?.anzahl ?? 0} Testaufnahmen - nur solche, die beide Seiten
        gemessen haben.
      </p>
    {/each}

    <p class="gedaempft">
      Liegen die vier Fassungen dicht beieinander, hat das Modell den Sprecher verstanden. Gewinnt
      es beim Original und verliert beim Rauschen, hat es die Aufnahmesituation gelernt.
    </p>
  {:else if lauf.status === 'fertig'}
    <p class="hinweise">
      Für diesen Lauf gibt es keine Grundlinie: In „hören" ist die Auswertung für
      {lauf.basismodell} auf diesen Aufnahmen noch nicht gerechnet. Ohne sie steht die Zahl dieses
      Standes allein da - und eine Verbesserung gegen nichts ist keine.
    </p>
  {/if}

  {#if daten?.protokoll}
    <p class="reihe">
      <button class="knopf" onclick={() => (protokollOffen = !protokollOffen)}>
        {protokollOffen ? 'Protokoll verbergen' : 'Protokoll anzeigen'}
      </button>
    </p>
    {#if protokollOffen}
      <!-- Nur das Ende: Wer ein Protokoll liest, sucht den letzten Satz vor
           dem Abbruch, nicht den ersten des Ladevorgangs. -->
      <pre class="protokoll">{daten.protokoll}</pre>
    {/if}
  {/if}
{/if}

<style>
  .zurueck {
    margin: 0 0 0.4rem;
    font-size: 0.9rem;
  }

  /* Feste Höhe: Ein Diagramm, das mit seinen Daten wächst, schöbe beim
     Nachladen alles darunter nach unten. */
  .bild {
    position: relative;
    height: 20rem;
    border: 1px solid var(--rand);
    border-radius: 0.5rem;
    background: #fff;
    padding: 0.5rem;
    box-sizing: border-box;
  }

  .leinwand {
    width: 100%;
    height: 100%;
  }

  .ueberlagert {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    text-align: center;
    padding: 1rem;
    pointer-events: none;
  }

  h4 {
    margin: 1rem 0 0.2rem;
    font-size: 0.95rem;
  }

  .vergleich {
    border-collapse: collapse;
    width: auto;
    min-width: min(100%, 26rem);
    margin: 0.3rem 0 0.2rem;
  }

  .vergleich th,
  .vergleich td {
    padding: 0.3rem 0.9rem 0.3rem 0;
    text-align: right;
    border-bottom: 1px solid var(--rand);
    font-variant-numeric: tabular-nums;
  }

  .vergleich thead th {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--gedaempft);
  }

  .vergleich tbody th {
    text-align: left;
    font-weight: 400;
  }

  .vergleich .stark {
    font-weight: 600;
  }

  /* Farbe allein trägt die Auskunft nicht: Das Vorzeichen steht im Text. */
  .besser {
    color: var(--akzent);
    font-weight: 600;
  }

  .schlechter {
    color: var(--fehler);
  }

  .klein {
    font-size: 0.85rem;
    margin: 0.1rem 0 0.6rem;
  }

  .protokoll {
    max-height: 22rem;
    overflow: auto;
    padding: 0.7rem;
    border: 1px solid var(--rand);
    border-radius: 0.4rem;
    background: var(--flaeche, #fff);
    font-size: 0.8rem;
    line-height: 1.45;
    white-space: pre-wrap;
    word-break: break-word;
  }
</style>
