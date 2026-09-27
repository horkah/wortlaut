<script lang="ts">
  /**
   * Der Zugang dieses Browsers - dieselbe Ansicht in jeder App.
   *
   * Es gibt einen Zugang je Browser, den alle Apps lesen (`zugang.ts`); wer
   * ihn hier einträgt, ist überall angemeldet. Der Rahmen hängt die Ansicht
   * ein (`Rahmen.svelte`); wohin es nach einem angenommenen Zugang geht, hängt
   * am Zugang: Ein Sprecher arbeitet weiter, wo er war, Verwaltung und Aufsicht
   * gehen zu den Sprechern.
   *
   * Der Menüpunkt steht immer da - ohne gültigen Zugang ist er der einzige Weg
   * herein. Aus demselben Grund lässt die PIN (`PinSchloss`, `pin.svelte.ts`)
   * jeden durch, dessen Zugang der Server nicht kennt.
   *
   * Ein Sprecher sieht zuerst nur, wessen Zugang hier liegt. Aufgeklappt lässt
   * er sich gegen einen Verwalter- oder Aufsichtstoken tauschen - der einzige
   * Weg in Verwaltung und Aufsicht; der persönliche Link holt ihn zurück.
   */
  import PinSchloss from './PinSchloss.svelte';
  import { SPRECHER_PFAD } from './apps';
  import { gehZu } from './route';
  import { ladeZugang, lage } from './lage.svelte';
  import { werRuft } from './wer';
  import { setzeZugang, zugang as gespeichert } from './zugang';

  let eingabe = $state(gespeichert());
  let meldung = $state('');
  let offen = $state(false);
  let angenommen = $state(false);
  // Nur für den Sprecherfall: Das Feld ist da, aber es drängt sich nicht auf.
  let wechseln = $state(false);

  // Speichern allein sagt noch nicht, ob der Zugang stimmt - darum eine echte
  // Anfrage hinterher. Ein falscher Token fällt sonst erst viel später auf.
  async function speichern() {
    setzeZugang(eingabe);
    meldung = 'Wird geprüft …';
    try {
      const wer = await werRuft();
      await ladeZugang();
      meldung =
        wer.art === 'sprecher'
          ? `Angenommen - dieser Browser gehört jetzt zu „${wer.name}“.`
          : wer.art === 'aufsicht'
            ? 'Angenommen - dieser Browser ist jetzt die Aufsicht.'
            : 'Token gespeichert, der Server nimmt ihn an.';
      angenommen = true;
    } catch (ursache) {
      angenommen = false;
      meldung =
        ursache instanceof Error && 'status' in ursache && ursache.status === 401
          ? 'Der Server weist diesen Zugang ab.'
          : `Prüfung nicht möglich: ${ursache instanceof Error ? ursache.message : ursache}`;
    }
  }
</script>

<h2>Zugangsdaten</h2>

{#snippet formular()}
  <div class="reihe">
    <input
      bind:value={eingabe}
      type={offen ? 'text' : 'password'}
      placeholder="Zugang oder Token"
      autocomplete="off"
      spellcheck="false"
      style="max-width:20rem"
    />
    <button class="knopf" onclick={() => (offen = !offen)}>
      {offen ? 'Verbergen' : 'Anzeigen'}
    </button>
    <button class="knopf haupt" onclick={speichern}>Speichern und prüfen</button>
  </div>
  {#if meldung}
    <p class="gedaempft">{meldung}</p>
  {/if}
  {#if angenommen}
    <!-- Der nächste Schritt, nicht der einzige Ausgang: Heraus käme man auch
         übers Menü. Die Sprecherliste liegt in „hören" - von dort ist es die
         Hash-Route, von anderswo dieselbe Adresse mit neuer Seite. -->
    {#if lage.art === 'sprecher'}
      <button class="knopf haupt" onclick={() => gehZu('/')}>Weiter</button>
    {:else}
      <button class="knopf haupt" onclick={() => (location.href = `/#${SPRECHER_PFAD}`)}>
        Weiter zu den Sprechern
      </button>
    {/if}
  {/if}
{/snippet}

<PinSchloss>
  {#if lage.art === 'sprecher'}
    <p>
      Dieser Browser hat den persönlichen Zugang von <strong>{lage.name}</strong>. Er kam über den
      Link, der einmal geöffnet wurde, und gilt weiter - hier ist nichts einzutragen.
    </p>
    <p class="gedaempft">
      Derselbe Zugang gilt in allen drei Apps: einmal geöffnet, überall angemeldet. Geht er
      verloren, gibt die Verwaltung einen neuen Link aus; der alte gilt dann nicht mehr.
    </p>

    <!-- Der Weg in die Verwaltung und in die Aufsicht führt über dasselbe
         Feld, und ohne ihn käme man von einem Sprechergerät nie dorthin. Er
         steht trotzdem hinter einem Klick: Wer hier aufnimmt, soll nicht als
         Erstes ein Token-Feld sehen.

         In **jeder** App, nicht nur in „hören": Es ist derselbe Browser und
         derselbe Zugang, und wo man ihn übergibt, hat mit dem Reiter nichts zu
         tun, auf dem man gerade steht. -->
    <h2>Diesen Browser übergeben</h2>
    {#if wechseln}
      <p class="gedaempft">
        Ein Browser trägt genau einen Zugang. Mit dem
        <code>WORTLAUT_AUTH_TOKEN</code> (Verwaltung) oder
        <code>WORTLAUT_ADMIN_TOKEN</code> (Aufsicht) gilt der von
        <strong>{lage.name}</strong> hier nicht mehr - der persönliche Link holt ihn zurück.
      </p>
      {@render formular()}
    {:else}
      <p class="gedaempft">
        Sichern, Umbenennen und Löschen brauchen den Verwalter- oder Aufsichtstoken. Danach steht
        die Sprecherliste in jeder App im Menü.
      </p>
      <button class="knopf" onclick={() => (wechseln = true)}>Zugang wechseln</button>
    {/if}
  {:else}
    <p class="gedaempft">
      Wer aufnehmen oder diktieren will, braucht hier nichts einzutragen - dafür gibt es den
      persönlichen Link. Er wird einmal geöffnet und gilt danach in allen drei Apps.
    </p>
    <p class="gedaempft">
      <strong>Verwaltung:</strong> der <code>WORTLAUT_AUTH_TOKEN</code> des Servers - Profile
      anlegen und persönliche Links ausgeben.
    </p>
    <p class="gedaempft">
      <strong>Aufsicht:</strong> der <code>WORTLAUT_ADMIN_TOKEN</code>, in dasselbe Feld - Einsicht
      in jeden Korpus, umbenennen, sichern, löschen.
    </p>
    {@render formular()}
  {/if}
</PinSchloss>
