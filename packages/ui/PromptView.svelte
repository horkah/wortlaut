<script lang="ts">
  /**
   * Eine Einheit groß, davor und dahinter je eine blass.
   *
   * Der Kontext hilft beim Verstehen des Zusammenhangs, ohne zum Ablesen zu
   * verleiten — deshalb blass und deutlich kleiner.
   */
  type Einheit = { id: string; text: string } | null;

  let {
    vorher,
    aktuell,
    nachher,
    schriftRem = 2,
  }: {
    vorher: Einheit;
    aktuell: Einheit;
    nachher: Einheit;
    /** Schriftgröße der aktuellen Einheit; einstellbar, weil die Zielgruppe
        sehr verschieden gut liest. */
    schriftRem?: number;
  } = $props();
</script>

<div class="vorlage">
  <p class="blass">{vorher?.text ?? ''}</p>
  <p class="aktuell" style="font-size:{schriftRem}rem">{aktuell?.text ?? ''}</p>
  <p class="blass">{nachher?.text ?? ''}</p>
</div>

<style>
  .vorlage {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    text-align: center;
    min-height: 10rem;
    justify-content: center;
  }
  .aktuell {
    line-height: 1.4;
    margin: 0;
  }
  .blass {
    color: #9a9a9a;
    font-size: 1rem;
    margin: 0;
    min-height: 1.4em;
  }
</style>
