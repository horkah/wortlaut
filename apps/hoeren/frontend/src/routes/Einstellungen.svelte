<script lang="ts">
  /**
   * Die gemeinsamen Geräteeinstellungen, dazu der Zugang zu dieser Instanz.
   *
   * Mikrofon, Stimme und Schrift stehen in `$ui/Einstellungen.svelte` — sie
   * gelten für alle Apps. Hier kommt nur hinzu, was allein diese App angeht:
   * der Zugang. Wer mit dem Zugang eines Sprechers hier ist, sieht ihn nicht.
   * Er hat nichts einzutragen — sein Zugang kam über einen Link und liegt
   * schon in diesem Browser; ein Feld daneben wäre nur ein Weg, ihn
   * kaputtzumachen. „schreiben" bekommt ihn aus demselben Grund nicht zu sehen
   * (Grundentscheidung 7).
   *
   * Dasselbe Feld nimmt den Verwalter- **und** den Aufsichtstoken: Der Server
   * sieht am Vorgelegten, welches von beidem es ist (backend/deps.py). Deshalb
   * wird die Aufsicht aus jedem Browser erreichbar, in dem jemand ihren Token
   * einträgt — es gibt keine zweite Adresse und keine zweite Anmeldung.
   */
  import Gemeinsam from '$ui/Einstellungen.svelte';
  import { SPRECHER_PFAD } from '$ui/apps';
  // `zugang` heißt hier anders: Der Name gehört schon dem Snippet, das die
  // gemeinsame Ansicht erwartet.
  import { ApiFehler, setzeZugang, werRuft, zugang as gespeichert } from '../lib/api';
  import { gehZu, ladeZugang, zustand } from '../lib/zustand.svelte';

  let tokenEingabe = $state(gespeichert());
  let zugangMeldung = $state('');
  let zugangOffen = $state(false);
  let angenommen = $state(false);

  // Speichern allein sagt noch nicht, ob der Token stimmt — darum eine echte
  // Anfrage hinterher. Ein falscher Token fällt sonst erst viel später auf.
  async function tokenSpeichern() {
    setzeZugang(tokenEingabe);
    zugangMeldung = 'Wird geprüft …';
    try {
      const wer = await werRuft();
      zugangMeldung =
        wer.art === 'sprecher'
          ? `Angenommen — dieser Browser gehört jetzt zu „${wer.name}“.`
          : wer.art === 'aufsicht'
            ? 'Angenommen — dieser Browser ist jetzt die Aufsicht.'
            : 'Token gespeichert, der Server nimmt ihn an.';
      angenommen = true;
      await ladeZugang();
    } catch (ursache) {
      angenommen = false;
      zugangMeldung =
        ursache instanceof ApiFehler && ursache.status === 401
          ? 'Der Server weist diesen Zugang ab.'
          : `Prüfung nicht möglich: ${ursache instanceof Error ? ursache.message : ursache}`;
    }
  }
</script>

<Gemeinsam>
  {#snippet zugang()}
    {#if zustand.art !== 'sprecher'}
      <h2>Zugang</h2>
      <p class="gedaempft">
        Für die Verwaltung: der <code>WORTLAUT_AUTH_TOKEN</code> des Servers. Er legt Profile an
        und gibt die persönlichen Links aus. Wer aufnehmen will, braucht hier nichts — dafür gibt
        es den Link. Der Wert bleibt in diesem Browser und wird beim Zurücksetzen unten nicht
        angetastet.
      </p>
      <p class="gedaempft">
        Für die <strong>Aufsicht</strong>: der <code>WORTLAUT_ADMIN_TOKEN</code>, in dasselbe
        Feld. Sie sieht in jeden Korpus, benennt um, sichert und löscht. Dieser Browser gehört
        danach der Aufsicht — ein Sprecher, der ihn vorher benutzt hat, öffnet einmal wieder
        seinen persönlichen Link.
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
        <!-- Der nächste Schritt, nicht der einzige Ausgang: Wer wegen des
             Tokens hergeschickt wurde, will jetzt zu den Sprechern. Heraus
             käme er auch übers Menü. -->
        <button class="knopf haupt" onclick={() => gehZu(SPRECHER_PFAD)}>
          Weiter zu den Sprechern
        </button>
      {/if}
    {/if}
  {/snippet}
</Gemeinsam>
