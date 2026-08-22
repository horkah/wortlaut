<script lang="ts">
  /**
   * Der Zugang dieses Browsers — dieselbe Ansicht in jeder App.
   *
   * Sie steht hier und nicht in einer App, weil es nur **einen** Zugang gibt:
   * Beide Apps lesen denselben Eintrag desselben Browsers (siehe `zugang.ts`),
   * und wer ihn hier einträgt, ist damit auch drüben angemeldet. Zwei
   * Formulare für dasselbe Geheimnis wären zwei Gelegenheiten, es
   * auseinanderlaufen zu lassen.
   *
   * Was die Apps unterscheiden, kommt als Eigenschaft herein: „hören" nimmt in
   * dasselbe Feld auch Verwalter- und Aufsichtstoken (`verwaltet`), und jede
   * App weiß selbst, wohin es nach einem angenommenen Zugang weitergeht
   * (`weiter`).
   *
   * Der Menüpunkt dazu steht immer im Menü, gerade auch ohne gültigen Zugang:
   * Dann ist er der einzige Weg herein, und ein Menü, das ihn erst nach der
   * Anmeldung zeigte, hätte die Tür hinter das Schloss gelegt. Wer mit dem
   * Zugang eines Sprechers hier ist, findet die Seite ebenfalls, aber kein
   * Eingabefeld: Sein Zugang kam über einen Link und liegt schon in diesem
   * Browser; ein Feld daneben wäre nur ein Weg, ihn kaputtzumachen. Auskunft
   * ja, Gelegenheit nein.
   */
  import type { Snippet } from 'svelte';
  import { setzeZugang, zugang as gespeichert } from './zugang';

  let {
    art,
    name = null,
    verwaltet = false,
    pruefe,
    weiter,
  }: {
    /** Wer hier gerade ruft: `sprecher`, `verwaltung`, `aufsicht`, `keiner`, `unbekannt`. */
    art: string;
    /** Der Name des Sprechers, falls einer hier ist. */
    name?: string | null;
    /**
     * Ob diese App außer Sprecherzugängen auch Verwalter- und Aufsichtstoken
     * kennt. Nur „hören" verwaltet welche; in „schreiben" gäbe es dazu nichts
     * zu sagen, und der Server wiese sie ohnehin ab.
     */
    verwaltet?: boolean;
    /**
     * Beim Server nachfragen, wer jetzt ruft — wirft, wenn der Zugang nicht
     * gilt. Jede App reicht ihren eigenen Weg herein; die Antwort ist
     * dieselbe.
     */
    pruefe: () => Promise<{ art: string; name: string | null }>;
    /** Der nächste Schritt nach einem angenommenen Zugang. */
    weiter?: Snippet;
  } = $props();

  let eingabe = $state(gespeichert());
  let meldung = $state('');
  let offen = $state(false);
  let angenommen = $state(false);

  // Speichern allein sagt noch nicht, ob der Zugang stimmt — darum eine echte
  // Anfrage hinterher. Ein falscher Token fällt sonst erst viel später auf.
  async function speichern() {
    setzeZugang(eingabe);
    meldung = 'Wird geprüft …';
    try {
      const wer = await pruefe();
      meldung =
        wer.art === 'sprecher'
          ? `Angenommen — dieser Browser gehört jetzt zu „${wer.name}“.`
          : wer.art === 'aufsicht'
            ? 'Angenommen — dieser Browser ist jetzt die Aufsicht.'
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

{#if art === 'sprecher'}
  <p>
    Dieser Browser hat den persönlichen Zugang von <strong>{name}</strong>. Er kam über den Link,
    der einmal geöffnet wurde, und gilt weiter — hier ist nichts einzutragen.
  </p>
  <p class="gedaempft">
    Derselbe Zugang gilt in beiden Apps: einmal geöffnet, überall angemeldet. Geht er verloren,
    gibt die Verwaltung einen neuen Link aus; der alte gilt dann nicht mehr.
  </p>
{:else}
  <p class="gedaempft">
    Wer aufnehmen oder diktieren will, braucht hier nichts einzutragen — dafür gibt es den
    persönlichen Link. Er wird einmal geöffnet und gilt danach in beiden Apps.
  </p>
  {#if verwaltet}
    <p class="gedaempft">
      Für die Verwaltung: der <code>WORTLAUT_AUTH_TOKEN</code> des Servers. Er legt Profile an und
      gibt die persönlichen Links aus. Der Wert bleibt in diesem Browser und wird beim
      Zurücksetzen unter „Einstellungen" nicht angetastet.
    </p>
    <p class="gedaempft">
      Für die <strong>Aufsicht</strong>: der <code>WORTLAUT_ADMIN_TOKEN</code>, in dasselbe Feld.
      Sie sieht in jeden Korpus, benennt um, sichert und löscht. Dieser Browser gehört danach der
      Aufsicht — ein Sprecher, der ihn vorher benutzt hat, öffnet einmal wieder seinen
      persönlichen Link.
    </p>
  {/if}
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
{/if}
