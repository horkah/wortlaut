<script lang="ts">
  /**
   * Die Verwaltung: Profile anlegen und Zugänge ausgeben.
   *
   * Hier wird nicht mehr ausgewählt, wer man ist - das entscheidet der Zugang,
   * mit dem der Browser ruft. Was hier passiert, ist die Übergabe: Für jeden
   * Sprecher wird einmal ein Link erzeugt, und den bekommt die Person als
   * Lesezeichen. Danach nie wieder etwas merken oder tippen.
   *
   * Den Link gibt es genau einmal zu sehen; gespeichert ist nur sein Prüfwert.
   * Verloren heißt deshalb: einen neuen ausgeben - und damit ist der alte tot.
   *
   * Dieselbe Seite sieht die Aufsicht, nur mit mehr darauf: Zu jedem Sprecher
   * steht dann, wie viel er gesammelt hat, und ein Weg in seine Daten
   * (`Einsicht.svelte`). Zwei getrennte Seiten wären zwei Listen derselben
   * Sprecher - eine davon immer die falsche.
   */
  import { dauer } from '$ui/zeit';
  import { ApiFehler } from '$ui/api';
  import { inDieZwischenablage } from '$ui/zwischenablage';
  import {
    alleSprecher,
    sicherungGesamt,
    sprachen as holeSprachen,
    sprecherAnlegen,
    sprecherListe,
    zugangAusgeben,
    zugangZurueckziehen,
    type Sprachwahl,
    type Sprecher,
    type Uebersicht,
  } from '../lib/api';
  import { EINSICHT_ROUTE, gehZu, ladeZugang, lage } from '../lib/zustand.svelte';

  let sprecher = $state<(Sprecher | Uebersicht)[]>([]);
  let fehler = $state('');
  let meldung = $state('');
  let packt = $state(false);
  let name = $state('');

  // Die Sprachen kommen vom Server (`api/sprachen.py`), nicht aus einer Liste
  // hier: Ein Profil trägt seine Sprache ein Leben lang, und welche es zu
  // wählen gibt, weiß die Bibliothek und nicht die Oberfläche.
  let waehlbar = $state<Sprachwahl[]>([]);
  let sprache = $state('');

  // Die Aufsicht sieht dieselbe Liste, holt sie aber über ihren eigenen Weg -
  // nur der bringt die Kennzahlen mit.
  const beaufsichtigt = $derived(lage.art === 'aufsicht');

  // Der frisch ausgegebene Zugang, solange er auf dem Bildschirm steht.
  let frisch = $state<{ sprecher_id: string; link: string } | null>(null);
  let kopiert = $state(false);

  async function lade() {
    fehler = '';
    try {
      if (waehlbar.length === 0) {
        waehlbar = await holeSprachen();
        // Dieselbe Vorauswahl wie auf dem Server, statt einer eigenen hier.
        sprache = (waehlbar.find((s) => s.vorgabe) ?? waehlbar[0])?.kuerzel ?? '';
      }
      sprecher = beaufsichtigt ? await alleSprecher() : await sprecherListe();
    } catch (ursache) {
      if (ursache instanceof ApiFehler && ursache.status === 401) await ladeZugang();
      else fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function lege_an(ereignis: SubmitEvent) {
    ereignis.preventDefault();
    fehler = '';
    try {
      const neuer = await sprecherAnlegen({ name, sprache });
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
    // Über den gemeinsamen Weg, seit „schreiben" denselben Knopf hat: Ein
    // nacktes `navigator.clipboard` gibt es nicht überall, und ein `await`
    // darauf warf hier einen Fehler, den niemand sah (`$ui/zwischenablage`).
    kopiert = await inDieZwischenablage(frisch.link);
    if (!kopiert) fehler = 'Das Kopieren hat nicht geklappt - der Link steht oben zum Auswählen.';
  }

  async function sichereAlles() {
    fehler = '';
    meldung = '';
    packt = true;
    try {
      await sicherungGesamt();
      meldung = 'Gesamtsicherung heruntergeladen.';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      packt = false;
    }
  }


  $effect(() => {
    if (lage.art === 'verwaltung' || lage.art === 'aufsicht') lade();
  });
</script>

<h2>Sprecher</h2>

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}
{#if meldung}
  <p class="gedaempft">{meldung}</p>
{/if}

{#if frisch}
  <!-- Nur jetzt zu sehen: Gespeichert ist nur der Prüfwert. Wer den Link
       wegklickt, gibt einen neuen aus - und der alte gilt dann nicht mehr. -->
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
      <div class="gedaempft">{person.sprache} · {person.id}</div>
      <div class="gedaempft">
        {person.zugang_erneuert
          ? `Zugang ausgegeben am ${person.zugang_erneuert.slice(0, 10)}`
          : 'Kein Zugang - für niemanden erreichbar'}
      </div>
      {#if 'kennzahlen' in person}
        <!-- Nur die Aufsicht bekommt diese Zahlen mitgeliefert. Sie stehen
             hier, weil sie die Frage beantworten, die man vor jedem Griff in
             einen Korpus hat: Wie viel steht darin? -->
        <div class="gedaempft">
          {person.kennzahlen.aufnahmen} Aufnahmen · {dauer(person.kennzahlen.sekunden)} ·
          {person.kennzahlen.quellen} Textquellen
        </div>
      {/if}
    </div>
    {#if beaufsichtigt}
      <button class="knopf" onclick={() => gehZu(`${EINSICHT_ROUTE}${person.id}`)}>
        Ansehen
      </button>
    {/if}
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
    <span>Sprache</span>
    <select bind:value={sprache} required>
      {#each waehlbar as wahl (wahl.kuerzel)}
        <option value={wahl.kuerzel}>{wahl.name}</option>
      {/each}
    </select>
  </label>
  <button class="knopf haupt" type="submit">Anlegen und Zugang ausgeben</button>
</form>

{#if beaufsichtigt}
  <h2>Gesamtsicherung</h2>
  <div class="karte">
    <p class="gedaempft">
      Alle Korpora in <strong>einer</strong> Datei, zurückzuspielen mit
      <code>scripts/restore.py</code>. Ohne Modellstände - die sind groß und neu zu rechnen.
    </p>
    <button class="knopf haupt" disabled={packt} onclick={sichereAlles}>
      {packt ? 'Wird gepackt …' : 'Gesamtsicherung herunterladen (.tgz)'}
    </button>
    <p class="gedaempft">
      Bei einem großen Bestand dauert das Packen; der Browser hält die Datei so lange im
      Speicher. Für sehr große Bestände besser <code>curl</code> - siehe
      <code>docs/betrieb.md</code>.
    </p>
  </div>
{/if}

<style>
  .neuer-zugang {
    border-color: var(--akzent);
  }

  /* Der Link ist lang und darf umbrechen - abgeschnitten wäre er unbrauchbar,
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
