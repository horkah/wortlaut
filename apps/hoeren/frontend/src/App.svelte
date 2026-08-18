<script lang="ts">
  import Kopfleiste from '$ui/Kopfleiste.svelte';
  import type { Menuepunkt } from '$ui/apps';
  import { zustand } from './lib/zustand.svelte';
  import Start from './routes/Start.svelte';
  import Quelle from './routes/Quelle.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Fortschritt from './routes/Fortschritt.svelte';
  import Einstellungen from './routes/Einstellungen.svelte';

  // Die Reihenfolge ist der Weg durch die App: Sprecher wählen, Text holen,
  // aufnehmen, nachsehen, was zusammengekommen ist.
  const MENUE: Menuepunkt[] = [
    { pfad: '/', text: 'Sprecher' },
    { pfad: '/quelle', text: 'Textquelle' },
    { pfad: '/aufnahme', text: 'Aufnehmen' },
    { pfad: '/fortschritt', text: 'Fortschritt' },
    { pfad: '/einstellungen', text: 'Einstellungen' },
  ];

  // Großgeschriebene Variablen sind in Svelte 5 als Komponente verwendbar.
  // Ohne gewählten Sprecher führt jeder Weg zurück zum Start.
  const Ansicht = $derived(
    !zustand.sprecher
      ? Start
      : ({
          '/quelle': Quelle,
          '/aufnahme': Aufnahme,
          '/fortschritt': Fortschritt,
          '/einstellungen': Einstellungen,
        }[zustand.route] ?? Start),
  );

  // Ohne Sprecher gibt es nur eine Ansicht — dann wäre das Menü eine Zeile
  // voller Sackgassen.
  const menue = $derived(zustand.sprecher ? MENUE : []);
  // Jeder unbekannte Hash landet bei Start; der Reiter muss das mitmachen.
  const offen = $derived(MENUE.some((p) => p.pfad === zustand.route) ? zustand.route : '/');
</script>

<Kopfleiste app="hoeren" punkte={menue} route={offen} />

<main>
  <Ansicht />
</main>
