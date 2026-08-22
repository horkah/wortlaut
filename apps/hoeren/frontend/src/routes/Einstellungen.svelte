<script lang="ts">
  /**
   * Die gemeinsamen Geräteeinstellungen, dazu der Zugang zu „hören".
   *
   * Mikrofon, Stimme und Schrift stehen in `$ui/Einstellungen.svelte` — sie
   * gelten für alle Apps. Hier kommt nur hinzu, was allein diese App angeht:
   * der Zugangstoken. „schreiben" bekommt ihn bewusst nicht zu sehen
   * (Grundentscheidung 7).
   */
  import Gemeinsam from '$ui/Einstellungen.svelte';
  import { SPRECHER_PFAD } from '$ui/apps';
  import { ApiFehler, setzeToken, sprecherListe, token } from '../lib/api';
  import { gehZu } from '../lib/zustand.svelte';

  let tokenEingabe = $state(token());
  let zugangMeldung = $state('');
  let zugangOffen = $state(false);
  let angenommen = $state(false);

  // Speichern allein sagt noch nicht, ob der Token stimmt — darum eine echte
  // Anfrage hinterher. Ein falscher Token fällt sonst erst viel später auf.
  async function tokenSpeichern() {
    setzeToken(tokenEingabe);
    zugangMeldung = 'Wird geprüft …';
    try {
      await sprecherListe();
      zugangMeldung = 'Token gespeichert, der Server nimmt ihn an.';
      angenommen = true;
    } catch (ursache) {
      angenommen = false;
      zugangMeldung =
        ursache instanceof ApiFehler && ursache.status === 401
          ? 'Der Server weist diesen Token ab.'
          : `Prüfung nicht möglich: ${ursache instanceof Error ? ursache.message : ursache}`;
    }
  }
</script>

<Gemeinsam>
  {#snippet zugang()}
    <h2>Zugang</h2>
    <p class="gedaempft">
      Nur nötig, wenn der Server mit <code>WORTLAUT_AUTH_TOKEN</code> läuft. Der Token bleibt in
      diesem Browser und wird beim Zurücksetzen unten nicht angetastet.
    </p>
    <div class="reihe">
      <input
        bind:value={tokenEingabe}
        type={zugangOffen ? 'text' : 'password'}
        placeholder="Token"
        autocomplete="off"
        spellcheck="false"
        style="max-width:20rem"
      />
      <button class="knopf" onclick={() => (zugangOffen = !zugangOffen)}>
        {zugangOffen ? 'Verbergen' : 'Anzeigen'}
      </button>
      <button class="knopf haupt" onclick={tokenSpeichern}>Speichern und prüfen</button>
    </div>
    {#if zugangMeldung}
      <p class="gedaempft">{zugangMeldung}</p>
    {/if}
    {#if angenommen}
      <!-- Ohne gewählten Sprecher steht keine Reiterreihe da, über die man
           zurückfände. Wer wegen des Tokens hergeschickt wurde, kommt hier
           wieder heraus. -->
      <button class="knopf haupt" onclick={() => gehZu(SPRECHER_PFAD)}>
        Weiter zu den Sprechern
      </button>
    {/if}
  {/snippet}
</Gemeinsam>
