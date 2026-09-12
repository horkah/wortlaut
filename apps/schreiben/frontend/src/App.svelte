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
   * Testaufnahmen gemessen. Der Menüpunkt „Modelle" und die Modellzeile unter
   * dem Aufnahmeknopf führen beide dorthin. Diese App war lange der zweite
   * Ort für dieselbe Entscheidung; sie zeigte eine Auswahl ohne die Zahlen,
   * an denen sie hängt.
   *
   * Einstellungen und Darstellung stehen im Menü, ohne dass diese Datei sie
   * kennt: Sie gehören zum Gerät und damit in den gemeinsamen Rahmen
   * (`$ui/Rahmen.svelte`). Diese App liest Mikrofon, Stimme und Schriftgröße
   * (siehe `Aufnahme` und `Ergebnis`), konnte sie aber lange als einzige nicht
   * ändern - wer hier ein leises Mikrofon hatte, musste dafür in „hören"
   * hinüber.
   *
   * Dazu kommt ein eigener Menüpunkt: die Zugangsdaten. Diese App führt seit
   * dem Wegfall der Einzelnutzer-Instanz denselben Sprecher wie „hören" - sein
   * Zugang entscheidet, auf welchem Modell hier gesprochen wird und in welchen
   * Korpus die Korrekturen zurückgehen. Ein zweites Anmeldefeld ist das nicht:
   * Der Zugang kommt über denselben persönlichen Link und liegt in demselben
   * Browser (siehe `$ui/zugang`).
   */
  import Rahmen from '$ui/Rahmen.svelte';
  import KeinZugang from '$ui/KeinZugang.svelte';
  import { MEINE_DATEN_PFAD, ZUGANGSDATEN_PFAD } from '$ui/apps';
  import {
    gehZu,
    ladeModellstand,
    ladeZugang,
    stelleSitzungWiederHer,
    zustand,
  } from './lib/zustand.svelte';
  import Aufnahme from './routes/Aufnahme.svelte';
  import Ergebnis from './routes/Ergebnis.svelte';
  import Zugangsdaten from './routes/Zugangsdaten.svelte';

  // Großgeschriebene Variablen sind in Svelte 5 als Komponente verwendbar.
  //
  // Die Zugangsdaten stehen vor der Zugangsprüfung: Ohne gültigen Zugang gibt
  // die API nichts her, und genau dort wird er eingesetzt. Ohne Text gibt es
  // nichts anzusehen - dann führt jeder Weg zur Aufnahme.
  const Ansicht = $derived(
    zustand.route === ZUGANGSDATEN_PFAD
      ? Zugangsdaten
      : zustand.route === '/ergebnis' && zustand.sitzung
        ? Ergebnis
        : Aufnahme,
  );

  // Ohne Zugang gäbe es hier nur abgewiesene Anfragen: kein Modell, keine
  // Sitzung, kein Diktat (siehe `backend/deps.py`). Ein Aufnahmeknopf, der
  // jedes Mal in einen Fehler liefe, wäre die schlechtere Antwort - also steht
  // dann dieselbe eine Karte da wie in „hören" und „lernen"
  // (`$ui/KeinZugang.svelte`). Die Zugangsdaten selbst bleiben ausgenommen:
  // Dorthin führt sie, sie darf nicht hinter ihr liegen.
  const ohneZugang = $derived(zustand.art === 'keiner' && zustand.route !== ZUGANGSDATEN_PFAD);

  // Die Zugangsdaten stehen immer da - auch und gerade ohne gültigen Zugang:
  // Dann ist der Punkt der einzige Weg herein. „Meine Daten" kommt dazu,
  // sobald ein Sprecher feststeht: Dieselbe Ansicht wie bei „hören" (dort
  // liegt der Korpus), darum ein `href` auf die laufende „hören"-Seite statt
  // eine eigene Route hier (siehe `Menuepunkt` in `apps.ts`).
  // „Modelle" steht hier ausdrücklich **nicht**: Die Ansicht ist ein Reiter in
  // „lernen", und ein Menüpunkt daneben wäre ein zweiter Weg dorthin. Diese App
  // hat schon einen, und zwar den besseren - die Modellzeile unter dem
  // Aufnahmeknopf (siehe `Aufnahme`). Wer sie liest, denkt gerade darüber nach,
  // ob ein anderes Modell besser zuhören würde; ein Menüpunkt erreichte
  // dagegen niemanden, der nicht ohnehin schon sucht.
  const uebergreifend = $derived([
    ...(zustand.art === 'sprecher'
      ? [{ pfad: MEINE_DATEN_PFAD, text: 'Meine Daten', href: `/#${MEINE_DATEN_PFAD}` }]
      : []),
    { pfad: ZUGANGSDATEN_PFAD, text: 'Zugangsdaten' },
  ]);

  // Für die Kopfzeile: der Name, den der Server zum vorgelegten Zugang nennt.
  // Solange die Auskunft aussteht, bleibt die Zeile unbestimmt und zeigt
  // nichts, statt kurz „kein Zugang" vorzutäuschen.
  const sprecher = $derived(zustand.art === 'unbekannt' ? undefined : zustand.name);

  ladeZugang();
  ladeModellstand();
  stelleSitzungWiederHer();
</script>

<Rahmen app="schreiben" route={zustand.route} {uebergreifend} {sprecher}>
  {#if ohneZugang}
    <KeinZugang {gehZu} />
  {:else}
    <Ansicht />
  {/if}
</Rahmen>
