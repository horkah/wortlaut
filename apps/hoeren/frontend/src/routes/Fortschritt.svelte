<script lang="ts">
  /**
   * Gesammelte Minuten gegen zwei Marken: ab etwa 1,5 Stunden wird ein Modell
   * brauchbar, ab etwa 20 Stunden gut. Danach flacht der Gewinn ab.
   */
  import { fortschritt, type Fortschritt } from '../lib/api';
  import { waehleSprecher, zustand } from '../lib/zustand.svelte';

  const sprecher = zustand.sprecher!;
  let daten = $state<Fortschritt | null>(null);

  const stunden = (sekunden: number) => (sekunden / 3600).toFixed(2);
  const anteil = (sekunden: number, marke: number) => Math.min(100, (sekunden / marke) * 100);

  fortschritt(sprecher).then((antwort) => (daten = antwort));
</script>

<h2>Fortschritt</h2>

{#if daten}
  <p style="font-size:2rem;margin:0">{stunden(daten.sekunden)} Stunden</p>
  <p class="gedaempft">{daten.aufnahmen} Aufnahmen · {daten.offene_einheiten} Einheiten offen</p>

  <h2>Marken</h2>
  <p>Brauchbar ab {stunden(daten.marke_brauchbar_s)} h</p>
  <div class="balken">
    <div style="width:{anteil(daten.sekunden, daten.marke_brauchbar_s)}%"></div>
  </div>
  <p style="margin-top:1rem">Gut ab {stunden(daten.marke_gut_s)} h</p>
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

<h2>Sprecher wechseln</h2>
<button class="knopf" onclick={() => waehleSprecher(null)}>Abmelden</button>

<style>
  table {
    border-collapse: collapse;
  }
  td {
    padding: 0.25rem 1.5rem 0.25rem 0;
    border-bottom: 1px solid var(--rand);
  }
</style>
