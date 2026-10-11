<script lang="ts">
  /**
   * Die Aufteilung der Aufnahmen auf die Faltungen der Kreuzvalidierung
   * (`docs/lernen.md`). Die Aufnahmen selbst stehen unter „Meine Daten".
   */
  import { erklaert } from '$ui/erklaerung';
  import { fehlertext } from '$ui/api';
  import { onMount } from 'svelte';
  import { MEINE_DATEN_PFAD } from '$ui/apps';
  import { aufteilung as ladeAufteilung, type Aufteilung } from '../lib/api';

  let daten = $state<Aufteilung | null>(null);
  let fehler = $state('');

  const faltungen = $derived(daten?.faltungen ?? 6);
  const jeFaltung = $derived(
    Object.entries(daten?.je_faltung ?? {})
      .map(([nummer, anzahl]) => ({ nummer: Number(nummer), anzahl }))
      .sort((a, b) => a.nummer - b.nummer),
  );
  const groesste = $derived(Math.max(1, ...jeFaltung.map((f) => f.anzahl)));

  function minuten(sekunden: number): string {
    const m = Math.round(sekunden / 60);
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
  }

  onMount(async () => {
    try {
      daten = await ladeAufteilung();
    } catch (ursache) {
      fehler = fehlertext(ursache);
    }
  });
</script>

<h2
  use:erklaert={'Ausgeliefert wird das Mittel der Faltungsmodelle, ohne die, die schiefgingen. Es hat gelernt, woran die Faltungen gemessen wurden; seine Zahl ist die der Kreuzvalidierung. Ein unabhängiger Test fehlt: Die Zahl gilt für diesen Korpus, nicht für die nächste Aufnahme.'}
>
  Aufteilung
</h2>

{#if fehler}
  <p class="fehler">{fehler}</p>
{:else if !daten}
  <p class="gedaempft">Wird geladen …</p>
{:else}
  <div class="karte">
    <h3
      use:erklaert={`Jede Aufnahme liegt fest in einer von ${faltungen} Faltungen. Ein Lauf trainiert ${faltungen}-mal, jeweils auf den übrigen Faltungen, und misst an der zurückgehaltenen. So hört jedes Modell nur Aufnahmen, die es nicht kannte - das ist die Zahl in „Modelle“.`}
    >
      {faltungen} Faltungen
    </h3>

    {#if daten.aufnahmen > 0}
      <div class="faltungen" aria-hidden="true">
        {#each jeFaltung as faltung (faltung.nummer)}
          <div class="faltung">
            <div class="saeule">
              <div class="fuellung" style="height: {(faltung.anzahl / groesste) * 100}%"></div>
            </div>
            <span class="klein">{faltung.nummer + 1}</span>
            <span class="gedaempft klein">{faltung.anzahl}</span>
          </div>
        {/each}
      </div>
      <p class="gedaempft klein">
        {daten.aufnahmen} Aufnahmen, {minuten(daten.sekunden)} Sprache ·
        <a href="/#{MEINE_DATEN_PFAD}">Meine Daten</a>
      </p>
    {/if}

    {#if !daten.genug}
      <p class="hinweise">
        Zu wenige Aufnahmen: {daten.aufnahmen} für {faltungen} Faltungen.
      </p>
    {/if}
  </div>
{/if}

<style>
  h3 {
    margin: 0 0 0.6rem;
    font-size: 1rem;
  }

  p {
    margin: 0 0 0.7rem;
    line-height: 1.55;
  }

  p:last-child {
    margin-bottom: 0;
  }

  .klein {
    font-size: 0.85rem;
  }

  /* Eine Säule je Faltung - kein Diagramm, nur ein Blick darauf, ob die
     Faltungen gleich schwer sind. */
  .faltungen {
    display: flex;
    align-items: flex-end;
    gap: 0.5rem;
    margin: 1rem 0 0.6rem;
    height: 5rem;
  }

  .faltung {
    display: flex;
    flex: 1;
    flex-direction: column;
    align-items: center;
    gap: 0.15rem;
    height: 100%;
  }

  .saeule {
    display: flex;
    flex: 1;
    align-items: flex-end;
    width: 100%;
    min-height: 0;
  }

  .fuellung {
    width: 100%;
    min-height: 2px;
    background: var(--akzent);
    border-radius: 0.2rem 0.2rem 0 0;
  }

  .hinweise {
    margin: 0.9rem 0 0.7rem;
  }
</style>
