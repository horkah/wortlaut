<script lang="ts">
  /**
   * Die Zugangsdaten dieser Instanz - die Ansicht dazu ist geteilt
   * (`$ui/Zugangsdaten.svelte`), weil alle drei Apps denselben Zugang lesen.
   *
   * Hier steht nur, was „lernen" davon unterscheidet: Es verwaltet nichts.
   * Diese App braucht den Zugang **eines** Sprechers, und nur den - ein
   * Verwalter- oder Aufsichtstoken kommt hier nicht durch, weil ein Modell zu
   * einem Menschen gehört und nicht zu einer Instanz.
   *
   * Die Ansicht steht trotzdem immer bereit, auch und gerade ohne gültigen
   * Zugang: Genau dann ist sie der einzige Weg herein, und ein Menü, das sie
   * erst nach erfolgreicher Anmeldung zeigt, hätte die Tür hinter dem Schloss.
   */
  import Zugangsdaten from '$ui/Zugangsdaten.svelte';
  import { werRuft } from '../lib/api';
  import { gehZu, ladeZugang, zustand } from '../lib/zustand.svelte';

  // Nach einem angenommenen Zugang gilt hier alles Weitere: Wer die Seite
  // gerade sieht, ist danach jemand anderes.
  async function pruefe() {
    const wer = await werRuft();
    await ladeZugang();
    return wer;
  }
</script>

<Zugangsdaten art={zustand.art} name={zustand.name} {pruefe}>
  {#snippet weiter()}
    <button class="knopf haupt" onclick={() => gehZu('/aufteilung')}>
      Weiter zur Aufteilung
    </button>
  {/snippet}
</Zugangsdaten>
