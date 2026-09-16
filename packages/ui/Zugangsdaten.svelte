<script lang="ts">
  /**
   * Der Zugang dieses Browsers - dieselbe Ansicht in jeder App.
   *
   * Sie steht hier und nicht in einer App, weil es nur **einen** Zugang gibt:
   * Alle drei Apps lesen denselben Eintrag desselben Browsers (siehe
   * `zugang.ts`), und wer ihn hier einträgt, ist damit auch in den anderen
   * angemeldet. Zwei Formulare für dasselbe Geheimnis wären zwei
   * Gelegenheiten, es auseinanderlaufen zu lassen.
   *
   * **Und deshalb ist die Übergabe hier nicht mehr an eine App gebunden.** Bis
   * September 2026 zeigte nur „hören" den Abschnitt „Diesen Browser
   * übergeben"; ein Schalter `verwaltet` gab ihn frei, mit der Begründung, nur
   * dort gebe es etwas zu verwalten. Das verwechselte zwei Dinge: *Wo* die
   * Verwaltung arbeitet, und *wo* man sich als Verwaltung ausweist. Wer in
   * „lernen" oder „schreiben" saß, kam an das Feld gar nicht heran - er musste
   * erst wissen, dass es in einer dritten App steht. Ein Zugang, der überall
   * gilt, wird überall eingetragen; wohin es danach geht, sagt das Menü
   * (`uebergreifendePunkte` in `apps.ts`).
   *
   * Was die Apps noch unterscheidet, kommt als Eigenschaft herein: jede weiß
   * selbst, wohin es nach einem angenommenen Zugang weitergeht (`weiter`).
   *
   * Der Menüpunkt dazu steht immer im Menü, gerade auch ohne gültigen Zugang:
   * Dann ist er der einzige Weg herein, und ein Menü, das ihn erst nach der
   * Anmeldung zeigte, hätte die Tür hinter das Schloss gelegt. Aus demselben
   * Grund lässt die PIN vor dieser Ansicht (`PinSchloss`) jeden durch, dessen
   * Zugang der Server nicht kennt: Ohne Sprecher gibt es keine PIN, nach der
   * zu fragen wäre, und das Feld hier wäre sonst hinter sich selbst
   * verschlossen (siehe `pin.svelte.ts`).
   *
   * Wer mit dem Zugang eines Sprechers hier ist, sieht zuerst nur, wessen
   * Zugang in diesem Browser liegt - kein Feld, in das er nichts einzutragen
   * hat und an dem er seinen Zugang nur kaputtmachen könnte. Zugeklappt ist
   * aber nicht verschlossen: Ein Browser trägt genau **einen** Zugang, und ihn
   * gegen den Verwalter- oder Aufsichtstoken zu tauschen, ist der einzige Weg
   * in die Verwaltung und in die Aufsicht. Wer diesen Rechner gerade zum
   * Sichern, Umbenennen oder Löschen benutzen will, klappt das Feld hier auf.
   * Der persönliche Zugang kommt danach mit einem Klick auf den Link zurück.
   */
  import type { Snippet } from 'svelte';
  import PinSchloss from './PinSchloss.svelte';
  import { werRuft } from './wer';
  import { setzeZugang, zugang as gespeichert } from './zugang';

  let {
    art,
    name = null,
    neuLaden,
    weiter,
  }: {
    /** Wer hier gerade ruft: `sprecher`, `verwaltung`, `aufsicht`, `keiner`, `unbekannt`. */
    art: string;
    /** Der Name des Sprechers, falls einer hier ist. */
    name?: string | null;
    /**
     * Den Zugangsstand dieser App neu einlesen, nachdem ein Token angenommen
     * wurde: Wer die Seite gerade sieht, ist danach jemand anderes.
     *
     * Gefragt, **wer** ruft, wird nicht mehr von hier aus: Das tut `werRuft`
     * für alle drei gleich (`wer.ts`). Diese Ansicht bekam die Frage einmal
     * als Eigenschaft herein, und jede App reichte dieselben vier Zeilen
     * hinein - bis auf „schreiben", das dabei seine eigene API fragte und
     * einen gültigen Aufsichtstoken abwies.
     */
    neuLaden: () => Promise<void>;
    /** Der nächste Schritt nach einem angenommenen Zugang. */
    weiter?: Snippet;
  } = $props();

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
      await neuLaden();
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
  {#if angenommen && weiter}
    <!-- Der nächste Schritt, nicht der einzige Ausgang: Heraus käme man auch
         übers Menü. -->
    {@render weiter()}
  {/if}
{/snippet}

<PinSchloss>
  {#if art === 'sprecher'}
    <p>
      Dieser Browser hat den persönlichen Zugang von <strong>{name}</strong>. Er kam über den Link,
      der einmal geöffnet wurde, und gilt weiter - hier ist nichts einzutragen.
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
        <strong>{name}</strong> hier nicht mehr - der persönliche Link holt ihn zurück.
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
