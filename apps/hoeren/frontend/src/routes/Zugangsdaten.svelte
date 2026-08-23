<script lang="ts">
  /**
   * Die Zugangsdaten dieser Instanz - die Ansicht dazu ist geteilt
   * (`$ui/Zugangsdaten.svelte`), weil beide Apps denselben Zugang lesen.
   *
   * Hier steht nur, was „hören" davon unterscheidet: Dasselbe Feld nimmt außer
   * einem Sprecherzugang auch den Verwalter- **und** den Aufsichtstoken. Der
   * Server sieht am Vorgelegten, welches von beidem es ist (backend/deps.py).
   * Deshalb wird die Aufsicht aus jedem Browser erreichbar, in dem jemand
   * ihren Token einträgt - es gibt keine zweite Adresse und keine zweite
   * Anmeldung.
   */
  import Zugangsdaten from '$ui/Zugangsdaten.svelte';
  import { SPRECHER_PFAD } from '$ui/apps';
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

<Zugangsdaten art={zustand.art} name={zustand.name} verwaltet {pruefe}>
  {#snippet weiter()}
    <!-- Wer wegen des Tokens hergeschickt wurde, will jetzt zu den Sprechern. -->
    <button class="knopf haupt" onclick={() => gehZu(SPRECHER_PFAD)}>
      Weiter zu den Sprechern
    </button>
  {/snippet}
</Zugangsdaten>
