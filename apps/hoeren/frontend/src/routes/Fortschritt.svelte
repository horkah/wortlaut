<script lang="ts">
  /**
   * Gesammelte Sprechzeit gegen zwei Marken: ab etwa 1,5 Stunden wird ein
   * Modell brauchbar, ab etwa 20 Stunden gut. Danach flacht der Gewinn ab.
   *
   * Die Zeit steht als Stunden, Minuten und Sekunden und nicht als
   * Dezimalstunden. Hier stand einmal „0,43 Stunden" - richtig gerechnet und
   * für die Zielperson keine Auskunft: Niemand weiß aus dem Stand, wie viele
   * Minuten das sind, und niemand sollte es ausrechnen müssen, um zu sehen,
   * wie weit er heute gekommen ist (Grundentscheidung 7). Gerechnet wird das
   * in `$ui/zeit`, damit dieselbe Zahl in „Meine Daten" und in der
   * Sprecherliste genauso dasteht.
   */
  import { dauer } from '$ui/zeit';
  import { fortschritt, type Fortschritt } from '../lib/api';

  let daten = $state<Fortschritt | null>(null);

  const anteil = (sekunden: number, marke: number) => Math.min(100, (sekunden / marke) * 100);

  /** Wie viel noch fehlt - die Zahl, nach der hier eigentlich gefragt wird. */
  const fehlt = (sekunden: number, marke: number) => Math.max(0, marke - sekunden);

  fortschritt().then((antwort) => (daten = antwort));
</script>

<h2>Fortschritt</h2>

{#if daten}
  <p class="gesamt">{dauer(daten.sekunden)}</p>
  <p class="gedaempft">
    gesprochen · {daten.aufnahmen} Aufnahmen · {daten.offene_einheiten} Einheiten offen
  </p>

  <h2>Marken</h2>
  <!-- Neben der Marke steht, was noch fehlt. Der Balken zeigt, wo man steht;
       die Frage dahinter ist aber „wie lange muss ich noch", und die
       beantwortet keine Länge, sondern eine Zahl. -->
  <p>
    Brauchbar ab {dauer(daten.marke_brauchbar_s)}
    {#if fehlt(daten.sekunden, daten.marke_brauchbar_s)}
      <span class="gedaempft">- noch {dauer(fehlt(daten.sekunden, daten.marke_brauchbar_s))}</span>
    {:else}
      <span class="gedaempft">- erreicht</span>
    {/if}
  </p>
  <div class="balken">
    <div style="width:{anteil(daten.sekunden, daten.marke_brauchbar_s)}%"></div>
  </div>
  <p style="margin-top:1rem">
    Gut ab {dauer(daten.marke_gut_s)}
    {#if fehlt(daten.sekunden, daten.marke_gut_s)}
      <span class="gedaempft">- noch {dauer(fehlt(daten.sekunden, daten.marke_gut_s))}</span>
    {:else}
      <span class="gedaempft">- erreicht</span>
    {/if}
  </p>
  <div class="balken"><div style="width:{anteil(daten.sekunden, daten.marke_gut_s)}%"></div></div>

  <h2>Zusammensetzung</h2>
  <p class="gedaempft">
    Nachgesprochenes und Korrekturen sind schwächere Daten und werden im Training
    niedriger gewichtet.
  </p>
  <table>
    <tbody>
      {#each Object.entries(daten.nach_modus) as [modus, anzahl]}
        <tr><td>Modus „{modus}“</td><td>{anzahl}</td></tr>
      {/each}
      {#each Object.entries(daten.nach_quelle) as [quelle, anzahl]}
        <tr><td>Quelle „{quelle}“</td><td>{anzahl}</td></tr>
      {/each}
    </tbody>
  </table>
{:else}
  <p class="gedaempft">Wird geladen …</p>
{/if}


<style>
  /* Die eine Zahl, für die diese Seite da ist - groß genug, um sie im
     Vorbeigehen zu lesen. */
  .gesamt {
    font-size: 2rem;
    font-weight: 600;
    margin: 0;
    font-variant-numeric: tabular-nums;
  }

  table {
    border-collapse: collapse;
  }
  td {
    padding: 0.25rem 1.5rem 0.25rem 0;
    border-bottom: 1px solid var(--rand);
  }
</style>
