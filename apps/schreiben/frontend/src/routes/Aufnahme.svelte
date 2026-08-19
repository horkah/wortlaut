<script lang="ts">
  /**
   * Ein großer Knopf, sonst nichts (Grundentscheidung 7).
   *
   * Gesprochen wird frei, nicht abgelesen: Was hier entsteht, sind eigene
   * Sätze. Nach dem Sprechen dauert es einen Augenblick — die Transkription
   * läuft auf dem Server und braucht je nach Modell ein paar Sekunden. Diese
   * Wartezeit muss man sehen, sonst drückt jemand ein zweites Mal.
   */
  import Recorder from '$ui/Recorder.svelte';
  import { einstellungen } from '$ui/einstellungen.svelte';
  import { diktieren, sitzungBeginnen } from '../lib/api';
  import { gehZu, setzeSitzung, zustand } from '../lib/zustand.svelte';

  let stand = $state<'bereit' | 'verstehe'>('bereit');
  let fehler = $state('');

  const angefangen = $derived((zustand.sitzung?.abschnitte.length ?? 0) > 0);

  async function sende(aufnahme: Blob) {
    fehler = '';
    stand = 'verstehe';
    try {
      // Die Sitzung entsteht erst jetzt: Wer die App nur öffnet, hinterlässt
      // keine leeren Zeilen in der Datenbank.
      const sitzung = zustand.sitzung ?? (await sitzungBeginnen());
      setzeSitzung(await diktieren(sitzung.id, aufnahme));
      gehZu('/ergebnis');
    } catch (ursache) {
      fehler = ursache instanceof Error ? ursache.message : String(ursache);
    } finally {
      stand = 'bereit';
    }
  }
</script>

<div class="mitte">
  <p class="ansage">{angefangen ? 'Weitersprechen' : 'Sprechen Sie einfach los.'}</p>

  <Recorder
    onaufnahme={sende}
    deaktiviert={stand === 'verstehe'}
    geraeteId={einstellungen.mikrofonId}
    verstaerkung={einstellungen.verstaerkung}
    autoPegel={einstellungen.autoPegel}
  />

  {#if stand === 'verstehe'}
    <p class="gedaempft">Wird verstanden …</p>
  {/if}

  {#if angefangen && stand === 'bereit'}
    <button class="knopf" onclick={() => gehZu('/ergebnis')}>Zum Text</button>
  {/if}

  {#if fehler}
    <p class="fehler">{fehler}</p>
  {/if}
</div>

<style>
  .mitte {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.25rem;
    margin-top: 4rem;
  }
  .ansage {
    font-size: 1.4rem;
    margin: 0;
  }
</style>
