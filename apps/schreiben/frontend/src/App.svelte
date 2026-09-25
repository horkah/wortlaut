<script lang="ts">
  /**
   * Zwei Ansichten, mehr nicht: sprechen und den Text ansehen.
   *
   * Die zweite Reiterreihe bleibt leer. Der Weg durch diese App ist keine
   * Auswahl, sondern eine Folge - sprechen, hören, bessern, bestätigen -, und
   * die Zielperson kann schlecht lesen (Grundentscheidung 7). Welcher
   * Modellstand hier arbeitet, steht darum nicht in der Kopfzeile, sondern
   * bei der Aufnahme selbst (siehe `Aufnahme`); die Kopfzeile zeigt
   * stattdessen den Sprecher, genau wie „hören" - beide führen dieselbe
   * Person, und ihr gesprochenes Wort soll später nach „hören" und „lernen"
   * zurückfließen.
   *
   * Gewechselt wird das Modell hier gar nicht mehr: Welches gilt, entscheidet
   * die eine Modellübersicht in „lernen" - dort stehen die eigenen Stände und
   * die unveränderten Grundmodelle in einer Tabelle, an denselben
   * Testaufnahmen gemessen. Die Modellzeile unter dem Aufnahmeknopf führt
   * dorthin. Diese App war lange der zweite Ort für dieselbe Entscheidung; sie
   * zeigte eine Auswahl ohne die Zahlen, an denen sie hängt.
   *
   * Das Menü samt seiner Ansichten - Audio, Darstellung, System, Zugangsdaten
   * - kennt diese Datei nicht: Es ist in jeder App dasselbe und gehört dem
   * gemeinsamen Rahmen (`$ui/Rahmen.svelte`). Diese App liest Mikrofon, Stimme
   * und Schriftgröße (siehe `Aufnahme` und `Ergebnis`), konnte sie aber lange
   * als einzige nicht ändern - wer hier ein leises Mikrofon hatte, musste
   * dafür in „hören" hinüber.
   */
  import Rahmen from '$ui/Rahmen.svelte';
  import { ladeModellstand, lage, stelleSitzungWiederHer, zustand } from './lib/zustand.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Ergebnis from './routes/Ergebnis.svelte';

  // Ohne Text gibt es nichts anzusehen - dann führt jeder Weg zur Aufnahme.
  const Ansicht = $derived(lage.route === '/ergebnis' && zustand.sitzung ? Ergebnis : Aufnahme);

  // Mit dem Zugang wechselt auch das Modell: Jeder Sprecher läuft auf seinem
  // eigenen Stand, und die Aufnahmeansicht soll ihn sofort richtig nennen -
  // auch wenn der Zugang gerade erst unter „Zugangsdaten" gewechselt wurde.
  $effect(() => {
    if (lage.sprecher) ladeModellstand();
  });

  stelleSitzungWiederHer();
</script>

<Rahmen app="schreiben" ansicht={Ansicht} />
