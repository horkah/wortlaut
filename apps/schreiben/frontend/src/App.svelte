<script lang="ts">
  /**
   * Sprechen und den Text ansehen - eine Folge, keine Auswahl: sprechen,
   * hören, bessern, bestätigen (Grundentscheidung 7). Die Kopfzeile zeigt den
   * Sprecher wie in „hören"; der Modellstand steht bei der Aufnahme und führt
   * zur Modelltafel in „lernen", wo entschieden wird, welches Modell gilt.
   *
   * Das Menü gehört dem gemeinsamen Rahmen (`$ui/Rahmen.svelte`).
   */
  import Rahmen from '$ui/Rahmen.svelte';
  import { ladeModellstand, lage, stelleSitzungWiederHer, zustand } from './lib/zustand.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Ergebnis from './routes/Ergebnis.svelte';

  // Ohne Text gibt es nichts anzusehen - dann führt jeder Weg zur Aufnahme.
  const Ansicht = $derived(lage.route === '/ergebnis' && zustand.sitzung ? Ergebnis : Aufnahme);

  // Mit dem Zugang wechselt das Modell - auch nach einem Wechsel unter „Zugangsdaten".
  $effect(() => {
    if (lage.sprecher) ladeModellstand();
  });

  stelleSitzungWiederHer();
</script>

<Rahmen app="schreiben" ansicht={Ansicht} />
