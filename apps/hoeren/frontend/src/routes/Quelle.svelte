<script lang="ts">
  /**
   * Textquelle wählen: entweder ein Thema, aus dem ein LLM Text erzeugt, oder
   * ein hochgeladener Text. Beides wird zu Sprecheinheiten geschnitten und
   * hinten an die Warteschlange gehängt.
   */
  import {
    quelleAusDatei,
    quelleAusLLM,
    quelleLoeschen,
    quelleText,
    quelleUmstellen,
    quellen,
    type Quelle,
  } from '../lib/api';
  import { gehZu } from '../lib/zustand.svelte';

  let liste = $state<Quelle[]>([]);
  let fehler = $state('');
  let laeuft = $state(false);

  let thema = $state('');
  let altersspanne = $state('Erwachsene');
  let umfang = $state(300);
  let datei = $state<FileList | null>(null);

  async function lade() {
    liste = await quellen();
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
    fuehreAus(() => quelleAusLLM({ thema, altersspanne, umfang }));
  };

  const ausDatei = (ereignis: SubmitEvent) => {
    ereignis.preventDefault();
    const gewaehlt = datei?.[0];
    if (gewaehlt) fuehreAus(() => quelleAusDatei(gewaehlt));
  };

  const stelleUm = (quelle: Quelle) =>
    fuehreAus(() => quelleUmstellen(quelle.id, !quelle.aktiv));

  function loesche(quelle: Quelle) {
    // Gewarnt wird vorher, nicht hinterher: Die Einheiten sind fort, und bei
    // einer erzeugten Quelle kostet ein neuer Anlauf wieder Rechenzeit.
    const sicher = confirm(
      `„${quelle.titel}“ mit ${quelle.einheiten} Einheiten löschen?\n\n` +
        'Das lässt sich nicht rückgängig machen. Soll die Quelle nur aus der ' +
        'Warteschlange verschwinden, stelle sie stattdessen ab.',
    );
    if (sicher) fuehreAus(() => quelleLoeschen(quelle.id));
  }

  async function zeigeText(quelle: Quelle) {
    // Das Fenster muss vor dem `await` aufgehen: Danach gilt es dem Browser
    // nicht mehr als Folge des Klicks und wird als Popup abgefangen.
    const tab = window.open('', '_blank');
    try {
      const text = await quelleText(quelle.id);
      const adresse = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
      if (tab) tab.location.href = adresse;
      else window.open(adresse, '_blank'); // doch abgefangen: zweiter Versuch
      // Erst freigeben, wenn der Tab sie geladen hat.
      setTimeout(() => URL.revokeObjectURL(adresse), 60_000);
    } catch (ursache) {
      tab?.close();
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

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
  <div class="karte zeile" class:still={!quelle.aktiv}>
    <button
      class="feld schalter"
      role="switch"
      aria-checked={quelle.aktiv}
      aria-label={quelle.aktiv ? 'Quelle abstellen' : 'Quelle wieder aufnehmen'}
      title={quelle.aktiv
        ? 'Aktiv — abstellen nimmt die Einheiten aus der Warteschlange'
        : 'Abgestellt — wieder aufnehmen stellt die Einheiten zurück'}
      disabled={laeuft}
      onclick={() => stelleUm(quelle)}
    >
      <!-- Ein- und Ausschalter: das übliche Zeichen, gefüllt wenn an. -->
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" aria-hidden="true">
        <path d="M12 3.5v8" />
        <path d="M7 6.6a7.5 7.5 0 1 0 10 0" />
      </svg>
    </button>

    <div class="mitte">
      <button class="titel" title="Text in einem neuen Tab ansehen" onclick={() => zeigeText(quelle)}>
        {quelle.titel}
      </button>
      <div class="gedaempft">
        {quelle.art} · {quelle.einheiten} Einheiten · {quelle.erstellt}
        {#if !quelle.aktiv}· abgestellt{/if}
      </div>
    </div>

    <button
      class="feld loeschen"
      aria-label="Quelle löschen"
      title="Quelle löschen"
      disabled={laeuft}
      onclick={() => loesche(quelle)}
    >
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M4 7h16M10 4h4M6 7l1 13h10l1-13M10 11v6M14 11v6" />
      </svg>
    </button>
  </div>
{:else}
  <p class="gedaempft">Noch keine Quelle.</p>
{/each}

{#if liste.length > 0}
  <button class="knopf haupt" onclick={() => gehZu('/aufnahme')}>Zur Aufnahme</button>
{/if}

<style>
  /* Schalter — Titel — Löschen. Die Mitte nimmt den Platz, die beiden Felder
     behalten ihre Größe, auch wenn der Titel lang ist. */
  .zeile {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .mitte {
    flex: 1;
    min-width: 0; /* sonst sprengt ein langer Titel die Zeile */
  }

  /* Beide Felder gleich groß und quadratisch: 2,75rem sind bei üblicher
     Grundschrift 44 px — das Maß, das ein Finger sicher trifft. */
  .feld {
    flex: none;
    display: grid;
    place-items: center;
    width: 2.75rem;
    height: 2.75rem;
    padding: 0;
    border: 1px solid var(--rand);
    border-radius: 0.5rem;
    background: none;
    color: var(--gedaempft);
    cursor: pointer;
  }

  .feld:disabled {
    opacity: 0.5;
    cursor: default;
  }

  /* Eingeschaltet ist der Normalfall und darf ruhig zu sehen sein. */
  .schalter[aria-checked='true'] {
    border-color: var(--akzent);
    background: var(--akzent-hell);
    color: var(--akzent);
  }

  /* Dieselbe Farbe wie `.fehler` in der gemeinsamen app.css. */
  .loeschen:hover:not(:disabled) {
    border-color: var(--fehler);
    color: var(--fehler);
  }

  /* Der Titel ist der Weg zum Text — als Knopf, damit der Token mitgeht,
     aber wie ein Verweis anzusehen. */
  .titel {
    display: block;
    max-width: 100%;
    padding: 0;
    border: 0;
    background: none;
    font: inherit;
    font-weight: 600;
    text-align: left;
    color: var(--akzent);
    text-decoration: underline;
    text-underline-offset: 0.15em;
    cursor: pointer;
    overflow-wrap: anywhere;
  }

  /* Abgestellt: sichtbar, aber erkennbar außer Dienst. */
  .still {
    opacity: 0.6;
  }
</style>
