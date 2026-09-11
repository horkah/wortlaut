<script lang="ts">
  /**
   * Die Klammer um eine Ansicht, die hinter der PIN liegt - „Darstellung" und
   * „Zugangsdaten" benutzen sie, „Meine Daten" hat ihre eigene, ältere Form
   * desselben Gedankens (siehe dort).
   *
   * Sie steht **in** den beiden Ansichten und nicht an ihren Aufrufstellen:
   * „Zugangsdaten" wird von jeder App einzeln eingehängt, und eine App, die
   * die Klammer vergisst, hätte ein Schloss, das nur die halbe Tür schließt.
   *
   * Solange die Auskunft aussteht, steht hier nichts: Ein kurz aufblitzendes
   * Formular, das gleich wieder verschwindet, sähe aus wie ein Fehler.
   */
  import type { Snippet } from 'svelte';
  import { entsperre, frageSchloss, gueltigePin, schloss } from './pin.svelte';

  let { children }: { children: Snippet } = $props();

  let eingabe = $state('');
  let fehler = $state('');
  let laeuft = $state(false);

  frageSchloss();

  async function absenden(ereignis: SubmitEvent) {
    ereignis.preventDefault();
    fehler = '';

    if (!gueltigePin(eingabe)) {
      fehler = 'Die PIN muss aus genau 4 Ziffern bestehen.';
      return;
    }

    laeuft = true;
    try {
      if (await entsperre(eingabe)) eingabe = '';
      else fehler = 'Falsche PIN.';
    } catch (ursache) {
      fehler = `Prüfung nicht möglich: ${ursache instanceof Error ? ursache.message : ursache}`;
    } finally {
      laeuft = false;
    }
  }
</script>

{#if schloss.stand === 'zu'}
  <h2>Gesperrt</h2>
  <div class="karte">
    <p>Diese Seite ist mit derselben PIN gesichert wie „Meine Daten“.</p>
    <p class="gedaempft">Geben Sie Ihre vierstellige PIN ein (4 Ziffern).</p>
    <form class="reihe" onsubmit={absenden}>
      <!-- `pattern` als Ausdruck, nicht als Text: In einer Vorlage ist `{4}`
           eine Einsetzung, `pattern="[0-9]{4}"` käme als `[0-9]4` beim Browser
           an - und der wiese dann jede richtige PIN ab, ohne dass `onsubmit`
           je liefe. Dieselbe Falle wie in `MeineDaten.svelte`. -->
      <input
        bind:value={eingabe}
        type="text"
        inputmode="numeric"
        pattern={'[0-9]{4}'}
        maxlength="4"
        placeholder="z.B. 1234"
        title="Genau 4 Ziffern (0-9)"
        autocomplete="off"
        required
      />
      <button class="knopf haupt" type="submit" disabled={laeuft}>Entsperren</button>
    </form>
    {#if fehler}<p class="fehler">{fehler}</p>{/if}
  </div>
  <p class="gedaempft">
    Vergeben wird die PIN unter „Meine Daten“. Wer sie vergessen hat, lässt sie von der Aufsicht
    zurücksetzen.
  </p>
{:else if schloss.stand !== 'unbekannt'}
  {@render children()}
{/if}
