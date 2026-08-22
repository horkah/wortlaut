<script lang="ts">
  import Kopfleiste from '$ui/Kopfleiste.svelte';
  import Fusszeile from '$ui/Fusszeile.svelte';
  import Darstellung from '$ui/Darstellung.svelte';
  import { DARSTELLUNG_PFAD, EINSTELLUNGEN_PFAD, SPRECHER_PFAD, type Menuepunkt } from '$ui/apps';
  import { EINSICHT_ROUTE, ladeZugang, zustand } from './lib/zustand.svelte';
  import Verwaltung from './routes/Verwaltung.svelte';
  import Einsicht from './routes/Einsicht.svelte';
  import Quelle from './routes/Quelle.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Fortschritt from './routes/Fortschritt.svelte';
  import Einstellungen from './routes/Einstellungen.svelte';

  // Die Reihenfolge ist der Weg durch die Arbeit an einem Sprecher: Text
  // holen, aufnehmen, nachsehen, was zusammengekommen ist. Die Einstellungen
  // stehen bewusst nicht darin, sondern im Menü der Kopfleiste (warum:
  // `apps.ts`).
  const MENUE: Menuepunkt[] = [
    { pfad: '/quelle', text: 'Textquelle' },
    { pfad: '/aufnahme', text: 'Aufnehmen' },
    { pfad: '/fortschritt', text: 'Fortschritt' },
  ];

  // Wer der Server in diesem Browser sieht, entscheidet, was es zu sehen gibt:
  // Ein Sprecher nimmt auf, die Verwaltung legt Profile an und gibt Zugänge
  // aus, die Aufsicht sieht über alle Korpora. Auswählen kann niemand mehr
  // etwas — die Kennung steckt im Zugang.
  const spricht = $derived(zustand.art === 'sprecher');
  const beaufsichtigt = $derived(zustand.art === 'aufsicht');

  // Großgeschriebene Variablen sind in Svelte 5 als Komponente verwendbar.
  //
  // Die Einstellungen stehen vor der Zugangsprüfung: Ohne Zugang liefert die
  // API nichts, und der Verwaltertoken wird genau dort eingetragen. Läge die
  // Ansicht dahinter, käme niemand je an sie heran.
  const Ansicht = $derived(
    zustand.route === EINSTELLUNGEN_PFAD
      ? Einstellungen
      : zustand.route === DARSTELLUNG_PFAD
        ? Darstellung
        : // Die Einsicht der Aufsicht in einen einzelnen Korpus. Sie steht in
          // keiner Reiterreihe: Hierher führt ein Klick aus der Sprecherliste,
          // zurück derselbe Weg.
          beaufsichtigt && zustand.route.startsWith(EINSICHT_ROUTE)
          ? Einsicht
          : !spricht
            ? Verwaltung
            : ({
                '/quelle': Quelle,
                '/aufnahme': Aufnahme,
                '/fortschritt': Fortschritt,
              }[zustand.route] ?? Quelle),
  );

  // Nur wer aufnimmt, hat Ansichten zu wechseln; die Verwaltung hat eine
  // einzige Seite, und eine Reiterreihe wäre dort eine Zeile voller
  // Sackgassen.
  const menue = $derived(spricht ? MENUE : []);
  // Der Sprecher steht nicht mehr im Menü: Er wird nicht gewählt, sondern
  // abgeleitet. Für Verwaltung und Aufsicht ist er der einzige Punkt — bei der
  // Aufsicht zugleich der Rückweg aus der Einsicht in einen einzelnen Korpus.
  const uebergreifend = $derived(spricht ? [] : [{ pfad: SPRECHER_PFAD, text: 'Sprecher' }]);
  const offen = $derived(
    zustand.route === EINSTELLUNGEN_PFAD || zustand.route === DARSTELLUNG_PFAD
      ? zustand.route
      : !spricht
        ? SPRECHER_PFAD
        : MENUE.some((punkt) => punkt.pfad === zustand.route)
          ? zustand.route
          : '/quelle',
  );

  // Für die Kopfzeile: der Name, den der Server zum vorgelegten Zugang nennt —
  // nicht der, den sich der Browser gemerkt hat. `undefined` heißt „führt
  // keinen Sprecher" (Verwaltung und Aufsicht), `null` heißt „kein gültiger
  // Zugang".
  const name = $derived(spricht || zustand.art === 'keiner' ? zustand.name : undefined);
  // Verwaltung und Aufsicht sagen, was sie sind — sonst sähe eine Seite ohne
  // Aufnahmeansichten aus wie ein Fehler. Bei der Aufsicht kommt hinzu, dass
  // sie in fremde Korpora sieht und aus ihnen löschen kann: Das soll dauerhaft
  // dastehen und nicht nur auf der Seite, auf der gerade gelöscht wird.
  const hinweis = $derived(
    beaufsichtigt ? 'Aufsicht' : zustand.art === 'verwaltung' ? 'Verwaltung' : '',
  );

  ladeZugang();
</script>

<Kopfleiste
  app="hoeren"
  punkte={menue}
  {uebergreifend}
  sprecher={name}
  {hinweis}
  route={offen}
/>

<main>
  <Ansicht />
</main>

<Fusszeile />
