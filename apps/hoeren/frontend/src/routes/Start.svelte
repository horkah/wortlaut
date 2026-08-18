<script lang="ts">
  /** Sprecher wählen oder anlegen — und, falls nötig, den Zugangstoken setzen. */
  import { ApiFehler, setzeToken, sprecherAnlegen, sprecherListe, token, type Sprecher } from '../lib/api';
  import { gehZu, waehleSprecher, zustand } from '../lib/zustand.svelte';

  let sprecher = $state<Sprecher[]>([]);
  let fehler = $state('');
  // Der Zugang steht sonst unter „Einstellungen". Hier taucht er nur auf, wenn
  // der Server ihn verlangt — ohne Sprecher ist jene Ansicht nicht erreichbar.
  let zugangNoetig = $state(false);
  let tokenEingabe = $state(token());
  let name = $state('');
  let basismodell = $state('openai/whisper-large-v3');

  async function lade() {
    fehler = '';
    try {
      sprecher = await sprecherListe();
      zugangNoetig = false;
    } catch (ursache) {
      const abgewiesen = ursache instanceof ApiFehler && ursache.status === 401;
      zugangNoetig = zugangNoetig || abgewiesen;
      fehler = abgewiesen
        ? 'Zugang nötig: bitte Token eintragen.'
        : String(ursache instanceof Error ? ursache.message : ursache);
    }
  }

  async function lege_an(ereignis: SubmitEvent) {
    ereignis.preventDefault();
    fehler = '';
    try {
      const neuer = await sprecherAnlegen({ name, basismodell });
      name = '';
      await lade();
      nimm(neuer.id);
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  function nimm(id: string) {
    waehleSprecher(id);
    gehZu('/quelle');
  }

  function tokenSpeichern() {
    setzeToken(tokenEingabe);
    lade();
  }

  lade();
</script>

<h2>Sprecher</h2>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{#each sprecher as person (person.id)}
  <div class="karte reihe">
    <div style="flex:1">
      <strong>{person.name}</strong>
      <div class="gedaempft">{person.basismodell} · {person.sprache} · {person.id}</div>
    </div>
    <button class="knopf haupt" onclick={() => nimm(person.id)}>
      {zustand.sprecher === person.id ? 'Weiter' : 'Auswählen'}
    </button>
  </div>
{:else}
  <p class="gedaempft">Noch kein Sprecherprofil vorhanden.</p>
{/each}

<h2>Neues Profil</h2>
<form onsubmit={lege_an}>
  <label>
    <span>Name</span>
    <input bind:value={name} required maxlength="200" />
  </label>
  <label>
    <span>Basismodell</span>
    <select bind:value={basismodell}>
      <option value="openai/whisper-large-v3">whisper-large-v3 (Betrieb)</option>
      <option value="openai/whisper-small">whisper-small (Entwicklung ohne GPU)</option>
      <option value="openai/whisper-tiny">whisper-tiny (noch weniger Rechenlast)</option>
    </select>
  </label>
  <button class="knopf haupt" type="submit">Anlegen</button>
</form>

{#if zugangNoetig}
  <h2>Zugang</h2>
  <p class="gedaempft">
    Dieser Server läuft mit <code>WORTLAUT_AUTH_TOKEN</code>. Später ist der Token unter
    „Einstellungen" zu ändern.
  </p>
  <div class="reihe">
    <input bind:value={tokenEingabe} type="password" placeholder="Token" style="max-width:20rem" />
    <button class="knopf" onclick={tokenSpeichern}>Speichern</button>
  </div>
{/if}
