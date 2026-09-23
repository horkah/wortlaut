<script lang="ts">
  /**
   * Der Lautstärkeverlauf einer Aufnahme, mit zwei Grenzen zum Anfassen.
   *
   * Gebraucht vom Zuschnitt in „hören": Die Kurve zeigt, wo gesprochen wurde,
   * die beiden Linien sagen, was davon bleiben soll, und beide lassen sich mit
   * Finger, Maus oder Tastatur verschieben.
   *
   * **Warum selbstgebaut und nicht wavesurfer.js.** Die Bibliothek nimmt eine
   * Audiodatei, dekodiert sie im Browser und zeichnet daraus eine Wellenform;
   * ihr Regions-Zusatz kann genau das, was hier gebraucht wird. Nur liegt die
   * Rechnung hier längst fertig da: Der Server misst den Pegel in 20-ms-
   * Fenstern ohnehin, für die Randstille jeder Aufnahme
   * (`wortlaut/audio.py`). Diese Zahlen kommen mit der Liste - ein paar
   * hundert je Aufnahme -, und daraus einen Pfad zu zeichnen sind dreißig
   * Zeilen. Die Datei dafür herunterzuladen und ein zweites Mal zu vermessen,
   * nur um eine Bibliothek benutzen zu können, wäre der Umweg.
   *
   * Dazu kommt der Ort: Diese Komponente liegt in `packages/ui`, und dort gibt
   * es kein eigenes `node_modules` - die geteilten Komponenten werden aus dem
   * der jeweiligen App gebaut und kommen bisher ohne eine einzige fremde
   * Bibliothek aus (siehe `apps/hoeren/frontend/src/lib/diagramm.ts`, wo
   * dieselbe Überlegung zum umgekehrten Ergebnis führte: ECharts kann, was
   * niemand nachbaut).
   *
   * **Warum SVG und nicht Leinwand.** Es sind ein paar hundert Punkte und zwei
   * Griffe, keine tausend Balken mit Zoom. Als SVG skaliert das Bild mit der
   * Spalte, ohne dass jemand die Auflösung nachführt, und die Griffe sind
   * echte Elemente - fokussierbar, mit `aria`-Werten, von der Tastatur aus
   * bedienbar. Das ist hier kein Zusatz: Die Ansicht richtet sich an jemanden,
   * der eine Zeile Text nur mit Mühe liest.
   *
   * **Die dritte Linie.** Wird `teilung` gebunden, steht zwischen den beiden
   * Grenzen eine weitere, gestrichelte: die Stelle, an der die Ansicht
   * „Schneiden" eine Aufnahme in zwei zerlegt. Ohne sie bleibt alles, wie es
   * war - der Zuschnitt kennt nur zwei.
   */

  let {
    verlauf,
    fensterS,
    schwelle = 0,
    dauerS,
    start = $bindable(0),
    ende = $bindable(0),
    teilung = $bindable(undefined),
    hoehe = 72,
    beschriftung = 'Ausschnitt',
  }: {
    /** Ein Pegelwert je Fenster, bezogen auf Vollausschlag (0 bis 1). */
    verlauf: number[];
    /** Wie lang ein Fenster dauert - Kurvenlänge mal dies ist die Dauer. */
    fensterS: number;
    /** Ab wo ein Fenster als Stimme zählt; 0 blendet die Linie aus. */
    schwelle?: number;
    /** Die volle Dauer der Aufnahme, also die Breite des Bildes. */
    dauerS: number;
    /** Anfang des Ausschnitts in Sekunden - wandert beim Ziehen mit. */
    start?: number;
    /** Ende des Ausschnitts in Sekunden - wandert beim Ziehen mit. */
    ende?: number;
    /** Wo geteilt wird, in Sekunden; ohne Wert keine dritte Linie. */
    teilung?: number;
    hoehe?: number;
    /** Wofür die beiden Griffe stehen, für Vorlesegeräte. */
    beschriftung?: string;
  } = $props();

  // Das Bild rechnet in einem festen Koordinatensystem und wird über
  // `preserveAspectRatio="none"` auf die Spalte gezogen. Damit hängt keine
  // einzige Zahl hier an der Breite in Pixeln - die kennt nur der Browser,
  // und nachzumessen wäre sie erst, wenn jemand zieht (siehe `zeitAn`).
  const BREITE = 1000;
  const MITTE = $derived(hoehe / 2);

  // Wie fein sich mit der Tastatur schieben lässt: ein Fenster je Druck,
  // zehn mit gedrückter Umschalttaste. Dasselbe Raster, in dem die Kurve
  // gemessen ist - feiner wäre eine Genauigkeit, die das Bild nicht zeigt.
  const SCHRITT = $derived(fensterS);

  let bild = $state<SVGSVGElement | null>(null);
  type Welche = 'start' | 'teilung' | 'ende';
  let zieht = $state<Welche | null>(null);

  const griffe = $derived(
    [
      { welche: 'start' as Welche, wert: start, name: 'Anfang' },
      ...(teilung === undefined
        ? []
        : [{ welche: 'teilung' as Welche, wert: teilung, name: 'Teilung' }]),
      { welche: 'ende' as Welche, wert: ende, name: 'Ende' },
    ],
  );

  const xVon = (sekunden: number) => (dauerS > 0 ? (sekunden / dauerS) * BREITE : 0);

  /**
   * Die Kurve als geschlossene Fläche, um die Mittellinie gespiegelt.
   *
   * Gespiegelt, weil so eine Wellenform aussieht und jeder sie als solche
   * liest - obwohl hier kein Wellenzug steht, sondern ein Effektivwert je
   * Fenster. Der Unterschied ist für diese Aufgabe keiner: Gesucht wird, wo
   * jemand zu sprechen anfängt, und das sieht man am Umriss.
   *
   * Die Wurzel dehnt die leisen Werte. Sprache füllt den Vollausschlag selten
   * aus; linear aufgetragen wäre eine ordentlich ausgesteuerte Aufnahme ein
   * flacher Strich mit drei Zacken, und die Einsatzstelle läge irgendwo darin.
   */
  const flaeche = $derived.by(() => {
    if (!verlauf.length) return '';
    const spitze = Math.max(...verlauf, 1e-6);
    const y = (wert: number) => Math.sqrt(Math.min(wert, spitze) / spitze) * (MITTE - 1);
    const x = (nummer: number) => (nummer / Math.max(verlauf.length - 1, 1)) * BREITE;

    const oben = verlauf.map((wert, nummer) => `${x(nummer).toFixed(2)},${(MITTE - y(wert)).toFixed(2)}`);
    const unten = verlauf
      .map((wert, nummer) => `${x(nummer).toFixed(2)},${(MITTE + y(wert)).toFixed(2)}`)
      .reverse();
    return `M${oben.join('L')}L${unten.join('L')}Z`;
  });

  /** Die Schwellenlinie, an der der Vorschlag hängt - auf derselben Stauchung. */
  const schwelleY = $derived.by(() => {
    const spitze = Math.max(...verlauf, 1e-6);
    return Math.sqrt(Math.min(schwelle, spitze) / spitze) * (MITTE - 1);
  });

  /** Wo auf der Zeitachse ein Zeiger steht - die einzige Stelle, die nachmisst. */
  function zeitAn(ereignis: PointerEvent): number {
    if (!bild) return 0;
    const kasten = bild.getBoundingClientRect();
    if (kasten.width <= 0) return 0;
    const anteil = (ereignis.clientX - kasten.left) / kasten.width;
    return Math.min(Math.max(anteil, 0), 1) * dauerS;
  }

  /**
   * Die Grenzen können sich nicht überholen - auch die Teilung nicht.
   *
   * Ein Ausschnitt mit dem Ende vor dem Anfang wäre keine Auswahl, sondern
   * eine Fehlermeldung, die erst der Server schreibt. Statt dessen bleibt ein
   * Fenster dazwischen stehen: Wer die eine Linie über die andere schiebt,
   * schiebt sie bis dicht davor und merkt an der Kurve, dass es nicht weiter
   * geht. Mit einer Teilung dazwischen stößt jede äußere Linie an sie und
   * nicht an die gegenüberliegende.
   */
  function setze(welche: Welche, sekunden: number) {
    const luft = fensterS;
    const links = teilung ?? ende;
    const rechts = teilung ?? start;
    if (welche === 'start') start = Math.min(Math.max(sekunden, 0), links - luft);
    else if (welche === 'ende') ende = Math.max(Math.min(sekunden, dauerS), rechts + luft);
    else teilung = Math.min(Math.max(sekunden, start + luft), ende - luft);
  }

  function greife(ereignis: PointerEvent, welche: Welche) {
    // Zeiger festhalten: Wer mit dem Finger über den Rand des Bildes fährt,
    // soll die Linie nicht verlieren. Ohne das endet jeder Zug, sobald der
    // Finger den Griff verlässt - und auf einem Telefon ist er dafür breiter
    // als der Griff.
    (ereignis.target as Element).setPointerCapture?.(ereignis.pointerId);
    zieht = welche;
    ereignis.preventDefault();
  }

  function ziehe(ereignis: PointerEvent) {
    if (!zieht) return;
    setze(zieht, zeitAn(ereignis));
    ereignis.preventDefault();
  }

  function lasse(ereignis: PointerEvent) {
    if (!zieht) return;
    (ereignis.target as Element).releasePointerCapture?.(ereignis.pointerId);
    zieht = null;
  }

  function tasten(ereignis: KeyboardEvent, welche: Welche) {
    const weite = ereignis.shiftKey ? SCHRITT * 10 : SCHRITT;
    const jetzt = welche === 'start' ? start : welche === 'ende' ? ende : (teilung ?? 0);
    if (ereignis.key === 'ArrowLeft') setze(welche, jetzt - weite);
    else if (ereignis.key === 'ArrowRight') setze(welche, jetzt + weite);
    // Pos1 und Ende schieben so weit, wie es geht - `setze` hält an der
    // Nachbarlinie an.
    else if (ereignis.key === 'Home') setze(welche, 0);
    else if (ereignis.key === 'End') setze(welche, dauerS);
    else return;
    ereignis.preventDefault();
  }

  const zahl = (sekunden: number) => `${sekunden.toFixed(2)} s`;
</script>

<svg
  bind:this={bild}
  class="verlauf"
  viewBox="0 0 {BREITE} {hoehe}"
  preserveAspectRatio="none"
  style="height: {hoehe}px"
  onpointermove={ziehe}
  onpointerup={lasse}
  onpointercancel={lasse}
  role="presentation"
>
  <!-- Was wegfällt, liegt unter einem Schleier. Nicht ausgeblendet: Man soll
       sehen, was man wegschneidet - erst dann ist die Linie ein Vorschlag und
       keine Wand. -->
  <rect x="0" y="0" width={xVon(start)} height={hoehe} class="verworfen" />
  <rect
    x={xVon(ende)}
    y="0"
    width={Math.max(BREITE - xVon(ende), 0)}
    height={hoehe}
    class="verworfen"
  />

  <path d={flaeche} class="kurve" />

  {#if schwelle > 0}
    <line x1="0" x2={BREITE} y1={MITTE - schwelleY} y2={MITTE - schwelleY} class="schwelle" />
    <line x1="0" x2={BREITE} y1={MITTE + schwelleY} y2={MITTE + schwelleY} class="schwelle" />
  {/if}

  {#each griffe as griff (griff.welche)}
    <g
      class="griff"
      class:aktiv={zieht === griff.welche}
      class:teilung={griff.welche === 'teilung'}
      role="slider"
      tabindex="0"
      aria-label="{beschriftung}: {griff.name}"
      aria-valuemin="0"
      aria-valuemax={dauerS}
      aria-valuenow={griff.wert}
      aria-valuetext={zahl(griff.wert)}
      onpointerdown={(e) => greife(e, griff.welche)}
      onkeydown={(e) => tasten(e, griff.welche)}
    >
      <!-- Der breite, unsichtbare Streifen ist die Fläche zum Anfassen. Eine
           zwei Pixel breite Linie trifft niemand mit dem Finger; getroffen
           werden muss aber die Linie, nicht der Bereich daneben. -->
      <rect x={xVon(griff.wert) - 14} y="0" width="28" height={hoehe} class="fangen" />
      <line x1={xVon(griff.wert)} x2={xVon(griff.wert)} y1="0" y2={hoehe} class="linie" />
      <!-- Zwei Kappen an den Enden: Sie sagen, dass hier etwas anzufassen ist,
           und sie geben dem Finger ein Ziel, das nicht die Kurve verdeckt. -->
      <rect x={xVon(griff.wert) - 5} y="0" width="10" height="7" class="kappe" />
      <rect x={xVon(griff.wert) - 5} y={hoehe - 7} width="10" height="7" class="kappe" />
    </g>
  {/each}
</svg>

<div class="marken gedaempft">
  <span>{zahl(start)}</span>
  {#if teilung === undefined}
    <span>{zahl(ende - start)} bleiben</span>
  {:else}
    <span>1: {zahl(teilung - start)}</span>
    <span>{zahl(teilung)}</span>
    <span>2: {zahl(ende - teilung)}</span>
  {/if}
  <span>{zahl(ende)}</span>
</div>

<style>
  .verlauf {
    display: block;
    width: 100%;
    background: var(--akzent-hell);
    border-radius: 0.4rem;
    /* Sonst wählt ein Zug auf dem Telefon Text aus oder scrollt die Seite,
       statt die Linie zu verschieben. */
    touch-action: none;
    user-select: none;
  }

  .kurve {
    fill: var(--akzent);
  }

  .verworfen {
    fill: var(--hintergrund);
    opacity: 0.72;
  }

  .schwelle {
    stroke: var(--gedaempft);
    stroke-width: 1;
    stroke-dasharray: 4 4;
    opacity: 0.5;
  }

  .fangen {
    fill: transparent;
  }

  .griff {
    cursor: ew-resize;
  }

  /* Orange, und zwar dasselbe, das in dieser Oberfläche „sieh hier hin"
     bedeutet (`--warnung`). Eine eigene Farbe für diese zwei Linien wäre eine
     vierte Bedeutung in einer Palette mit dreien. */
  .linie {
    stroke: var(--warnung);
    stroke-width: 2;
  }

  .kappe {
    fill: var(--warnung);
    rx: 2;
  }

  /* Die Teilung gestrichelt: Sie begrenzt nichts, was wegfällt, sondern
     trennt zwei Teile, die beide bleiben. */
  .griff.teilung .linie {
    stroke-dasharray: 6 4;
  }

  .griff.aktiv .linie,
  .griff:focus-visible .linie {
    stroke-width: 3;
  }

  .griff:focus-visible {
    outline: 2px solid var(--warnung);
    outline-offset: 2px;
  }

  .marken {
    display: flex;
    justify-content: space-between;
    font-variant-numeric: tabular-nums;
    margin-top: 0.2rem;
  }
</style>
