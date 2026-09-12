<script lang="ts">
  /**
   * Die fertigen Modellstände - und welcher freigegeben ist.
   *
   * **Warum Freigeben ein eigener Knopf ist.** Ein durchgelaufenes Training
   * ist noch kein Modell, das jemand benutzen soll. Zwischen „hat gerechnet"
   * und „damit diktiere ich" liegt der Blick auf die Zahlen, und den nimmt
   * einem nichts ab.
   *
   * **Warum trotzdem alle stehen bleiben.** Vier Läufe ergeben vier Stände,
   * und welcher der beste ist, beantwortet man nicht, indem man drei wegwirft.
   * Freigegeben ist höchstens einer - der, den „schreiben" von sich aus nimmt;
   * die übrigen lassen sich dort ausdrücklich auswählen.
   */
  import { onMount } from 'svelte';
  import { gibFrei, modelle as ladeModelle, type Modellstand } from '../lib/api';

  let staende = $state<Modellstand[]>([]);
  let fehler = $state('');
  let geladen = $state(false);
  let arbeitet = $state('');

  const METHODEN: Record<string, string> = { full: 'Volles Training', lora: 'Feintuning (LoRA)' };
  const DATEN: Record<string, string> = {
    original: 'Nur Originale',
    augmentiert: 'Mit Abwandlungen',
  };

  // Jüngster zuerst: Wer hierherkommt, sucht meist den, der gerade fertig wurde.
  const sortiert = $derived([...staende].reverse());

  function zeit(roh: string): string {
    const wann = new Date(roh);
    return Number.isNaN(wann.getTime()) ? roh : wann.toLocaleDateString('de-DE');
  }

  async function hole() {
    try {
      staende = (await ladeModelle()).staende;
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      geladen = true;
    }
  }

  async function freigeben(version: string) {
    arbeitet = version;
    try {
      staende = (await gibFrei(version)).staende;
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      arbeitet = '';
    }
  }

  onMount(hole);
</script>

<h2>Modelle</h2>
<p class="gedaempft">
  Was die Läufe hervorgebracht haben. Ein Stand ist ein Verzeichnis unter <code>data/modelle/</code>
  - kopierbar, sicherbar, verschiebbar. Freigegeben ist höchstens einer; das ist der, mit dem
  „schreiben" von sich aus arbeitet.
</p>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{#if !geladen}
  <p class="gedaempft">Wird geladen …</p>
{:else if !staende.length}
  <div class="karte">
    <p>Noch kein Modell trainiert.</p>
    <p class="gedaempft">
      Unter „Training" wird ein Lauf beauftragt; sobald er durch ist, steht sein Stand hier.
    </p>
  </div>
{:else}
  <div class="staende">
    {#each sortiert as stand (stand.version)}
      <div class="karte stand" class:frei={stand.status === 'active'}>
        <div class="kopfzeile">
          <p class="marke">
            {METHODEN[stand.methode] ?? stand.methode} · {DATEN[stand.daten] ?? stand.daten}
          </p>
          {#if stand.status === 'active'}
            <span class="abzeichen">freigegeben</span>
          {/if}
        </div>

        <p class="gedaempft klein">
          {stand.basismodell} · {zeit(stand.erstellt)} · Version <code>{stand.version}</code>
        </p>

        {#if stand.genauigkeit !== null || stand.wer !== null}
          <p class="zahlen">
            {#if stand.genauigkeit !== null}
              <strong>{stand.genauigkeit.toFixed(1)} %</strong> Genauigkeit
            {/if}
            {#if stand.wer !== null}
              <span class="gedaempft">· WER {stand.wer.toFixed(3)}</span>
            {/if}
            {#if stand.test_einheiten}
              <span class="gedaempft">· über {stand.test_einheiten} Testproben</span>
            {/if}
          </p>
          <p class="gedaempft klein">
            Über alle vier Fassungen zusammen. Aufgeschlüsselt und der Grundlinie
            gegenübergestellt steht es beim Lauf.
          </p>
        {/if}

        <div class="reihe">
          {#if stand.job_id}
            <a class="knopf" href="#/lauf/{stand.job_id}">Zum Lauf</a>
          {/if}
          {#if stand.status !== 'active'}
            <button
              class="knopf haupt"
              onclick={() => freigeben(stand.version)}
              disabled={arbeitet === stand.version}
            >
              Freigeben
            </button>
            <span class="gedaempft klein">
              Freigeben zieht jeden anderen Stand zurück - es gilt immer höchstens einer.
            </span>
          {:else}
            <span class="gedaempft klein">
              „schreiben" nimmt diesen Stand, solange dort nichts anderes gewählt ist.
            </span>
          {/if}
        </div>
      </div>
    {/each}
  </div>
{/if}

<style>
  .staende {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }

  .stand.frei {
    border-color: var(--akzent);
  }

  .kopfzeile {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.4rem 1rem;
  }

  .marke {
    margin: 0;
    font-weight: 600;
    color: var(--akzent);
  }

  /* Nicht nur eine Farbe: Der Zustand steht als Wort da, damit er auch ohne
     Farbunterscheidung zu lesen ist. */
  .abzeichen {
    padding: 0.1rem 0.5rem;
    border-radius: 0.25rem;
    background: var(--akzent);
    color: #fff;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .zahlen {
    margin: 0.5rem 0 0.1rem;
    font-variant-numeric: tabular-nums;
  }

  .klein {
    font-size: 0.85rem;
    margin: 0.2rem 0;
  }
</style>
