<script lang="ts">
  /**
   * Ein unverändertes Whisper-Modell: was es ist, was davon hier liegt, und
   * wie es diesem Menschen zuhört.
   *
   * Das Gegenstück zur Einzelansicht eines Laufs (`Lauf.svelte`) und so weit
   * wie möglich wie sie gebaut - Steckbrief oben, Zahlen darunter. Nur hat ein
   * Grundmodell keinen Auftrag, keine Kurven und kein Protokoll; dafür zwei
   * Steckbriefe: die Modellkarte von OpenAI und das, was der Modellcache
   * dieser Maschine über die geladene Fassung sagt (`api/modelle.grundmodell`).
   *
   * **Die Zahlen sind die der Modelltabelle**, aus derselben Rechnung und über
   * dieselben Aufnahmen. Wo ein anderes Modell freigegeben ist, steht es
   * daneben: Die Frage vor einem Grundmodell ist meist, ob es das eigene
   * schlägt - nicht umgekehrt wie beim Lauf, der sich gegen seine Baseline misst.
   */
  import { fehlertext } from '$ui/api';
  import { ANZEIGE_GEBIET } from '$ui/sprache';
  import { zeitpunkt } from '$ui/zeit';
  import { MODELLE_PFAD } from '$ui/apps';
  import {
    grundmodell as ladeGrundmodell,
    type Grundmodelleinzeln,
    type Mass,
    type Modell,
  } from '../lib/api';
  import { gehZu, grundmodellAusRoute, lage, LAUF_ROUTE } from '../lib/zustand.svelte';

  // Der Name steht in der Adresse (`GRUNDMODELL_ROUTE`) - wie beim Lauf.
  const name = $derived(grundmodellAusRoute(lage.route));

  let daten = $state<Grundmodelleinzeln | null>(null);
  let fehler = $state('');

  const modell = $derived(daten?.modell ?? null);
  const freigabe = $derived(daten?.freigabe ?? null);
  const gemessen = $derived(Object.keys(modell?.werte ?? {}).length > 0);

  $effect(() => {
    const gewuenscht = name;
    if (!gewuenscht) return;
    daten = null;
    fehler = '';
    ladeGrundmodell(gewuenscht)
      .then((antwort) => {
        if (gewuenscht === name) daten = antwort;
      })
      .catch((ursache) => {
        fehler = fehlertext(ursache);
      });
  });

  function wert(zeile: Modell | null, mass: string): number | null {
    return zeile?.werte[mass] ?? null;
  }

  function zahl(roh: number | null, mass: Mass): string {
    if (roh === null) return '–';
    return (
      roh.toLocaleString(ANZEIGE_GEBIET, {
        minimumFractionDigits: mass.stellen,
        maximumFractionDigits: mass.stellen,
      }) + mass.einheit
    );
  }

  /**
   * Um wie viel dieses Modell vom freigegebenen abweicht - in Prozentpunkten
   * bei der Genauigkeit, sonst relativ. Vorzeichen wie gemessen; ob das
   * besser ist, sagt `besser`.
   */
  function abstand(mass: Mass, dieses: number | null, frei: number | null): string {
    if (dieses === null || frei === null) return '';
    if (mass.schluessel === 'genauigkeit') {
      const punkte = dieses - frei;
      return `${punkte >= 0 ? '+' : ''}${punkte.toFixed(1)} Pp.`;
    }
    if (!frei) return '';
    const anteil = ((dieses - frei) / frei) * 100;
    return `${anteil >= 0 ? '+' : ''}${anteil.toFixed(0)} %`;
  }

  function besser(mass: Mass, dieses: number | null, frei: number | null): boolean | null {
    if (dieses === null || frei === null || dieses === frei) return null;
    return mass.hoch_ist_gut ? dieses > frei : dieses < frei;
  }
</script>

<p class="zurueck">
  <a href="#{MODELLE_PFAD}" onclick={() => gehZu(MODELLE_PFAD)}>← Modelle</a>
</p>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{#if !daten}
  {#if !fehler}<p class="gedaempft">Wird geladen …</p>{/if}
{:else}
  <div class="kopfzeile">
    <h2>
      <code class="kennung">Grundmodell</code>
      <span class="optionscode">{daten.titel}</span>
    </h2>
    {#if daten.freigegeben}
      <span class="abzeichen">freigegeben</span>
    {/if}
  </div>
  {#if daten.erklaerung}
    <p class="gedaempft">{daten.erklaerung}</p>
  {/if}

  <!-- Zwei Steckbriefe wie der eine beim Lauf: erst, was das Modell ist,
       dann, was davon hier liegt. Beschriftet vom Server. -->
  {#if daten.steckbrief.length}
    <details class="steckbrief">
      <summary>Steckbrief des Modells</summary>
      <dl>
        {#each daten.steckbrief as feld (feld.begriff)}
          <dt>{feld.begriff}</dt>
          <dd>
            {feld.art === 'zeit' ? zeitpunkt(feld.wert) : feld.wert}
            {#if feld.hinweis}<span class="gedaempft klein">{feld.hinweis}</span>{/if}
          </dd>
        {/each}
      </dl>
    </details>
  {/if}

  <details class="steckbrief">
    <summary>Auf dieser Maschine</summary>
    <dl>
      {#each daten.vor_ort as feld (feld.begriff)}
        <dt>{feld.begriff}</dt>
        <dd>
          {feld.art === 'zeit' ? zeitpunkt(feld.wert) : feld.wert}
          {#if feld.hinweis}<span class="gedaempft klein">{feld.hinweis}</span>{/if}
        </dd>
      {/each}
    </dl>
  </details>

  {#if gemessen && modell}
    <h3>Auf den Aufnahmen dieses Menschen</h3>
    <p class="gedaempft">
      Dieselben Zahlen wie in der Modelltabelle, über dieselben Aufnahmen. Ein Grundmodell hat
      keine davon gelernt - jede ist für es neu.
      {#if freigabe}
        Daneben das freigegebene Modell,
        {#if freigabe.job_id}
          <a class="optionscode" href="#{LAUF_ROUTE}{freigabe.job_id}">{freigabe.name}</a>.
        {:else}
          {freigabe.name}.
        {/if}
      {/if}
    </p>

    <table class="vergleich">
      <thead>
        <tr>
          <th scope="col">Maß</th>
          <th scope="col">Dieses Modell</th>
          {#if freigabe}
            <th scope="col">Freigegeben</th>
            <th scope="col">Abstand</th>
          {/if}
        </tr>
      </thead>
      <tbody>
        {#each daten.masse as mass (mass.schluessel)}
          {@const dieses = wert(modell, mass.schluessel)}
          {@const frei = wert(freigabe, mass.schluessel)}
          {#if dieses !== null}
            <tr>
              <th scope="row" title={mass.erklaerung}>{mass.name}</th>
              <td class="stark">{zahl(dieses, mass)}</td>
              {#if freigabe}
                <td>{zahl(frei, mass)}</td>
                <td
                  class:besser={besser(mass, dieses, frei) === true}
                  class:schlechter={besser(mass, dieses, frei) === false}
                >
                  {abstand(mass, dieses, frei)}
                </td>
              {/if}
            </tr>
          {/if}
        {/each}
      </tbody>
    </table>
    <p class="gedaempft klein">
      Über {modell.aufnahmen}
      {modell.aufnahmen === 1 ? 'Aufnahme' : 'Aufnahmen'}{#if !daten.vergleichbar}
        - noch kein gemeinsamer Boden mit den anderen Modellen{/if}.
    </p>

    <p class="gedaempft">
      Hervorgehoben heißt: Hier ist dieses Grundmodell besser als das freigegebene. Die Rechenzeit gilt für
      das Rechenwerk oben im Steckbrief.
    </p>
  {:else}
    <p class="hinweise">
      Auf diesen Aufnahmen hat {daten.titel} noch nichts gemessen. In „hören" unter
      „Auswertung" läuft es über den Korpus - danach stehen hier seine Zahlen.
    </p>
  {/if}
{/if}

<style>
  .optionscode {
    font-family: ui-monospace, Menlo, Consolas, monospace;
  }

  .kopfzeile {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .kennung {
    font-size: 0.6em;
    padding: 0.05em 0.35em;
    margin-right: 0.35em;
    border: 1px solid var(--rand);
    border-radius: 3px;
    color: var(--gedaempft);
    vertical-align: middle;
  }

  .abzeichen {
    padding: 0.05rem 0.45rem;
    border-radius: 0.25rem;
    background: var(--akzent);
    color: #fff;
    font-size: 0.72rem;
    font-weight: 600;
    white-space: nowrap;
  }

  .steckbrief {
    margin: 0 0 1rem;
    border: 1px solid var(--rand);
    border-radius: 4px;
    padding: 0.4rem 0.8rem;
  }

  .steckbrief summary {
    cursor: pointer;
    font-weight: 600;
  }

  .steckbrief dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.25rem 1rem;
    margin: 0.6rem 0 0.2rem;
  }

  .steckbrief dt {
    color: var(--gedaempft);
  }

  .steckbrief dd {
    margin: 0;
  }

  .steckbrief dd .klein {
    display: block;
  }

  @media (max-width: 40rem) {
    .steckbrief dl {
      grid-template-columns: 1fr;
    }

    .steckbrief dt {
      margin-top: 0.4rem;
    }
  }

  .zurueck {
    margin: 0 0 0.4rem;
    font-size: 0.9rem;
  }

  .vergleich {
    border-collapse: collapse;
    width: auto;
    min-width: min(100%, 26rem);
    margin: 0.3rem 0 0.2rem;
  }

  .vergleich th,
  .vergleich td {
    padding: 0.3rem 0.9rem 0.3rem 0;
    text-align: right;
    border-bottom: 1px solid var(--rand);
    font-variant-numeric: tabular-nums;
  }

  .vergleich thead th {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--gedaempft);
  }

  .vergleich tbody th {
    text-align: left;
    font-weight: 400;
  }

  .vergleich .stark {
    font-weight: 600;
  }

  /* Farbe allein trägt die Auskunft nicht: Das Vorzeichen steht im Text. */
  .besser {
    color: var(--akzent);
    font-weight: 600;
  }

  .schlechter {
    color: var(--fehler);
  }

  .klein {
    font-size: 0.85rem;
    margin: 0.1rem 0 0.6rem;
  }
</style>
