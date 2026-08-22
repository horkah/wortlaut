<script lang="ts">
  import Kopfleiste from '$ui/Kopfleiste.svelte';
  import { EINSTELLUNGEN_PFAD, SPRECHER_PFAD, type Menuepunkt } from '$ui/apps';
  import { sprecherHolen } from './lib/api';
  import { zustand } from './lib/zustand.svelte';
  import Start from './routes/Start.svelte';
  import Quelle from './routes/Quelle.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Fortschritt from './routes/Fortschritt.svelte';
  import Einstellungen from './routes/Einstellungen.svelte';

  // Die Reihenfolge ist der Weg durch die Arbeit an einem Sprecher: Text
  // holen, aufnehmen, nachsehen, was zusammengekommen ist.
  //
  // Weder der Sprecher noch die Einstellungen stehen darin. Beide gelten über
  // diese App hinaus — der Sprecher ist die Klammer um den ganzen Korpus, die
  // Einstellungen gehören zum Gerät — und hängen deshalb im Menü der
  // Kopfleiste, an derselben Stelle wie in jeder anderen App.
  const MENUE: Menuepunkt[] = [
    { pfad: '/quelle', text: 'Textquelle' },
    { pfad: '/aufnahme', text: 'Aufnehmen' },
    { pfad: '/fortschritt', text: 'Fortschritt' },
  ];

  const UEBERGREIFEND: Menuepunkt[] = [{ pfad: SPRECHER_PFAD, text: 'Sprecher' }];

  // Großgeschriebene Variablen sind in Svelte 5 als Komponente verwendbar.
  //
  // Die Einstellungen stehen vor der Sprecherprüfung: Ohne Token liefert
  // `/api/speakers` nichts, und der Token wird genau dort eingetragen. Läge
  // die Ansicht hinter „erst ein Sprecher", käme niemand je an sie heran.
  // Ohne gewählten Sprecher führt sonst jeder Weg zur Sprecherwahl — mit ihm
  // ist die Textquelle der erste Schritt.
  const Ansicht = $derived(
    zustand.route === EINSTELLUNGEN_PFAD
      ? Einstellungen
      : zustand.route === SPRECHER_PFAD || !zustand.sprecher
        ? Start
        : ({
            '/quelle': Quelle,
            '/aufnahme': Aufnahme,
            '/fortschritt': Fortschritt,
          }[zustand.route] ?? Quelle),
  );

  // Ohne Sprecher gibt es nur eine Ansicht — dann wäre das Menü eine Zeile
  // voller Sackgassen.
  const menue = $derived(zustand.sprecher ? MENUE : []);
  // Auf einer übergreifenden Ansicht ist kein Reiter offen, sondern der
  // Menüpunkt; jeder unbekannte Hash landet bei der Textquelle.
  const offen = $derived(
    zustand.route === EINSTELLUNGEN_PFAD || zustand.route === SPRECHER_PFAD
      ? zustand.route
      : MENUE.some((punkt) => punkt.pfad === zustand.route)
        ? zustand.route
        : '/quelle',
  );

  // Der Name für die Kopfzeile. Gespeichert ist nur die Kennung — den Namen
  // holt diese Anfrage, sobald sich der Sprecher ändert. Schlägt sie fehl
  // (kein Token, gelöschter Sprecher), bleibt der Platzhalter stehen; die
  // Kopfzeile ist kein Ort für Fehlermeldungen.
  let name = $state<string | null>(null);
  $effect(() => {
    const kennung = zustand.sprecher;
    if (!kennung) {
      name = null;
      return;
    }
    let gilt_noch = true;
    sprecherHolen(kennung)
      .then((sprecher) => gilt_noch && (name = sprecher.name))
      .catch(() => gilt_noch && (name = null));
    return () => (gilt_noch = false);
  });
</script>

<Kopfleiste
  app="hoeren"
  punkte={menue}
  uebergreifend={UEBERGREIFEND}
  sprecher={name}
  route={offen}
/>

<main>
  <Ansicht />
</main>
