<script lang="ts">
  /**
   * Die anklickbare Abschnittsliste von „schreiben".
   *
   * Ein Abschnitt ist die Einheit, in der Whisper den Text zerlegt hat, und
   * zugleich die Einheit der Korrektur: Wer einen anklickt, spricht genau
   * diesen einen neu ein — der Rest bleibt stehen. Deshalb ist jeder
   * Abschnitt eine eigene Schaltfläche und nicht ein Stück Fließtext.
   *
   * Zwei Markierungen, absichtlich verschieden: `gesprochen` wandert beim
   * Vorlesen mit (blass hinterlegt, folgt der Stimme), `offen` ist der
   * Abschnitt, der gerade neu eingesprochen wird (kräftig umrandet, wartet
   * auf den Menschen).
   */
  type Abschnitt = { id: string; text: string; herkunft: string };

  let {
    abschnitte,
    gesprochen = null,
    offen = null,
    schriftRem = 1.6,
    onwaehle,
  }: {
    abschnitte: Abschnitt[];
    /** Kennung des gerade vorgelesenen Abschnitts. */
    gesprochen?: string | null;
    /** Kennung des Abschnitts, der neu eingesprochen wird. */
    offen?: string | null;
    schriftRem?: number;
    /** Bekommt die Kennung, nicht den Abschnitt: Der Aufrufer kennt seine
        eigene, vollständigere Fassung davon. */
    onwaehle: (id: string) => void;
  } = $props();
</script>

<ol class="abschnitte" style="font-size:{schriftRem}rem">
  {#each abschnitte as abschnitt (abschnitt.id)}
    <li>
      <button
        type="button"
        class="abschnitt"
        class:gesprochen={abschnitt.id === gesprochen}
        class:offen={abschnitt.id === offen}
        class:neu={abschnitt.herkunft === 'neu'}
        onclick={() => onwaehle(abschnitt.id)}
      >
        {abschnitt.text}
      </button>
    </li>
  {/each}
</ol>

<style>
  .abschnitte {
    list-style: none;
    margin: 1.5rem 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  /* Fläche statt Linie: die Zielperson trifft mit dem Finger, nicht mit der Maus. */
  .abschnitt {
    font: inherit;
    text-align: left;
    width: 100%;
    line-height: 1.45;
    padding: 0.6rem 0.8rem;
    border: 2px solid transparent;
    border-radius: 0.4rem;
    background: #fff;
    color: inherit;
    cursor: pointer;
  }

  .abschnitt:hover {
    border-color: var(--rand);
  }

  .abschnitt.gesprochen {
    background: var(--akzent-hell);
  }

  .abschnitt.offen {
    border-color: var(--akzent);
  }

  /* Schon einmal neu eingesprochen — eine Spur, kein Alarm. */
  .abschnitt.neu {
    border-left: 4px solid var(--akzent-hell);
  }
</style>
