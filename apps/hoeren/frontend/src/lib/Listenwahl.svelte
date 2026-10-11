<script lang="ts">
  /**
   * Wie die Aufnahmenliste in „Meine Daten" steht: sortiert, gefiltert, wie
   * viele je Seite.
   *
   * Zugeklappt eine Zeile, die sagt, was gilt; aufgeklappt Chips je Gruppe.
   * Ein Chip der Sortierung trägt einen Pfeil für die Richtung - ein zweites
   * Tippen auf den gewählten kehrt sie um.
   *
   * **Die Arten** sind überschneidungsfrei, jede Aufnahme gehört zu genau
   * einer; jede ist für sich an- und abwählbar, mit ihrer Zahl. Arten ohne
   * Aufnahme stehen nicht da.
   */
  import {
    VORGABE_ARTEN,
    type Aufnahmeart,
    type Aufnahmenseite,
    type Listenwahl,
    type Quellenwahl,
  } from './api';

  let {
    wahl = $bindable(),
    proSeite = $bindable(),
    quellen,
    arten,
    gesamt,
    aendere,
  }: {
    wahl: Listenwahl;
    proSeite: number;
    quellen: Quellenwahl[];
    arten: Aufnahmenseite['arten'];
    gesamt: number;
    /** Nach jeder Änderung - die Liste lädt neu. */
    aendere: () => void;
  } = $props();

  const GROESSEN = [10, 20, 50, 100];
  const SORTIERUNGEN: { schluessel: Listenwahl['sortierung']; name: string }[] = [
    { schluessel: 'geaendert', name: 'Geändert' },
    { schluessel: 'aufgenommen', name: 'Aufgenommen' },
    { schluessel: 'qualitaet', name: 'Qualität' },
  ];
  const NAMEN: Record<Aufnahmeart, string> = {
    gelesen: 'Gelesen',
    nachgesprochen: 'Nachgesprochen',
    frei: 'Frei',
    korrektur_geprueft: 'Korrektur, geprüft',
    korrektur_ungeprueft: 'Korrektur, ungeprüft',
    verworfen: 'Verworfen',
  };

  let offen = $state(false);

  const pfeil = (richtung: Listenwahl['richtung']) => (richtung === 'ab' ? '↓' : '↑');
  const sortname = $derived(SORTIERUNGEN.find((s) => s.schluessel === wahl.sortierung)?.name ?? '');
  const sichtbar = $derived(arten.filter((eintrag) => eintrag.anzahl > 0));
  const vorgabe = (gewaehlt: Aufnahmeart[]) =>
    gewaehlt.length === VORGABE_ARTEN.length && VORGABE_ARTEN.every((art) => gewaehlt.includes(art));
  const gefiltert = $derived(wahl.quelle !== '' || !vorgabe(wahl.arten));

  /** Eine Art an oder ab. */
  function schalte(art: Aufnahmeart) {
    const an = wahl.arten.includes(art);
    filtere({ arten: an ? wahl.arten.filter((a) => a !== art) : [...wahl.arten, art] });
  }

  /** Eine Sortierung wählen - die gewählte noch einmal kehrt die Richtung um. */
  function sortiere(schluessel: Listenwahl['sortierung']) {
    wahl =
      wahl.sortierung === schluessel
        ? { ...wahl, richtung: wahl.richtung === 'ab' ? 'auf' : 'ab' }
        : { ...wahl, sortierung: schluessel, richtung: 'ab' };
    aendere();
  }

  function filtere(neu: Partial<Listenwahl>) {
    wahl = { ...wahl, ...neu };
    aendere();
  }

  function groesse(anzahl: number) {
    proSeite = anzahl;
    aendere();
  }
</script>

<div class="listenwahl">
  <button
    class="kopf"
    aria-expanded={offen}
    aria-label="Sortieren, filtern, Aufnahmen je Seite"
    onclick={() => (offen = !offen)}
  >
    <svg viewBox="0 0 16 16" aria-hidden="true" class="trichter" class:aktiv={gefiltert}
      ><path d="M1.5 2.5h13l-5 6v4.5l-3 1.5v-6z" /></svg
    >
    <span>{gesamt}</span>
    <span class="gedaempft">·</span>
    <span>{sortname} {pfeil(wahl.richtung)}</span>
    <span class="gedaempft">· {proSeite}/Seite</span>
    <svg viewBox="0 0 16 16" aria-hidden="true" class="winkel" class:offen
      ><path d="M4 6l4 4 4-4" /></svg
    >
  </button>

  {#if offen}
    <div class="feld">
      <div class="gruppe">
        <span class="marke">Sortieren</span>
        <div class="chips">
          {#each SORTIERUNGEN as sortierung (sortierung.schluessel)}
            {@const gewaehlt = wahl.sortierung === sortierung.schluessel}
            <button
              class="chip"
              class:gewaehlt
              aria-pressed={gewaehlt}
              title={gewaehlt ? 'Noch einmal tippen kehrt die Richtung um' : undefined}
              onclick={() => sortiere(sortierung.schluessel)}
            >
              {sortierung.name}{#if gewaehlt}<span class="pfeil">{pfeil(wahl.richtung)}</span
                >{/if}
            </button>
          {/each}
        </div>
      </div>

      <div class="gruppe">
        <span class="marke">Art</span>
        <div class="chips">
          {#each sichtbar as eintrag (eintrag.art)}
            {@const an = wahl.arten.includes(eintrag.art)}
            <button
              class="chip"
              class:gewaehlt={an}
              aria-pressed={an}
              onclick={() => schalte(eintrag.art)}
              >{NAMEN[eintrag.art]}<span class="anzahl">{eintrag.anzahl}</span></button
            >
          {/each}
        </div>
      </div>

      <div class="gruppe">
        <span class="marke">Quelle</span>
        <select
          value={wahl.quelle}
          onchange={(ereignis) => filtere({ quelle: ereignis.currentTarget.value })}
        >
          <option value="">Alle</option>
          {#each quellen as quelle (quelle.id)}
            <option value={quelle.id}>{quelle.titel}</option>
          {/each}
        </select>
      </div>

      <div class="gruppe">
        <span class="marke">Je Seite</span>
        <div class="chips">
          {#each GROESSEN as anzahl (anzahl)}
            <button
              class="chip"
              class:gewaehlt={proSeite === anzahl}
              aria-pressed={proSeite === anzahl}
              onclick={() => groesse(anzahl)}>{anzahl}</button
            >
          {/each}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .listenwahl {
    margin: 0 0 0.75rem;
  }

  .kopf {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.7rem;
    border: 1px solid var(--rand);
    border-radius: 999px;
    background: #fff;
    font: inherit;
    font-size: 0.85rem;
    color: var(--text);
    cursor: pointer;
  }
  .kopf:hover,
  .kopf:focus-visible {
    border-color: var(--akzent);
  }

  svg {
    width: 0.9rem;
    height: 0.9rem;
    flex: none;
  }
  .trichter {
    fill: none;
    stroke: var(--gedaempft);
    stroke-width: 1.4;
    stroke-linejoin: round;
  }
  .trichter.aktiv {
    fill: var(--akzent);
    stroke: var(--akzent);
  }
  .winkel {
    fill: none;
    stroke: var(--gedaempft);
    stroke-width: 1.6;
    stroke-linecap: round;
    transition: transform 0.15s ease;
  }
  .winkel.offen {
    transform: rotate(180deg);
  }

  .feld {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.5rem 0.9rem;
    align-items: center;
    margin-top: 0.5rem;
    padding: 0.75rem 0.9rem;
    border: 1px solid var(--rand);
    border-radius: 0.6rem;
    background: #fff;
  }
  .gruppe {
    display: contents;
  }
  .marke {
    font-size: 0.8rem;
    color: var(--gedaempft);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.65rem;
    border: 1px solid var(--rand);
    border-radius: 999px;
    background: var(--hintergrund);
    font: inherit;
    font-size: 0.85rem;
    color: var(--text);
    cursor: pointer;
  }
  .chip:hover,
  .chip:focus-visible {
    border-color: var(--akzent);
  }
  .chip.gewaehlt {
    background: var(--akzent);
    border-color: var(--akzent);
    color: #fff;
  }
  .pfeil {
    font-weight: bold;
  }
  .anzahl {
    font-size: 0.75rem;
    opacity: 0.7;
    font-variant-numeric: tabular-nums;
  }

  select {
    justify-self: start;
    max-width: 100%;
    margin: 0;
    font-size: 0.85rem;
  }

  @media (max-width: 480px) {
    .feld {
      grid-template-columns: 1fr;
      gap: 0.25rem;
    }
    .marke {
      margin-top: 0.35rem;
    }
  }
</style>
