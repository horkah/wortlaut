<script lang="ts">
  /**
   * Farben, Schriftart und Schriftgrößen — eine eigene Ansicht neben
   * `Einstellungen.svelte`.
   *
   * Warum getrennt: siehe `DARSTELLUNG_PFAD` in `apps.ts`. Die Werte selbst,
   * ihre Vorgaben und wie sie auf die App wirken, stehen in
   * `einstellungen.svelte.ts`; hier steht nur die Bedienung dazu.
   */
  import PromptView from './PromptView.svelte';
  import {
    einstellungen,
    setzeDarstellungZurueck,
    setzeFarbe,
    setzeGrundschrift,
    setzeSchrift,
    setzeSchriftart,
    FARBEN,
    GRUNDSCHRIFT_SPANNE,
    SCHRIFT_SPANNE,
    SCHRIFTARTEN,
  } from './einstellungen.svelte';

  const PROBE = 'Am Montag gehe ich zum Markt und kaufe frisches Brot.';
</script>

<h2>Farben</h2>
<p class="gedaempft">
  Wirkt sofort und in jeder App — dieser Browser merkt sich die Wahl, wie bei Mikrofon und Stimme
  auch.
</p>

{#each FARBEN as farbe (farbe.schluessel)}
  <label class="farbe">
    <span>{farbe.name}</span>
    <div class="reihe">
      <input
        type="color"
        value={einstellungen.farben[farbe.schluessel]}
        oninput={(ereignis) => setzeFarbe(farbe.schluessel, ereignis.currentTarget.value)}
      />
      <input
        type="text"
        class="hex"
        value={einstellungen.farben[farbe.schluessel]}
        spellcheck="false"
        onchange={(ereignis) => setzeFarbe(farbe.schluessel, ereignis.currentTarget.value)}
      />
    </div>
  </label>
{/each}

<h2>Schriftart</h2>
<label>
  <span>Schriftart der Oberfläche</span>
  <select
    value={einstellungen.schriftart}
    onchange={(ereignis) => setzeSchriftart(ereignis.currentTarget.value)}
  >
    {#each SCHRIFTARTEN as schriftart (schriftart.wert)}
      <option value={schriftart.wert}>{schriftart.name}</option>
    {/each}
  </select>
</label>

<h2>Schriftgröße</h2>
<label>
  <span>Grundschriftgröße der Oberfläche — {einstellungen.grundschriftPx} px</span>
  <input
    type="range"
    class="schieber"
    min={GRUNDSCHRIFT_SPANNE.min}
    max={GRUNDSCHRIFT_SPANNE.max}
    step={GRUNDSCHRIFT_SPANNE.schritt}
    value={einstellungen.grundschriftPx}
    oninput={(ereignis) => setzeGrundschrift(Number(ereignis.currentTarget.value))}
  />
</label>
<p class="gedaempft">Betrifft Knöpfe, Beschriftungen und Fließtext — alles außer der Vorlage unten.</p>

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
<p class="gedaempft">
  Der Satz, der beim Sprechen und beim Diktieren groß in der Mitte steht (siehe „hören" und
  „schreiben").
</p>

<div class="karte">
  <PromptView vorher={null} aktuell={{ id: 'probe', text: PROBE }} nachher={null} schriftRem={einstellungen.schriftRem} />
</div>

<h2>Zurücksetzen</h2>
<p class="gedaempft">Setzt Farben, Schriftart und Schriftgrößen auf die Vorgaben zurück.</p>
<button class="knopf" onclick={setzeDarstellungZurueck}>Auf Vorgaben zurücksetzen</button>

<style>
  .schieber {
    border: 0;
    padding: 0;
    max-width: 20rem;
  }

  /* Farbfeld und Hex-Eingabe nebeneinander, nicht als eigene `label`-Zeile:
     Beides steuert denselben Wert, nur das eine per Auge, das andere für den,
     der den Code schon kennt. */
  .farbe .reihe {
    align-items: center;
  }

  input[type='color'] {
    width: 3rem;
    padding: 0.15rem;
  }

  .hex {
    max-width: 8rem;
    font-family: monospace;
  }
</style>
