<script lang="ts">
  /**
   * Zwei Ansichten, mehr nicht: sprechen und den Text ansehen.
   *
   * Die zweite Reiterreihe bleibt leer. Der Weg durch diese App ist keine
   * Auswahl, sondern eine Folge — sprechen, hören, bessern, bestätigen —, und
   * die Zielperson kann schlecht lesen (Grundentscheidung 7). Welcher
   * Modellstand hier arbeitet, steht darum nicht in der Kopfzeile, sondern
   * bei der Aufnahme selbst (siehe `Aufnahme`); die Kopfzeile zeigt
   * stattdessen den Sprecher, genau wie „hören" — beide führen dieselbe
   * Person, und ihr gesprochenes Wort soll später nach „hören" und „lernen"
   * zurückfließen.
   *
   * Einstellungen und Darstellung sind die eine Ausnahme, und sie
   * widersprechen dem nicht: Diese App liest Mikrofon, Stimme und
   * Schriftgröße (siehe `Aufnahme` und `Ergebnis`), konnte sie aber bisher
   * als einzige nicht ändern — wer hier ein leises Mikrofon hatte, musste
   * dafür in „hören" hinüber. Sie liegen eingeklappt hinter dem Menüknopf,
   * damit die Oberfläche ein großer Knopf bleibt.
   */
  import Kopfleiste from '$ui/Kopfleiste.svelte';
  import Fusszeile from '$ui/Fusszeile.svelte';
  import Einstellungen from '$ui/Einstellungen.svelte';
  import Darstellung from '$ui/Darstellung.svelte';
  import { DARSTELLUNG_PFAD, EINSTELLUNGEN_PFAD } from '$ui/apps';
  import { ladeModellstand, stelleSitzungWiederHer, zustand } from './lib/zustand.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Ergebnis from './routes/Ergebnis.svelte';

  // Großgeschriebene Variablen sind in Svelte 5 als Komponente verwendbar.
  // Ohne Text gibt es nichts anzusehen — dann führt jeder Weg zur Aufnahme.
  const Ansicht = $derived(
    zustand.route === EINSTELLUNGEN_PFAD
      ? Einstellungen
      : zustand.route === DARSTELLUNG_PFAD
        ? Darstellung
        : zustand.route === '/ergebnis' && zustand.sitzung
          ? Ergebnis
          : Aufnahme,
  );

  // Der Sprecher dieser Instanz, für die Kopfzeile — dieselbe Kennung, unter
  // der auch die Aufnahmen abgelegt werden. Solange die Auskunft noch
  // aussteht, bleibt sie unbestimmt und die Zeile zeigt nichts, statt kurz
  // „kein Zugang" vorzutäuschen.
  const sprecher = $derived(zustand.modellstand?.sprecher_id);

  ladeModellstand();
  stelleSitzungWiederHer();
</script>

<Kopfleiste app="schreiben" route={zustand.route} {sprecher} />

<main>
  <Ansicht />
</main>

<Fusszeile />
