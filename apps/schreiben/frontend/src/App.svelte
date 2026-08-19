<script lang="ts">
  /**
   * Zwei Ansichten, mehr nicht: sprechen und den Text ansehen.
   *
   * Die zweite Reiterreihe bleibt leer. Der Weg durch diese App ist keine
   * Auswahl, sondern eine Folge — sprechen, hören, bessern, bestätigen —, und
   * die Zielperson kann schlecht lesen (Grundentscheidung 7). Stattdessen
   * steht rechts oben dauerhaft, welcher Modellstand hier arbeitet.
   */
  import Kopfleiste from '$ui/Kopfleiste.svelte';
  import { modell, type Modell } from './lib/api';
  import { stelleSitzungWiederHer, zustand } from './lib/zustand.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Ergebnis from './routes/Ergebnis.svelte';

  let modellstand = $state<Modell | null>(null);

  // Großgeschriebene Variablen sind in Svelte 5 als Komponente verwendbar.
  // Ohne Text gibt es nichts anzusehen — dann führt jeder Weg zur Aufnahme.
  const Ansicht = $derived(zustand.route === '/ergebnis' && zustand.sitzung ? Ergebnis : Aufnahme);

  modell()
    .then((antwort) => (modellstand = antwort))
    .catch(() => (modellstand = null)); // ohne Auskunft bleibt die Zeile leer
  stelleSitzungWiederHer();
</script>

<Kopfleiste app="schreiben" hinweis={modellstand?.beschriftung ?? ''} />

<main>
  <Ansicht />
</main>
