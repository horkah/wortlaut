<script lang="ts">
  /**
   * Warnungen und Fehler von Webdienst und Trainer der letzten sieben Tage -
   * der Menüpunkt „Fehlerprotokoll".
   *
   * Geschrieben wird es in `wortlaut/fehlerlog.py`, gelesen über
   * `GET /api/fehlerlog` in „hören". Sehen dürfen es Aufsicht, Verwaltung und
   * wer den Trainerschlüssel im Browser hat; er geht als eigener Kopf mit.
   * Älteres als eine Woche verwirft der Server.
   *
   * Jüngstes oben. Eine Ausnahme samt Stapel steht eingeklappt unter ihrer
   * Zeile - wer sie braucht, klappt sie auf.
   */
  import { api } from './api';
  import { mitSchluessel } from './schluessel.svelte';
  import { zeitpunkt } from './zeit';

  interface Eintrag {
    zeit: string;
    stufe: string;
    dienst: string;
    quelle: string;
    text: string;
    ausnahme: string;
  }

  const hoeren = api('/api');

  const DIENSTE: Record<string, string> = {
    app: 'Webdienst',
    trainer: 'Läufer',
    training: 'Training',
  };

  let eintraege = $state<Eintrag[]>([]);
  let tage = $state(7);
  let fehler = $state('');
  let laedt = $state(false);
  let nurFehler = $state(false);

  const gezeigt = $derived(nurFehler ? eintraege.filter((e) => e.stufe === 'fehler') : eintraege);
  const anzahlFehler = $derived(eintraege.filter((e) => e.stufe === 'fehler').length);

  async function hole() {
    laedt = true;
    try {
      const antwort = await hoeren.anfrage<{ eintraege: Eintrag[]; tage: number }>(
        '/fehlerlog',
        { headers: mitSchluessel(['trainer']) },
      );
      eintraege = antwort.eintraege;
      tage = antwort.tage;
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      laedt = false;
    }
  }

  hole();
</script>

<div class="kopf">
  <h2>Fehlerprotokoll</h2>
  <button class="knopf" onclick={hole} disabled={laedt}>Neu laden</button>
</div>

<p class="gedaempft">
  Warnungen und Fehler von Webdienst, Läufer und Training der letzten {tage} Tage, das jüngste
  zuerst. Älteres wird verworfen.
</p>

{#if fehler}
  <p class="fehler">{fehler}</p>
{:else if !eintraege.length}
  <p class="gedaempft">{laedt ? 'Wird geladen …' : `Keine Warnungen und Fehler seit ${tage} Tagen.`}</p>
{:else}
  <div class="leiste">
    <span class="gedaempft klein">
      {eintraege.length}
      {eintraege.length === 1 ? 'Eintrag' : 'Einträge'}, davon {anzahlFehler} Fehler
    </span>
    <label class="schalter">
      <input type="checkbox" bind:checked={nurFehler} />
      <span>Nur Fehler</span>
    </label>
  </div>

  <ul class="liste">
    {#each gezeigt as eintrag, stelle (stelle)}
      <li class:fehlerzeile={eintrag.stufe === 'fehler'}>
        <div class="zeile">
          <span class="stufe">{eintrag.stufe === 'fehler' ? 'Fehler' : 'Warnung'}</span>
          <span class="zeit">{zeitpunkt(eintrag.zeit)}</span>
          <span class="gedaempft klein">{DIENSTE[eintrag.dienst] ?? eintrag.dienst} · {eintrag.quelle}</span>
        </div>
        <p class="text">{eintrag.text}</p>
        {#if eintrag.ausnahme}
          <details>
            <summary class="klein">Ausnahme</summary>
            <pre>{eintrag.ausnahme}</pre>
          </details>
        {/if}
      </li>
    {/each}
  </ul>
{/if}

<style>
  .kopf {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.25rem 1rem;
    margin: 0 0 0.75rem;
  }

  .kopf h2 {
    margin: 0;
  }

  .leiste {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
    margin: 0 0 0.5rem;
  }

  .schalter {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin: 0;
  }

  .schalter input {
    width: auto;
    margin: 0;
  }

  .liste {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .liste li {
    border-top: 1px solid var(--rand);
    padding: 0.5rem 0;
  }

  .zeile {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.25rem 0.75rem;
  }

  .stufe {
    font-weight: 600;
    font-size: 0.85rem;
    color: var(--warnung);
  }

  .fehlerzeile .stufe {
    color: var(--fehler);
  }

  .zeit {
    font-variant-numeric: tabular-nums;
    font-size: 0.9rem;
  }

  .text {
    margin: 0.2rem 0 0;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  }

  pre {
    margin: 0.3rem 0 0;
    padding: 0.5rem;
    overflow-x: auto;
    font-size: 0.8rem;
    background: var(--akzent-hell);
    border-radius: 4px;
  }
</style>
