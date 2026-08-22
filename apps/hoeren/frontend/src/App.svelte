<script lang="ts">
  import Kopfleiste from '$ui/Kopfleiste.svelte';
  import { EINSTELLUNGEN_PFAD, type Menuepunkt } from '$ui/apps';
  import { zustand } from './lib/zustand.svelte';
  import Start from './routes/Start.svelte';
  import Quelle from './routes/Quelle.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Fortschritt from './routes/Fortschritt.svelte';
  import Einstellungen from './routes/Einstellungen.svelte';

  // Die Reihenfolge ist der Weg durch die App: Sprecher wählen, Text holen,
  // aufnehmen, nachsehen, was zusammengekommen ist. Die Einstellungen stehen
  // bewusst nicht darin — sie gehören zum Gerät und nicht zu dieser App und
  // hängen deshalb im Menü der Kopfleiste.
  const MENUE: Menuepunkt[] = [
    { pfad: '/', text: 'Sprecher' },
    { pfad: '/quelle', text: 'Textquelle' },
    { pfad: '/aufnahme', text: 'Aufnehmen' },
    { pfad: '/fortschritt', text: 'Fortschritt' },
  ];

  // Großgeschriebene Variablen sind in Svelte 5 als Komponente verwendbar.
  //
  // Die Einstellungen stehen vor der Sprecherprüfung: Ohne Token liefert
  // `/api/speakers` nichts, und der Token wird genau dort eingetragen. Läge
  // die Ansicht hinter „erst ein Sprecher", käme niemand je an sie heran.
  // Ohne gewählten Sprecher führt sonst jeder Weg zurück zum Start.
  const Ansicht = $derived(
    zustand.route === EINSTELLUNGEN_PFAD
      ? Einstellungen
      : !zustand.sprecher
        ? Start
        : ({
            '/quelle': Quelle,
            '/aufnahme': Aufnahme,
            '/fortschritt': Fortschritt,
          }[zustand.route] ?? Start),
  );

  // Ohne Sprecher gibt es nur eine Ansicht — dann wäre das Menü eine Zeile
  // voller Sackgassen.
  const menue = $derived(zustand.sprecher ? MENUE : []);
  // Jeder unbekannte Hash landet bei Start; der Reiter muss das mitmachen.
  // In den Einstellungen ist kein Reiter offen, sondern der Menüpunkt.
  const offen = $derived(
    zustand.route === EINSTELLUNGEN_PFAD
      ? EINSTELLUNGEN_PFAD
      : MENUE.some((p) => p.pfad === zustand.route)
        ? zustand.route
        : '/',
  );
</script>

<Kopfleiste app="hoeren" punkte={menue} route={offen} />

<main>
  <Ansicht />
</main>
