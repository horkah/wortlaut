<script lang="ts">
  /**
   * Läufe beauftragen und ihnen zusehen.
   *
   * **Warum vier Knöpfe und keine Formularseite.** Es gibt genau vier Läufe:
   * zwei Methoden mal zwei Datensätze. Alles andere steht fest - das
   * Grundmodell, die Aufteilung, die Zahlen des Rezepts. Eine Seite voller
   * Felder täuschte eine Freiheit vor, die es nicht gibt, und jede
   * Einstellmöglichkeit wäre eine, deren Wirkung später niemand mehr
   * zuzuordnen weiß.
   *
   * **Warum die Liste im Takt nachfragt.** Ein Training dauert Stunden. Der
   * Balken soll währenddessen wachsen, ohne dass jemand neu lädt - und er soll
   * es auch dann, wenn der Auftrag in einem anderen Reiter angestoßen wurde.
   * Im Ruhezustand bleibt ein langsamer Takt: Läuft nichts, ist nichts zu
   * sehen.
   */
  import { onMount } from 'svelte';
  import {
    beauftrage as beauftrageLauf,
    brichAb,
    laeufe as ladeLaeufe,
    type Lauf,
    type Laufliste,
  } from '../lib/api';
  import { LAUF_ROUTE, gehZu } from '../lib/zustand.svelte';

  // Während gerechnet wird, soll der Balken mitwachsen - aber ein Takt von
  // einer Sekunde brächte nichts: Ein Trainingsschritt dauert länger.
  const TAKT_LAEUFT = 3000;
  const TAKT_RUHT = 20000;

  let daten = $state<Laufliste | null>(null);
  let fehler = $state('');
  let bestellt = $state('');

  let methode = $state('lora');
  let datensatz = $state('original');

  const laeufe = $derived(daten?.laeufe ?? []);
  const arbeitet = $derived(laeufe.some((lauf) => lauf.status === 'laeuft'));
  const wartend = $derived(laeufe.filter((lauf) => lauf.status === 'wartet').length);

  /**
   * Welche der vier Kombinationen schon gelaufen sind. Nicht, um sie zu
   * sperren - ein zweiter Lauf derselben Art ist ein gutes Recht, etwa nach
   * fünfzig neuen Aufnahmen -, sondern um zu zeigen, was noch fehlt: Die
   * Frage dieser App ist der Vergleich der vier, und der ist erst mit allen
   * vieren zu haben.
   */
  const gerechnet = $derived(
    new Set(
      laeufe
        .filter((lauf) => lauf.status === 'fertig')
        .map((lauf) => `${lauf.methode}/${lauf.daten}`),
    ),
  );

  const STUFEN: Record<string, string> = {
    vorbereiten: 'wird vorbereitet',
    laden: 'Modell wird geladen',
    training: 'trainiert',
    sichern: 'wird gesichert',
    umwandeln: 'wird umgewandelt',
    bewerten: 'wird an den Testaufnahmen gemessen',
  };

  const STATUS: Record<string, string> = {
    wartet: 'wartet auf den Trainer',
    laeuft: 'läuft',
    fertig: 'fertig',
    gescheitert: 'gescheitert',
    abgebrochen: 'zurückgenommen',
  };

  function bezeichnung(lauf: Lauf): string {
    const m = daten?.methoden.find((wahl) => wahl.schluessel === lauf.methode);
    const d = daten?.datensaetze.find((wahl) => wahl.schluessel === lauf.daten);
    return `${m?.name ?? lauf.methode} · ${d?.name ?? lauf.daten}`;
  }

  function zeit(roh: string): string {
    if (!roh) return '';
    const wann = new Date(roh);
    return Number.isNaN(wann.getTime()) ? roh : wann.toLocaleString('de-DE');
  }

  async function hole() {
    try {
      daten = await ladeLaeufe();
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function bestelle() {
    bestellt = 'laeuft';
    try {
      await beauftrageLauf(methode, datensatz);
      await hole();
      fehler = '';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      bestellt = '';
    }
  }

  async function nimmZurueck(jobId: string) {
    try {
      await brichAb(jobId);
      await hole();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  onMount(() => {
    let uhr: ReturnType<typeof setTimeout>;
    let beendet = false;

    // Ein sich selbst neu stellender Wecker statt eines festen Intervalls: So
    // hängt der Takt am Zustand, und zwei Abfragen können sich nicht
    // überholen, wenn der Server einmal länger braucht.
    async function takt() {
      await hole();
      if (beendet) return;
      uhr = setTimeout(takt, arbeitet || wartend ? TAKT_LAEUFT : TAKT_RUHT);
    }

    takt();
    return () => {
      beendet = true;
      clearTimeout(uhr);
    };
  });
</script>

<h2>Training</h2>
<p class="gedaempft">
  Aus den Aufnahmen von „hören" ein Modell für diese eine Stimme. Trainiert wird auf
  {daten?.basismodell ?? 'whisper-small'} - fest, denn nur so ist das Ergebnis mit der Grundlinie
  aus der Auswertung vergleichbar.
</p>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

<div class="karte bestellung">
  {#if daten && !daten.bereit}
    <p>{daten.hinweis}</p>
  {:else if daten}
    <div class="wahlen">
      <fieldset>
        <legend>Wie trainiert wird</legend>
        {#each daten.methoden as wahl (wahl.schluessel)}
          <label class="option">
            <input type="radio" bind:group={methode} value={wahl.schluessel} />
            <span>
              <strong>{wahl.name}</strong>
              <span class="gedaempft">{wahl.erklaerung}</span>
            </span>
          </label>
        {/each}
      </fieldset>

      <fieldset>
        <legend>Womit</legend>
        {#each daten.datensaetze as wahl (wahl.schluessel)}
          <label class="option">
            <input type="radio" bind:group={datensatz} value={wahl.schluessel} />
            <span>
              <strong>{wahl.name}</strong>
              <span class="gedaempft">{wahl.erklaerung}</span>
            </span>
          </label>
        {/each}
      </fieldset>
    </div>

    <div class="reihe">
      <button class="knopf haupt" onclick={bestelle} disabled={bestellt === 'laeuft'}>
        Training beauftragen
      </button>
      <span class="gedaempft">
        {#if gerechnet.has(`${methode}/${datensatz}`)}
          Diese Kombination ist schon gerechnet - ein zweiter Lauf nimmt die seither
          hinzugekommenen Aufnahmen mit.
        {:else}
          Der Lauf rechnet auf der Karte und dauert; er wartet, bis der Trainer Zeit hat.
        {/if}
      </span>
    </div>

    <!-- Vier Felder, und man sieht auf einen Blick, welche noch fehlen: Die
         Frage dieser App ist der Vergleich der vier. -->
    <div class="matrix" aria-hidden="true">
      {#each daten.methoden as m (m.schluessel)}
        {#each daten.datensaetze as d (d.schluessel)}
          <span class="feld" class:da={gerechnet.has(`${m.schluessel}/${d.schluessel}`)}>
            {m.name} · {d.name}
          </span>
        {/each}
      {/each}
    </div>
  {:else}
    <p class="gedaempft">Wird geladen …</p>
  {/if}
</div>

{#if laeufe.length}
  <h3>Läufe</h3>
  <div class="laeufe">
    {#each laeufe as lauf (lauf.job_id)}
      <div class="karte lauf" class:offen={lauf.status === 'laeuft'}>
        <div class="kopfzeile">
          <p class="marke">{bezeichnung(lauf)}</p>
          <span class="zustand {lauf.status}">{STATUS[lauf.status] ?? lauf.status}</span>
        </div>

        <p class="gedaempft klein">
          {zeit(lauf.erstellt)} · {lauf.aufnahmen} Aufnahmen ·
          {lauf.zeilen.train ?? 0} Proben zum Lernen,
          {lauf.zeilen.test ?? 0} zum Prüfen
        </p>

        {#if lauf.status === 'laeuft'}
          <!-- Der Balken bleibt leer, solange der Trainer die Schrittzahl nicht
               genannt hat: Ein Balken, der bei null steht und nicht weiß, wovon,
               ist eine Behauptung. Die Stufe daneben sagt, dass es vorangeht. -->
          <div class="balken" aria-hidden="true">
            <div class="fuellung" style="width: {(lauf.anteil ?? 0) * 100}%"></div>
          </div>
          <p class="klein">
            {STUFEN[lauf.stufe] ?? lauf.stufe}
            {#if lauf.anteil !== null}
              <span class="gedaempft">· {(lauf.anteil * 100).toFixed(0)} %</span>
            {/if}
          </p>
        {/if}

        {#if lauf.fehler}
          <p class="hinweise">{lauf.fehler}</p>
        {/if}

        <div class="reihe">
          <a class="knopf" href="#{LAUF_ROUTE}{lauf.job_id}">
            {lauf.status === 'fertig' ? 'Ergebnis ansehen' : 'Kurven ansehen'}
          </a>
          {#if lauf.status === 'wartet'}
            <button class="knopf" onclick={() => nimmZurueck(lauf.job_id)}>
              Zurücknehmen
            </button>
            <span class="gedaempft klein">
              Solange niemand rechnet, lässt sich der Auftrag zurückziehen.
            </span>
          {/if}
        </div>
      </div>
    {/each}
  </div>
{/if}

<style>
  .bestellung {
    margin-bottom: 1.4rem;
  }

  .wahlen {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem 2rem;
    margin-bottom: 0.8rem;
  }

  fieldset {
    border: none;
    padding: 0;
    margin: 0;
    min-width: min(100%, 18rem);
    flex: 1;
  }

  legend {
    padding: 0;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--gedaempft);
    margin-bottom: 0.4rem;
  }

  /* Die Begründung steht unter dem Namen und nicht in einem Tooltip: Was die
     Wahl bedeutet, soll lesen können, wer sie trifft. */
  .option {
    display: flex;
    align-items: flex-start;
    gap: 0.6rem;
    margin: 0 0 0.5rem;
    cursor: pointer;
  }

  .option span {
    display: block;
    margin: 0;
  }

  .option .gedaempft {
    font-size: 0.85rem;
    line-height: 1.4;
  }

  .matrix {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.9rem;
  }

  .feld {
    padding: 0.25rem 0.6rem;
    border: 1px dashed var(--rand);
    border-radius: 0.3rem;
    font-size: 0.8rem;
    color: var(--gedaempft);
  }

  .feld.da {
    border-style: solid;
    border-color: var(--akzent);
    color: var(--akzent);
    font-weight: 600;
  }

  .laeufe {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }

  .lauf.offen {
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

  .zustand {
    font-size: 0.85rem;
    color: var(--gedaempft);
  }

  .zustand.gescheitert {
    color: var(--fehler);
    font-weight: 600;
  }

  .zustand.fertig {
    color: var(--akzent);
    font-weight: 600;
  }

  .klein {
    font-size: 0.85rem;
    margin: 0.3rem 0;
  }

  .balken {
    height: 0.5rem;
    margin: 0.6rem 0 0.2rem;
    border-radius: 0.25rem;
    background: var(--rand);
    overflow: hidden;
  }

  .fuellung {
    height: 100%;
    background: var(--akzent);
    transition: width 0.4s ease;
  }
</style>
