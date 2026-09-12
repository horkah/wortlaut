<script lang="ts">
  /**
   * Welches Modell zuhört.
   *
   * **Warum es diese Ansicht gibt.** Früher stand das Modell in der Umgebung
   * und ein Wechsel war ein Neustart - richtig, solange es je Sprecher
   * höchstens einen trainierten Stand gab. „lernen" liefert vier (zwei
   * Methoden mal zwei Datensätze), und daneben stehen die unveränderten
   * Grundmodelle, gegen die in „hören" schon gemessen wurde. Welches davon
   * dieser Person am besten zuhört, beantwortet keine Kennzahl allein; das
   * beantwortet sich beim Diktieren.
   *
   * **Was dabei nicht aufgegeben wird.** Zu jeder Ausgabe steht fest, welches
   * Modell sie erzeugt hat: Die Zeile unter dem Aufnahmeknopf nennt es
   * dauerhaft, samt Methode und Datensatz. Wer eine Fehlerkennung beurteilt,
   * beurteilt immer ein bestimmtes Modell.
   *
   * **Warum im Menü und nicht in der Reiterreihe.** Die Zielperson kann
   * schlecht lesen (Grundentscheidung 7), und die App soll ein großer Knopf
   * bleiben. Ein Modell zu wechseln ist ein Nachjustieren, keine Tätigkeit -
   * es gehört dorthin, wo auch Mikrofon und Stimme stehen.
   */
  import { modellWaehlen, type Modellwahl } from '../lib/api';
  import { ladeModellstand, zustand } from '../lib/zustand.svelte';

  let fehler = $state('');
  let arbeitet = $state('');

  const modell = $derived(zustand.modellstand);
  const auswahl = $derived(modell?.auswahl ?? []);
  const grundmodelle = $derived(auswahl.filter((wahl) => wahl.art === 'grundmodell'));
  const trainiert = $derived(auswahl.filter((wahl) => wahl.art === 'trainiert'));

  const METHODEN: Record<string, string> = { full: 'Volles Training', lora: 'Feintuning (LoRA)' };
  const DATEN: Record<string, string> = {
    original: 'Nur Originale',
    augmentiert: 'Mit Abwandlungen',
  };

  function untertitel(wahl: Modellwahl): string {
    if (wahl.art === 'grundmodell') {
      return 'Unverändert, so wie es Whisper ausliefert.';
    }
    const teile = [
      METHODEN[wahl.methode ?? ''] ?? wahl.methode,
      DATEN[wahl.daten ?? ''] ?? wahl.daten,
    ].filter(Boolean);
    if (wahl.wer !== null) {
      teile.push(`WER ${wahl.wer.toFixed(3)} auf den Testaufnahmen`);
    }
    return teile.join(' · ');
  }

  async function waehle(ref: string) {
    arbeitet = ref || 'vorgabe';
    fehler = '';
    try {
      await modellWaehlen(ref);
      await ladeModellstand();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      arbeitet = '';
    }
  }
</script>

<h2>Modell</h2>
<p class="gedaempft">
  Wer hier zuhört. Die Wahl gilt sofort und bleibt, bis sie geändert wird - ein Neustart ist dafür
  nicht nötig. Was gerade arbeitet, steht auch unter dem Aufnahmeknopf.
</p>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{#if !modell}
  <p class="gedaempft">Wird geladen …</p>
{:else}
  <div class="karte jetzt">
    <p class="marke">Gerade geladen</p>
    <p class="beschriftung">{modell.beschriftung}</p>
    {#if !modell.gewaehlt}
      <p class="gedaempft klein">
        Nichts ausgewählt - es gilt die Vorgabe: der Stand, den „lernen" freigegeben hat, und
        solange es keinen gibt, das unveränderte Grundmodell.
      </p>
    {:else}
      <div class="reihe">
        <button class="knopf" onclick={() => waehle('')} disabled={arbeitet === 'vorgabe'}>
          Zurück zur Vorgabe
        </button>
      </div>
    {/if}
  </div>

  {#if trainiert.length}
    <h3>Eigene Modelle</h3>
    <p class="gedaempft">
      Aus „lernen", auf der eigenen Stimme trainiert. Der freigegebene ist die Vorgabe; die
      anderen lassen sich hier ausprobieren, ohne dort etwas zu ändern.
    </p>
    <div class="liste">
      {#each trainiert as wahl (wahl.ref)}
        <button
          type="button"
          class="eintrag"
          class:aktiv={modell.ref === wahl.ref}
          disabled={arbeitet === wahl.ref}
          onclick={() => waehle(wahl.ref)}
        >
          <span class="zeile">
            <strong>{wahl.beschriftung}</strong>
            {#if wahl.freigegeben}
              <span class="abzeichen">freigegeben</span>
            {/if}
            {#if modell.ref === wahl.ref}
              <span class="abzeichen jetzt">läuft</span>
            {/if}
          </span>
          <span class="gedaempft klein">{untertitel(wahl)}</span>
        </button>
      {/each}
    </div>
  {/if}

  <h3>Grundmodelle</h3>
  <p class="gedaempft">
    Unverändertes Whisper - dieselben, gegen die in „hören" unter „Auswertung" gemessen wird. Wer
    dort Zahlen gesehen hat, bekommt hier genau den Erkenner, zu dem sie gehören.
  </p>
  <div class="liste">
    {#each grundmodelle as wahl (wahl.ref)}
      <button
        type="button"
        class="eintrag"
        class:aktiv={modell.ref === wahl.ref}
        disabled={arbeitet === wahl.ref}
        onclick={() => waehle(wahl.ref)}
      >
        <span class="zeile">
          <strong>{wahl.beschriftung}</strong>
          {#if modell.ref === wahl.ref}
            <span class="abzeichen jetzt">läuft</span>
          {/if}
        </span>
        <span class="gedaempft klein">{untertitel(wahl)}</span>
      </button>
    {/each}
  </div>

  <p class="gedaempft klein">
    Ein größeres Grundmodell hört genauer und rechnet länger: Nach dem Wechsel dauert das erste
    Diktat spürbar länger, weil das Modell erst geladen wird.
  </p>
{/if}

<style>
  .jetzt {
    margin-bottom: 1.2rem;
  }

  .marke {
    margin: 0 0 0.3rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--akzent);
  }

  .beschriftung {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
  }

  .liste {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    margin-bottom: 1.2rem;
  }

  /* Große Flächen statt Auswahlliste: Die Zielperson soll treffen, ohne zu
     zielen (Grundentscheidung 7) - und die Begründung steht in der Fläche mit
     drin, statt in einem Tooltip zu verschwinden. */
  .eintrag {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    width: 100%;
    padding: 0.7rem 0.9rem;
    text-align: left;
    border: 1px solid var(--rand);
    border-radius: 0.45rem;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  .eintrag:hover:not(:disabled) {
    border-color: var(--akzent);
  }

  .eintrag:disabled {
    opacity: 0.6;
    cursor: progress;
  }

  .eintrag.aktiv {
    border-color: var(--akzent);
    border-width: 2px;
    padding: calc(0.7rem - 1px) calc(0.9rem - 1px);
  }

  .zeile {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.5rem;
  }

  /* Nicht nur eine Farbe: Der Zustand steht als Wort da, damit er auch ohne
     Farbunterscheidung zu lesen ist. */
  .abzeichen {
    padding: 0.05rem 0.45rem;
    border-radius: 0.25rem;
    border: 1px solid var(--akzent);
    color: var(--akzent);
    font-size: 0.72rem;
    font-weight: 600;
  }

  .abzeichen.jetzt {
    background: var(--akzent);
    color: #fff;
  }

  .klein {
    font-size: 0.85rem;
    margin: 0;
  }
</style>
