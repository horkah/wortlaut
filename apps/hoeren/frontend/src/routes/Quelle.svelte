<script lang="ts">
  /**
   * Textquelle wählen: entweder ein Thema, aus dem ein LLM Text erzeugt, oder
   * ein hochgeladener Text. Beides wird zu Sprecheinheiten geschnitten und
   * hinten an die Warteschlange gehängt.
   */
  import { quelleAusDatei, quelleAusLLM, quellen, type Quelle } from '../lib/api';
  import { gehZu, zustand } from '../lib/zustand.svelte';

  const sprecher = zustand.sprecher!;

  let liste = $state<Quelle[]>([]);
  let fehler = $state('');
  let laeuft = $state(false);

  let thema = $state('');
  let altersspanne = $state('Erwachsene');
  let umfang = $state(300);
  let datei = $state<FileList | null>(null);

  async function lade() {
    liste = await quellen(sprecher);
  }

  async function fuehreAus(arbeit: () => Promise<unknown>) {
    fehler = '';
    laeuft = true;
    try {
      await arbeit();
      await lade();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      laeuft = false;
    }
  }

  const ausLLM = (ereignis: SubmitEvent) => {
    ereignis.preventDefault();
    fuehreAus(() => quelleAusLLM(sprecher, { thema, altersspanne, umfang }));
  };

  const ausDatei = (ereignis: SubmitEvent) => {
    ereignis.preventDefault();
    const gewaehlt = datei?.[0];
    if (gewaehlt) fuehreAus(() => quelleAusDatei(sprecher, gewaehlt));
  };

  lade();
</script>

<h2>Thema (Text vom Sprachmodell)</h2>
<form onsubmit={ausLLM}>
  <label>
    <span>Thema oder Stichwort</span>
    <input bind:value={thema} required placeholder="Zum Beispiel: Einkaufen im Wochenmarkt" />
  </label>
  <label>
    <span>Altersspanne der Zielgruppe</span>
    <input bind:value={altersspanne} placeholder="Erwachsene, 8-12, …" />
  </label>
  <label>
    <span>Umfang (ungefähre Wortzahl)</span>
    <input type="number" bind:value={umfang} min="50" max="3000" step="50" />
  </label>
  <button class="knopf haupt" type="submit" disabled={laeuft}>Text erzeugen</button>
</form>

<h2>Eigener Text</h2>
<p class="gedaempft">txt, md, pdf, epub oder docx.</p>
<form onsubmit={ausDatei}>
  <input type="file" accept=".txt,.md,.pdf,.epub,.docx" bind:files={datei} />
  <button class="knopf" type="submit" disabled={laeuft}>Hochladen</button>
</form>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

<h2>Vorhandene Quellen</h2>
{#each liste as quelle (quelle.id)}
  <div class="karte">
    <strong>{quelle.titel}</strong>
    <div class="gedaempft">{quelle.art} · {quelle.einheiten} Einheiten · {quelle.erstellt}</div>
  </div>
{:else}
  <p class="gedaempft">Noch keine Quelle.</p>
{/each}

{#if liste.length > 0}
  <button class="knopf haupt" onclick={() => gehZu('/aufnahme')}>Zur Aufnahme</button>
{/if}
