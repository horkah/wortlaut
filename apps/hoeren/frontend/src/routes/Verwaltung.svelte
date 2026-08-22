<script lang="ts">
  /**
   * Die Verwaltung: Profile anlegen und Zugänge ausgeben.
   *
   * Hier wird nicht mehr ausgewählt, wer man ist — das entscheidet der Zugang,
   * mit dem der Browser ruft. Was hier passiert, ist die Übergabe: Für jeden
   * Sprecher wird einmal ein Link erzeugt, und den bekommt die Person als
   * Lesezeichen. Danach nie wieder etwas merken oder tippen.
   *
   * Den Link gibt es genau einmal zu sehen; gespeichert ist nur sein Prüfwert.
   * Verloren heißt deshalb: einen neuen ausgeben — und damit ist der alte tot.
   */
  import { EINSTELLUNGEN_PFAD } from '$ui/apps';
  import {
    ApiFehler,
    sprecherAnlegen,
    sprecherListe,
    zugangAusgeben,
    zugangZurueckziehen,
    type Sprecher,
  } from '../lib/api';
  import { gehZu, ladeZugang, zustand } from '../lib/zustand.svelte';

  let sprecher = $state<Sprecher[]>([]);
  let fehler = $state('');
  let name = $state('');
  let basismodell = $state('openai/whisper-large-v3');

  // Der frisch ausgegebene Zugang, solange er auf dem Bildschirm steht.
  let frisch = $state<{ sprecher_id: string; link: string } | null>(null);
  let kopiert = $state(false);

  const zugangNoetig = $derived(zustand.art === 'keiner');

  async function lade() {
    fehler = '';
    if (zugangNoetig) return;
    try {
      sprecher = await sprecherListe();
    } catch (ursache) {
      if (ursache instanceof ApiFehler && ursache.status === 401) await ladeZugang();
      else fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function lege_an(ereignis: SubmitEvent) {
    ereignis.preventDefault();
    fehler = '';
    try {
      const neuer = await sprecherAnlegen({ name, basismodell });
      name = '';
      await gib_aus(neuer.id);
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function gib_aus(id: string) {
    fehler = '';
    kopiert = false;
    try {
      const ausgegeben = await zugangAusgeben(id);
      // Der Link zeigt auf diese Seite; das Geheimnis steht im Fragment und
      // geht damit nie an den Server.
      const wurzel = `${window.location.origin}${window.location.pathname}`;
      frisch = {
        sprecher_id: id,
        link: `${wurzel}#/zugang/${encodeURIComponent(ausgegeben.zugang)}`,
      };
      await lade();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function zieh_zurueck(person: Sprecher) {
    if (!confirm(`Zugang von „${person.name}“ zurückziehen? Der Link gilt danach nicht mehr.`))
      return;
    fehler = '';
    try {
      await zugangZurueckziehen(person.id);
      if (frisch?.sprecher_id === person.id) frisch = null;
      await lade();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function kopiere() {
    if (!frisch) return;
    await navigator.clipboard.writeText(frisch.link);
    kopiert = true;
  }

  $effect(() => {
    if (zustand.art === 'verwaltung') lade();
  });
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
      Dieser Browser hat keinen gültigen Zugang. Wer aufnehmen will, öffnet einmal seinen
      persönlichen Link; wer verwaltet, trägt den Verwaltertoken ein.
    </p>
    <button class="knopf haupt" onclick={() => gehZu(EINSTELLUNGEN_PFAD)}>
      Zu den Einstellungen
    </button>
    <p class="gedaempft">
      Der Token steht dort unter „Zugang". Er bleibt in diesem Browser gespeichert.
    </p>
  </div>
{:else}
  {#if frisch}
    <!-- Nur jetzt zu sehen: Gespeichert ist nur der Prüfwert. Wer den Link
         wegklickt, gibt einen neuen aus — und der alte gilt dann nicht mehr. -->
    <div class="karte neuer-zugang">
      <strong>Zugang ausgegeben</strong>
      <p class="gedaempft">
        Diesen Link auf dem Gerät der Person einmal öffnen und als Lesezeichen ablegen. Er ist
        <em>jetzt</em> zu sehen und später nicht mehr.
      </p>
      <code class="link">{frisch.link}</code>
      <div class="reihe">
        <button class="knopf haupt" onclick={kopiere}>
          {kopiert ? 'Kopiert' : 'Link kopieren'}
        </button>
        <button class="knopf" onclick={() => (frisch = null)}>Fertig</button>
      </div>
    </div>
  {/if}

  {#each sprecher as person (person.id)}
    <div class="karte reihe">
      <div style="flex:1">
        <strong>{person.name}</strong>
        <div class="gedaempft">{person.basismodell} · {person.sprache} · {person.id}</div>
        <div class="gedaempft">
          {person.zugang_erneuert
            ? `Zugang ausgegeben am ${person.zugang_erneuert.slice(0, 10)}`
            : 'Kein Zugang — für niemanden erreichbar'}
        </div>
      </div>
      {#if person.zugang_erneuert}
        <button class="knopf" onclick={() => zieh_zurueck(person)}>Zurückziehen</button>
      {/if}
      <button class="knopf haupt" onclick={() => gib_aus(person.id)}>
        {person.zugang_erneuert ? 'Neuen Zugang' : 'Zugang ausgeben'}
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
    <button class="knopf haupt" type="submit">Anlegen und Zugang ausgeben</button>
  </form>
{/if}

<style>
  .neuer-zugang {
    border-color: var(--akzent);
  }

  /* Der Link ist lang und darf umbrechen — abgeschnitten wäre er unbrauchbar,
     und er wird nicht gelesen, sondern kopiert. */
  .link {
    display: block;
    margin: 0.5rem 0;
    padding: 0.5rem;
    border-radius: 0.35rem;
    background: var(--akzent-hell);
    font-size: 0.85rem;
    overflow-wrap: anywhere;
  }
</style>
