<script lang="ts">
  /**
   * Was „hören" an eigenen Ansichten hat - der Rahmen darum steht in
   * `$ui/Rahmen.svelte` und ist in jeder App derselbe, samt Menü.
   *
   * Die Reiter stehen in `REITER` (`$ui/apps`): der Weg durch die Arbeit an
   * einem Sprecher - Text holen, aufnehmen, nachsehen, was zusammengekommen
   * ist, und am Ende messen, was die Modelle daraus machen.
   */
  import Rahmen from '$ui/Rahmen.svelte';
  import {
    AUSWERTUNG_PFAD,
    EDITIEREN_ROUTE,
    MEINE_DATEN_PFAD,
    SPRECHER_PFAD,
    ZUSCHNITT_PFAD,
  } from '$ui/apps';
  import { EINSICHT_ROUTE, lage } from './lib/zustand.svelte';
  import Verwaltung from './routes/Verwaltung.svelte';
  import Einsicht from './routes/Einsicht.svelte';
  import MeineDaten from './routes/MeineDaten.svelte';
  import Auswertung from './routes/Auswertung.svelte';
  import Quelle from './routes/Quelle.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Fortschritt from './routes/Fortschritt.svelte';
  import Zuschnitt from './routes/Zuschnitt.svelte';
  import Editieren from './routes/Editieren.svelte';

  const ANSICHTEN = {
    '/quelle': Quelle,
    '/aufnahme': Aufnahme,
    '/fortschritt': Fortschritt,
    [AUSWERTUNG_PFAD]: Auswertung,
  };

  // Wer der Server in diesem Browser sieht, entscheidet, was es zu sehen gibt:
  // Ein Sprecher nimmt auf, die Verwaltung legt Profile an und gibt Zugänge
  // aus, die Aufsicht sieht über alle Korpora. Auswählen kann niemand mehr
  // etwas - die Kennung steckt im Zugang.
  const spricht = $derived(lage.art === 'sprecher');
  const beaufsichtigt = $derived(lage.art === 'aufsicht');

  // Was außerhalb der Reiter steht; `null` heißt: der Reiter zur Route.
  const Ansicht = $derived(
    // Die Einsicht der Aufsicht in einen einzelnen Korpus. Sie steht in
    // keiner Reiterreihe: Hierher führt ein Klick aus der Sprecherliste,
    // zurück derselbe Weg.
    beaufsichtigt && lage.route.startsWith(EINSICHT_ROUTE)
      ? Einsicht
      : // Dasselbe für den Sprecher selbst - dieselbe Ansicht wie die Einsicht
        // der Aufsicht, nur auf die eigenen Daten (siehe `MeineDaten.svelte`).
        lage.route === MEINE_DATEN_PFAD
        ? MeineDaten
        : // Der Zuschnitt, erreichbar aus „Meine Daten" und nur von dort (siehe
          // `ZUSCHNITT_PFAD` in `$ui/apps`), und darunter „Editieren" - eine
          // Aufnahme daraus teilen oder mit berichtigtem Text kopieren. Beide
          // brauchen einen Sprecher: Es sind dessen eigene Aufnahmen.
          spricht && lage.route === ZUSCHNITT_PFAD
          ? Zuschnitt
          : spricht && lage.route.startsWith(EDITIEREN_ROUTE)
            ? Editieren
            : // Nur wer aufnimmt, hat Reiter; Verwaltung und Aufsicht haben eine
              // einzige Seite, und eine Reiterreihe wäre dort eine Zeile voller
              // Sackgassen.
              !spricht
              ? Verwaltung
              : null,
  );
</script>

<!-- Für Verwaltung und Aufsicht ist die Sprecherliste, was für einen Sprecher
     die Reiter sind: Sie markiert das Menü als offen. -->
<Rahmen
  app="hoeren"
  ansichten={spricht ? ANSICHTEN : {}}
  ansicht={Ansicht}
  markiert={spricht ? undefined : SPRECHER_PFAD}
/>
