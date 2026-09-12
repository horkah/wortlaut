<script lang="ts">
  /**
   * Der Zugang dieses Browsers - die Ansicht dazu ist geteilt
   * (`$ui/Zugangsdaten.svelte`).
   *
   * Hier gibt es nichts zu verwalten: Diese App kennt nur Sprecherzugänge,
   * einen Verwalter- oder Aufsichtstoken weist ihr Server ab (backend/deps.py).
   * Der Punkt steht trotzdem im Menü, und gerade dann, wenn noch kein Zugang
   * da ist - er sagt, woran es fehlt, statt die Seite an lauter abgewiesenen
   * Anfragen scheitern zu lassen.
   */
  import Zugangsdaten from '$ui/Zugangsdaten.svelte';
  import { werRuft } from '../lib/api';
  import { gehZu, ladeModellstand, ladeZugang, zustand } from '../lib/zustand.svelte';

  // Mit dem Zugang wechselt auch das Modell: Jeder Sprecher läuft auf seinem
  // eigenen Stand, und die Kopfzeile soll ihn sofort richtig nennen.
  async function pruefe() {
    const wer = await werRuft();
    await ladeZugang();
    await ladeModellstand();
    return wer;
  }
</script>

<!-- Derselbe Rückweg wie bei „Modell", aus demselben Grund: Diese App hat
     keine Reiterreihe, also muss ihn die Ansicht mitbringen. Nur solange ein
     Zugang gilt - ohne ihn führte er auf einen Aufnahmeknopf, der ins Leere
     liefe, und die Ansicht hier ist dann der einzige sinnvolle Ort. -->
{#if zustand.art === 'sprecher'}
  <p class="zurueck">
    <button class="knopf" onclick={() => gehZu('/')}>← Zurück zum Diktieren</button>
  </p>
{/if}

<Zugangsdaten art={zustand.art} name={zustand.name} {pruefe}>
  {#snippet weiter()}
    <button class="knopf haupt" onclick={() => gehZu('/')}>Weiter zum Diktat</button>
  {/snippet}
</Zugangsdaten>

<style>
  .zurueck {
    margin: 0 0 0.8rem;
  }
</style>
