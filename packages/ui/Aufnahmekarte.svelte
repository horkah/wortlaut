<script lang="ts">
  /**
   * Eine Aufnahme als Karte - in „Meine Daten" (hören) als Klappkarte der
   * Liste, in „Auswertung" (lernen) aufgeklappt für die gewählte Spalte.
   *
   * Oben der Text, darunter Dauer, Art, Tag, Hinweise und rechts die
   * Genauigkeit des Modells von „schreiben" (`Guete`) oder „editiert".
   * Aufgeklappt die Wellenform zum Anhören (`$ui/Abspieler`), der Knopf in den
   * Editor und der Papierkorb mit Rückfrage. Die Wellenform holt die Karte
   * selbst, sobald sie offen ist - das Audio erst das erste Tippen darauf.
   */
  import { fehlertext } from './api';
  import Abspieler from './Abspieler.svelte';
  import Papierkorb from './Papierkorb.svelte';
  import Rueckfrage from './Rueckfrage.svelte';
  import Warnzeichen from './Warnzeichen.svelte';
  import { tag } from './zeit';
  import Guete from './Guete.svelte';
  import {
    aufnahmeVerwerfen,
    meineAufnahmeAudio,
    meineWellenform,
    type AufsichtAufnahme,
    type Guteskala,
    type Wellenform,
  } from './aufnahme';

  let {
    aufnahme,
    skala,
    modell,
    offen,
    bearbeitbar,
    onklappe,
    onbearbeite,
    onverworfen,
    onfehler,
  }: {
    aufnahme: AufsichtAufnahme;
    skala: Guteskala;
    /** Das Modell, dessen Genauigkeit `aufnahme.qualitaet` ist. */
    modell: string;
    offen: boolean;
    /** Ob der Bearbeitungsschlüssel gilt - sonst kein Knopf in den Editor. */
    bearbeitbar: boolean;
    /** Ohne: Die Karte bleibt, wie sie ist, und nimmt keinen Klick an. */
    onklappe?: () => void;
    onbearbeite: () => void;
    /** Nach dem Löschen. */
    onverworfen: () => void;
    onfehler: (text: string) => void;
  } = $props();

  let wellenform = $state<Wellenform | null>(null);
  let fragt = $state(false);
  let loescht = $state(false);

  // Aufgeklappt die Kurve; ein Schnitt im Editor ändert `geaendert` und damit sie.
  $effect(() => {
    const id = aufnahme.id;
    void aufnahme.geaendert;
    wellenform = null;
    if (!offen || !aufnahme.audio_vorhanden) return;
    let gilt = true;
    meineWellenform(id)
      .then((kurve) => {
        if (gilt) wellenform = kurve;
      })
      .catch((ursache) => {
        if (gilt) onfehler(fehlertext(ursache));
      });
    return () => {
      gilt = false;
    };
  });

  /**
   * Ein Klick irgendwo auf die Karte klappt sie auf oder zu - außer auf das,
   * was in ihr selbst etwas tut, und außer nach dem Markieren von Text.
   */
  function klickAufKarte(ereignis: MouseEvent) {
    if (!onklappe) return;
    const ziel = ereignis.target as Element;
    // Die Wellenform spielt ab (`$ui/Abspieler`) - ihr Tippen gehört nicht der Karte.
    if (ziel.closest('audio, a, button:not(.aufklapper), [role="button"]')) return;
    if (window.getSelection()?.toString()) return;
    onklappe();
  }

  async function verwirf() {
    fragt = false;
    loescht = true;
    try {
      await aufnahmeVerwerfen(aufnahme.id);
      onverworfen();
    } catch (ursache) {
      onfehler(fehlertext(ursache));
    } finally {
      loescht = false;
    }
  }
</script>

<!-- Die ganze Karte nimmt den Klick an; für Tastatur und Vorlesestimme ist
     der Text oben der Knopf, der sie auf- und zuklappt. -->
<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div
  class="karte aufnahme"
  id="aufnahme-{aufnahme.id}"
  class:offen
  class:klappbar={onklappe !== undefined}
  onclick={klickAufKarte}
>
  {#if onklappe}
    <button class="aufklapper" aria-expanded={offen}>{aufnahme.text}</button>
  {:else}
    <p class="aufklapper">{aufnahme.text}</p>
  {/if}
  <div class="gedaempft zeile">
    <span>
      {aufnahme.dauer_s.toFixed(1)} s · {aufnahme.modus} · {tag(aufnahme.erstellt)}
      {#if aufnahme.hinweise.length}<Warnzeichen hinweise={aufnahme.hinweise} />{/if}
      {#if aufnahme.status !== 'ok'}· <strong>{aufnahme.status}</strong>{/if}
    </span>
    {#if aufnahme.editiert}
      <span class="editiert" title="Editiert - noch in keinem Training von {modell}">editiert</span>
    {:else if aufnahme.qualitaet !== null}
      <Guete wert={aufnahme.qualitaet} {skala} {modell} />
    {/if}
  </div>
  {#if offen}
    <div class="reihe aufgeklappt">
      <div class="spieler">
        {#if wellenform}
          <!-- Der Schlüssel trägt Dauer und letztes Speichern: Nach einem
               Schnitt ist es eine andere Datei. -->
          <Abspieler
            schluessel="{aufnahme.id}@{aufnahme.dauer_s}@{aufnahme.geaendert ?? ''}"
            verlauf={wellenform.verlauf}
            fensterS={wellenform.fenster_s}
            dauerS={wellenform.dauer_s}
            lade={() => meineAufnahmeAudio(aufnahme.id)}
          />
        {/if}
      </div>
      {#if aufnahme.status === 'ok'}
        {#if bearbeitbar && aufnahme.audio_vorhanden}
          <button
            class="bearbeiten"
            title="Bearbeiten"
            aria-label="Aufnahme bearbeiten"
            onclick={onbearbeite}
          >
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              stroke-width="1.75"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
              <path d="m14.5 5.5 3 3" />
            </svg>
          </button>
        {/if}
        <Papierkorb
          title="Aufnahme löschen"
          label="Aufnahme löschen"
          disabled={loescht}
          onclick={() => (fragt = true)}
        />
      {/if}
    </div>
  {/if}
</div>

<Rueckfrage
  offen={fragt}
  titel="Aufnahme löschen?"
  knopf="Löschen"
  gefahr
  onja={verwirf}
  onnein={() => (fragt = false)}
>
  <p>„{aufnahme.text}“</p>
  <p><strong>Gelöscht wird:</strong></p>
  <ul>
    <li>die Aufnahme mit Ton und Messwerten</li>
  </ul>
  <p>Der Text bleibt und steht wieder zum Aufnehmen an.</p>
</Rueckfrage>

<style>
  .karte.aufnahme.klappbar {
    cursor: pointer;
  }

  .karte.aufnahme.offen {
    border-color: var(--akzent);
  }

  /* Der Text der Karte als Knopf - ohne Aussehen eines Knopfs. */
  .aufklapper {
    display: block;
    width: 100%;
    margin: 0 0 0.2rem;
    padding: 0;
    border: none;
    background: none;
    font: inherit;
    color: inherit;
    text-align: left;
  }

  button.aufklapper {
    cursor: pointer;
  }

  /* Die Kennzeile: links, was die Aufnahme ist, rechts, wie gut sie gehört wurde. */
  .zeile {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .aufgeklappt {
    margin-top: 0.75rem;
    gap: 0.5rem;
  }

  .spieler {
    flex: 1;
    min-width: 12rem;
  }

  /* Quadratisch und so groß wie der Papierkorb daneben. */
  .bearbeiten {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: none;
    width: 2.2rem;
    height: 2.2rem;
    padding: 0;
    border: 1px solid var(--akzent);
    border-radius: 0.35rem;
    background: #fff;
    color: var(--akzent);
    cursor: pointer;
  }

  .bearbeiten:hover,
  .bearbeiten:focus-visible {
    background: var(--akzent-hell);
  }
</style>
