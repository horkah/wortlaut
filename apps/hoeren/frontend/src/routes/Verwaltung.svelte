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
  import KeinZugang from '$ui/KeinZugang.svelte';
  import { ApiFehler } from '$ui/api';
  import {
    alleSprecher,
    sicherungGesamt,
    sprecherAnlegen,
    sprecherListe,
    TEMPOFAKTOREN,
    tempoSetzen,
    zugangAusgeben,
    zugangZurueckziehen,
    type Sprecher,
    type Uebersicht,
  } from '../lib/api';
  import { EINSICHT_ROUTE, gehZu, ladeZugang, zustand } from '../lib/zustand.svelte';

  let sprecher = $state<(Sprecher | Uebersicht)[]>([]);
  let fehler = $state('');
  /** Welches Profil gerade umgestellt wird - der Wähler bleibt so lange gesperrt. */
  let stellt = $state('');
  let meldung = $state('');
  let packt = $state(false);
  let name = $state('');
  let basismodell = $state('openai/whisper-large-v3');

  // Die Aufsicht sieht dieselbe Liste, holt sie aber über ihren eigenen Weg -
  // nur der bringt die Kennzahlen mit.
  const beaufsichtigt = $derived(zustand.art === 'aufsicht');

  // Der frisch ausgegebene Zugang, solange er auf dem Bildschirm steht.
  let frisch = $state<{ sprecher_id: string; link: string } | null>(null);
  let kopiert = $state(false);

  const zugangNoetig = $derived(zustand.art === 'keiner');

  async function lade() {
    fehler = '';
    if (zugangNoetig) return;
    try {
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

  /**
   * Den Tempofaktor umstellen.
   *
   * Mit Rückfrage, und zwar einer, die den Preis nennt: Danach ist jede
   * Auswertung und jedes Modell des alten Faktors außer Kraft, und es muss
   * alles neu gemessen werden. Das ist umkehrbar - aber nicht umsonst, und
   * wer es aus Versehen anklickt, soll es vorher erfahren.
   */
  async function stelle_tempo(person: Sprecher, faktor: number) {
    if (faktor === (person.tempo ?? 1)) return;
    const wohin =
      faktor === 1 ? 'auf normale Geschwindigkeit' : `auf ${faktor}-fach schneller`;
    if (
      !confirm(
        `„${person.name}“ ${wohin} umstellen?\n\n` +
          'Alle Auswertungen und Modelle des bisherigen Faktors bleiben erhalten, gelten ' +
          'aber nicht mehr, solange dieser eingestellt ist. Sie kommen zurück, sobald Sie ' +
          'zurückstellen. Bis dahin muss alles neu gemessen und neu trainiert werden.',
      )
    ) {
      // Der Wähler zeigt sonst den abgelehnten Wert an - zurück auf das, was gilt.
      await lade();
      return;
    }
    fehler = '';
    stellt = person.id;
    try {
      await tempoSetzen(person.id, faktor);
      meldung = `„${person.name}“ steht jetzt ${wohin.replace('auf ', 'auf ')}.`;
      await lade();
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
      await lade();
    } finally {
      stellt = '';
    }
  }

  async function kopiere() {
    if (!frisch) return;
    await navigator.clipboard.writeText(frisch.link);
    kopiert = true;
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
    if (zustand.art === 'verwaltung' || zustand.art === 'aufsicht') lade();
  });
</script>

{#if zugangNoetig}
  <!-- Ohne Zugang wären Überschrift, Liste und Formular lauter Sackgassen:
       Alle fragen denselben Server, der sie abweist. Also steht hier nur der
       eine Schritt, der weiterführt - und zwar derselbe wie in „lernen" und
       „schreiben" (siehe `$ui/KeinZugang.svelte`). `verwaltet`, weil dasselbe
       Feld hier auch den Verwalter- und den Aufsichtstoken nimmt. -->
  <KeinZugang {gehZu} verwaltet />
{:else}
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
        <div class="gedaempft">{person.basismodell} · {person.sprache} · {person.id}</div>
        <div class="gedaempft">
          {person.zugang_erneuert
            ? `Zugang ausgegeben am ${person.zugang_erneuert.slice(0, 10)}`
            : 'Kein Zugang - für niemanden erreichbar'}
        </div>
        <!-- Vorspulen: die eine Einstellung dieses Profils, die sich
             nachträglich ändern lässt. Sie steht hier und nicht bei den
             Aufnahmen, weil sie für Fachleute ist und nicht für den Menschen,
             der spricht - er merkt nichts davon, es sei denn, er diktiert. -->
        <label class="tempo">
          <span class="gedaempft klein">Vorspulen vor jeder Erkennung</span>
          <select
            value={person.tempo ?? 1}
            disabled={stellt === person.id}
            onchange={(e) => stelle_tempo(person, Number(e.currentTarget.value))}
          >
            {#each TEMPOFAKTOREN as faktor (faktor)}
              <option value={faktor}>
                {faktor === 1 ? 'Aus - normale Geschwindigkeit' : `${faktor}-fach schneller`}
              </option>
            {/each}
          </select>
        </label>
        <p class="gedaempft klein tempo-hinweis">
          Für Fachleute: spult vor Auswertung und Training vor, bei gleicher Tonhöhe. Für sehr
          langsame Sprecher - ob Whisper sie schneller besser versteht, ist damit messbar.
        </p>
        {#if (person.tempo ?? 1) !== 1}
          <p class="warnung-zeile">
            <strong>Vorgespult mit Faktor {person.tempo}.</strong>
            Messungen anderer Geschwindigkeit gelten nicht, bleiben aber erhalten und kommen
            beim Zurückstellen wieder. Bis dahin ist alles neu zu messen.
          </p>
        {/if}

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
      <span>Basismodell</span>
      <select bind:value={basismodell}>
        <option value="openai/whisper-large-v3">whisper-large-v3 (Betrieb)</option>
        <option value="openai/whisper-small">whisper-small (Entwicklung ohne GPU)</option>
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
{/if}

<style>
  .tempo {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    margin-top: 0.5rem;
    max-width: 22rem;
  }

  .tempo-hinweis {
    margin: 0.25rem 0 0;
    max-width: 42rem;
  }

  /* Nicht rot: Das hier ist kein Fehler, sondern ein Zustand, den jemand
     absichtlich hergestellt hat. Die Warnfarbe der App sagt „aufpassen",
     nicht „kaputt". */
  .warnung-zeile {
    margin: 0.5rem 0 0;
    padding: 0.5rem 0.7rem;
    border-left: 3px solid var(--warnung);
    background: var(--akzent-hell);
    max-width: 42rem;
  }

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
