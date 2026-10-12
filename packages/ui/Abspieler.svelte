<script lang="ts">
  /**
   * Eine Aufnahme anhören, wie in „Editieren" - nur ohne Editor: die
   * Wellenform mit Cursor (`Pegelverlauf.svelte`, ohne `bedienbar`).
   *
   * Ein Tippen auf die Kurve spielt, ein zweites hält an, ein drittes spielt
   * von dort weiter; am Ende beginnt es wieder vorn. Die Datei holt erst das
   * erste Tippen (`lade`), abgespielt wird über `ausschnitt.ts` - dieselbe
   * Stelle wie im Editor, und immer nur eines zur Zeit.
   */
  import { onDestroy } from 'svelte';
  import Pegelverlauf from './Pegelverlauf.svelte';
  import { folge, spiele, stelle, stoppe, vergiss, wecke } from './ausschnitt';

  let {
    schluessel,
    verlauf,
    fensterS,
    dauerS,
    lade,
    hoehe = 40,
  }: {
    /** Unter welchem Namen die dekodierte Datei liegt - je Aufnahme und Stand. */
    schluessel: string;
    verlauf: number[];
    fensterS: number;
    dauerS: number;
    /** Die Datei, beim ersten Abspielen geholt. */
    lade: () => Promise<Blob>;
    hoehe?: number;
  } = $props();

  let datei: Blob | null = null;
  let spielt = $state(false);
  let cursor = $state<number | null>(null);
  // Wo angehalten wurde - von dort geht es weiter.
  let ab = 0;

  async function tippe() {
    if (spielt) {
      ab = stelle(schluessel) ?? 0;
      stoppe();
      spielt = false;
      cursor = ab;
      return;
    }
    wecke();
    datei ??= await lade();
    spielt = true;
    await spiele(schluessel, datei, ab, dauerS, () => {
      spielt = false;
      ab = 0;
      cursor = null;
    });
    folge(schluessel, (sekunde) => {
      if (!spielt) return;
      // Ohne Stelle hat etwas anderes zu spielen begonnen.
      if (sekunde === null) {
        spielt = false;
        ab = 0;
      }
      cursor = sekunde;
    });
  }

  onDestroy(() => {
    if (spielt) stoppe();
    vergiss(schluessel);
  });
</script>

<Pegelverlauf
  {verlauf}
  {fensterS}
  {dauerS}
  {cursor}
  {hoehe}
  bedienbar={false}
  ontipp={tippe}
  beschriftung={spielt ? 'Anhalten' : 'Abspielen'}
/>
