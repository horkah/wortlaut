<script lang="ts">
  import { zustand } from './lib/zustand.svelte';
  import Start from './routes/Start.svelte';
  import Quelle from './routes/Quelle.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Fortschritt from './routes/Fortschritt.svelte';

  // Großgeschriebene Variablen sind in Svelte 5 als Komponente verwendbar.
  // Ohne gewählten Sprecher führt jeder Weg zurück zum Start.
  const Ansicht = $derived(
    !zustand.sprecher
      ? Start
      : ({ '/quelle': Quelle, '/aufnahme': Aufnahme, '/fortschritt': Fortschritt }[zustand.route] ??
        Start),
  );
</script>

<header class="kopf">
  <h1>wortlaut · hören</h1>
  {#if zustand.sprecher}
    <nav>
      <a href="#/">Start</a>
      <a href="#/quelle">Textquelle</a>
      <a href="#/aufnahme">Aufnehmen</a>
      <a href="#/fortschritt">Fortschritt</a>
    </nav>
  {/if}
</header>

<main>
  <Ansicht />
</main>
