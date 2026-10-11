<script lang="ts">
  /**
   * Wie gut das Modell von „schreiben" eine Aufnahme gehört hat - ein kleiner
   * Ring mit der Zahl, so hoch wie eine Textzeile.
   *
   * Die Farbe läuft von Rot über Orange, Gelb und Hellgrün nach Dunkelgrün,
   * gemessen an der Skala dieses Sprechers (`skala`, `services/uebersicht.py`):
   * Rot an ihrem unteren, Dunkelgrün an ihrem oberen Ende. Der Ring füllt sich
   * mit dem Wert selbst, bis 100.
   */
  import type { Guteskala } from './api';

  let { wert, skala, modell }: { wert: number; skala: Guteskala; modell: string } = $props();

  // Die Stufen der Farbe, gleich weit auseinander zwischen Rot und Dunkelgrün.
  const STUFEN: [number, number, number][] = [
    [198, 40, 40],
    [239, 108, 0],
    [242, 184, 0],
    [124, 179, 66],
    [27, 110, 50],
  ];

  function farbe(prozent: number): string {
    const anteil = Math.min(Math.max((prozent - skala.rot) / (skala.gruen - skala.rot), 0), 1);
    const lage = anteil * (STUFEN.length - 1);
    const unten = Math.min(Math.floor(lage), STUFEN.length - 2);
    const rest = lage - unten;
    const [a, b] = [STUFEN[unten], STUFEN[unten + 1]];
    const mische = (stelle: number) => Math.round(a[stelle] + (b[stelle] - a[stelle]) * rest);
    return `rgb(${mische(0)}, ${mische(1)}, ${mische(2)})`;
  }

  // Der Ring: Umfang eines Kreises mit Radius 6.
  const UMFANG = 2 * Math.PI * 6;
  const gefuellt = $derived((Math.min(Math.max(wert, 0), 100) / 100) * UMFANG);
</script>

<span
  class="guete"
  style="--farbe: {farbe(wert)}"
  title="Genauigkeit von {modell}: {wert.toFixed(0)} %"
  aria-label="Genauigkeit {wert.toFixed(0)} Prozent"
>
  <svg viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="8" cy="8" r="6" class="spur" />
    <circle
      cx="8"
      cy="8"
      r="6"
      class="wert"
      stroke-dasharray="{gefuellt} {UMFANG}"
      transform="rotate(-90 8 8)"
    />
  </svg>
  <span class="zahl">{wert.toFixed(0)}</span>
</span>

<style>
  .guete {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    flex: none;
    line-height: 1;
    font-size: 0.8rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    /* Etwas dunkler als der Ring - Gelb auf Weiß wäre sonst kaum zu lesen. */
    color: color-mix(in srgb, var(--farbe) 72%, black);
  }

  svg {
    width: 0.95rem;
    height: 0.95rem;
  }

  circle {
    fill: none;
    stroke-width: 2.5;
  }

  .spur {
    stroke: var(--rand);
  }

  .wert {
    stroke: var(--farbe);
    stroke-linecap: round;
  }

  .zahl::after {
    content: ' %';
    font-weight: 400;
    font-size: 0.7rem;
  }
</style>
