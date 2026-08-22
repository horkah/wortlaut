<script lang="ts">
  /**
   * Sprecher wählen oder anlegen.
   *
   * Fehlt der Zugang, steht hier kein zweites Eingabefeld: Der Token gehört in
   * die Einstellungen, und diese Ansicht schickt nur hin. Ein Feld an zwei
   * Stellen wäre eine Stelle zu viel.
   */
  import { EINSTELLUNGEN_PFAD } from '$ui/apps';
  import { ApiFehler, sprecherAnlegen, sprecherListe, type Sprecher } from '../lib/api';
  import { gehZu, waehleSprecher, zustand } from '../lib/zustand.svelte';

  let sprecher = $state<Sprecher[]>([]);
  let fehler = $state('');
  let zugangNoetig = $state(false);
  let name = $state('');
  let basismodell = $state('openai/whisper-large-v3');

  async function lade() {
    fehler = '';
    try {
      sprecher = await sprecherListe();
      zugangNoetig = false;
    } catch (ursache) {
      // Ein abgewiesener Zugang ist kein Fehler, sondern ein fehlender
      // Schritt — er bekommt unten seinen eigenen Hinweis statt einer roten
      // Zeile.
      zugangNoetig = ursache instanceof ApiFehler && ursache.status === 401;
      fehler = zugangNoetig ? '' : String(ursache instanceof Error ? ursache.message : ursache);
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

  lade();
</script>

<h2>Sprecher</h2>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

{#if zugangNoetig}
  <!-- Ohne Zugang wären Liste und Formular zwei Sackgassen: Beide fragen
       denselben Server, der beide abweist. Also steht hier nur der eine
       Schritt, der weiterführt. -->
  <div class="karte">
    <p>
      Dieser Server verlangt einen Zugangstoken. Ohne ihn bleiben Sprecher und Aufnahmen
      verborgen.
    </p>
    <button class="knopf haupt" onclick={() => gehZu(EINSTELLUNGEN_PFAD)}>
      Zu den Einstellungen
    </button>
    <p class="gedaempft">
      Der Token steht dort unter „Zugang". Er bleibt in diesem Browser gespeichert.
    </p>
  </div>
{:else}
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
{/if}
