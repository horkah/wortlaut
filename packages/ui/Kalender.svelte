<script lang="ts">
  /**
   * Ein Monatskalender, auf dem die Tage mit Aufnahmen markiert sind.
   *
   * Für „Meine Daten": Die Liste der Sitzungen sagte Zeile für Zeile, was ein
   * Blick auf einen Kalender auf einmal sagt - an welchen Tagen geübt wurde
   * und wie regelmäßig. Die Zahl je Tag steht im Tooltip, nicht in der
   * Fläche: Gesehen werden soll das Muster, gelesen nur, wer nachfragt.
   *
   * Wie viele Monate nebeneinander stehen, hängt an der eigenen Breite, nicht
   * an der des Fensters - schmal einer, breit zwei: der laufende und der
   * davor. Geblättert wird mit den Pfeilen oder mit einem Wisch, nie über den
   * laufenden Monat hinaus und nie vor den ersten mit Daten.
   */
  import { fly } from 'svelte/transition';

  let {
    tage,
    einheit = ['Aufnahme', 'Aufnahmen'],
  }: {
    /** Je Tag (`2026-10-03`, Zeitzone des Betrachters) die Anzahl. */
    tage: Map<string, number>;
    /** Wie die Anzahl heißt, Einzahl und Mehrzahl. */
    einheit?: [string, string];
  } = $props();

  const MONATE = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
  ];
  const WOCHENTAGE = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  /** Ab dieser eigenen Breite (px) stehen zwei Monate nebeneinander. */
  const ZWEI_AB = 520;

  const zwei = (zahl: number) => String(zahl).padStart(2, '0');

  // Ein Monat als eine Zahl - Jahr mal zwölf plus Monat -, damit Blättern
  // nur Addieren ist und kein Jahreswechsel eigens bedacht werden muss.
  const heute = new Date();
  const heuteSchluessel = `${heute.getFullYear()}-${zwei(heute.getMonth() + 1)}-${zwei(heute.getDate())}`;
  const laufend = heute.getFullYear() * 12 + heute.getMonth();

  let breite = $state(0);
  const anzahl = $derived(breite >= ZWEI_AB ? 2 : 1);

  /** Der rechte, also jüngste der sichtbaren Monate. */
  let ende = $state(laufend);
  const monate = $derived(Array.from({ length: anzahl }, (_, i) => ende - anzahl + 1 + i));

  const fruehester = $derived.by(() => {
    let erster = laufend;
    for (const schluessel of tage.keys()) {
      const [jahr, monat] = schluessel.split('-').map(Number);
      erster = Math.min(erster, jahr * 12 + monat - 1);
    }
    return erster;
  });
  const kannZurueck = $derived(monate[0] > fruehester);
  const kannVor = $derived(ende < laufend);

  // Woher der neue Monat einfährt: von rechts beim Vorblättern, von links
  // beim Zurück. Wer weniger Bewegung eingestellt hat, bekommt keine.
  let richtung = $state(1);
  const ruhig =
    typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  function blaettere(schritt: 1 | -1) {
    if (schritt < 0 ? !kannZurueck : !kannVor) return;
    richtung = schritt;
    ende += schritt;
    gezeigt = null;
  }

  type Zelle = { tag: number; schluessel: string; spalte: number } | null;

  /** Die Zellen eines Monats, Montag zuerst, mit Lücken davor. */
  function zellen(monatsnummer: number): Zelle[] {
    const jahr = Math.floor(monatsnummer / 12);
    const monat = monatsnummer % 12;
    const versatz = (new Date(jahr, monat, 1).getDay() + 6) % 7;
    const laenge = new Date(jahr, monat + 1, 0).getDate();
    const ergebnis: Zelle[] = Array.from({ length: versatz }, () => null);
    for (let tag = 1; tag <= laenge; tag++) {
      ergebnis.push({
        tag,
        schluessel: `${jahr}-${zwei(monat + 1)}-${zwei(tag)}`,
        spalte: (versatz + tag - 1) % 7,
      });
    }
    return ergebnis;
  }

  const titel = (monatsnummer: number) =>
    `${MONATE[monatsnummer % 12]} ${Math.floor(monatsnummer / 12)}`;

  function auskunft(zelle: NonNullable<Zelle>, zahl: number) {
    const monat = Number(zelle.schluessel.slice(5, 7)) - 1;
    const wort = zahl === 1 ? einheit[0] : einheit[1];
    return `${WOCHENTAGE[zelle.spalte]}, ${zelle.tag}. ${MONATE[monat]}: ${zahl} ${wort}`;
  }

  // Welcher Tag gerade seinen Tooltip zeigt. Einer auf einmal - beim
  // Darüberfahren, beim Fokussieren und beim Antippen derselbe.
  let gezeigt = $state<string | null>(null);
  let getippt = $state(false);

  function tippe(schluessel: string) {
    if (gezeigt === schluessel && getippt) {
      gezeigt = null;
      getippt = false;
    } else {
      gezeigt = schluessel;
      getippt = true;
    }
  }

  let huelle: HTMLElement;

  // Safari auf dem iPhone fokussiert angetippte Knöpfe nicht; ein Tippen
  // daneben schließt den Tooltip deshalb hier und nicht über `blur`.
  function anderswo(ereignis: PointerEvent) {
    if (getippt && !huelle.contains(ereignis.target as Node)) {
      gezeigt = null;
      getippt = false;
    }
  }

  // Wischen: waagrecht und deutlich genug, sonst ist es ein Rollen der Seite
  // oder ein Tippen. Nach links wischen holt den späteren Monat, wie beim
  // Umblättern.
  let start: { x: number; y: number } | null = null;

  function beruehrt(ereignis: TouchEvent) {
    const finger = ereignis.touches[0];
    start = ereignis.touches.length === 1 ? { x: finger.clientX, y: finger.clientY } : null;
  }

  function losgelassen(ereignis: TouchEvent) {
    if (!start) return;
    const finger = ereignis.changedTouches[0];
    const dx = finger.clientX - start.x;
    const dy = finger.clientY - start.y;
    start = null;
    if (Math.abs(dx) > 40 && Math.abs(dx) > 1.5 * Math.abs(dy)) blaettere(dx < 0 ? 1 : -1);
  }

  function taste(ereignis: KeyboardEvent) {
    if (ereignis.key === 'Escape') {
      gezeigt = null;
      getippt = false;
    }
  }
</script>

<svelte:window onpointerdown={anderswo} />

<div
  class="kalender"
  bind:this={huelle}
  bind:clientWidth={breite}
  ontouchstart={beruehrt}
  ontouchend={losgelassen}
  role="group"
  aria-label="Kalender"
>
  <button
    class="pfeil zurueck"
    aria-label="Früherer Monat"
    disabled={!kannZurueck}
    onclick={() => blaettere(-1)}
  >
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path d="M15 5l-7 7 7 7" />
    </svg>
  </button>
  <button
    class="pfeil vor"
    aria-label="Späterer Monat"
    disabled={!kannVor}
    onclick={() => blaettere(1)}
  >
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path d="M9 5l7 7-7 7" />
    </svg>
  </button>

  {#key ende}
    <div
      class="monate"
      style:--spalten={anzahl}
      in:fly={{ x: 28 * richtung, duration: ruhig ? 0 : 220 }}
    >
      {#each monate as monatsnummer (monatsnummer)}
        <section class="monat" aria-label={titel(monatsnummer)}>
          <h3>{titel(monatsnummer)}</h3>
          <div class="raster">
            {#each WOCHENTAGE as wochentag (wochentag)}
              <span class="wochentag" aria-hidden="true">{wochentag}</span>
            {/each}
            {#each zellen(monatsnummer) as zelle, i (i)}
              {#if !zelle}
                <span></span>
              {:else}
                {@const zahl = tage.get(zelle.schluessel) ?? 0}
                <span class="zelle">
                  {#if zahl}
                    <button
                      class="tag aktiv"
                      class:heute={zelle.schluessel === heuteSchluessel}
                      aria-label={auskunft(zelle, zahl)}
                      onmouseenter={() => (gezeigt = zelle.schluessel)}
                      onmouseleave={() => {
                        if (!getippt) gezeigt = null;
                      }}
                      onfocus={() => (gezeigt = zelle.schluessel)}
                      onblur={() => {
                        gezeigt = null;
                        getippt = false;
                      }}
                      onclick={() => tippe(zelle.schluessel)}
                      onkeydown={taste}
                    >
                      {zelle.tag}
                    </button>
                    {#if gezeigt === zelle.schluessel}
                      <span
                        class="blase"
                        class:links={zelle.spalte <= 1}
                        class:rechts={zelle.spalte >= 5}
                        aria-hidden="true"
                      >
                        {auskunft(zelle, zahl)}
                      </span>
                    {/if}
                  {:else}
                    <span class="tag" class:heute={zelle.schluessel === heuteSchluessel}>
                      {zelle.tag}
                    </span>
                  {/if}
                </span>
              {/if}
            {/each}
          </div>
        </section>
      {/each}
    </div>
  {/key}
</div>

<style>
  /* `pan-y`: Senkrecht rollt die Seite wie immer, waagrecht gehört der Wisch
     dem Kalender. `clip` statt `hidden`: Der einfahrende Monat soll die Seite
     nicht seitlich rollen lassen, die Tooltips dürfen nach oben hinaus. */
  .kalender {
    position: relative;
    overflow-x: clip;
    touch-action: pan-y;
    user-select: none;
    -webkit-user-select: none;
  }

  .monate {
    display: grid;
    grid-template-columns: repeat(var(--spalten), minmax(0, 1fr));
    gap: 2rem;
  }

  h3 {
    margin: 0 0 0.75rem;
    height: 2rem;
    line-height: 2rem;
    font-size: 0.95rem;
    font-weight: 600;
    text-align: center;
  }

  /* Die Pfeile stehen auf der Höhe der Monatsnamen, ganz außen - bei zwei
     Monaten also links vom einen und rechts vom anderen. */
  .pfeil {
    position: absolute;
    top: 0;
    z-index: 1;
    display: grid;
    place-items: center;
    width: 2rem;
    height: 2rem;
    padding: 0;
    border: 1px solid transparent;
    border-radius: 50%;
    background: none;
    color: var(--akzent);
    cursor: pointer;
  }

  .pfeil svg {
    fill: none;
    stroke: currentColor;
    stroke-width: 1.75;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .pfeil:hover:not(:disabled) {
    border-color: var(--rand);
  }

  .pfeil:focus-visible {
    outline: 2px solid var(--akzent);
    outline-offset: 1px;
  }

  .pfeil:disabled {
    color: var(--rand);
    cursor: default;
  }

  .zurueck {
    left: 0;
  }

  .vor {
    right: 0;
  }

  .raster {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    row-gap: 0.25rem;
    justify-items: center;
  }

  .wochentag {
    padding-bottom: 0.25rem;
    font-size: 0.75rem;
    color: var(--gedaempft);
  }

  .zelle {
    position: relative;
  }

  .tag {
    display: grid;
    place-items: center;
    width: 2.1rem;
    height: 2.1rem;
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: none;
    font: inherit;
    font-size: 0.85rem;
    font-variant-numeric: tabular-nums;
    color: var(--text);
  }

  .tag.heute {
    box-shadow: inset 0 0 0 1.5px var(--akzent);
    font-weight: 600;
  }

  .tag.aktiv {
    background: var(--akzent);
    color: #fff;
    font-weight: 600;
    cursor: pointer;
  }

  /* Heute und aktiv: der Ring rückt nach außen, damit er auf der gefüllten
     Fläche nicht verschwindet. */
  .tag.aktiv.heute {
    box-shadow:
      0 0 0 2px #fff,
      0 0 0 3.5px var(--akzent);
  }

  .tag.aktiv:focus-visible {
    outline: 2px solid var(--akzent);
    outline-offset: 2px;
  }

  .blase {
    position: absolute;
    bottom: calc(100% + 0.35rem);
    left: 50%;
    translate: -50% 0;
    z-index: 2;
    padding: 0.35rem 0.6rem;
    border-radius: 0.4rem;
    background: var(--text);
    color: var(--hintergrund);
    font-size: 0.8rem;
    white-space: nowrap;
    pointer-events: none;
    box-shadow: 0 4px 14px rgb(0 0 0 / 0.15);
  }

  /* Am Rand des Rasters zur Mitte hin ausgerichtet, sonst ragte die Blase
     über die Karte hinaus. */
  .blase.links {
    left: 0;
    translate: none;
  }

  .blase.rechts {
    left: auto;
    right: 0;
    translate: none;
  }
</style>
