<script lang="ts">
  /**
   * Die Einstellungen aller Apps — eine Ansicht, nicht drei.
   *
   * Die Werte selbst und warum sie geteilt sind: `einstellungen.svelte.ts`.
   * Hier steht nur die Bedienung dazu, mit Probe — ob ein Tempo passt und ob
   * ein Mikrofon taugt, hört man und liest man nicht ab.
   *
   * Was nur eine App angeht, kommt als `zugang` von außen herein: Der
   * Zugangstoken gehört zu „hören" und hat in „schreiben" nichts zu suchen
   * (Grundentscheidung 7).
   */
  import type { Snippet } from 'svelte';
  import Mikrofontest from './Mikrofontest.svelte';
  import PromptView from './PromptView.svelte';
  import { beiStimmenAenderung, sprich, stimmen, stimmeNachUri } from './speak';
  import {
    einstellungen,
    setzeAutoPegel,
    setzeMikrofon,
    setzeSchrift,
    setzeStimme,
    setzeTempo,
    setzeVerstaerkung,
    setzeZurueck,
    SCHRIFT_SPANNE,
    TEMPO_SPANNE,
  } from './einstellungen.svelte';

  let { zugang }: { zugang?: Snippet } = $props();

  const PROBE = 'Am Montag gehe ich zum Markt und kaufe frisches Brot.';

  let liste = $state(stimmen());
  let fehler = $state('');

  // Die Stimmenliste trifft auf manchen Systemen erst nach dem Laden ein.
  $effect(() => beiStimmenAenderung(() => (liste = stimmen())));

  // Über `liste`, damit die Anzeige nachzieht, wenn die Stimmen spät eintreffen.
  const gewaehlt = $derived(stimmeNachUri(einstellungen.stimmeUri, liste));

  async function probe() {
    fehler = '';
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

{#if liste.length === 0}
  <p class="gedaempft">
    Dieser Browser meldet keine deutsche Stimme. Das Vorsprechen bleibt dann aus; siehe
    <code>docs/betrieb.md</code>.
  </p>
{:else}
  <label>
    <span>Stimme</span>
    <select
      value={gewaehlt?.voiceURI}
      onchange={(ereignis) => setzeStimme(ereignis.currentTarget.value)}
    >
      {#each liste as stimme (stimme.voiceURI)}
        <option value={stimme.voiceURI}>{stimme.name} ({stimme.lang})</option>
      {/each}
    </select>
  </label>
  <p class="gedaempft">
    Welche Stimmen zur Wahl stehen und wie natürlich sie klingen, bestimmt das Betriebssystem,
    nicht diese App.
  </p>
{/if}

<label>
  <span>Sprechtempo — {einstellungen.tempo.toFixed(1)}×</span>
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

<h2>Anzeige</h2>

<label>
  <span>Schriftgröße der Vorlage — {einstellungen.schriftRem.toFixed(1)} rem</span>
  <input
    type="range"
    class="schieber"
    min={SCHRIFT_SPANNE.min}
    max={SCHRIFT_SPANNE.max}
    step={SCHRIFT_SPANNE.schritt}
    value={einstellungen.schriftRem}
    oninput={(ereignis) => setzeSchrift(Number(ereignis.currentTarget.value))}
  />
</label>

<div class="karte">
  <PromptView
    vorher={null}
    aktuell={{ id: 'probe', text: PROBE }}
    nachher={null}
    schriftRem={einstellungen.schriftRem}
  />
</div>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{@render zugang?.()}

<h2>Zurücksetzen</h2>
<p class="gedaempft">Setzt Mikrofon, Stimme, Tempo und Schriftgröße auf die Vorgaben zurück.</p>
<button class="knopf" onclick={setzeZurueck}>Auf Vorgaben zurücksetzen</button>

<style>
  /* Die globale Regel für `input` gibt Rahmen und Polster — beides steht
     einem Schieberegler schlecht. */
  .schieber {
    border: 0;
    padding: 0;
    max-width: 20rem;
  }
</style>
