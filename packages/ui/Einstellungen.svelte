<script lang="ts">
  /**
   * Die Einstellungen aller Apps - eine Ansicht, nicht drei.
   *
   * Die Werte selbst und warum sie geteilt sind: `einstellungen.svelte.ts`.
   * Hier steht nur die Bedienung dazu, mit Probe - ob ein Tempo passt und ob
   * ein Mikrofon taugt, hört man und liest man nicht ab.
   *
   * Farben, Schriftart und Schriftgrößen stehen nicht hier, sondern in
   * `Darstellung.svelte`, einem eigenen Menüpunkt (siehe `DARSTELLUNG_PFAD`
   * in `apps.ts`): Mikrofon und Stimme misst man einmal ein, die Darstellung
   * darf jeder anfassen, ohne durch Technisches zu blättern. Aus demselben
   * Grund steht der Zugang dieses Browsers ebenfalls nicht hier, sondern unter
   * `ZUGANGSDATEN_PFAD`.
   */
  import Mikrofontest from './Mikrofontest.svelte';
  import {
    beiStimmenAenderung,
    istServestimme,
    SERVE_PRAEFIX,
    serveSchluessel,
    spieleVor,
    sprich,
    stimmen,
    stimmeNachUri,
    type Servestimme,
  } from './speak';
  import {
    einstellungen,
    setzeAutoPegel,
    setzeMikrofon,
    setzeStimme,
    setzeTempo,
    setzeVerstaerkung,
    setzeZurueck,
    TEMPO_SPANNE,
  } from './einstellungen.svelte';

  const PROBE = 'Am Montag gehe ich zum Markt und kaufe frisches Brot.';

  /**
   * Stimmen, die der **Server** sprechen kann - von der App hereingereicht.
   *
   * Diese Ansicht liegt in `packages/ui` und wird von allen drei Apps benutzt;
   * die Servestimmen gibt es aber nur, wo es Vorlagen gibt („hören"). Sie hier
   * selbst zu holen hieße, dass diese Datei einen Endpunkt kennt, den zwei der
   * drei Apps nicht haben. Ohne Eigenschaft bleibt alles, wie es war.
   */
  let {
    servestimmen = [],
    probeHolen,
  }: {
    servestimmen?: Servestimme[];
    probeHolen?: (schluessel: string) => Promise<Blob>;
  } = $props();

  let liste = $state(stimmen());
  let fehler = $state('');

  // Die Stimmenliste trifft auf manchen Systemen erst nach dem Laden ein.
  $effect(() => beiStimmenAenderung(() => (liste = stimmen())));

  // Über `liste`, damit die Anzeige nachzieht, wenn die Stimmen spät eintreffen.
  const gewaehlt = $derived(stimmeNachUri(einstellungen.stimmeUri, liste));
  const serveGewaehlt = $derived(
    istServestimme(einstellungen.stimmeUri)
      ? servestimmen.find((s) => SERVE_PRAEFIX + s.schluessel === einstellungen.stimmeUri)
      : undefined,
  );
  // Der Wert des Auswahlfelds: eine Servestimme trägt ihr Präfix, eine
  // Browserstimme ihre `voiceURI`.
  const wert = $derived(
    istServestimme(einstellungen.stimmeUri) ? einstellungen.stimmeUri : gewaehlt?.voiceURI,
  );

  async function probe() {
    fehler = '';
    if (serveGewaehlt && probeHolen) {
      let url: string | null = null;
      try {
        url = URL.createObjectURL(await probeHolen(serveGewaehlt.schluessel));
        await spieleVor(url, einstellungen.tempo);
        return;
      } catch {
        fehler = 'Diese Stimme spricht gerade nicht - der Browser übernimmt.';
      } finally {
        if (url) URL.revokeObjectURL(url);
      }
    }
    try {
      await sprich(PROBE, { stimme: gewaehlt, tempo: einstellungen.tempo });
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }
</script>

<h2>Mikrofon</h2>

<Mikrofontest
  geraeteId={einstellungen.mikrofonId}
  verstaerkung={einstellungen.verstaerkung}
  autoPegel={einstellungen.autoPegel}
  ongeraet={setzeMikrofon}
  onverstaerkung={setzeVerstaerkung}
  onautoPegel={setzeAutoPegel}
/>

<h2>Vorlesen</h2>

{#if liste.length === 0 && servestimmen.length === 0}
  <p class="gedaempft">
    Dieser Browser meldet keine deutsche Stimme, und auf dem Server liegt keine. Das Vorsprechen
    bleibt dann aus; siehe <code>docs/betrieb.md</code>.
  </p>
{:else}
  <label>
    <span>Stimme</span>
    <select value={wert} onchange={(ereignis) => setzeStimme(ereignis.currentTarget.value)}>
      {#if servestimmen.length}
        <optgroup label="Vom Server - überall gleich">
          {#each servestimmen as stimme (stimme.schluessel)}
            <option value={SERVE_PRAEFIX + stimme.schluessel}>{stimme.name}</option>
          {/each}
        </optgroup>
      {/if}
      {#if liste.length}
        <optgroup label="Von diesem Gerät">
          {#each liste as stimme (stimme.voiceURI)}
            <option value={stimme.voiceURI}>{stimme.name} ({stimme.lang})</option>
          {/each}
        </optgroup>
      {/if}
    </select>
  </label>
  {#if serveGewaehlt}
    <p class="gedaempft">
      {serveGewaehlt.erklaerung} Diese Stimme kommt vom Server: Sie klingt auf jedem Gerät gleich -
      unter Linux wie auf dem Telefon.
    </p>
  {:else}
    <p class="gedaempft">
      Welche Gerätestimmen zur Wahl stehen und wie natürlich sie klingen, bestimmt das
      Betriebssystem, nicht diese App.
      {#if servestimmen.length}
        Die Stimmen vom Server klingen überall gleich.
      {/if}
    </p>
  {/if}
{/if}

<label>
  <span>Sprechtempo - {einstellungen.tempo.toFixed(1)}×</span>
  <input
    type="range"
    class="schieber"
    min={TEMPO_SPANNE.min}
    max={TEMPO_SPANNE.max}
    step={TEMPO_SPANNE.schritt}
    value={einstellungen.tempo}
    oninput={(ereignis) => setzeTempo(Number(ereignis.currentTarget.value))}
  />
</label>
<p class="gedaempft">Langsamer ist leichter nachzusprechen, aber ermüdet über eine lange Sitzung.</p>

<div class="reihe">
  <button class="knopf" onclick={probe} disabled={liste.length === 0}>▶ Probe hören</button>
</div>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

<h2>Zurücksetzen</h2>
<p class="gedaempft">Setzt Mikrofon, Stimme und Tempo auf die Vorgaben zurück.</p>
<button class="knopf" onclick={setzeZurueck}>Auf Vorgaben zurücksetzen</button>

<style>
  /* Die globale Regel für `input` gibt Rahmen und Polster - beides steht
     einem Schieberegler schlecht. */
  .schieber {
    border: 0;
    padding: 0;
    max-width: 20rem;
  }
</style>
