<script lang="ts">
  /**
   * Die Hauptansicht: eine Einheit zeigen, dazu aufnehmen, prüfen, weiter.
   *
   * Zwei Wege zur selben Einheit:
   * • ablesen → `gelesen`
   * • erst vorlesen lassen, dann nachsprechen → `nachgesprochen`
   * Der Modus wird mitgeschickt, weil Nachgesprochenes Sprechtempo und
   * Satzmelodie der Vorgabe übernimmt und im Training anders gewichtet gehört.
   */
  import AudioPlayer from '$ui/AudioPlayer.svelte';
  import PromptView from '$ui/PromptView.svelte';
  import Recorder from '$ui/Recorder.svelte';
  import { beiStimmenAenderung, brichVorlesenAb, deutscheStimmen, sprich, stimmeVerfuegbar } from '$ui/speak';
  import {
    aufnahmeSenden,
    aufnahmeVerwerfen,
    naechsteEinheit,
    sitzungBeginnen,
    type Aufnahme,
    type Naechste,
  } from '../lib/api';
  import { gehZu, zustand } from '../lib/zustand.svelte';

  const sprecher = zustand.sprecher!;
  const SITZUNG_SCHLUESSEL = `wortlaut.sitzung.${sprecher}`;
  const STIMME_SCHLUESSEL = 'wortlaut.stimme';

  let stand = $state<'laedt' | 'bereit' | 'sendet' | 'geprueft'>('laedt');
  let ausschnitt = $state<Naechste | null>(null);
  let letzte = $state<Aufnahme | null>(null);
  let abspielUrl = $state<string | null>(null);
  let nachgesprochen = $state(false);
  let fehler = $state('');
  let sitzung: string | null = null;

  // Stimmen kommen auf manchen Systemen erst asynchron nach dem Laden der
  // Seite an (`voiceschanged`), deshalb hier neu abfragen statt nur einmal.
  let stimmen = $state(deutscheStimmen());
  let stimmeUri = $state(localStorage.getItem(STIMME_SCHLUESSEL));
  // Ohne eigene Wahl: die vom Browser als Standard markierte Stimme, sonst
  // die erste — damit die Anzeige im <select> nie von dem abweicht, was
  // tatsächlich gesprochen wird.
  const gewaehlteStimme = $derived(
    stimmen.find((s) => s.voiceURI === stimmeUri) ?? stimmen.find((s) => s.default) ?? stimmen[0] ?? null,
  );

  $effect(() => beiStimmenAenderung(() => (stimmen = deutscheStimmen())));

  function stimmeWaehlen(uri: string) {
    stimmeUri = uri;
    localStorage.setItem(STIMME_SCHLUESSEL, uri);
  }

  const fortschritt = $derived(
    ausschnitt && ausschnitt.gesamt > 0 ? (ausschnitt.erledigt / ausschnitt.gesamt) * 100 : 0,
  );

  async function beginne() {
    // Sitzung überdauert einen Neuladen des Browsers, aber nicht den Tab —
    // genau die Lebensdauer, die zu „unterbrechbar" passt.
    sitzung = sessionStorage.getItem(SITZUNG_SCHLUESSEL);
    if (!sitzung) {
      sitzung = (await sitzungBeginnen(sprecher)).id;
      sessionStorage.setItem(SITZUNG_SCHLUESSEL, sitzung);
    }
    await hole();
  }

  async function hole() {
    loeseUrl();
    letzte = null;
    nachgesprochen = false;
    ausschnitt = await naechsteEinheit(sprecher, sitzung);
    stand = 'bereit';
  }

  function loeseUrl() {
    if (abspielUrl) URL.revokeObjectURL(abspielUrl);
    abspielUrl = null;
  }

  async function vorlesen() {
    if (!ausschnitt?.aktuell) return;
    nachgesprochen = true; // schon der Versuch verändert die Sprechweise
    try {
      await sprich(ausschnitt.aktuell.text, gewaehlteStimme);
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    }
  }

  async function sende(aufnahme: Blob) {
    if (!ausschnitt?.aktuell) return;
    brichVorlesenAb();
    fehler = '';
    stand = 'sendet';
    abspielUrl = URL.createObjectURL(aufnahme);
    try {
      letzte = await aufnahmeSenden(sprecher, {
        audio: aufnahme,
        prompt_id: ausschnitt.aktuell.id,
        modus: nachgesprochen ? 'nachgesprochen' : 'gelesen',
        session: sitzung,
      });
      stand = 'geprueft';
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
      stand = 'bereit';
    }
  }

  async function nochmal() {
    if (!letzte) return;
    await aufnahmeVerwerfen(sprecher, letzte.id);
    await hole(); // dieselbe Einheit ist damit wieder offen
  }

  beginne().catch((ursache) => {
    fehler = ursache instanceof Error ? ursache.message : String(ursache);
  });
</script>

{#if stand === 'laedt'}
  <p class="gedaempft">Wird geladen …</p>
{:else if ausschnitt && !ausschnitt.aktuell}
  <h2>Alles aufgenommen</h2>
  <p>Für diesen Sprecher ist derzeit keine Einheit mehr offen.</p>
  <div class="reihe">
    <button class="knopf haupt" onclick={() => gehZu('/quelle')}>Neue Textquelle</button>
    <button class="knopf" onclick={() => gehZu('/fortschritt')}>Fortschritt ansehen</button>
  </div>
{:else if ausschnitt}
  <p class="gedaempft">{ausschnitt.erledigt} von {ausschnitt.gesamt} Einheiten</p>
  <div class="balken"><div style="width:{fortschritt}%"></div></div>

  <PromptView vorher={ausschnitt.vorher} aktuell={ausschnitt.aktuell} nachher={ausschnitt.nachher} />

  {#if stimmeVerfuegbar()}
    <div class="reihe" style="justify-content:center">
      <button class="knopf" onclick={vorlesen} disabled={stand === 'sendet'}>
        ▶ Vorsprechen lassen
      </button>
      {#if stimmen.length > 1}
        <select
          aria-label="Stimme"
          value={gewaehlteStimme?.voiceURI}
          onchange={(ereignis) => stimmeWaehlen(ereignis.currentTarget.value)}
          style="width:auto;max-width:16rem"
        >
          {#each stimmen as stimme (stimme.voiceURI)}
            <option value={stimme.voiceURI}>{stimme.name}</option>
          {/each}
        </select>
      {/if}
      {#if nachgesprochen}
        <span class="gedaempft">wird als „nachgesprochen“ gespeichert</span>
      {/if}
    </div>
  {/if}

  <div class="mitte">
    {#if stand === 'geprueft' && letzte}
      <AudioPlayer quelle={abspielUrl} beschriftung="Ihre Aufnahme" />
      <p class="gedaempft">{letzte.dauer_s.toFixed(1)} s · {letzte.pegel_dbfs.toFixed(0)} dBFS</p>

      {#if letzte.hinweise.length > 0}
        <div class="hinweise">
          <strong>Aufgefallen ist:</strong>
          <ul>
            {#each letzte.hinweise as hinweis}<li>{hinweis}</li>{/each}
          </ul>
          <p class="gedaempft">
            Das ist ein Hinweis, keine Ablehnung — die Aufnahme ist gespeichert.
          </p>
        </div>
      {/if}

      <div class="reihe" style="justify-content:center">
        <button class="knopf" onclick={nochmal}>Verwerfen und noch einmal</button>
        <button class="knopf haupt" onclick={hole}>Weiter</button>
      </div>
    {:else}
      <Recorder onaufnahme={sende} deaktiviert={stand === 'sendet'} />
      {#if stand === 'sendet'}<p class="gedaempft">Wird geprüft …</p>{/if}
    {/if}
  </div>
{/if}

{#if fehler}
  <p class="fehler">{fehler}</p>
{/if}

<style>
  .mitte {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    margin-top: 2rem;
  }
  ul {
    margin: 0.5rem 0;
  }
</style>
