<script lang="ts">
  /**
   * Ein großer Knopf, sonst nichts (Grundentscheidung 7).
   *
   * Gesprochen wird frei, nicht abgelesen: Was hier entsteht, sind eigene
   * Sätze. Nach dem Sprechen dauert es einen Augenblick - die Transkription
   * läuft auf dem Server und braucht je nach Modell ein paar Sekunden. Diese
   * Wartezeit muss man sehen, sonst drückt jemand ein zweites Mal.
   */
  import Recorder from '$ui/Recorder.svelte';
  import { einstellungen } from '$ui/einstellungen.svelte';
  import { MODELLE_URL } from '$ui/apps';
  import { diktieren, sitzungBeginnen } from '../lib/api';
  import { gehZu, setzeSitzung, zustand } from '../lib/zustand.svelte';

  // Der Modellstand steht hier, nicht in der Kopfzeile: Wer eine Ausgabe
  // beurteilt, muss sehen, welcher Stand sie erzeugt hat - direkt bei der
  // Aufnahme, die ihn erzeugt. Die Zeile ist zugleich der Weg zur
  // Modellübersicht in „lernen": Wer sie liest, denkt gerade darüber nach,
  // ob ein anderes Modell besser zuhören würde.
  const beschriftung = $derived(zustand.modellstand?.beschriftung ?? '');

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

  {#if beschriftung}
    <p class="modellstand gedaempft">
      <a href={MODELLE_URL}>{beschriftung}</a>
    </p>
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
  /* Randnotiz unter dem Aufnahmeknopf - bleibt leise, auch als Verweis: Sie
     soll den Knopf darüber nicht um Aufmerksamkeit bringen. */
  .modellstand {
    font-size: 0.8rem;
    margin: 0;
    text-align: center;
  }

  .modellstand a {
    color: inherit;
    text-decoration-color: var(--rand);
  }
</style>
