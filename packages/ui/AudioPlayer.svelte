<script lang="ts">
  /** Abspielen dessen, was gerade aufgenommen wurde. Ohne `beschriftung` nur der Player. */
  let { quelle, beschriftung = '' }: { quelle: string | null; beschriftung?: string } = $props();
</script>

{#if quelle}
  <figure class="abspieler">
    {#if beschriftung}<figcaption>{beschriftung}</figcaption>{/if}
    <!-- svelte-ignore a11y_media_has_caption (eigene Sprachaufnahme, kein Untertitel) -->
    <audio controls src={quelle} preload="metadata"></audio>
  </figure>
{/if}

<style>
  .abspieler {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.9rem;
    color: #555;
    margin: 0;
  }
  audio {
    width: 100%;
    max-width: 28rem;
  }
</style>
