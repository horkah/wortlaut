<script lang="ts" module>
  /**
   * Die Grenzen stehen doppelt: hier und in
   * `apps/hoeren/backend/services/quality.py`. Absicht — die Anzeige soll
   * vorwegnehmen, was der Server nachher meldet, und das geht nur, wenn sie
   * dieselben Zahlen benutzt. Wer dort etwas ändert, ändert es hier mit.
   */
  export const LEISE_DBFS = -35;
  export const LAUT_DBFS = -6;

  /** Weiter unten ist alles gleich still; die Anzeige würde nur zappeln. */
  const BODEN_DBFS = -60;

  function anteil(dbfs: number): number {
    return Math.min(100, Math.max(0, ((dbfs - BODEN_DBFS) / -BODEN_DBFS) * 100));
  }
</script>

<script lang="ts">
  import type { Pegel } from './mikrofon';

  let { pegel, beschriftung = 'Pegel' }: { pegel: Pegel; beschriftung?: string } = $props();

  const urteil = $derived(
    pegel.rms < LEISE_DBFS ? 'leise' : pegel.rms > LAUT_DBFS ? 'laut' : 'gut',
  );
  const text = $derived(
    urteil === 'leise'
      ? 'zu leise — Verstärkung erhöhen oder näher ans Mikrofon'
      : urteil === 'laut'
        ? 'zu laut — Verstärkung senken'
        : 'guter Pegel',
  );
</script>

<div class="pegel">
  <div class="skala" role="meter" aria-label={beschriftung} aria-valuenow={Math.round(pegel.rms)}
       aria-valuemin={BODEN_DBFS} aria-valuemax={0} aria-valuetext="{Math.round(pegel.rms)} dBFS, {text}">
    <div class="zone leise" style="width:{anteil(LEISE_DBFS)}%"></div>
    <div class="zone laut" style="left:{anteil(LAUT_DBFS)}%"></div>
    <div class="fuellung {urteil}" style="width:{anteil(pegel.rms)}%"></div>
    <!-- Die Spitze entscheidet über Übersteuerung, der Mittelwert über
         Verständlichkeit. Beides gehört sichtbar. -->
    <div class="spitze" style="left:{anteil(pegel.spitze)}%"></div>
  </div>
  <p class="gedaempft ablesung">
    <span class="wert">{pegel.rms > BODEN_DBFS ? `${pegel.rms.toFixed(0)} dBFS` : 'still'}</span>
    <span class:warnt={urteil !== 'gut'}>{text}</span>
  </p>
</div>

<style>
  .skala {
    position: relative;
    height: 1.4rem;
    background: var(--rand);
    border-radius: 0.3rem;
    overflow: hidden;
  }
  .zone {
    position: absolute;
    top: 0;
    bottom: 0;
    background: #00000010;
  }
  .zone.laut {
    right: 0;
  }
  .fuellung {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    background: var(--akzent);
    transition: width 60ms linear;
  }
  .fuellung.leise {
    background: var(--gedaempft);
  }
  .fuellung.laut {
    background: var(--fehler);
  }
  .spitze {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--text);
  }
  .ablesung {
    display: flex;
    gap: 0.75rem;
    margin: 0.3rem 0 0;
  }
  .wert {
    font-variant-numeric: tabular-nums;
    min-width: 5rem;
  }
  .warnt {
    color: var(--warnung);
  }
</style>
