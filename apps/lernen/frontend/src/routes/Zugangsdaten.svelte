<script lang="ts">
  /**
   * Die Zugangsdaten dieser Instanz - die Ansicht dazu ist geteilt
   * (`$ui/Zugangsdaten.svelte`), weil alle drei Apps denselben Zugang lesen.
   *
   * Hier steht nur, was „lernen" davon unterscheidet: wohin es nach einem
   * angenommenen Zugang weitergeht. Alles andere ist in allen drei gleich -
   * auch die Übergabe des Browsers an die Verwaltung oder die Aufsicht, die
   * bis September 2026 nur „hören" anbot.
   *
   * Zum Trainieren braucht diese App den Zugang **eines** Sprechers: Ein
   * Modell gehört zu einem Menschen und nicht zu einer Instanz, und ihre API
   * weist einen Verwalter- oder Aufsichtstoken entsprechend ab. Das ist aber
   * kein Grund, das Feld hier zu verstecken - wer diesen Browser übergeben
   * will, tut es, wo er gerade steht, und findet die Sprecherliste danach im
   * Menü.
   *
   * Die Ansicht steht trotzdem immer bereit, auch und gerade ohne gültigen
   * Zugang: Genau dann ist sie der einzige Weg herein, und ein Menü, das sie
   * erst nach erfolgreicher Anmeldung zeigt, hätte die Tür hinter dem Schloss.
   */
  import Zugangsdaten from '$ui/Zugangsdaten.svelte';
  import { gehZu, ladeZugang, zustand } from '../lib/zustand.svelte';

</script>

<Zugangsdaten art={zustand.art} name={zustand.name} neuLaden={ladeZugang}>
  {#snippet weiter()}
    <button class="knopf haupt" onclick={() => gehZu('/aufteilung')}>
      Weiter zur Aufteilung
    </button>
  {/snippet}
</Zugangsdaten>
