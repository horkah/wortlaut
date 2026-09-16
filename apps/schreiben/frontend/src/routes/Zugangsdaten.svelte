<script lang="ts">
  /**
   * Der Zugang dieses Browsers - die Ansicht dazu ist geteilt
   * (`$ui/Zugangsdaten.svelte`).
   *
   * Hier gibt es nichts zu verwalten: Zum Diktieren braucht es den Zugang
   * eines Sprechers, und die eigene API dieser App weist einen Verwalter- oder
   * Aufsichtstoken entsprechend ab (backend/deps.py). Der Punkt steht trotzdem
   * im Menü, und gerade dann, wenn noch kein Zugang da ist - er sagt, woran es
   * fehlt, statt die Seite an lauter abgewiesenen Anfragen scheitern zu
   * lassen.
   *
   * **Das Feld nimmt trotzdem alle drei Arten an.** Es geht hier nicht ums
   * Diktieren, sondern darum, diesen Browser jemandem zu übergeben: Wer seinen
   * Aufsichtstoken einträgt, während „schreiben" offen ist, hat ihn danach in
   * allen drei Apps. Geprüft wird deshalb bei „hören" und nicht hier
   * (`$ui/wer.ts`) - dort werden alle drei Arten erkannt. Diese Ansicht fragte
   * einmal die eigene API und wies dabei einen gültigen Aufsichtstoken ab.
   */
  import Zugangsdaten from '$ui/Zugangsdaten.svelte';
  import { gehZu, ladeModellstand, ladeZugang, zustand } from '../lib/zustand.svelte';

  // Mit dem Zugang wechselt auch das Modell: Jeder Sprecher läuft auf seinem
  // eigenen Stand, und die Kopfzeile soll ihn sofort richtig nennen. Das ist
  // der Grund, warum es diese Eigenschaft überhaupt gibt - die anderen beiden
  // Apps haben hier nur `ladeZugang`.
  async function neuLaden() {
    await ladeZugang();
    await ladeModellstand();
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

<Zugangsdaten art={zustand.art} name={zustand.name} {neuLaden}>
  {#snippet weiter()}
    <button class="knopf haupt" onclick={() => gehZu('/')}>Weiter zum Diktat</button>
  {/snippet}
</Zugangsdaten>

<style>
  .zurueck {
    margin: 0 0 0.8rem;
  }
</style>
